#!/usr/bin/env python3
"""Replace the per-clip generated music of a cut with one score, keeping dialogue and effects.

Every creative decision comes from the project's mix config (JSON); this tool has no built-in
taste. The config says which separated stems stay, which spans are muted on which stem, where
each score cue sits and how loud, and how hard the score is ducked under which stem:

  {"separator": {"model": "<demucs model>"},
   "keep_stems": ["<stem>", ...],
   "mute_spans": [{"stem": "<stem>", "start": 0.0, "end": 0.0}],
   "score": [{"file": "<path in project>", "start": 0.0, "gain_db": 0.0}],
   "ducking": {"key_stem": "<stem>", "threshold": 0.0, "ratio": 0.0, "attack_ms": 0, "release_ms": 0},
   "loudness": "<loudnorm target, optional>"}

Stem separation needs demucs in the interpreter given by --demucs-python (or $DEMUCS_PY); when
it is missing the tool stops and says so. --dry-run prints the commands and runs nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from check_post_deps import HINTS, missing_for
from drama_project import (
    ProjectError, nonempty, now_iso, read_json, resolve_in_project, sha256_file, write_json_atomic,
)

EXIT_OK, EXIT_REFUSED, EXIT_INPUT, EXIT_DEPENDENCY = 0, 1, 3, 4
DUCKING_FIELDS = ("key_stem", "threshold", "ratio", "attack_ms", "release_ms")


def number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def positive(value: object) -> bool:
    return number(value) and float(value) > 0


def cue_timing_ok(cue: dict[str, Any], default_zero_start: bool = False) -> bool:
    start = cue.get("start", 0.0 if default_zero_start else None)
    if not number(start) or float(start) < 0 or not number(cue.get("gain_db")):
        return False
    if cue.get("end") is not None and (not number(cue["end"]) or float(cue["end"]) <= float(start)):
        return False
    c_start, c_end = cue.get("clip_start"), cue.get("clip_end")
    if c_start is not None and (not number(c_start) or float(c_start) < 0):
        return False
    if c_end is not None and (not number(c_end) or float(c_end) <= float(c_start or 0.0)):
        return False
    return all(cue.get(k) is None or positive(cue[k]) for k in ("fade_in_s", "fade_out_s"))


def span_effects_errors(items: object, stems: list[str]) -> list[str]:
    if items is None:
        return []
    if not isinstance(items, list):
        return ["MIX_SPAN_EFFECT_INVALID:0"]
    errors = []
    for index, fx in enumerate(items):
        span_ok = (isinstance(fx, dict) and fx.get("stem") in stems and number(fx.get("start"))
                   and number(fx.get("end")) and 0 <= fx["start"] < fx["end"])
        low, high, gain = (fx.get("lowpass"), fx.get("highpass"), fx.get("gain_db")) if isinstance(fx, dict) else (None,) * 3
        fx_ok = ((low is None or positive(low)) and (high is None or positive(high))
                 and (gain is None or number(gain)) and any(v is not None for v in (low, high, gain)))
        if not (span_ok and fx_ok):
            errors.append(f"MIX_SPAN_EFFECT_INVALID:{index}")
    return errors


def config_errors(config: object, project: Path) -> list[str]:
    """Everything the mix needs must be stated; nothing is assumed."""
    if not isinstance(config, dict):
        return ["MIX_CONFIG_NOT_AN_OBJECT"]
    errors = []
    stems = config.get("keep_stems")
    if not nonempty((config.get("separator") or {}).get("model") if isinstance(config.get("separator"), dict) else None):
        errors.append("MIX_CONFIG_MISSING:separator.model")
    if not isinstance(stems, list) or not stems or not all(nonempty(stem) for stem in stems):
        return errors + ["MIX_CONFIG_MISSING:keep_stems"]
    for index, span in enumerate(config.get("mute_spans") or []):
        ok = isinstance(span, dict) and span.get("stem") in stems and number(span.get("start")) and number(span.get("end"))
        if not ok or span["end"] <= span["start"]:
            errors.append(f"MIX_MUTE_SPAN_INVALID:{index}")
    errors += span_effects_errors(config.get("span_effects"), stems)
    score = config.get("score")
    if not isinstance(score, list) or not score:
        errors.append("MIX_CONFIG_MISSING:score")
    for index, cue in enumerate(score if isinstance(score, list) else []):
        path = resolve_in_project(project, cue.get("file")) if isinstance(cue, dict) else None
        if path is None or not path.is_file() or not cue_timing_ok(cue):
            errors.append(f"MIX_SCORE_CUE_INVALID:{index}")
    ambience = config.get("ambience")
    if ambience is not None and not isinstance(ambience, list):
        errors.append("MIX_AMBIENCE_INVALID:0")
    for index, cue in enumerate(ambience if isinstance(ambience, list) else []):
        path = resolve_in_project(project, cue.get("file")) if isinstance(cue, dict) else None
        if path is None or not path.is_file() or not cue_timing_ok(cue, default_zero_start=True):
            errors.append(f"MIX_AMBIENCE_INVALID:{index}")
    ducking = config.get("ducking")
    if ducking is not None:
        missing = [name for name in DUCKING_FIELDS if not isinstance(ducking, dict) or ducking.get(name) in (None, "")]
        errors += [f"MIX_CONFIG_MISSING:ducking.{name}" for name in missing]
        if not missing and ducking["key_stem"] not in stems:
            errors.append("MIX_DUCKING_KEY_NOT_KEPT")
    return errors


def stems_dir(root: Path, model: str, cut: Path) -> Path:
    return root / model / cut.stem


def separation_commands(cut: Path, root: Path, model: str, python: str) -> list[list[str]]:
    wav = root / f"{cut.stem}.wav"
    return [["ffmpeg", "-v", "error", "-y", "-i", str(cut), "-vn", "-ac", "2", str(wav)],
            [python, "-m", "demucs", "-n", model, "-o", str(root), str(wav)]]


def stem_filters(config: dict[str, Any], stem: str) -> list[str]:
    filters = [f"volume=enable='between(t,{span['start']},{span['end']})':volume=0"
               for span in config.get("mute_spans") or [] if span["stem"] == stem]
    for fx in config.get("span_effects") or []:
        if fx["stem"] != stem:
            continue
        gate = f"enable='between(t,{fx['start']},{fx['end']})'"
        if fx.get("highpass") is not None:
            filters.append(f"highpass=f={fx['highpass']}:{gate}")
        if fx.get("lowpass") is not None:
            filters.append(f"lowpass=f={fx['lowpass']}:{gate}")
        if fx.get("gain_db") is not None:
            filters.append(f"volume={gate}:volume={fx['gain_db']}dB")
    return filters or ["anull"]


def cue_chain(index: int, cue: dict[str, Any], label: str) -> str:
    start = float(cue.get("start", 0.0))
    c_start, c_end = cue.get("clip_start"), cue.get("clip_end")
    span_len = float(cue["end"]) - start if cue.get("end") is not None else None
    if span_len is not None and (c_end is None or (c_end - float(c_start or 0.0)) > span_len):
        c_end = float(c_start or 0.0) + span_len
    parts: list[str] = []
    if c_start is not None or c_end is not None:
        opts = ([f"start={c_start}"] if c_start is not None else []) + ([f"end={c_end}"] if c_end is not None else [])
        parts += [f"atrim={':'.join(opts)}", "asetpts=PTS-STARTPTS"]
    clip_len = (float(c_end) - float(c_start or 0.0)) if c_end is not None else span_len
    if cue.get("fade_in_s") is not None:
        parts.append(f"afade=t=in:st=0:d={cue['fade_in_s']}")
    if cue.get("fade_out_s") is not None:
        st = f":st={round(max(0.0, clip_len - float(cue['fade_out_s'])), 3)}" if clip_len is not None else ""
        parts.append(f"afade=t=out{st}:d={cue['fade_out_s']}")
    parts += [f"volume={cue['gain_db']}dB", f"adelay={round(start * 1000)}:all=1"]
    return f"[{index}:a]" + ",".join(parts) + f"[{label}]"


def mix_graph(config: dict[str, Any]) -> str:
    """ffmpeg filter graph: inputs are the cut (0), kept stems, score cues, then optional ambience."""
    stems, score, ambience = config["keep_stems"], config["score"], config.get("ambience") or []
    ducking, chains, labels = config.get("ducking"), [], []
    for index, stem in enumerate(stems, start=1):
        split = f",asplit=2[s{index}][key]" if ducking and ducking["key_stem"] == stem else f"[s{index}]"
        chains.append(f"[{index}:a]" + ",".join(stem_filters(config, stem)) + split)
        labels.append(f"[s{index}]")
    cues = [f"[c{i}]" for i in range(len(score))]
    chains += [cue_chain(len(stems) + 1 + i, cue, f"c{i}") for i, cue in enumerate(score)]
    chains.append("".join(cues) + f"amix=inputs={len(cues)}:normalize=0[score]")
    amb_base = len(stems) + 1 + len(score)
    amb_labels = [f"[a{i}]" for i in range(len(ambience))]
    chains += [cue_chain(amb_base + i, cue, f"a{i}") for i, cue in enumerate(ambience)]
    if ducking:
        chains.append("[score][key]sidechaincompress=threshold={threshold}:ratio={ratio}:attack={attack_ms}"
                      ":release={release_ms}[bed]".format(**ducking))
    tail = f",loudnorm={config['loudness']}" if nonempty(config.get("loudness")) else ""
    bus = labels + [("[bed]" if ducking else "[score]")] + amb_labels
    chains.append("".join(bus) + f"amix=inputs={len(bus)}:normalize=0:duration=first{tail},apad[out]")
    return ";".join(chains)


def mix_command(cut: Path, output: Path, config: dict[str, Any], project: Path, stems: Path) -> list[str]:
    """The mixed audio is padded and `-shortest` then stops at the picture: the cut keeps its length."""
    inputs = ["-i", str(cut)]
    for stem in config["keep_stems"]:
        inputs += ["-i", str(stems / f"{stem}.wav")]
    for cue in [*(config["score"]), *(config.get("ambience") or [])]:
        inputs += ["-i", str(resolve_in_project(project, cue["file"]))]
    return ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", mix_graph(config),
            "-map", "0:v", "-map", "[out]", "-c:v", "copy", "-c:a", "aac", "-shortest", str(output)]


def write_remix_sidecar(cut: Path, output: Path, config: dict[str, Any]) -> Path:
    sidecar = output.with_suffix(".remix.json")
    write_json_atomic(sidecar, {
        "tool": "remix_score", "cut_sha256": sha256_file(cut), "output_sha256": sha256_file(output),
        "separator_model": config["separator"]["model"], "keep_stems": list(config["keep_stems"]),
        "score_files": [cue["file"] for cue in config["score"]],
        "ambience_files": [cue["file"] for cue in config.get("ambience") or []], "built_at": now_iso(),
    })
    return sidecar


def remix(args: argparse.Namespace) -> dict[str, Any]:
    project = args.project.expanduser()
    config = read_json(args.config.expanduser())
    errors = config_errors(config, project)
    if errors:
        raise ProjectError(errors[0], ";".join(errors[1:]))
    if not args.cut.is_file():
        raise ProjectError("INPUT_ERROR", f"cut not found: {args.cut}")
    model = config["separator"]["model"]
    root = (args.stems_dir or project / "stems").expanduser()
    stems = stems_dir(root, model, args.cut)
    ready = all((stems / f"{stem}.wav").is_file() for stem in config["keep_stems"])
    commands = ([] if ready else separation_commands(args.cut, root, model, args.demucs_python))
    commands.append(mix_command(args.cut, args.output, config, project, stems))
    if args.dry_run:
        return {"dry_run": True, "stems_reused": ready, "would_run": commands}
    gaps = missing_for(["assemble"] if ready else ["assemble", "remix"], sys.executable, args.demucs_python)
    if gaps:
        names = sorted({name for names in gaps.values() for name in names})
        raise ProjectError("POST_DEPENDENCY_MISSING", json.dumps(
            {"missing": gaps, "next": {name: HINTS.get(name, "see scripts/check_post_deps.py") for name in names}}, ensure_ascii=False))
    root.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for command in commands:
        subprocess.run(command, check=True)
    sidecar = write_remix_sidecar(args.cut, args.output, config)
    return {"ok": True, "output": str(args.output), "sidecar": str(sidecar),
            "stems": str(stems), "stems_reused": ready}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes: 0 done; 1 config refused; 3 input or ffmpeg error; 4 dependency missing.")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--cut", required=True, type=Path, help="the assembled cut")
    parser.add_argument("--config", required=True, type=Path, help="the project's mix config JSON")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--stems-dir", type=Path, help="where separated stems live; default: <project>/stems")
    parser.add_argument("--demucs-python", default=os.environ.get("DEMUCS_PY") or sys.executable,
                        help="interpreter that has demucs; default: $DEMUCS_PY or this one")
    parser.add_argument("--dry-run", action="store_true", help="print the commands; run nothing")
    args = parser.parse_args(argv)
    try:
        result = remix(args)
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return {"INPUT_ERROR": EXIT_INPUT, "POST_DEPENDENCY_MISSING": EXIT_DEPENDENCY}.get(exc.code, EXIT_REFUSED)
    except subprocess.CalledProcessError as exc:
        print(json.dumps({"ok": False, "errors": [f"COMMAND_FAILED:{shlex.join(map(str, exc.cmd[:3]))}:{exc.returncode}"]}, indent=2))
        return EXIT_INPUT
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
