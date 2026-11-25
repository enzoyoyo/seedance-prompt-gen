#!/usr/bin/env python3
"""Turn one 片场 (local stage desk) camera into 00_previs planning sidecars.

Local only, standard library only. No network, no model calls. Reads the
project JSON saved by the browser app (1 grid unit = 1 metre, Y up, a camera
rig looks along its own +Z, cameras live at the root) and writes
manifest.json / camera.json / blocking.md / nbp-camera-fragment.json.
The camera fields are inferred candidates, not a model contract.
"""
from __future__ import annotations

import argparse
from decimal import ROUND_HALF_UP, Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys

NODE_TYPES = ('actor', 'primitive', 'model', 'group', 'camera')
SUBJECT_TYPES = ('actor', 'primitive', 'model')
ASPECTS = {'16:9': 16 / 9, '9:16': 9 / 16, '4:3': 4 / 3, '1:1': 1.0, '2.39:1': 2.39, '4:5': 4 / 5}
POSES = {
    'stand': ('站立', 0.86), 'walk': ('行走', 0.86), 'run': ('跑步', 0.82),
    'crouch': ('半蹲', 0.56), 'kneel': ('单膝跪', 0.5), 'reach': ('伸手', 0.86),
    'confront': ('对峙', 0.86), 'lookback': ('回头', 0.86), 'watch': ('观察', 0.86),
}
# Planning assumptions, not measurements of the clay figure.
PERSON_HEIGHT_M = 1.75
STANDING_HIP_M = 0.86
SHAPE_HEIGHT_M = {'box': 0.6, 'sphere': 0.56, 'cylinder': 0.8}
FULL_FRAME_DIAGONAL_MM = math.hypot(36, 24)
SHOT_SIZES = ((0.3, '特写'), (0.5, '近景'), (0.8, '中景'), (2.2, '全景'))
MOTION_USE = '只承担机位与路径，不继承灰模外观'
INFERRED = '推断，可改'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def vector(value, n, label):
    require(isinstance(value, list) and len(value) == n and all(number(x) for x in value), f'Invalid finite vector: {label}')


def validate(project):
    require(isinstance(project, dict), 'Project must be a JSON object')
    require(project.get('version') == 1, 'Unknown stage project version (expected 1)')
    nodes = project.get('nodes')
    require(isinstance(nodes, list) and nodes, 'Project has no nodes')
    ids = set()
    for node in nodes:
        require(isinstance(node, dict), 'Node must be an object')
        node_id = node.get('id')
        require(isinstance(node_id, str) and node_id and node_id not in ids, f'Invalid or duplicate node id: {node_id!r}')
        ids.add(node_id)
        require(node.get('type') in NODE_TYPES, f'Unknown node type: {node.get("type")!r}')
        require(isinstance(node.get('name'), str) and node['name'].strip(), f'Node {node_id} needs a name')
        for key in ('position', 'rotation', 'scale'):
            vector(node.get(key), 3, f'{node_id}.{key}')
        if node['type'] == 'actor':
            require(node.get('pose', 'stand') in POSES, f'Unknown pose on {node_id}')
        if node['type'] == 'camera':
            require(node.get('parentId') is None, f'Camera {node_id} must sit at the world root')
            require(number(node.get('fov')) and 1 < node['fov'] < 179, f'Invalid fov on {node_id}')
            require(node.get('aspectKey') in ASPECTS, f'Unknown aspectKey on {node_id}')
            if 'lookAt' in node:
                vector(node['lookAt'], 3, f'{node_id}.lookAt')
    for node in nodes:
        parent = node.get('parentId')
        require(parent is None or parent in ids, f'Missing parent for {node["id"]}')
    require(any(node['type'] == 'camera' for node in nodes), 'Project has no camera')
    path = project.get('path', [])
    require(isinstance(path, list), 'path must be a list')
    for point in path:
        vector(point, 2, 'path point')
    world_transforms(nodes)


def euler_xyz(rotation):
    """Rotation matrix for three.js Euler order XYZ (Rx * Ry * Rz)."""
    a, b, c = rotation
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    return [
        [cb * cc, -cb * sc, sb],
        [ca * sc + sa * sb * cc, ca * cc - sa * sb * sc, -sa * cb],
        [sa * sc - ca * sb * cc, sa * cc + ca * sb * sc, ca * cb],
    ]


def mat_mul(m, n):
    return [[sum(m[i][k] * n[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def apply(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def add(a, b):
    return [x + y for x, y in zip(a, b)]


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def normalize(v):
    length = math.sqrt(dot(v, v))
    require(length > 1e-9, 'Degenerate direction')
    return [x / length for x in v]


def world_transforms(nodes):
    """World position, rotation-only frame and Y scale per node id."""
    by_id = {node['id']: node for node in nodes}
    done = {}

    def resolve(node_id, trail):
        if node_id in done:
            return done[node_id]
        require(node_id not in trail, f'Parent cycle at {node_id}')
        node = by_id[node_id]
        rotation = euler_xyz(node['rotation'])
        scale = node['scale']
        if node.get('parentId') is None:
            parent = {'position': [0.0, 0.0, 0.0], 'linear': [[1, 0, 0], [0, 1, 0], [0, 0, 1]], 'rotation': [[1, 0, 0], [0, 1, 0], [0, 0, 1]], 'scale_y': 1.0}
        else:
            parent = resolve(node['parentId'], trail | {node_id})
        local_linear = [[rotation[i][j] * scale[j] for j in range(3)] for i in range(3)]
        result = {
            'position': add(parent['position'], apply(parent['linear'], node['position'])),
            'linear': mat_mul(parent['linear'], local_linear),
            'rotation': mat_mul(parent['rotation'], rotation),
            'scale_y': parent['scale_y'] * scale[1],
        }
        done[node_id] = result
        return result

    for node in nodes:
        resolve(node['id'], frozenset())
    return done


def js_fixed(value, digits=1):
    """Number.prototype.toFixed: half away from zero on the exact binary value."""
    if value == 0:
        value = 0.0
    return str(Decimal(value).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def js_round(value):
    return math.floor(value + 0.5)


def find_camera(nodes, wanted):
    matches = [node for node in nodes if node['type'] == 'camera' and wanted in (node['id'], node['name'])]
    require(matches, f'Camera not found: {wanted}')
    require(len(matches) == 1, f'Camera name is ambiguous: {wanted}')
    return matches[0]


def subject_height(node, frame):
    if node['type'] == 'actor':
        hip = POSES[node.get('pose', 'stand')][1]
        return PERSON_HEIGHT_M * hip / STANDING_HIP_M * frame['scale_y']
    if node['type'] == 'model':
        return PERSON_HEIGHT_M * frame['scale_y']
    return SHAPE_HEIGHT_M.get(node.get('shape'), 0.6) * frame['scale_y']


def facing_text(dot_value):
    if dot_value > 0.6:
        return '面向镜头'
    if dot_value > 0.2:
        return '四分之三侧面'
    if dot_value > -0.2:
        return '正侧面'
    if dot_value > -0.6:
        return '四分之三背面'
    return '背对镜头'


def build(project, camera_node, shot_id, has_motion, revision):
    nodes = project['nodes']
    by_id = {node['id']: node for node in nodes}
    frames = world_transforms(nodes)
    cam_frame = frames[camera_node['id']]
    cam_pos = cam_frame['position']
    forward = normalize(apply(cam_frame['rotation'], [0, 0, 1]))
    flat_right = cross(forward, [0, 1, 0])
    require(math.sqrt(dot(flat_right, flat_right)) > 1e-6, 'Camera looks straight up or down; blocking sides are undefined')
    flat_right = normalize(flat_right)
    screen_right = normalize(apply(cam_frame['rotation'], [-1, 0, 0]))
    screen_up = normalize(apply(cam_frame['rotation'], [0, 1, 0]))
    vfov = camera_node['fov']
    aspect = ASPECTS[camera_node['aspectKey']]
    tan_v = math.tan(math.radians(vfov) / 2)
    hfov = math.degrees(2 * math.atan(tan_v * aspect))
    focal_equiv = FULL_FRAME_DIAGONAL_MM / (2 * tan_v * math.hypot(1, aspect))

    look_target = by_id.get(project.get('lookAtId'))
    if look_target is not None and look_target['type'] == 'camera':
        look_target = None
    look_name = look_target['name'] if look_target else None
    if 'lookAt' in camera_node:
        look_point, look_source = camera_node['lookAt'], 'project'
    elif look_target is not None:
        frame = frames[look_target['id']]
        look_point = add(frame['position'], [0, subject_height(look_target, frame) / 2, 0])
        look_source = 'approximated'
    else:
        look_point, look_source = [0, 1, 0], 'scene_center'

    warnings = []
    lines = [
        camera_node['name'],
        f'视野 {js_round(vfov)}°',
        f'画幅 {camera_node["aspectKey"]}',
        f'镜头位置 {js_fixed(cam_pos[0])}, {js_fixed(cam_pos[1])}, {js_fixed(cam_pos[2])} 米',
        f'看向 {look_name}' if look_name else '看向场景中心',
        '',
    ]
    subjects = []
    for node in nodes:
        if node['type'] not in SUBJECT_TYPES:
            continue
        frame = frames[node['id']]
        pos = frame['position']
        rel = sub(pos, cam_pos)
        side, depth, foot = dot(rel, flat_right), dot(rel, forward), pos[1] - cam_pos[1]
        side_text = '在镜头中轴' if abs(side) < 0.15 else f'在画面右侧 {js_fixed(side)} 米' if side > 0 else f'在画面左侧 {js_fixed(abs(side))} 米'
        depth_text = f'前方 {js_fixed(depth)} 米' if depth >= 0 else f'后方 {js_fixed(abs(depth))} 米'
        foot_text = f'脚高于镜头 {js_fixed(foot)} 米' if foot > 0.15 else f'脚低于镜头 {js_fixed(abs(foot))} 米' if foot < -0.15 else '脚与镜头同高'
        pose = POSES[node.get('pose', 'stand')][0] if node['type'] == 'actor' else None
        facing = None
        if node['type'] == 'actor':
            front = normalize(apply(frame['rotation'], [0, 0, 1]))
            toward = sub(cam_pos, pos)
            facing = facing_text(dot(front, normalize(toward))) if dot(toward, toward) > 1e-12 else '正侧面'
        parent = by_id.get(node.get('parentId'))
        group = parent['name'] if parent else None
        lines.append(f'{node["name"]}{"，" + pose if pose else ""}{"，属于" + group if group else ""}')
        lines.append(f'{side_text}，{depth_text}，{foot_text}{"，" + facing if facing else ""}')
        height = subject_height(node, frame)
        center = add(pos, [0, height / 2, 0])
        center_rel = sub(center, cam_pos)
        center_depth = dot(center_rel, forward)
        in_frame = center_depth > 0.05 and abs(dot(center_rel, screen_up)) <= center_depth * tan_v and abs(dot(center_rel, screen_right)) <= center_depth * tan_v * aspect
        subjects.append({
            'id': node['id'], 'name': node['name'], 'type': node['type'], 'pose': node.get('pose') if node['type'] == 'actor' else None,
            'group': group, 'visible': node.get('visible', True) is not False,
            'world_position': [round(x, 3) for x in pos],
            'side_m': round(side, 3), 'depth_m': round(depth, 3), 'foot_rel_camera_m': round(foot, 3),
            'facing': facing, 'assumed_height_m': round(height, 3), 'center_in_frame': in_frame,
            '_center_depth': center_depth, '_height': height, '_base_y': pos[1],
        })
    if not subjects:
        lines.append('空间里还没有角色或道具。')

    main = None
    if look_target is not None and look_target['type'] in SUBJECT_TYPES:
        main = next(s for s in subjects if s['id'] == look_target['id'])
        if main['_center_depth'] <= 0.05:
            warnings.append(f'看向对象 {main["name"]} 在镜头后方，景别改按前方最近主体推断')
            main = None
    if main is None:
        ahead = [s for s in subjects if s['_center_depth'] > 0.05 and s['visible']]
        actors = [s for s in ahead if s['type'] == 'actor']
        pool = actors or ahead
        main = min(pool, key=lambda s: s['_center_depth']) if pool else None

    basis = {'camera_height_m': round(cam_pos[1], 3), 'pitch_deg': round(math.degrees(math.asin(max(-1, min(1, forward[1])))), 1)}
    if main is None:
        shot_size, angle = '远景', '平视'
        warnings.append('镜头前方没有可见主体，景别与角度只是占位推断')
    else:
        visible_height = 2 * main['_center_depth'] * tan_v
        ratio = visible_height / main['_height']
        shot_size = next((label for limit, label in SHOT_SIZES if ratio <= limit), '远景')
        head = main['_base_y'] + main['_height']
        delta = cam_pos[1] - head
        angle = '俯拍' if delta > 0.25 else '仰拍' if cam_pos[1] < main['_base_y'] + 0.55 * main['_height'] else '平视'
        basis.update({
            'subject': main['name'], 'subject_distance_m': round(main['_center_depth'], 3),
            'visible_height_m': round(visible_height, 3), 'visible_to_subject_ratio': round(ratio, 3),
            'subject_head_m': round(head, 3), 'camera_minus_head_m': round(delta, 3),
        })
    if main is not None and not main['center_in_frame']:
        warnings.append(f'主体 {main["name"]} 的中心不在画框内')

    path = [list(point) for point in project.get('path', [])]
    is_active = project.get('activeShotId') == camera_node['id']
    path_applies = len(path) >= 2 and is_active
    if len(path) >= 2 and not is_active:
        active = by_id.get(project.get('activeShotId'))
        warnings.append(f'路点由当前机位 {active["name"] if active else "（无）"} 播放，本机位按固定机位推断')
    target_text = look_name or '场景中心'
    movement = f'沿路点推轨，看向 {target_text}' if path_applies else 'locked'
    lens_note = f'垂直视野 {js_round(vfov)}°，画幅 {camera_node["aspectKey"]}，约合 {js_round(focal_equiv)} mm 全画幅等效（换算值）'
    for subject in subjects:
        for key in ('_center_depth', '_height', '_base_y'):
            subject.pop(key)

    camera = {
        'schema': 'stage-desk-camera-1',
        'shot_id': shot_id,
        'camera_id': camera_node['id'],
        'camera_name': camera_node['name'],
        'is_active_shot': is_active,
        'units': 'metre',
        'up_axis': '+Y',
        'position': [round(x, 4) for x in cam_pos],
        'forward': [round(x, 5) for x in forward],
        'screen_right': [round(x, 5) for x in screen_right],
        'screen_up': [round(x, 5) for x in screen_up],
        'rotation_euler_xyz_rad': camera_node['rotation'],
        'vertical_fov_deg': vfov,
        'horizontal_fov_deg': round(hfov, 2),
        'aspect_key': camera_node['aspectKey'],
        'aspect': round(aspect, 5),
        'focal_length_35mm_equiv_mm': {
            'value': round(focal_equiv, 1),
            'basis': '换算值：由垂直视野与画幅得对角视野，按 35mm 全画幅对角 43.27 mm 折算；不是实拍镜头参数',
        },
        'look_at': {'point': [round(x, 4) for x in look_point], 'target_id': look_target['id'] if look_target else None, 'target_name': look_name, 'source': look_source},
        'path': {'points_xz': path, 'height_m': round(cam_pos[1] or 1.5, 4), 'applies_to_this_camera': path_applies},
        'subjects': subjects,
        'assumptions': {'person_height_m': PERSON_HEIGHT_M, 'shape_height_m': SHAPE_HEIGHT_M},
    }
    fragment = {
        'status': 'planning_only',
        'note': INFERRED,
        'camera': {'shot_size': shot_size, 'angle': angle, 'movement': movement, 'lens_note': lens_note},
        'references': [],
        'basis': basis,
        'first_frame_gate': '片场 PNG 不直接进首帧槽：先经 whitemodel-previs S6 升级为 first_graded.png',
    }
    if has_motion:
        fragment['references'].append({'ref': f'@motion_stage_{shot_id.lower()}_v{revision:02d}', 'role': 'motion', 'use': MOTION_USE})
    blocking = '\n'.join([
        f'# 站位说明 {shot_id} · {camera_node["name"]}',
        '',
        f'来源：片场工程「{project.get("name", "")}」，导出时间 {project.get("exportedAt") or "未记录"}。1 格 = 1 米，Y 向上。与片场右侧站位说明同口径，只交空间合同，不交材质、服装、面部。',
        '',
        '```text',
        *lines,
        '```',
        '',
    ])
    return camera, fragment, blocking, warnings


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--project', required=True, type=Path, help='片场 project JSON (保存 or 交接)')
    parser.add_argument('--shot', required=True, help='Shot id such as S01')
    parser.add_argument('--camera', required=True, help='Camera name or id in the project, e.g. "机位 1"')
    parser.add_argument('--still', type=Path, help='Camera PNG exported by 片场')
    parser.add_argument('--motion', type=Path, help='Camera move webm/mp4 recorded by 片场')
    parser.add_argument('--revision', type=int, default=1, help='Version number for the motion tag (default 1)')
    parser.add_argument('--output', type=Path, help='New directory; refused if it exists')
    parser.add_argument('--check', action='store_true', help='Validate only; no writes')
    args = parser.parse_args(argv)
    require(re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', args.shot) is not None, 'Invalid shot id (letters and digits, e.g. S01)')
    require(1 <= args.revision <= 99, 'Invalid revision')
    project = json.loads(args.project.read_text(encoding='utf-8'))
    validate(project)
    camera_node = find_camera(project['nodes'], args.camera)
    for path, suffixes in ((args.still, ('.png',)), (args.motion, ('.webm', '.mp4'))):
        if path is not None:
            require(path.is_file(), f'File not found: {path}')
            require(path.suffix.lower() in suffixes, f'Unsupported file type: {path.name}')
    camera, fragment, blocking, warnings = build(project, camera_node, args.shot, args.motion is not None, args.revision)
    if args.check:
        print(json.dumps({'status': 'valid', 'scope': 'planning_only', 'shot_id': args.shot, 'camera': camera_node['name'], 'camera_fields': fragment['camera'], 'warnings': warnings}, ensure_ascii=False))
        return 0
    require(args.output is not None, '--output required unless --check')
    require(not args.output.exists() and not args.output.is_symlink(), 'OUTPUT_EXISTS: use a new revision directory')
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    inputs = {'project': (args.project, 'stage-project.json')}
    if args.still is not None:
        inputs['still'] = (args.still, 'still.png')
    if args.motion is not None:
        inputs['motion'] = (args.motion, 'motion' + args.motion.suffix.lower())
    for source, name in inputs.values():
        shutil.copyfile(source, output / name)
    write_json(output / 'camera.json', camera)
    write_json(output / 'nbp-camera-fragment.json', fragment)
    (output / 'blocking.md').write_text(blocking, encoding='utf-8')
    names = [name for _, name in inputs.values()] + ['camera.json', 'blocking.md', 'nbp-camera-fragment.json']
    manifest = {
        'status': 'planning_only',
        'source': 'stage-desk',
        'shot_id': args.shot,
        'camera': camera_node['name'],
        'exported_at': project.get('exportedAt'),
        'visual_qc': 'needs_review',
        'geometry_qc': 'needs_review',
        'provider_submission': 'not_performed',
        'delivery': '00_previs only; 不进成片目录',
        'camera_fields': INFERRED,
        'warnings': warnings,
        'inputs': {key: {'source': str(source.expanduser().resolve()), 'copy': name} for key, (source, name) in inputs.items()},
        'artifacts': {name: {'path': str(output / name), 'sha256': sha256(output / name)} for name in names},
    }
    write_json(output / 'manifest.json', manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
