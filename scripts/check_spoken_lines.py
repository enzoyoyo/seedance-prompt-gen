#!/usr/bin/env python3
"""Per-shot acceptance, check 1 of 4: does the clip speak the line the shot spec asks for?

The clip is transcribed (a cached transcript is reused when present, otherwise the ASR command
is run) and compared with the spec line word by word. It catches a clip with no speech, a line
cut off before the shot ends, and a clip that speaks another shot's line. The report it writes
is the only accepted evidence for the `lines` check in ledger_submit.py accept.

ASR mishears names and numbers, so the comparison tolerates a share of unmatched words
(--min-coverage); it is a tolerance for transcription noise, not a creative setting.

A fresh transcription needs an explicit model (--asr-model or $ASR_MODEL): without one the ASR
command may start downloading its default model unannounced. The error lists the models already
in the local cache, so the choice never costs a download.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

from check_script_coverage import SEGMENT_LABEL_RE, spec_segments
from drama_ledger import find_take
from drama_project import ProjectError, read_json, resolve_in_project, sha256_file, write_json_atomic
from validate_shot_spec import active_shots, load_project_spec, shot_rows

TOOL_NAME = "check_spoken_lines"
EXIT_OK, EXIT_MISMATCH, EXIT_INPUT, EXIT_DEPENDENCY = 0, 1, 3, 4
QC_DIR = "qc"


def is_ideograph(char: str) -> bool:
    return unicodedata.category(char) == "Lo"


def words(text: str) -> list[str]:
    """Comparable tokens: letter/digit runs, with unspaced scripts split per character."""
    tokens: list[str] = []
    run = ""
    for char in unicodedata.normalize("NFKC", text).casefold():
        if char.isalnum() and not is_ideograph(char):
            run += char
            continue
        if run:
            tokens.append(run)
            run = ""
        if is_ideograph(char):
            tokens.append(char)
    return tokens + ([run] if run else [])


def common_in_order(expected: list[str], heard: list[str]) -> int:
    """Length of the longest common subsequence: expected words heard in the right order."""
    previous = [0] * (len(heard) + 1)
    for token in expected:
        current = [0]
        for index, other in enumerate(heard, start=1):
            current.append(previous[index - 1] + 1 if token == other else max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def coverage(expected: list[str], heard: list[str]) -> float:
    return common_in_order(expected, heard) / len(expected) if expected else 1.0


def spoken_text(segment: str) -> str:
    return SEGMENT_LABEL_RE.sub("", segment, count=1)


def best_other_shot(heard: list[str], others: dict[str, list[str]], minimum: float) -> str | None:
    """Another shot whose line the clip speaks instead, if any reaches the tolerance."""
    scored = [(coverage(tokens, heard), shot_id) for shot_id, tokens in others.items() if tokens]
    best = max(scored, default=(0.0, None))
    return best[1] if best[0] >= minimum else None


def compare(expected: list[str], heard_text: str, others: dict[str, list[str]],
            minimum: float) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Per-segment coverage, errors and warnings for one clip."""
    heard = words(heard_text)
    rows = [{"segment": segment, "coverage": round(coverage(words(spoken_text(segment)), heard), 3)}
            for segment in expected]
    if not expected:
        return rows, [], (["SPEECH_IN_A_SHOT_WITHOUT_LINES"] if heard else [])
    if not heard:
        return rows, ["NO_SPEECH"], []
    errors = [f"LINE_INCOMPLETE:{row['segment']}" for row in rows if row["coverage"] < minimum]
    if errors:
        other = best_other_shot(heard, others, minimum)
        if other is not None:
            errors.append(f"WRONG_BEAT_LINE:{other}")
    return rows, errors, []


def transcript_text(payload: object) -> str:
    """Text of a transcript JSON: a `text` field, or the joined text of its `segments`."""
    if isinstance(payload, dict) and isinstance(payload.get("text"), str):
        return payload["text"]
    segments = payload.get("segments") if isinstance(payload, dict) else payload
    if isinstance(segments, list) and all(isinstance(row, dict) for row in segments):
        return " ".join(str(row.get("text", "")) for row in segments)
    raise ProjectError("INPUT_ERROR", "transcript JSON has neither `text` nor `segments`")


def cached_asr_models() -> list[str]:
    """Model files the local whisper-style ASR already has, so choosing one downloads nothing."""
    root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "whisper"
    return sorted(path.stem for path in root.glob("*.pt")) if root.is_dir() else []


def asr_model_args(model: str | None, extra: list[str]) -> list[str]:
    """`--model <name>` for the ASR command; refuses to run without an explicit choice."""
    if "--model" in extra:
        return []
    if model:
        return ["--model", model]
    cached = cached_asr_models()
    raise ProjectError("ASR_MODEL_NOT_CHOSEN",
                       "pass --asr-model <name> or set ASR_MODEL; models already on disk: "
                       + (", ".join(cached) or "none (choosing any model will download it; ask the user first)"))


def require_asr(binary: str) -> None:
    if shutil.which(binary) is None:
        raise ProjectError("ASR_DEPENDENCY_MISSING",
                           f"{binary}: not on PATH; put the ASR command on PATH or pass --asr-bin <path>, "
                           "or supply an existing transcript with --asr-json / --asr-dir")


def run_asr_json(clip: Path, binary: str, extra: list[str], keep_in: Path | None = None) -> Any:
    """Transcribe with the local ASR command; fails loudly when it is not installed."""
    require_asr(binary)
    with tempfile.TemporaryDirectory() as scratch:
        out_dir = keep_in or Path(scratch)
        out_dir.mkdir(parents=True, exist_ok=True)
        command = [binary, str(clip), "--output_format", "json", "--output_dir", str(out_dir), *extra]
        done = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        produced = out_dir / f"{clip.stem}.json"
        if done.returncode != 0 or not produced.is_file():
            raise ProjectError("ASR_FAILED", f"{binary} exit {done.returncode}: {done.stderr.strip()[-300:]}")
        return read_json(produced)


def run_asr(clip: Path, binary: str, extra: list[str]) -> str:
    return transcript_text(run_asr_json(clip, binary, extra))


def heard_text(clip: Path, asr_json: Path | None, asr_dir: Path | None,
               binary: str, extra: list[str], model: str | None = None) -> tuple[str, str]:
    """Transcript text and where it came from: an explicit file, a cache directory, or a fresh run."""
    cached = asr_json or (asr_dir / f"{clip.stem}.json" if asr_dir else None)
    if cached is not None and cached.is_file():
        return transcript_text(read_json(cached)), f"cached:{cached.name}"
    if asr_json is not None:
        raise ProjectError("INPUT_ERROR", f"transcript not found: {asr_json}")
    require_asr(binary)
    return run_asr(clip, binary, [*asr_model_args(model, extra), *extra]), f"asr:{binary}"


def spec_lines(spec: dict[str, Any]) -> dict[str, list[str]]:
    return {shot["id"]: spec_segments(shot) for shot in active_shots(shot_rows(spec))}


def project_inputs(project: Path, take_id: str) -> tuple[Path, str, list[str], dict[str, list[str]]]:
    """Clip, spec id, expected segments and every other shot's words for one ledger take."""
    spec, _, manifest = load_project_spec(project)
    take = find_take(manifest, take_id)
    clip = resolve_in_project(project, take.get("file"))
    if clip is None or not clip.is_file():
        raise ProjectError("CLIP_FILE_MISSING", f"{take_id}:{take.get('file')}")
    rows = {shot.get("id"): shot for shot in shot_rows(spec)}
    shot = rows.get(take.get("spec_id"))
    if shot is None:
        raise ProjectError("UNKNOWN_SHOT", str(take.get("spec_id")))
    others = {shot_id: [token for segment in segments for token in words(spoken_text(segment))]
              for shot_id, segments in spec_lines(spec).items() if shot_id != shot["id"]}
    return clip, shot["id"], spec_segments(shot), others


def build_report(clip: Path, shot_id: str | None, expected: list[str], others: dict[str, list[str]],
                 heard: str, source: str, minimum: float) -> dict[str, Any]:
    rows, errors, warnings = compare(expected, heard, others, minimum)
    return {"tool": TOOL_NAME, "clip": clip.name, "clip_sha256": sha256_file(clip), "shot": shot_id,
            "expected": expected, "heard": heard.strip(), "transcript_source": source,
            "min_coverage": minimum, "coverage": rows, "ok": not errors, "errors": errors, "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes: 0 spoken as specified; 1 mismatch; 3 input error; 4 ASR dependency missing or failed.")
    parser.add_argument("--project", type=Path, help="project directory (with --take)")
    parser.add_argument("--take", help="ledger take id; the clip and expected line come from the ledger and spec")
    parser.add_argument("--clip", type=Path, help="clip file, when checking outside a project")
    parser.add_argument("--expected", action="append", default=[], help="expected spoken line (repeatable), with --clip")
    parser.add_argument("--asr-json", type=Path, help="existing transcript JSON for this clip")
    parser.add_argument("--asr-dir", type=Path, help="directory of cached transcripts named <clip stem>.json")
    parser.add_argument("--asr-bin", default="whisper", help="ASR command taking <clip> --output_format json --output_dir")
    parser.add_argument("--asr-model", default=os.environ.get("ASR_MODEL"),
                        help="ASR model for a fresh transcription; default $ASR_MODEL; required unless cached")
    parser.add_argument("--asr-arg", action="append", default=[], help="extra argument for the ASR command (repeatable)")
    parser.add_argument("--min-coverage", type=float, default=0.8, help="share of expected words that must be heard in order")
    parser.add_argument("--report", type=Path, help="where to write the report; default: <project>/qc/<clip stem>.lines.json")
    args = parser.parse_args(argv)
    try:
        if args.project and args.take:
            project = args.project.expanduser()
            clip, shot_id, expected, others = project_inputs(project, args.take)
            report_path = args.report or project / QC_DIR / f"{clip.stem}.lines.json"
        elif args.clip:
            clip, shot_id, expected, others = args.clip.expanduser(), None, args.expected, {}
            if not clip.is_file():
                raise ProjectError("CLIP_FILE_MISSING", str(clip))
            report_path = args.report
        else:
            parser.error("give --project with --take, or --clip")
        heard, source = heard_text(clip, args.asr_json, args.asr_dir, args.asr_bin, args.asr_arg, args.asr_model)
        report = {**build_report(clip, shot_id, expected, others, heard, source, args.min_coverage),
                  "asr_model": args.asr_model if source.startswith("asr:") else None}
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(report_path, report)
    except ProjectError as exc:
        print(json.dumps({"tool": TOOL_NAME, "ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return {"INPUT_ERROR": EXIT_INPUT, "ASR_DEPENDENCY_MISSING": EXIT_DEPENDENCY, "ASR_FAILED": EXIT_DEPENDENCY,
                "ASR_MODEL_NOT_CHOSEN": EXIT_DEPENDENCY}.get(exc.code, EXIT_MISMATCH)
    print(json.dumps({**report, "report": str(report_path) if report_path else None}, ensure_ascii=False, indent=2))
    return EXIT_OK if report["ok"] else EXIT_MISMATCH


if __name__ == "__main__":
    sys.exit(main())
