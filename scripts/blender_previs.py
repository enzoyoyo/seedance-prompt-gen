#!/usr/bin/env python3
"""Local-only, explicit Blender previz. No network, plugins or model calls.

Consumes a small proxy plan, saves an editable blend and PNG sequence,
then encodes/probes/decodes MP4. This is not a general scene importer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fields(value, required, optional=()):
    require(isinstance(value, dict), 'Expected object')
    require(set(required) <= set(value), f'Missing fields: {set(required) - set(value)}')
    require(not (set(value) - set(required) - set(optional)), 'Unknown fields')


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def vector(value, n=3):
    require(isinstance(value, list) and len(value) == n and all(number(x) for x in value), 'Invalid finite vector')


def sample(keys, frame, name):
    if frame <= keys[0]['frame']:
        return list(keys[0][name])
    for a, b in zip(keys, keys[1:]):
        if frame <= b['frame']:
            u = (frame - a['frame']) / (b['frame'] - a['frame'])
            return [(1 - u) * x + u * y for x, y in zip(a[name], b[name])]
    return list(keys[-1][name])


def validate_keys(keys, end, camera=False):
    require(isinstance(keys, list) and len(keys) >= 2, 'At least two keys required')
    previous = 0
    for key in keys:
        fields(key, ['frame', 'position', 'target'] if camera else ['frame', 'position'])
        require(type(key['frame']) is int and previous < key['frame'] <= end, 'Invalid key order/range')
        previous = key['frame']
        vector(key['position'])
        if camera:
            vector(key['target'])
    require(keys[0]['frame'] == 1 and keys[-1]['frame'] == end, 'Keys must cover full frame range')


def validate(plan):
    fields(plan, ['schema_version', 'shot_id', 'fps', 'frame_end', 'width', 'height', 'engine', 'objects', 'camera', 'events'])
    require(plan['schema_version'] == 'blender-previs-1', 'Unknown schema')
    require(isinstance(plan['shot_id'], str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', plan['shot_id']), 'Invalid shot ID')
    for name in ('fps', 'frame_end', 'width', 'height'):
        require(type(plan[name]) is int and plan[name] > 0, f'Invalid {name}')
    require(plan['frame_end'] >= 2, 'At least two frames required')
    require(plan['width'] % 2 == 0 and plan['height'] % 2 == 0, 'Even dimensions required for yuv420p')
    # Local resource guard, not a model capability or recommended shot length.
    require(plan['frame_end'] <= 2400 and plan['fps'] <= 120 and plan['width'] * plan['height'] * plan['frame_end'] <= 1_000_000_000, 'Local render budget exceeded; use a smaller previz')
    require(plan['engine'] in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT', 'BLENDER_WORKBENCH', 'CYCLES'), 'Unsupported engine')
    require(isinstance(plan['objects'], list) and 0 < len(plan['objects']) <= 200, 'Invalid proxy count')
    names = set()
    for obj in plan['objects']:
        fields(obj, ['id', 'kind', 'position', 'size', 'color', 'role'], ['position_keys'])
        require(isinstance(obj['id'], str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', obj['id']) and obj['id'] not in names, 'Invalid or duplicate object ID')
        names.add(obj['id'])
        require(obj['kind'] in ('cube', 'sphere'), 'Only cube/sphere proxies supported')
        require(isinstance(obj['role'], str) and bool(obj['role'].strip()), 'Proxy role required')
        vector(obj['position']); vector(obj['size']); vector(obj['color'])
        require(all(x > 0 for x in obj['size']), 'Positive dimensions required')
        require(all(0 <= x <= 1 for x in obj['color']), 'Invalid color')
        if 'position_keys' in obj:
            validate_keys(obj['position_keys'], plan['frame_end'])
            require(obj['position_keys'][0]['position'] == obj['position'], 'Static/start position conflict')
    camera = plan['camera']
    fields(camera, ['lens_mm', 'sensor_width_mm', 'clip_start', 'clip_end', 'keys'])
    for name in ('lens_mm', 'sensor_width_mm', 'clip_start', 'clip_end'):
        require(number(camera[name]) and camera[name] > 0, 'Invalid camera scalar')
    require(camera['clip_end'] > camera['clip_start'], 'Invalid clipping range')
    validate_keys(camera['keys'], plan['frame_end'], camera=True)
    for frame in range(1, plan['frame_end'] + 1):
        pos, target = (sample(camera['keys'], frame, name) for name in ('position', 'target'))
        require(sum((a - b) ** 2 for a, b in zip(pos, target)) > 1e-10, 'Coincident camera target')
    require(isinstance(plan['events'], list), 'Events must be a list')
    names = set()
    for event in plan['events']:
        fields(event, ['id', 'frame'])
        require(isinstance(event['id'], str) and event['id'].strip() and event['id'] not in names, 'Invalid event ID')
        names.add(event['id'])
        require(type(event['frame']) is int and 1 <= event['frame'] <= plan['frame_end'], 'Invalid event frame')


def blender_build(plan, output):
    import bpy
    from mathutils import Vector
    validate(plan)
    require(bpy.app.background, 'Must run in a separate background Blender process')
    scene = bpy.context.scene
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene.render.engine = plan['engine']  # Fail rather than silently changing engine.
    scene.frame_start = 1
    scene.frame_end = plan['frame_end']
    scene.render.fps = plan['fps']
    scene.render.fps_base = 1
    scene.render.resolution_x = plan['width']
    scene.render.resolution_y = plan['height']
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.film_transparent = False
    scene.render.filepath = str(output / 'frames/frame_')
    scene.world.color = (0.12, 0.12, 0.12)
    if plan['engine'] == 'CYCLES':
        scene.cycles.samples = 8
    if plan['engine'] == 'BLENDER_WORKBENCH':
        scene.display.shading.color_type = 'OBJECT'
    for item in plan['objects']:
        if item['kind'] == 'cube':
            bpy.ops.mesh.primitive_cube_add(size=1, location=item['position'])
        else:
            bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.5, location=item['position'])
        obj = bpy.context.object
        obj.name = item['id']
        obj.dimensions = item['size']
        obj.color = (*item['color'], 1)
        obj['proxy_role'] = item['role']
        material = bpy.data.materials.new(item['id'] + '_mat')
        material.diffuse_color = obj.color
        material.use_nodes = True
        shader = material.node_tree.nodes.get('Principled BSDF')
        shader.inputs['Base Color'].default_value = obj.color
        shader.inputs['Roughness'].default_value = 0.8
        obj.data.materials.append(material)
        if 'position_keys' in item:
            for frame in range(1, scene.frame_end + 1):
                obj.location = sample(item['position_keys'], frame, 'position')
                obj.keyframe_insert(data_path='location', frame=frame)
    for location, power, size in [((1, -3, 6), 1500, 5), ((-4, 2, 4), 1000, 4)]:
        bpy.ops.object.light_add(type='AREA', location=location)
        light = bpy.context.object
        light.data.energy = power
        light.data.shape = 'DISK'
        light.data.size = size
        light.rotation_euler = (Vector((0, 0, 0)) - light.location).to_track_quat('-Z', 'Y').to_euler()
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.name = 'PREVIS_CAMERA'
    camera.rotation_mode = 'QUATERNION'
    scene.camera = camera
    for name, source in [('lens', 'lens_mm'), ('sensor_width', 'sensor_width_mm'), ('clip_start', 'clip_start'), ('clip_end', 'clip_end')]:
        setattr(camera.data, name, plan['camera'][source])
    camera.data.sensor_fit = 'HORIZONTAL'
    camera.data.dof.use_dof = False
    rows = []
    for frame in range(1, scene.frame_end + 1):
        pos = sample(plan['camera']['keys'], frame, 'position')
        target = sample(plan['camera']['keys'], frame, 'target')
        camera.location = pos
        camera.rotation_quaternion = (Vector(target) - Vector(pos)).to_track_quat('-Z', 'Y')
        camera.keyframe_insert(data_path='location', frame=frame)
        camera.keyframe_insert(data_path='rotation_quaternion', frame=frame)
    for event in plan['events']:
        scene.timeline_markers.new(event['id'], frame=event['frame'])
    for frame in range(1, scene.frame_end + 1):
        scene.frame_set(frame)
        evaluated = camera.evaluated_get(bpy.context.evaluated_depsgraph_get())
        rows.append({'frame': frame, 'time_s': (frame - 1) / plan['fps'], 'camera_matrix_world': [list(row) for row in evaluated.matrix_world]})
    (output / 'camera-samples.json').write_text(json.dumps(rows, indent=2))
    scene['purpose'] = 'planning_only; proxy colors are role labels, not final appearance'
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'scene.blend'))
    bpy.ops.render.render(animation=True)
    (output / 'blender-build.json').write_text(json.dumps({'blender_version': bpy.app.version_string, 'engine': scene.render.engine, 'status': 'rendered', 'geometry_qc': 'needs_review'}, indent=2))


def executable(name, override=None):
    if override:
        path = Path(override).expanduser()
        require(path.is_file() and os.access(path, os.X_OK), f'Executable unavailable: {override}')
        return str(path.resolve())
    found = shutil.which(name)
    if not found and name == 'blender':
        fallback = Path('/Applications/Blender.app/Contents/MacOS/Blender')
        if fallback.is_file():
            found = str(fallback)
    require(bool(found), f'Executable not found: {name}')
    return found


def run_logged(args, log):
    with log.open('w') as stream:
        result = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT, check=False)
    require(result.returncode == 0, f'Command failed ({result.returncode}); see {log}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check', action='store_true', help='Validate JSON only; no writes or Blender invocation')
    parser.add_argument('--blender-bin', help='Explicit executable; otherwise BLENDER_BIN, PATH, then macOS app')
    args = parser.parse_args(argv)
    plan = json.loads(args.plan.read_text())
    validate(plan)
    if args.check:
        print(json.dumps({'status': 'valid', 'scope': 'planning_only', 'frames': plan['frame_end'], 'duration_s': plan['frame_end'] / plan['fps']}))
        return 0
    require(args.output is not None, '--output required unless --check')
    require(not args.output.exists() and not args.output.is_symlink(), 'OUTPUT_EXISTS: use a new revision directory')
    blender = executable('blender', args.blender_bin or os.environ.get('BLENDER_BIN'))
    ffmpeg, ffprobe = executable('ffmpeg'), executable('ffprobe')
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'frames').mkdir()
    (output / 'plan.json').write_text(json.dumps(plan, indent=2))
    try:
        run_logged([blender, '--background', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1', '--python', str(Path(__file__).resolve()), '--', '--internal-build', str(output / 'plan.json'), str(output)], output / 'blender.log')
        expected = {f'frame_{frame:04d}.png' for frame in range(1, plan['frame_end'] + 1)}
        actual = {f.name for f in (output / 'frames').glob('*.png') if f.stat().st_size > 0}
        require(expected == actual, 'Rendered frame set does not match plan')
        movie = output / 'previz.mp4'
        run_logged([ffmpeg, '-nostdin', '-n', '-framerate', str(plan['fps']), '-start_number', '1', '-i', str(output / 'frames/frame_%04d.png'), '-frames:v', str(plan['frame_end']), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', str(movie)], output / 'encode.log')
        probe = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(movie)], text=True))
        videos = [x for x in probe['streams'] if x['codec_type'] == 'video']
        require(len(videos) == 1, 'Expected one video stream')
        video = videos[0]
        require(int(video['nb_read_frames']) == plan['frame_end'], 'Encoded frame count mismatch')
        require(video['width'] == plan['width'] and video['height'] == plan['height'], 'Encoded dimensions mismatch')
        require(abs(float(probe['format']['duration']) - plan['frame_end'] / plan['fps']) <= 1 / plan['fps'], 'Duration mismatch')
        (output / 'probe.json').write_text(json.dumps(probe, indent=2))
        run_logged([ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-i', str(movie), '-f', 'null', '-'], output / 'decode.log')
        manifest = {'status': 'technical_pass', 'purpose': 'planning_only', 'visual_qc': 'needs_review', 'geometry_qc': 'needs_review', 'provider_submission': 'not_performed', 'artifacts': {name: {'path': str(output / name), 'sha256': hashlib.sha256((output / name).read_bytes()).hexdigest()} for name in ('plan.json', 'scene.blend', 'previz.mp4', 'camera-samples.json', 'probe.json')}}
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        print(json.dumps(manifest, indent=2))
    except Exception as exc:
        (output / 'failure.json').write_text(json.dumps({'status': 'failed', 'error': str(exc)}))
        raise
    return 0


if __name__ == '__main__':
    if '--internal-build' in sys.argv:
        import bpy
        require(bpy.app.background, 'Internal invocation requires background Blender')
        index = sys.argv.index('--internal-build')
        blender_build(json.loads(Path(sys.argv[index + 1]).read_text()), Path(sys.argv[index + 2]))
    else:
        try:
            sys.exit(main())
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            print(str(error), file=sys.stderr)
            sys.exit(1)
