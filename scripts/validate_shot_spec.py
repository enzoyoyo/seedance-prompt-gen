#!/usr/bin/env python3
"""Validate a shot spec: the one file that drives paid submissions for an AI short drama.

The spec is a thin projection of the NBP v2 contract (see references/shot-spec.md). Only
invariants are checked: reference files exist and are declared at the start of the prompt,
durations fit the channel limit recorded in the project's capability card, and a retake names
what it replaces and changes exactly one variable. Shot count, shot length and wording are
never prescribed here.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from drama_project import (
    TIERS, ProjectError, drama_block, load_manifest, nonempty, parse_day, read_json, section,
)
from shot_invariants import (
    check_actors_and_headcount, check_props_continuity, check_props_state, mentions_screen_or_ui,
)

DEFAULT_SPEC_NAME = "shots.json"
SHOT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
# Ways a prompt can point at the Nth reference image; the group is the 1-based index.
IMAGE_INDEX_RE = re.compile(r"(?:\bimage\s*|@image|图(?:片|像)?\s*|@图)(\d+)", re.IGNORECASE)
SENTENCE_END_RE = re.compile(r"[.。!?！？\n]")
BEAT_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
SCREEN_UI_MODES = frozenset({"none", "clean_plate_post_replace"})


def positive_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and value > 0


def shot_rows(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Shots in file order with `id` filled in; accepts a dict keyed by id or a list."""
    shots = spec.get("shots")
    if isinstance(shots, dict):
        return [{**row, "id": key} for key, row in shots.items() if isinstance(row, dict)]
    if isinstance(shots, list):
        return [row for row in shots if isinstance(row, dict)]
    return []


def superseded_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {row["supersedes"] for row in rows if nonempty(row.get("supersedes"))}


def active_shots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shots that are still meant to be in the cut: not replaced by a retake entry."""
    replaced = superseded_ids(rows)
    return [row for row in rows if row.get("id") not in replaced]


def root_id(rows: list[dict[str, Any]], shot_id: str) -> str:
    """Follow `supersedes` back to the original shot; retakes keep the original's place."""
    by_id = {row.get("id"): row for row in rows}
    seen, current = set(), shot_id
    while current in by_id and nonempty(by_id[current].get("supersedes")) and current not in seen:
        seen.add(current)
        current = by_id[current]["supersedes"]
    return current


def shot_beats(shot: dict[str, Any], known_beats: list[str]) -> list[str]:
    """Script beat IDs a shot covers: explicit `beats` list, else IDs found in the `beat` text."""
    explicit = shot.get("beats")
    if isinstance(explicit, list):
        return [item for item in explicit if nonempty(item)]
    text = shot.get("beat")
    if not nonempty(text):
        return []
    known = set(known_beats)
    return [token for token in BEAT_TOKEN_RE.findall(text) if token in known]


def channel_of(spec: dict[str, Any], shot: dict[str, Any]) -> str | None:
    name = shot.get("channel") or spec.get("channel")
    return name if nonempty(name) else None


def model_of(spec: dict[str, Any], shot: dict[str, Any]) -> str | None:
    name = shot.get("model") or spec.get("model")
    return name if nonempty(name) else None


def is_reuse(shot: dict[str, Any], tier: str | None = None) -> bool:
    """Whether the shot uses an existing clip instead of a generation.

    `reuse_tiers` limits the clip to those tiers (a taken-over draft, say); the other tiers are
    generated. Without a tier the question is "is this shot never generated at all".
    """
    if not nonempty(shot.get("reuse")):
        return False
    scoped = shot.get("reuse_tiers")
    if scoped is None:
        return True
    return tier is not None and isinstance(scoped, list) and tier in scoped


def ref_search_dirs(spec: dict[str, Any], spec_dir: Path) -> list[Path]:
    """Episode first, then the series level above it, so a second episode inherits identity refs."""
    dirs = [spec_dir / "refs", spec_dir, spec_dir.parent / "refs", spec_dir.parent]
    inherits = spec.get("inherits")
    if nonempty(inherits):
        parent = (spec_dir / inherits).resolve().parent
        dirs += [parent / "refs", parent]
    return dirs


def resolve_ref(spec: dict[str, Any], spec_dir: Path, name: str) -> Path | None:
    table = spec.get("refs")
    entry = table.get(name) if isinstance(table, dict) else None
    declared = entry.get("path") if isinstance(entry, dict) else None
    candidates = [spec_dir / declared] if nonempty(declared) else []
    candidates += [folder / name for folder in ref_search_dirs(spec, spec_dir)]
    return next((path.resolve() for path in candidates if path.is_file()), None)


def inherited_text(spec: dict[str, Any], spec_dir: Path, field: str) -> str:
    """A film-level text field, falling back to the series file named by `inherits`."""
    value = spec.get(field)
    if nonempty(value):
        return value
    inherits = spec.get("inherits")
    if not nonempty(inherits):
        return ""
    parent = read_json((spec_dir / inherits).resolve())
    value = parent.get(field) if isinstance(parent, dict) else None
    return value if nonempty(value) else ""


def compose_prompt(spec: dict[str, Any], spec_dir: Path, shot: dict[str, Any]) -> str:
    """The exact text an adapter receives: shot prompt followed by the film-level style suffix."""
    parts = [shot.get("prompt", "").strip(), inherited_text(spec, spec_dir, "style_suffix").strip()]
    return " ".join(part for part in parts if part)


def ref_mentioned(prompt: str, index: int, name: str, spec: dict[str, Any]) -> bool:
    if any(int(found) == index for found in IMAGE_INDEX_RE.findall(prompt)):
        return True
    table = spec.get("refs")
    entry = table.get(name) if isinstance(table, dict) else None
    labels = [Path(name).stem] + ([entry["role"]] if isinstance(entry, dict) and nonempty(entry.get("role")) else [])
    return any(label.casefold() in prompt.casefold() for label in labels)


def check_refs(spec: dict[str, Any], spec_dir: Path, shot: dict[str, Any]) -> list[str]:
    sid, refs, prompt = shot["id"], shot.get("refs", []), shot.get("prompt", "")
    if not isinstance(refs, list) or any(not nonempty(item) for item in refs):
        return [f"INVALID_REFS:{sid}"]
    errors = [f"REF_FILE_MISSING:{sid}:{name}" for name in refs if resolve_ref(spec, spec_dir, name) is None]
    if not refs or not nonempty(prompt):
        return errors
    opening = SENTENCE_END_RE.split(prompt.strip(), maxsplit=1)[0]
    if not any(ref_mentioned(opening, index, name, spec) for index, name in enumerate(refs, start=1)):
        errors.append(f"REF_ROLES_NOT_AT_PROMPT_START:{sid}")
    for index, name in enumerate(refs, start=1):
        if not ref_mentioned(prompt, index, name, spec):
            errors.append(f"REF_ROLE_NOT_DECLARED:{sid}:{index}:{name}")
    extra = sorted({int(found) for found in IMAGE_INDEX_RE.findall(prompt)} - set(range(1, len(refs) + 1)))
    errors.extend(f"PROMPT_MENTIONS_UNDECLARED_IMAGE:{sid}:{index}" for index in extra)
    return errors


def card_limit(card: object, name: str, today: date) -> tuple[float | None, list[str]]:
    """Max single-shot duration from the channel's capability card, never from memory."""
    if not isinstance(card, dict):
        return None, [f"CHANNEL_CARD_MISSING:{name}"]
    expires = parse_day(card.get("expires_at"))
    if expires is None or today > expires:
        return None, [f"CHANNEL_CARD_EXPIRED:{name}"]
    limit = section(section(card, "limits"), "max_duration_s")
    if not positive_number(limit.get("value")) or parse_day(limit.get("verified_at")) is None:
        return None, [f"CHANNEL_LIMIT_MISSING:{name}:max_duration_s"]
    return float(limit["value"]), []


def check_durations(spec: dict[str, Any], rows: list[dict[str, Any]],
                    channels: dict[str, Any], today: date) -> list[str]:
    errors: list[str] = []
    limits: dict[str, float | None] = {}
    for shot in rows:
        if is_reuse(shot):
            continue
        sid, name = shot["id"], channel_of(spec, shot)
        if name is None:
            errors.append(f"SHOT_WITHOUT_CHANNEL:{sid}")
            continue
        if name not in limits:
            limits[name], card_errors = card_limit(channels.get(name), name, today)
            errors.extend(card_errors)
        limit = limits[name]
        if limit is not None and positive_number(shot.get("duration")) and shot["duration"] > limit:
            errors.append(f"DURATION_OVER_LIMIT:{sid}:{shot['duration']}>{limit:g}")
    return errors


def check_retakes(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    ids = {row["id"] for row in rows}
    targets: dict[str, list[str]] = {}
    for shot in rows:
        target = shot.get("supersedes")
        if target is None:
            continue
        sid = shot["id"]
        if not nonempty(target) or target not in ids or target == sid:
            errors.append(f"UNKNOWN_SUPERSEDED_SHOT:{sid}:{target}")
            continue
        targets.setdefault(target, []).append(sid)
        changed = shot.get("changed_variables")
        count = len(changed) if isinstance(changed, list) and all(nonempty(item) for item in changed) else 0
        if count != 1:
            errors.append(f"RETAKE_CHANGED_VARIABLES_NOT_ONE:{sid}:{count}")
    errors.extend(f"SUPERSEDED_TWICE:{target}:{','.join(sorted(by))}"
                  for target, by in sorted(targets.items()) if len(by) > 1)
    return errors


def check_spatial_and_ui(spec_dir: Path, shot: dict[str, Any]) -> list[str]:
    sid = shot["id"]
    generated = not is_reuse(shot)
    errors: list[str] = []
    if "actor_count" in shot:
        count = shot["actor_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            errors.append(f"INVALID_ACTOR_COUNT:{sid}")
    errors += check_actors_and_headcount(shot, generated)
    if "previs_ref" in shot:
        rel = shot["previs_ref"]
        if not nonempty(rel) or not str(rel).replace("\\", "/").startswith("00_previs/"):
            errors.append(f"PREVIS_REF_OUTSIDE_00_PREVIS:{sid}")
        elif not (spec_dir / str(rel)).is_file():
            errors.append(f"PREVIS_REF_MISSING:{sid}:{rel}")
    if "screen_ui" in shot and shot["screen_ui"] not in SCREEN_UI_MODES:
        errors.append(f"RAW_SCREEN_UI_FORBIDDEN:{sid}")
    elif generated and "screen_ui" not in shot and mentions_screen_or_ui(shot):
        errors.append(f"SCREEN_UI_REQUIRED:{sid}")
    errors += check_props_state(shot)
    return errors


def check_shot(spec: dict[str, Any], spec_dir: Path, shot: dict[str, Any]) -> list[str]:
    sid = shot["id"]
    errors: list[str] = []
    if not nonempty(shot.get("beat")) and not shot.get("beats"):
        errors.append(f"SHOT_WITHOUT_BEAT:{sid}")
    line = shot.get("line", "")
    if not isinstance(line, (str, list)) or (isinstance(line, list) and any(not nonempty(x) for x in line)):
        errors.append(f"INVALID_LINE:{sid}")
    if nonempty(shot.get("reuse")) and not (spec_dir / shot["reuse"]).is_file():
        errors.append(f"REUSE_FILE_MISSING:{sid}:{shot['reuse']}")
    scoped = shot.get("reuse_tiers")
    if scoped is not None and (not isinstance(scoped, list) or not scoped or not set(scoped) <= set(TIERS)):
        errors.append(f"INVALID_REUSE_TIERS:{sid}")
    errors.extend(check_spatial_and_ui(spec_dir, shot))
    if is_reuse(shot):
        return errors
    if not nonempty(shot.get("prompt")):
        errors.append(f"SHOT_WITHOUT_PROMPT:{sid}")
    if not positive_number(shot.get("duration")):
        errors.append(f"INVALID_DURATION:{sid}")
    return errors + check_refs(spec, spec_dir, shot)


def validate_spec(spec: object, spec_dir: Path, channels: dict[str, Any], today: date) -> list[str]:
    """Invariant errors for one spec; an empty list means it may drive submissions."""
    if not isinstance(spec, dict):
        return ["SPEC_NOT_AN_OBJECT"]
    rows = shot_rows(spec)
    if not rows:
        return ["SPEC_SHOTS_EMPTY"]
    errors: list[str] = []
    seen: set[str] = set()
    valid: list[dict[str, Any]] = []
    for index, shot in enumerate(rows):
        sid = shot.get("id")
        if not isinstance(sid, str) or not SHOT_ID_RE.fullmatch(sid):
            errors.append(f"SHOT_ID_INVALID:{index}")
        elif sid in seen:
            errors.append(f"DUPLICATE_SHOT_ID:{sid}")
        else:
            seen.add(sid)
            valid.append(shot)
    for field in ("style_suffix", "identity_note"):
        if field in spec and not isinstance(spec[field], str):
            errors.append(f"INVALID_FILM_FIELD:{field}")
    post = spec.get("post_beats", [])
    if not isinstance(post, list) or any(not nonempty(item) for item in post):
        errors.append("INVALID_POST_BEATS")
    for shot in valid:
        errors.extend(check_shot(spec, spec_dir, shot))
    active = active_shots(valid)
    return (errors + check_retakes(valid) + check_durations(spec, active, channels, today)
            + check_props_continuity(active))


def load_project_spec(project: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    """Spec, its directory and the manifest that names it."""
    manifest = load_manifest(project)
    relative = drama_block(manifest).get("shot_spec") or DEFAULT_SPEC_NAME
    path = (project / relative).resolve()
    if not path.is_file():
        raise ProjectError("SHOT_SPEC_MISSING", str(relative))
    spec = read_json(path)
    if not isinstance(spec, dict):
        raise ProjectError("INPUT_ERROR", f"{path.name}:not an object")
    return spec, path.parent, manifest


def project_spec_errors(project: Path, today: date) -> tuple[dict[str, Any], list[str]]:
    from ledger_submit import Context, spec_errors
    from lock_script import locked_script_text, verify_lock

    spec, spec_dir, manifest = load_project_spec(project)
    if not verify_lock(project):
        return spec, spec_errors(Context(project, manifest, spec, spec_dir), locked_script_text(project), today)
    channels = section(drama_block(manifest), "channels")
    return spec, validate_spec(spec, spec_dir, channels if isinstance(channels, dict) else {}, today)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Exit codes: 0 valid; 1 invariant errors; 3 file or JSON error.",
    )
    parser.add_argument("--project", type=Path, help="project directory (spec and channel cards from its manifest)")
    parser.add_argument("--spec", type=Path, help="spec file, when validating outside a project")
    parser.add_argument("--channels", type=Path, help="JSON object of channel capability cards, with --spec")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD, for card expiry")
    args = parser.parse_args(argv)
    try:
        if args.project:
            spec, errors = project_spec_errors(args.project.expanduser(), args.today)
        elif args.spec:
            spec_path = args.spec.expanduser().resolve()
            spec, spec_dir = read_json(spec_path), spec_path.parent
            channels = read_json(args.channels.expanduser()) if args.channels else {}
            errors = validate_spec(spec, spec_dir, channels if isinstance(channels, dict) else {}, args.today)
        else:
            parser.error("give --project or --spec")
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 3 if exc.code == "INPUT_ERROR" else 1
    shots = len(shot_rows(spec)) if isinstance(spec, dict) else 0
    print(json.dumps({"ok": not errors, "errors": errors, "shots": shots}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
