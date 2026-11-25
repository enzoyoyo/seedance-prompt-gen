#!/usr/bin/env python3
"""Validate the merged open-drama director and its routing contracts."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys

from validate_platform_evidence import evaluate as evaluate_platform
from validate_platform_evidence import validate_ledger as validate_platform_ledger


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"
EVALS = ROOT / "references" / "open-drama-routing-evals.jsonl"
PLATFORM_LEDGER = ROOT / "references" / "platform-evidence-ledger.jsonl"
REQUIRED_REFERENCES = [
    "open-creative-director.md",
    "human-texture-and-script-gate.md",
    "live-trend-intelligence.md",
    "platform-risk-and-compliance.md",
    "2026-platform-evidence.md",
    "dramatic-tension-engine.md",
    "title-craft.md",
]
REQUIRED_EVALS = {
    "script_only_family",
    "quiet_suspense",
    "visual_comedy",
    "latest_tiktok",
    "bounded_provocation",
    "product_lane",
    "vfx_lane",
    "publish_gate",
    "quiet_locked_observation",
    "dialogue_contact_coverage",
    "provider_short_ceiling",
    "mode_conflict",
    "false_belief_power_shift",
    "continuous_vs_cut",
    "minimal_back_view_asset",
    "deterministic_ui_insert",
    "thin_brief_intake",
    "owner_idea_diagnosis",
}


def validate_entrypoint() -> list[str]:
    errors: list[str] = []
    text = SKILL.read_text(encoding="utf-8")
    for name in REQUIRED_REFERENCES:
        if f"references/{name}" not in text:
            errors.append(f"SKILL.md does not route to {name}")
        if not (ROOT / "references" / name).is_file():
            errors.append(f"missing reference: {name}")
    required_meaning = [
        "开放短剧导演层（创意规则优先级）",
        "形式自由，张力不自由",
        "## 剧本张力门",
        "## 剧本接单两态",
        "仍是硬约束",
        "Grok、豆包",
        "原始 URL",
        "只要剧本就停在文本",
    ]
    for value in required_meaning:
        if value not in text:
            errors.append(f"SKILL.md missing merged invariant: {value}")
    return errors


def validate_evals() -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(EVALS.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"eval line {line_number}: {exc}")
            continue
        eval_id = row.get("id")
        if not isinstance(eval_id, str) or not eval_id or eval_id in seen:
            errors.append(f"eval line {line_number}: missing or duplicate id")
            continue
        seen.add(eval_id)
        expected = row.get("expected")
        if not row.get("request") or not isinstance(expected, dict):
            errors.append(f"eval {eval_id}: invalid request or expected contract")
            continue
        route = expected.get("route")
        must = expected.get("must")
        must_not = expected.get("must_not")
        if not isinstance(route, str) or not route:
            errors.append(f"eval {eval_id}: missing route")
        if not isinstance(must, list) or not must:
            errors.append(f"eval {eval_id}: must must be a non-empty list")
        if not isinstance(must_not, list) or not must_not:
            errors.append(f"eval {eval_id}: must_not must be a non-empty list")
        if isinstance(must, list) and isinstance(must_not, list):
            overlap = sorted(set(must) & set(must_not))
            if overlap:
                errors.append(f"eval {eval_id}: contradictory requirements {overlap}")
    missing = sorted(REQUIRED_EVALS - seen)
    if missing:
        errors.append(f"routing eval coverage missing: {missing}")
    return errors


def validate_platform_repository() -> list[str]:
    """Wire only the offline repository stage; never imply publish readiness."""
    bundle, ledger_errors, _ = validate_platform_ledger(PLATFORM_LEDGER)
    if bundle is None or ledger_errors:
        codes = sorted({item.get("code", "UNKNOWN") for item in ledger_errors})
        return [f"platform evidence repository invalid: {codes}"]
    result = evaluate_platform(
        bundle,
        "repository",
        datetime.now().astimezone(),
    )
    if (
        result.get("verdict") != "PASS"
        or result.get("publishable") is not False
        or result.get("authoritative") is not False
    ):
        return ["platform repository PASS must remain non-authoritative and publishable=false"]
    return []


def main() -> int:
    errors = validate_entrypoint() + validate_evals() + validate_platform_repository()
    if errors:
        print("FAIL: merged open-drama validation", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        "PASS: structural contracts only; merged open-drama references, "
        f"{len(REQUIRED_EVALS)} routing fixtures, and platform repository "
        "evidence are valid (publishable=false)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
