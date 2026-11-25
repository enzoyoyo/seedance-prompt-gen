#!/usr/bin/env python3
"""Assemble the approved takes of one tier into a single cut, in shot-spec order.

Only takes with status `approved`, non-stale state, and reference digests matching the current locked
identity/scene/previs assets are accepted; upstream script/previs/identity modifications block assembly,
dry runs included.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import cutlist_io
from media_inspection import probe
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from change_impact import (
    pending_gate2_errors, stale_previs_scenes, stale_shot_ids, stale_take_errors, take_matches_current_refs,
)
from drama_project import (
    TIERS, ProjectError, drama_block, now_iso, resolve_in_project, section, sha256_file, take_rows,
    update_manifest, write_json_atomic,
)
from lock_script import verify_lock
from previs_coverage import identity_gate_errors, previs_gate_errors, shot_ref_provenance_errors
from validate_shot_spec import active_shots, load_project_spec, root_id, shot_beats, shot_rows

EXIT_OK, EXIT_REFUSED, EXIT_INPUT, EXIT_DEPENDENCY = 0, 1, 3, 4
AUDIO_RATE = 48000
BLACK_RE = re.compile(r"black_start:(?P<s0>[0-9.]+)\s+black_end:(?P<s1>[0-9.]+)")
FREEZE_START_RE = re.compile(r"freeze_start:\s*(?P<s0>[0-9.]+)")
FREEZE_END_RE = re.compile(r"freeze_end:\s*(?P<s1>[0-9.]+)")


def upstream_integrity_errors(project: Path, manifest: dict[str, Any], spec: dict[str, Any],
                              spec_dir: Path) -> list[str]:
    drama = drama_block(manifest)
    errors = verify_lock(project)
    if errors:
        return errors
    errors += pending_gate2_errors(drama)
    errors += [f"STALE_PREVIS_SCENE:{sc}" for sc in sorted(stale_previs_scenes(drama))]
    errors += previs_gate_errors(project, drama)
    errors += identity_gate_errors(project, drama)
    errors += shot_ref_provenance_errors(project, drama, spec, spec_dir)
    return errors


def approved_takes(manifest: dict[str, Any], spec: dict[str, Any], spec_dir: Path, tier: str,
                   prefix: str | None = None) -> list[dict[str, Any]]:
    """One non-stale approved take per active shot (matching current ref digests), in spec order."""
    rows = shot_rows(spec)
    drama = drama_block(manifest)
    stale_shots = stale_shot_ids(drama)
    post = set(spec.get("post_beats") or [])
    candidates = [shot for shot in active_shots(rows)
                  if not prefix or root_id(rows, shot["id"]).startswith(prefix)]
    if prefix and not candidates:
        raise ProjectError("NO_SHOTS_FOR_PREFIX", prefix)
    picked, missing, ref_drifted = [], [], []
    for shot in candidates:
        if set(shot_beats(shot, [])) and set(shot_beats(shot, [])) <= post:
            continue
        root = root_id(rows, shot["id"])
        take = next((row for row in take_rows(manifest) if row.get("shot_id") == root and row.get("status") == "approved"
                     and (row.get("tier") == tier or row.get("origin") == "reused")), None)
        if take is None:
            missing.append(shot["id"])
            continue
        if root in stale_shots:
            raise ProjectError("STALE_TAKE_INVALIDATED", str(take.get("take_id") or root))
        picked.append(take)
        if not take_matches_current_refs(spec, spec_dir, take) and take.get("stale") is not True:
            ref_drifted.append(str(take.get("take_id")))
    if missing:
        raise ProjectError("SHOT_WITHOUT_APPROVED_TAKE", ",".join(missing))
    stale = stale_take_errors(picked)
    if stale:
        raise ProjectError("STALE_TAKE_INVALIDATED", ",".join(err.split(":", 1)[1] for err in stale))
    if ref_drifted:
        raise ProjectError("TAKE_REF_DIGEST_STALE", ",".join(ref_drifted))
    return picked


def probe_format(path: Path) -> tuple[str, str]:
    facts = probe(path)
    if not facts["video_streams"]:
        raise ProjectError("VIDEO_STREAM_MISSING", path.name)
    return f"{facts['width']}x{facts['height']}", facts["fps"]


def probe_duration(path: Path) -> float:
    done = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                          stdout=subprocess.PIPE, text=True, check=True)
    return float(done.stdout.strip())


def has_audio(path: Path) -> bool:
    done = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                           "-of", "csv=p=0", str(path)], stdout=subprocess.PIPE, text=True, check=True)
    return bool(done.stdout.strip())


def normalise_command(source: Path, target: Path, size: str, fps: str,
                      span: tuple[float, float] | None, audio: bool,
                      fade_ms: int = 0, clip_duration: float | None = None) -> list[str]:
    width, height = size.split("x")
    cut = ["-ss", str(span[0]), "-to", str(span[1])] if span else []
    v_chain = (f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p[v]")
    silence = [] if audio else ["-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo"]
    if fade_ms <= 0 or not audio or clip_duration is None:
        return ["ffmpeg", "-v", "error", "-y", *cut, "-i", str(source), *silence, "-filter_complex", v_chain,
                "-map", "[v]", "-map", "0:a" if audio else "1:a", "-shortest",
                "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-ar", str(AUDIO_RATE), "-ac", "2", str(target)]
    fade_s = min(fade_ms / 1000.0, max(0.001, clip_duration / 2.0))
    out_st = round(max(0.0, clip_duration - fade_s), 4)
    graph = f"{v_chain};[0:a]afade=t=in:st=0:d={fade_s:g},afade=t=out:st={out_st:g}:d={fade_s:g}[a]"
    return ["ffmpeg", "-v", "error", "-y", *cut, "-i", str(source), "-filter_complex", graph,
            "-map", "[v]", "-map", "[a]", "-shortest",
            "-c:v", "libx264", "-crf", "18", "-c:a", "aac", "-ar", str(AUDIO_RATE), "-ac", "2", str(target)]


def normalize_cfr(source, target, size, fps, span, audio, stream_index, fade_ms, duration, replacement=None):
    if stream_index is None:
        raise ProjectError("VIDEO_STREAM_MISSING", source.name)
    cut = ["-ss", str(span[0]), "-to", str(span[1])] if span else []
    silence = [] if audio else ["-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo"]
    audio_map = "0:a:0?" if audio else "1:a:0"
    if replacement:
        silence = [*cut, "-i", str(replacement)]
        audio_map = "1:a:0"
    w, h = size.split("x")
    graph = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    fade = []
    if audio and fade_ms and duration:
        seconds = min(fade_ms / 1000, duration / 2)
        fade = ["-af", f"afade=t=in:d={seconds},afade=t=out:st={duration-seconds}:d={seconds}"]
    rate = Fraction(fps)
    frames = max(1, round(Fraction(str(duration)) * rate))
    return ["ffmpeg", "-nostdin", "-v", "error", "-y", *cut, "-i", str(source), *silence,
            "-t", str(float(frames / rate)), "-frames:v", str(frames),
            "-map", "0:v:0" if stream_index == 0 else f"0:{stream_index}", "-map", audio_map,
            "-vf", graph, *fade, "-r", fps, "-fps_mode", "cfr", "-pix_fmt", "yuv420p", "-c:v", "libx264",
            "-c:a", "aac", "-ar", str(AUDIO_RATE), "-ac", "2", "-shortest", str(target)]


def end_card_command(target: Path, size: str, fps: str, seconds: float) -> list[str]:
    return ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s={size}:r={fps}:d={seconds}",
            "-f", "lavfi", "-i", f"anullsrc=r={AUDIO_RATE}:cl=stereo", "-t", str(seconds),
            "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", str(target)]


def concat_command(listing: Path, output: Path, loudness: str | None) -> list[str]:
    audio = ["-af", f"loudnorm={loudness}", "-ar", str(AUDIO_RATE), "-c:a", "aac"] if loudness else ["-c:a", "copy"]
    return ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c:v", "copy", *audio, str(output)]


def trims(items: list[str]) -> dict[str, tuple[float, float]]:
    result = {}
    for item in items:
        name, _, span = item.partition("=")
        try:
            start, end = (float(part) for part in span.split(","))
        except ValueError as exc:
            raise ProjectError("INPUT_ERROR", f"--trim expects SPEC_ID=START,END: {item}") from exc
        result[name] = (start, end)
    return result


def plan(args: argparse.Namespace, takes: list[dict[str, Any]], work: Path) -> tuple[list[list[str]], list[dict[str, Any]]]:
    project = args.project.expanduser()
    sources = [resolve_in_project(project, take.get("file")) for take in takes]
    for take, source in zip(takes, sources):
        if source is None or not source.is_file() or sha256_file(source) != take.get("file_sha256"):
            raise ProjectError("APPROVED_FILE_MISSING_OR_CHANGED", take["take_id"])
    size, fps = (args.size, args.fps) if args.size and args.fps else probe_format(sources[0])
    size, fps = args.size or size, args.fps or fps
    edits = {}
    if args.cutlist_in:
        rate, edits, args.end_card = cutlist_io.read(args.cutlist_in, takes)
        fps = str(rate)
    else:
        rate = Fraction(fps)
    args.cut_rate = rate
    spans = trims(args.trim)
    commands, parts = [], []
    for index, (take, source) in enumerate(zip(takes, sources)):
        part, span = work / f"{index:03d}.mp4", spans.get(take["spec_id"])
        facts = probe(source)
        edit = edits.get(take["take_id"], {})
        transform = edit.get("transform", {"size": size, "fit": "contain"})
        if transform.get("fit") != "contain" or set(transform) != {"size", "fit"}:
            raise ProjectError("UNSUPPORTED_CUT_TRANSFORM")
        size = transform["size"]
        if not re.fullmatch(r"[1-9]\d*x[1-9]\d*", size):
            raise ProjectError("INVALID_CUT_DIMENSIONS")
        if edit:
            span = (float(edit["source_in"] / rate), float(edit["source_out"] / rate))
        if span and not 0 <= span[0] < span[1] <= facts["duration"] + .5 / float(rate):
            raise ProjectError("INVALID_SOURCE_RANGE", take["take_id"])
        route = edit.get("audio_route", take.get("audio_route", "keep_native"))
        if route not in {"keep_native", "native_no_dialogue", "mute", "replace_dialogue"}:
            raise ProjectError("INVALID_AUDIO_ROUTE", route)
        replacement, stem_info = None, {}
        if route == "replace_dialogue":
            name = edit.get("dialogue_stem") or take.get("dialogue_stem")
            replacement = resolve_in_project(project, name)
            if not replacement or not replacement.is_file():
                raise ProjectError("DIALOGUE_STEM_MISSING", take["take_id"])
            stem = probe(replacement)
            if not stem["audio_streams"] or stem["duration"] < (span[1] if span else facts["duration"]) - .5 / float(rate):
                raise ProjectError("DIALOGUE_STEM_TOO_SHORT", str(name))
            stem_info = {"dialogue_stem": name, "dialogue_stem_hash": sha256_file(replacement)}
            if edit and edit.get("dialogue_stem_hash") != stem_info["dialogue_stem_hash"]:
                raise ProjectError("DIALOGUE_STEM_CHANGED", str(name))
        audio = bool(replacement or facts["audio_streams"]) and route != "mute"
        dur = span[1] - span[0] if span else facts["duration"]
        if args.frame_normalize or replacement:
            commands.append(normalize_cfr(source, part, size, fps, span, audio, facts["primary_index"], args.fade_ms, dur, replacement))
        else:
            commands.append(normalise_command(source, part, size, fps, span, audio, args.fade_ms, dur))
        parts.append({"take_id": take["take_id"], "spec_id": take["spec_id"], "part": part,
                      "source_hash": take["file_sha256"], "transform": transform, "audio_route": route, **stem_info,
                      "source": take["file"], "offset": span[0] if span else 0.0})
    if args.end_card:
        part = work / "end_card.mp4"
        commands.append(end_card_command(part, size, fps, args.end_card))
        parts.append({"take_id": None, "spec_id": None, "part": part, "source": "<end card>", "offset": 0.0})
    concatenate = concat_command(work / "list.txt", args.output, args.loudness)
    if args.frame_normalize:
        index = concatenate.index("-c:v")
        concatenate[index:index + 2] = ["-vf", f"setpts=N/(({fps})*TB)", "-r", fps, "-fps_mode", "cfr",
                                         "-c:v", "libx264", "-crf", "18"]
    commands.append(concatenate)
    return commands, parts


def timeline(parts: list[dict[str, Any]], rate: Fraction) -> list[dict[str, Any]]:
    rows, clock = [], 0
    for part in parts:
        count = round(Fraction(str(probe(part["part"])["duration"])) * rate)
        start = round(Fraction(str(part["offset"])) * rate)
        length = float(count / rate)
        rows.append({"take_id": part["take_id"], "spec_id": part["spec_id"], "source": part["source"],
                     "source_hash": part.get("source_hash"), "transform": part.get("transform", {}),
                     **{k: part[k] for k in ("dialogue_stem", "dialogue_stem_hash") if k in part},
                     "audio_route": part.get("audio_route", "mute"), "source_in": start, "source_out": start + count,
                     "timeline_in": clock, "timeline_out": clock + count, "start": round(float(clock / rate), 3), "duration": round(length, 3), "offset": part["offset"]})
        clock += count
    return rows


def record_cut(args: argparse.Namespace, rows: list[dict[str, Any]], takes: list[dict[str, Any]]) -> None:
    project = args.project.expanduser()
    output = args.output.resolve()
    inside = output.is_relative_to(project.resolve())
    cut = {
        "file": str(output.relative_to(project.resolve())) if inside else str(output),
        "file_sha256": sha256_file(output),
        "built_at": now_iso(),
        "takes": [row["take_id"] for row in rows if row["take_id"]],
        "take_sha256s": {t["take_id"]: t.get("file_sha256") for t in takes if t.get("take_id")},
    }

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        drama = drama_block(manifest)
        if args.prefix:
            key = f"{args.tier}:{args.prefix}"
            return {**manifest, "drama": {**drama, "act_cuts": {**section(drama, "act_cuts"), key: cut}}}
        return {**manifest, "drama": {**drama, "cuts": {**section(drama, "cuts"), args.tier: cut}}}
    update_manifest(project, mutate)


def detect_spans(output: Path) -> list[dict[str, Any]]:
    done = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(output), "-vf",
         "blackdetect=d=0.05:pix_th=0.10,freezedetect=n=0.003:d=0.12", "-an", "-f", "null", "-"],
        stderr=subprocess.PIPE, text=True, check=True,
    )
    events = [{"kind": "black", "start": float(m["s0"]), "end": float(m["s1"])}
              for m in BLACK_RE.finditer(done.stderr)]
    f_start: float | None = None
    for line in done.stderr.splitlines():
        if m := FREEZE_START_RE.search(line):
            f_start = float(m["s0"])
        elif (m := FREEZE_END_RE.search(line)) and f_start is not None:
            events.append({"kind": "freeze", "start": f_start, "end": float(m["s1"])})
            f_start = None
    if f_start is not None:
        events.append({"kind": "freeze", "start": f_start, "end": float("inf")})
    return events


def check_seams(output: Path, rows: list[dict[str, Any]]) -> Path:
    non_card = [row for row in rows if row.get("source") != "<end card>"]
    boundaries = [round(row["start"] + row["duration"], 3) for row in non_card[:-1]]
    events = detect_spans(output) if boundaries else []
    defects = [{"seam_at": seam, **ev} for seam in boundaries for ev in events
               if ev["start"] <= seam + 0.12 and ev["end"] >= seam - 0.12]
    report_path = output.with_suffix(".seams.json")
    write_json_atomic(report_path, {"ok": not defects, "boundaries": boundaries, "defects": defects})
    if defects:
        first = defects[0]
        raise ProjectError("CUT_SEAM_DEFECT", f"{first['kind']}@{first['seam_at']}")
    return report_path


def assemble(args: argparse.Namespace) -> dict[str, Any]:
    if args.fade_ms < 0:
        raise ProjectError("INPUT_ERROR", f"--fade-ms must be >= 0: {args.fade_ms}")
    project = args.project.expanduser()
    spec, spec_dir, manifest = load_project_spec(project)
    args.frame_normalize = drama_block(manifest).get("sop_version") == "3.0" or bool(args.cutlist_in or args.cutlist_out)
    if args.frame_normalize:
        args.fps = args.fps or "24"
    upstream_errs = upstream_integrity_errors(project, manifest, spec, spec_dir)
    if upstream_errs:
        head, _, detail = upstream_errs[0].partition(":")
        raise ProjectError(head, detail)
    takes = approved_takes(manifest, spec, spec_dir, args.tier, args.prefix)
    protected = {resolve_in_project(project, t.get("file")) for t in takes}
    protected.update(resolve_in_project(project, t.get("dialogue_stem")) for t in takes)
    output_paths = [args.output, args.output.with_suffix(".timeline.json")]
    if args.frame_normalize:
        output_paths.append(args.cutlist_out or args.output.with_suffix(".otio"))
    if args.check_seams:
        output_paths.append(args.output.with_suffix(".seams.json"))
    targets = {p.resolve() for p in output_paths}
    if len(targets) != len(output_paths) or targets & protected:
        raise ProjectError("CUT_OUTPUT_PATH_CONFLICT")
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise ProjectError("POST_DEPENDENCY_MISSING", tool)
    with tempfile.TemporaryDirectory(prefix="assemble-") as scratch:
        work = Path(scratch)
        commands, parts = plan(args, takes, work)
        if args.dry_run:
            return {"dry_run": True, "would_run": commands, "takes": [take["take_id"] for take in takes]}
        (work / "list.txt").write_text("".join(f"file '{part['part']}'\n" for part in parts), encoding="utf-8")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        for command in commands[:-1]:
            subprocess.run(command, check=True)
        rows = timeline(parts, args.cut_rate)
        subprocess.run(commands[-1], check=True)
    timeline_path = args.output.with_suffix(".timeline.json")
    timeline_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.frame_normalize:
        cutlist_io.write(args.cutlist_out or args.output.with_suffix(".otio"), rows, args.cut_rate)
    seams_path = check_seams(args.output, rows) if args.check_seams else None
    record_cut(args, rows, takes)
    out = {"ok": True, "output": str(args.output), "timeline": str(timeline_path), "clips": len(takes),
           "loudness": args.loudness or "not normalised: no --loudness target given"}
    return {**out, "seams": str(seams_path)} if seams_path else out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes: 0 done; 1 refused; 3 input or ffmpeg error; 4 ffmpeg/ffprobe missing.")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--tier", required=True, choices=TIERS)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--size", help="WIDTHxHEIGHT; default: the first clip's")
    parser.add_argument("--fps", help="frame rate; default: the first clip's")
    parser.add_argument("--cutlist-in", type=Path)
    parser.add_argument("--cutlist-out", type=Path)
    parser.add_argument("--loudness", help="loudnorm target, e.g. I=<LUFS>:TP=<dBTP>:LRA=<LU>; omitted = untouched")
    parser.add_argument("--end-card", type=float, help="append a silent black end card of this many seconds")
    parser.add_argument("--prefix", help="only assemble shots whose root id starts with this prefix (per-act review)")
    parser.add_argument("--trim", action="append", default=[], help="SPEC_ID=START,END seconds kept of that take (repeatable)")
    parser.add_argument("--fade-ms", type=int, default=0, help="per-clip audio edge fade in ms; 0 = untouched")
    parser.add_argument("--check-seams", action="store_true", help="detect black/freeze defects across cut boundaries")
    parser.add_argument("--dry-run", action="store_true", help="print the commands; run and record nothing")
    args = parser.parse_args(argv)
    try:
        result = assemble(args)
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return {"INPUT_ERROR": EXIT_INPUT, "POST_DEPENDENCY_MISSING": EXIT_DEPENDENCY}.get(exc.code, EXIT_REFUSED)
    except subprocess.CalledProcessError as exc:
        print(json.dumps({"ok": False, "errors": [f"FFMPEG_FAILED:{exc.cmd[0]}:{exc.returncode}"]}, indent=2))
        return EXIT_INPUT
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
