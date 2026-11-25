#!/usr/bin/env python3
"""Lock the user-approved script: sha256 + beat ID list + confirmation time in script.lock.json.

Every paid submission verifies this lock; one changed character makes the hash differ and the
submission is refused. Locking never rewrites the script text.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from check_release_intent import undecided_sensitive_hits
from check_script_coverage import parse_script
from drama_project import (
    SCRIPT_LOCK_NAME, ProjectError, drama_block, load_manifest, manifest_path, nonempty,
    now_iso, read_json, resolve_in_project, section, sha256_file, write_json_atomic,
)

LOCK_VERSION = "1.0"


def read_lock(project: Path) -> dict[str, Any] | None:
    path = project / SCRIPT_LOCK_NAME
    if not path.is_file():
        return None
    lock = read_json(path)
    return lock if isinstance(lock, dict) else {}


def verify_lock(project: Path) -> list[str]:
    """Return gate errors; an empty list means the locked script is byte-identical."""
    lock = read_lock(project)
    if lock is None:
        return ["SCRIPT_NOT_LOCKED"]
    script = resolve_in_project(project, lock.get("script"))
    digest, beats = lock.get("sha256"), lock.get("beats")
    if script is None or not nonempty(digest) or not isinstance(beats, list) or not beats \
            or not nonempty(lock.get("confirmed_by_user")):
        return ["SCRIPT_LOCK_INVALID"]
    if not script.is_file():
        return [f"SCRIPT_MISSING:{lock.get('script')}"]
    if sha256_file(script) != digest:
        return [f"SCRIPT_CHANGED_AFTER_LOCK:{lock.get('script')}"]
    return []


def locked_script_text(project: Path) -> str:
    """Text of the locked script; raises when the lock does not hold."""
    errors = verify_lock(project)
    if errors:
        raise ProjectError(errors[0])
    lock = read_lock(project) or {}
    script = resolve_in_project(project, lock.get("script"))
    if script is None:
        raise ProjectError("SCRIPT_LOCK_INVALID")
    return script.read_text(encoding="utf-8")


def sensitive_terms(project: Path) -> tuple[list[Any], list[Any]]:
    if not manifest_path(project).is_file():
        return [], []
    intent = section(drama_block(load_manifest(project)), "release_intent")
    terms, decisions = intent.get("sensitive_terms"), intent.get("sensitive_decisions")
    return (terms if isinstance(terms, list) else []), (decisions if isinstance(decisions, list) else [])


def build_lock(project: Path, script_arg: str, user_words: str, relock: bool) -> dict[str, Any]:
    script = resolve_in_project(project, script_arg)
    if script is None or not script.is_file():
        raise ProjectError("SCRIPT_MISSING", script_arg)
    if not nonempty(user_words):
        raise ProjectError("USER_CONFIRMATION_REQUIRED", "pass the user's own approval words")
    previous = read_lock(project)
    if previous is not None and not relock:
        raise ProjectError("SCRIPT_ALREADY_LOCKED", "re-locking needs --relock and a new user approval")
    text = script.read_text(encoding="utf-8")
    beats, lines, errors = parse_script(text)
    if errors:
        raise ProjectError(errors[0], "number beats in source order first; do not edit wording")
    terms, decisions = sensitive_terms(project)
    hits = undecided_sensitive_hits(text, terms, decisions)
    if hits:
        raise ProjectError("SENSITIVE_HIT_UNDECIDED", ",".join(hits))
    lock = {
        "version": LOCK_VERSION,
        "script": str(script.relative_to(project.resolve())),
        "sha256": sha256_file(script),
        "beats": beats,
        "dialogue_lines": len(lines),
        "confirmed_at": now_iso(),
        "confirmed_by_user": user_words.strip(),
    }
    if previous:
        lock["relocked_from_sha256"] = previous.get("sha256")
    return lock


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Exit codes: 0 locked / lock holds; 1 gate refused; 3 file or JSON error.",
    )
    parser.add_argument("--project", required=True, type=Path, help="project directory")
    parser.add_argument("--script", help="beat-tagged script path, relative to the project")
    parser.add_argument("--confirmed-by-user", default="", help="the user's approval, quoted verbatim")
    parser.add_argument("--relock", action="store_true", help="replace an existing lock after a new approval")
    parser.add_argument("--verify", action="store_true", help="only check that the lock still holds")
    args = parser.parse_args()
    project = args.project.expanduser()
    try:
        if args.verify:
            errors = verify_lock(project)
            print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
            return 1 if errors else 0
        if not args.script:
            parser.error("--script is required unless --verify is given")
        lock = build_lock(project, args.script, args.confirmed_by_user, args.relock)
        write_json_atomic(project / SCRIPT_LOCK_NAME, lock)
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 3 if exc.code == "INPUT_ERROR" else 1
    print(json.dumps({"ok": True, "lock": lock}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
