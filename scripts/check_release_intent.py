#!/usr/bin/env python3
"""Release-intent gate: must be complete before the first paid submission.

Checks invariants only: the aspect ratio is derived from the stated platforms (or is the
explicit no-platform master), sensitive terms found in the script each carry a user decision,
and labels are limited to what the user asked for. Platform disclosure rules are recorded as
questions for the user; this gate never adds a label by itself.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from check_script_coverage import parse_script
from drama_project import ProjectError, drama_block, load_manifest, nonempty, section

LABEL_POLICY = "user_requested_only"
RATIO_RE = re.compile(r"\d+(?:\.\d+)?:\d+(?:\.\d+)?")
RATIO_SOURCES = {"platform", "master_default"}


def fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def strings(value: object) -> list[str]:
    return [item for item in value if nonempty(item)] if isinstance(value, list) else []


def sensitive_hits(script_text: str, terms: list[Any]) -> dict[str, list[str]]:
    """Map each term to the script lines that contain it (dialogue first, whole text as fallback)."""
    _, lines, _ = parse_script(script_text)
    spoken = [line["words"] for line in lines] or script_text.splitlines()
    hits: dict[str, list[str]] = {}
    for term in strings(terms):
        found = [line.strip() for line in spoken if fold(term) in fold(line)]
        if found:
            hits[term] = found
    return hits


def undecided_sensitive_hits(script_text: str, terms: list[Any], decisions: list[Any]) -> list[str]:
    decided = {
        fold(row["term"]) for row in decisions
        if isinstance(row, dict) and nonempty(row.get("term")) and nonempty(row.get("decision"))
    }
    return sorted(term for term in sensitive_hits(script_text, terms) if fold(term) not in decided)


def check_ratio(intent: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    platforms = intent.get("platforms")
    if not isinstance(platforms, list) or any(not nonempty(item) for item in platforms):
        return ["RELEASE_INTENT_INCOMPLETE:platforms"]
    ratio, source = intent.get("aspect_ratio"), intent.get("aspect_ratio_source")
    if not (isinstance(ratio, str) and RATIO_RE.fullmatch(ratio)):
        errors.append("RELEASE_INTENT_INCOMPLETE:aspect_ratio")
    if source not in RATIO_SOURCES or not nonempty(intent.get("aspect_ratio_reason")):
        errors.append("RELEASE_INTENT_INCOMPLETE:aspect_ratio_reason")
    if platforms and source != "platform":
        errors.append("ASPECT_RATIO_NOT_DERIVED_FROM_PLATFORM")
    if not platforms and intent.get("platform_undecided") is not True:
        errors.append("RELEASE_INTENT_INCOMPLETE:platforms_or_platform_undecided")
    return errors


def check_labels_block(intent: dict[str, Any]) -> list[str]:
    labels = intent.get("labels")
    if not isinstance(labels, dict):
        return ["RELEASE_INTENT_INCOMPLETE:labels"]
    errors: list[str] = []
    if labels.get("policy") != LABEL_POLICY:
        errors.append("LABEL_POLICY_MUST_BE_USER_REQUESTED_ONLY")
    if not isinstance(labels.get("requested"), list):
        errors.append("RELEASE_INTENT_INCOMPLETE:labels.requested")
    questions = labels.get("disclosure_questions", [])
    if not isinstance(questions, list):
        return errors + ["RELEASE_INTENT_INCOMPLETE:labels.disclosure_questions"]
    for index, row in enumerate(questions):
        if not isinstance(row, dict) or not nonempty(row.get("platform")) or not nonempty(row.get("question")):
            errors.append(f"DISCLOSURE_QUESTION_INVALID:{index}")
    return errors


def check_lexicon_block(intent: dict[str, Any], script_text: str | None) -> list[str]:
    lexicon = intent.get("lexicon")
    if lexicon is None:
        return []
    if not isinstance(lexicon, list):
        return ["RELEASE_INTENT_INCOMPLETE:lexicon"]
    errors: list[str] = []
    for idx, row in enumerate(lexicon):
        if (not isinstance(row, dict) or not nonempty(row.get("canonical"))
                or not isinstance(row.get("forbidden_variants"), list)):
            errors.append(f"LEXICON_ENTRY_INVALID:{idx}")
    if not errors and script_text is not None:
        errors.extend(lexicon_violations(lexicon, script_text, "script"))
    return errors


ASCII_ALNUM_RE = re.compile(r"[a-z0-9]")


def variant_pattern(bad: str) -> re.Pattern[str]:
    prefix = r"(?<![a-z0-9])" if ASCII_ALNUM_RE.match(bad[0]) else ""
    suffix = r"(?![a-z0-9])" if ASCII_ALNUM_RE.match(bad[-1]) else ""
    return re.compile(f"{prefix}{re.escape(bad)}{suffix}")


def lexicon_violations(lexicon: object, text: str, where: str) -> list[str]:
    if not isinstance(lexicon, list) or not text:
        return []
    folded = fold(text)
    errors: list[str] = []
    for row in lexicon:
        if not isinstance(row, dict) or not nonempty(row.get("canonical")):
            continue
        scrubbed = folded.replace(fold(row["canonical"]), " ")
        for bad in strings(row.get("forbidden_variants")):
            target = fold(bad)
            if target and variant_pattern(target).search(scrubbed):
                errors.append(f"LEXICON_VARIANT_FORBIDDEN:{where}:{bad}->{row['canonical']}")
    return errors


def check_intent(intent: object, script_text: str | None) -> list[str]:
    """Gate errors for one release_intent block; an empty list means it is complete."""
    if not isinstance(intent, dict) or not intent:
        return ["RELEASE_INTENT_MISSING"]
    errors = check_ratio(intent) + check_labels_block(intent) + check_lexicon_block(intent, script_text)
    duration = intent.get("target_duration_s")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
        errors.append("RELEASE_INTENT_INCOMPLETE:target_duration_s")
    for field in ("real_public_figures", "on_screen_text", "native_bgm"):
        if not isinstance(intent.get(field), bool):
            errors.append(f"RELEASE_INTENT_INCOMPLETE:{field}")
    terms, decisions = intent.get("sensitive_terms"), intent.get("sensitive_decisions", [])
    if not isinstance(terms, list) or not isinstance(decisions, list):
        errors.append("RELEASE_INTENT_INCOMPLETE:sensitive_terms")
    elif script_text is not None:
        errors.extend(f"SENSITIVE_HIT_UNDECIDED:{term}"
                      for term in undecided_sensitive_hits(script_text, terms, decisions))
    return errors


def check_applied_labels(intent: dict[str, Any], applied: object) -> list[str]:
    """Delivery-time check: nothing was labelled beyond the user's request; questions answered."""
    labels = section(intent, "labels")
    requested = {fold(item) for item in strings(labels.get("requested"))}
    errors = [f"UNREQUESTED_LABEL:{item}" for item in strings(applied) if fold(item) not in requested]
    for row in labels.get("disclosure_questions", []) or []:
        if isinstance(row, dict) and not nonempty(row.get("user_answer")):
            errors.append(f"DISCLOSURE_QUESTION_UNANSWERED:{row.get('platform')}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Exit codes: 0 complete; 1 incomplete or undecided hits; 3 file or JSON error.",
    )
    parser.add_argument("--project", required=True, type=Path, help="project directory")
    parser.add_argument("--script", type=Path, help="script to scan for sensitive terms")
    args = parser.parse_args()
    try:
        intent = section(drama_block(load_manifest(args.project.expanduser())), "release_intent")
        text = args.script.expanduser().read_text(encoding="utf-8") if args.script else None
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 3 if exc.code == "INPUT_ERROR" else 1
    except OSError as exc:
        print(json.dumps({"ok": False, "errors": [f"INPUT_ERROR:{type(exc).__name__}"]}, indent=2))
        return 3
    errors = check_intent(intent, text)
    hits = sensitive_hits(text, intent.get("sensitive_terms") or []) if text else {}
    print(json.dumps({"ok": not errors, "errors": errors, "sensitive_hits": hits},
                     ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
