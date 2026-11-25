#!/usr/bin/env python3
"""Takeover audit: what another session or host left behind, before anything is regenerated.

Read-only on the project and offline: it never submits and never contacts a provider. It does
the four takeover duties and prints one report:
  1. beats: the script's beat ids; an unnumbered script can be written out as a numbered copy
     whose words are byte-identical (ids are only inserted after the action marker);
  2. mapping: which shots cover which beat, and the beats nothing covers;
  3. clips: an ffprobe inventory of the clips on disk. A clip's status comes only from a
     verdict recorded against that file in a given ledger: reuse_candidate (accepted),
     rejected, or pending_acceptance (no verdict); unreadable clips are redo, clips that match
     no active shot are orphan. File names are never read for meaning. A shot with several
     clips is listed under shot_choices: the user picks one, the audit never does;
  4. records: submissions recorded without any job ID, listed for the user. They are never
     resubmitted from here.
A ledger with no recognisable submission record, or a verdict word it does not know, is an
error rather than a guess. Every clip, reuse candidates included, enters takes[] only through
`ledger_submit.py reuse` and then per-shot acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from check_script_coverage import BEAT_RE, check_spec_coverage, parse_script
from drama_project import VIDEO_SUFFIXES, ProjectError, nonempty, read_json
from validate_shot_spec import active_shots, shot_beats, shot_rows

ACTION_MARK = "△"
INSERTED_ID_RE = re.compile(r"(?m)^(\s*△\s*)\[[A-Za-z][A-Za-z0-9_-]*\] ")
STATE_KEYS = ("job_state", "status", "state", "final_status")
# Keys that hold a human acceptance verdict, and the words accepted for each side. `status` only
# counts when it carries the ledger's own approved/rejected words; elsewhere it is a job state.
VERDICT_KEYS = ("qc", "verdict", "acceptance", "review")
ACCEPTED_WORDS = frozenset({"approved", "accepted", "accept", "pass", "passed", "ok", "通过"})
REJECTED_WORDS = frozenset({"rejected", "reject", "fail", "failed", "判废", "拒收"})
STATUS_VERDICTS = {"approved": "accepted", "rejected": "rejected"}
VERDICT_WORD_RE = re.compile(r"\s*([^\s:：,，;；()（）]+)")
EXIT_OK, EXIT_INPUT, EXIT_DEPENDENCY = 0, 3, 4
SCRIPT_SUFFIXES = frozenset({".py", ".sh", ".zsh", ".bash", ".mjs", ".js"})
SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules", ".venv", "venv"})
SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent
BYPASS_RULES: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = (
    ("xyq", re.compile(r"\bpippit-tool-cli\b"),
     re.compile(r"\b(?:generate-video|generate-image|short-drama)\b")),
    ("lovart", re.compile(r"\bagent_skill(?:\.py)?\b|lgw\.lovart\.ai"),
     re.compile(r"generate_video_|\.send\(|['\"]chat['\"]|--include-tools|--prefer-models")),
    ("higgsfield", re.compile(r"\bhiggsfield\b|\bhf_cli\b|platform\.higgsfield\.ai"),
     re.compile(r"['\"]generate['\"]|/generations\b|\bseedance[_-]")),
    ("atlas", re.compile(r"api\.atlascloud\.ai"),
     re.compile(r"generateVideo|/predictions\b")),
    ("elevenlabs", re.compile(r"api\.elevenlabs\.io|\belevenlabs\b"),
     re.compile(r"text-to-speech|sound-generation")),
)


def number_beats(text: str) -> tuple[str, int]:
    """Insert beat ids after unnumbered action markers; every other byte stays as it is."""
    used = set(parse_script(text)[0])
    scene, beat, added, out = 1, 0, 0, []
    seen_action = False
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            scene, beat, seen_action = (scene + 1 if seen_action else scene), 0, False
        elif stripped.startswith(ACTION_MARK):
            seen_action = True
            if not BEAT_RE.match(stripped.strip()):
                beat += 1
                while f"S{scene}-B{beat}" in used:
                    beat += 1
                used.add(f"S{scene}-B{beat}")
                head = line[:len(line) - len(stripped)] + ACTION_MARK
                rest = stripped[len(ACTION_MARK):]
                gap = rest[:len(rest) - len(rest.lstrip(" \t"))]
                line = f"{head}{gap}[S{scene}-B{beat}] {rest[len(gap):]}"
                added += 1
        out.append(line)
    return "".join(out), added


def audit_script(text: str, numbered_out: Path | None) -> dict[str, Any]:
    beats, lines, errors = parse_script(text)
    unnumbered = sum(1 for raw in text.splitlines()
                     if raw.strip().startswith(ACTION_MARK) and not BEAT_RE.match(raw.strip()))
    report: dict[str, Any] = {"beats": beats, "dialogue_lines": len(lines), "unnumbered_action_lines": unnumbered,
                              "format_errors": errors}
    if numbered_out is not None and unnumbered:
        numbered, added = number_beats(text)
        if INSERTED_ID_RE.sub(r"\1", numbered).replace("\r\n", "\n") == text.replace("\r\n", "\n") and not beats:
            numbered_out.write_text(numbered, encoding="utf-8")
            report.update(numbered_copy=str(numbered_out), beats_added=added)
        else:
            report["numbering_refused"] = "TEXT_WOULD_CHANGE_OR_PARTLY_NUMBERED: number the remaining beats by hand"
    return report


def audit_mapping(script_text: str, spec: dict[str, Any]) -> dict[str, Any]:
    beats = parse_script(script_text)[0]
    rows = active_shots(shot_rows(spec))
    covered = {beat: [shot["id"] for shot in rows if beat in shot_beats(shot, beats)] for beat in beats}
    result = check_spec_coverage(script_text, spec)
    return {"beat_to_shots": covered, "missing_beats": [beat for beat, shots in covered.items() if not shots],
            "coverage_errors": result["errors"]}


def probe(path: Path) -> dict[str, Any]:
    """Container facts from ffprobe; `error` is set when the file cannot be read as video."""
    from media_inspection import probe as media_probe
    try:
        facts = media_probe(path)
    except ProjectError:
        return {"error": "UNREADABLE_OR_NO_VIDEO_STREAM"}
    if not facts["video_streams"]:
        return {"error": "UNREADABLE_OR_NO_VIDEO_STREAM"}
    return {"duration_s": round(facts["duration"], 3), "width": facts["width"],
            "height": facts["height"], "has_audio": bool(facts["audio_streams"])}


def verdict_word(value: Any) -> str | None:
    """The leading word of a verdict, lower-cased; a dict verdict reads its result or verdict."""
    if isinstance(value, dict):
        value = value.get("result", value.get("verdict"))
    if not nonempty(value):
        return None
    match = VERDICT_WORD_RE.match(value)
    return match.group(1).lower() if match else None


def record_verdict(payload: dict[str, Any], trail: str) -> tuple[str | None, str | None]:
    """(verdict, key) recorded on one submission; an unknown verdict word is an error."""
    for key in VERDICT_KEYS:
        word = verdict_word(payload.get(key))
        if word is None:
            continue
        if word in ACCEPTED_WORDS:
            return "accepted", key
        if word in REJECTED_WORDS:
            return "rejected", key
        raise ProjectError("UNRECOGNIZED_VERDICT", f"{trail or '(root)'}/{key}={payload.get(key)!r}")
    status = STATUS_VERDICTS.get(str(payload.get("status")))
    return (status, "status") if status else (None, None)


def foreign_records(payload: Any, trail: str = "") -> list[dict[str, Any]]:
    """Every object in a foreign ledger that looks like a submission: it carries a state or a file."""
    found: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        if any(nonempty(payload.get(key)) for key in (*STATE_KEYS, "file")):
            ids = sorted(key for key, value in payload.items()
                         if (key == "id" or key.endswith("_id") or key == "job_ids") and value not in (None, "", {}, []))
            state = next((payload[key] for key in STATE_KEYS if nonempty(payload.get(key))), None)
            verdict, source = record_verdict(payload, trail)
            values = {key: str(payload[key]) for key in ids if isinstance(payload[key], (str, int))}
            found.append({"record": trail or "(root)", "state": state, "id_fields": ids, "ids": values,
                          "file": Path(payload["file"]).name if nonempty(payload.get("file")) else None,
                          "verdict": verdict, "verdict_source": source})
        for key, value in payload.items():
            found.extend(foreign_records(value, f"{trail}/{key}" if trail else str(key)))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            found.extend(foreign_records(value, f"{trail}[{index}]"))
    return found


def ledger_records(path: Path) -> list[dict[str, Any]]:
    """Submission records of one ledger file; a structure with none is refused, not guessed."""
    records = foreign_records(read_json(path))
    if not records:
        raise ProjectError("UNRECOGNIZED_LEDGER",
                           f"{path.name}: no object carries a state or a file; describe its records to the user")
    return records


def match_shot(stem: str, shot_ids: list[str]) -> str | None:
    """The longest shot id the clip name starts with."""
    hits = [shot_id for shot_id in shot_ids if stem == shot_id or stem.startswith(shot_id + "_")]
    return max(hits, key=len, default=None)


def clip_status(facts: dict[str, Any], shot_id: str | None, verdicts: set[str]) -> str:
    if "error" in facts:
        return "redo"
    if shot_id is None:
        return "orphan"
    if "rejected" in verdicts:
        return "rejected"
    return "reuse_candidate" if "accepted" in verdicts else "pending_acceptance"


def shot_choices(per_shot: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Shots with more than one usable clip: each clip is listed and the user picks one."""
    choices = {}
    for shot_id, clips in per_shot.items():
        if len(clips) > 1:
            for row in clips:
                row["notes"].append("MULTIPLE_CLIPS_FOR_SHOT")
            choices[shot_id] = {"clips": [{"file": row["file"], "status": row["status"]} for row in clips],
                                "action": "The user picks one clip; write it as `reuse` on this shot in the spec."}
    return choices


def audit_clips(clips_dir: Path, spec: dict[str, Any] | None, records: list[dict[str, Any]]) -> dict[str, Any]:
    if shutil.which("ffprobe") is None:
        raise ProjectError("FFPROBE_MISSING", "install ffmpeg; the clip inventory is not guessed")
    shots = active_shots(shot_rows(spec)) if spec else []
    post = set(spec.get("post_beats") or []) if spec else set()
    ids = [shot["id"] for shot in shots]
    with_id = {row["file"] for row in records if row["file"] and row["id_fields"]}
    rows, per_shot = [], {}
    paths = sorted(item for item in clips_dir.iterdir() if item.is_file() and item.suffix.lower() in VIDEO_SUFFIXES)
    for path in paths:
        facts, shot_id = probe(path), match_shot(path.stem, ids)
        verdicts = {row["verdict"] for row in records if row["file"] == path.name and row["verdict"]}
        status = clip_status(facts, shot_id, verdicts)
        notes = [] if path.name in with_id else ["NO_SUBMISSION_RECORD_WITH_ID"]
        recorded = {key: value for row in records if row["file"] == path.name for key, value in row["ids"].items()}
        rows.append({"file": path.name, "shot": shot_id, "status": status, **facts, "recorded_ids": recorded,
                     "notes": notes})
        if status in ("reuse_candidate", "pending_acceptance"):
            per_shot.setdefault(shot_id, []).append(rows[-1])
    on_disk = {path.name for path in paths}
    missing = [shot["id"] for shot in shots if shot["id"] not in per_shot and not set(shot_beats(shot, [])) & post]
    return {"clips": rows, "shot_choices": shot_choices(per_shot), "missing_shots": missing,
            "records_file_not_on_disk": [{"record": row["record"], "file": row["file"], "verdict": row["verdict"]}
                                         for row in records if row["file"] and row["file"] not in on_disk]}


def resolve_scan_root(args: argparse.Namespace) -> Path | None:
    if args.project is not None:
        root = args.project.expanduser().resolve()
        if not root.is_dir():
            raise ProjectError("INPUT_ERROR", f"not a directory: {args.project}")
        return root
    if args.spec is not None:
        return args.spec.expanduser().resolve().parent
    if args.clips_dir is not None:
        return args.clips_dir.expanduser().resolve().parent
    parent = args.script.expanduser().resolve().parent
    sys_tmp = {Path("/tmp").resolve(), Path(tempfile.gettempdir()).resolve()}
    return None if parent in sys_tmp else parent


def iter_script_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in sorted(dirs) if d not in SKIP_DIRS]
        folder = Path(dirpath).resolve()
        if folder == SKILL_SCRIPTS_DIR or SKILL_SCRIPTS_DIR in folder.parents:
            continue
        for name in sorted(files):
            candidate = Path(dirpath) / name
            if candidate.suffix.lower() in SCRIPT_SUFFIXES:
                found.append(candidate)
    return found


def file_bypass_hits(path: Path, root: Path) -> list[dict[str, Any]]:
    try:
        raw_text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    active = [(idx, line) for idx, line in enumerate(raw_text.splitlines(), 1)
              if not line.lstrip().startswith("#") and "--help" not in line]
    code_body = "\n".join(line for _, line in active)
    if "ledger_submit.py" in code_body:
        return []
    rel = str(path.relative_to(root))
    hits: list[dict[str, Any]] = []
    for provider, tool_re, action_re in BYPASS_RULES:
        if not tool_re.search(code_body):
            continue
        hit = next(((idx, line.strip()) for idx, line in active if action_re.search(line)), None)
        if hit is not None:
            hits.append({"file": rel, "line": hit[0], "provider": provider, "match": hit[1][:120]})
    return hits


def scan_bypass_scripts(root: Path | None) -> list[dict[str, Any]]:
    if root is None or not root.is_dir():
        return []
    return [hit for path in iter_script_files(root) for hit in file_bypass_hits(path, root)]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    script_text = args.script.expanduser().read_text(encoding="utf-8")
    spec = read_json(args.spec.expanduser()) if args.spec else None
    records = [row for path in args.records for row in ledger_records(path.expanduser())]
    bypass = scan_bypass_scripts(resolve_scan_root(args))
    report: dict[str, Any] = {"script": audit_script(script_text, args.numbered_out)}
    if spec is not None:
        report["mapping"] = audit_mapping(script_text, spec)
    if args.clips_dir:
        if not args.clips_dir.expanduser().is_dir():
            raise ProjectError("INPUT_ERROR", f"not a directory: {args.clips_dir}")
        report.update(audit_clips(args.clips_dir.expanduser(), spec, records))
    report["records_without_id"] = [row for row in records if not row["id_fields"]]
    report["records_seen"] = len(records)
    report["bypass_scripts"] = bypass
    report["warnings"] = [f"BYPASS_PROVIDER_SCRIPT:{row['file']}:{row['line']}:{row['provider']}" for row in bypass]
    report["rules"] = ["The script is locked input: number it, never rewrite it.",
                       "Nothing is regenerated or resubmitted by this audit.",
                       "Show records_without_id to the user; recover them from the provider's own history.",
                       "A clip's status comes only from a recorded verdict; pending_acceptance is not reusable yet.",
                       "Never reuse a rejected clip. Where shot_choices lists several clips, the user picks one.",
                       "Write the chosen clip as `reuse` and its recorded_ids as `reuse_job_ids` on the spec shot "
                       "(add `reuse_tiers` when later tiers are still to be generated).",
                       "Enter the chosen clip with `ledger_submit.py reuse`, then run all four acceptance checks."]
    return report


def main(argv: list[str] | None = None) -> int:
    args_in = sys.argv[1:] if argv is None else argv
    if args_in[:1] == ["reconcile"]:
        from project_inventory import reconcile_cli
        return reconcile_cli(args_in[1:])
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes: 0 report printed; 3 file or JSON error; 4 ffprobe missing.")
    parser.add_argument("--script", required=True, type=Path, help="the script as the user brought it")
    parser.add_argument("--project", type=Path, help="project root directory to scan for bypass scripts")
    parser.add_argument("--spec", type=Path, help="existing shot spec, if any")
    parser.add_argument("--clips-dir", type=Path, help="directory of clips already generated")
    parser.add_argument("--records", action="append", default=[], type=Path,
                        help="a ledger or log JSON left by the earlier session (repeatable)")
    parser.add_argument("--numbered-out", type=Path, help="write a beat-numbered copy of an unnumbered script here")
    args = parser.parse_args(argv)
    try:
        report = build_report(args)
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return EXIT_DEPENDENCY if exc.code == "FFPROBE_MISSING" else EXIT_INPUT
    except OSError as exc:
        print(json.dumps({"ok": False, "errors": [f"INPUT_ERROR:{type(exc).__name__}"]}, indent=2))
        return EXIT_INPUT
    print(json.dumps({"ok": True, **report}, ensure_ascii=False, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
