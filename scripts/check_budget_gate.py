#!/usr/bin/env python3
"""Draft-first and budget gate for one paid submission of an AI short drama.

Reads the channel capability card recorded in the project manifest and the take ledger. It never
queries a provider: balances and prices are whatever was recorded from a real read-back.
SPEC v2.0 projects (`drama.sop_version == "2.0"`) enforce the double circuit breaker on an
irreversible spend ledger:
- Local cap: one shot may be re-rendered at most 2 times per tier (`preparing` reserves a slot).
- Global cap: cumulative video re-renders across ALL tiers (`draft` + `lowres` + `final`) and all
  historical/active shots may not exceed `min(5, floor(30% of active generated shots))`; marking a
  take `STALE` or superseding/removing a shot never erases already-spent renders.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from change_impact import take_matches_current_refs
from drama_project import (
    LIVE_JOB_STATES, TIERS, ProjectError, drama_block, nonempty, parse_day, resolve_in_project,
    section, sha256_file, take_rows,
)
from likeness_probe import likeness_probe_errors
from validate_shot_spec import (
    active_shots, channel_of, is_reuse, load_project_spec, positive_number, root_id, shot_rows,
)

CARD_BOOLEAN_ANSWERS = ("draft_tier", "draft_upgradable", "balance_query", "recover_by_id")
CARD_TEXT_ANSWERS = ("ref_transport", "plan_required")
CARD_QUOTA_ANSWERS = ("daily_limit",)
UNKNOWN_WORDS = frozenset({"unknown", "undisclosed", "?"})
REVIEW_TIERS = frozenset({"draft", "lowres"})
LOCAL_RERUN_CAP = 2
GLOBAL_RERUN_RATIO = 0.30
GLOBAL_RERUN_HARD_CAP = 5


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def answer(card: dict[str, Any], field: str) -> Any:
    return section(card, field).get("value")


def valid_card_value(field: str, value: Any) -> bool:
    if field in CARD_BOOLEAN_ANSWERS:
        return isinstance(value, bool)
    if field in CARD_QUOTA_ANSWERS:
        return (not isinstance(value, bool) and isinstance(value, int) and value > 0) or nonempty(value)
    return nonempty(value)


def is_unknown_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    folded = value.strip().casefold()
    return folded in UNKNOWN_WORDS or folded.startswith("todo_verify_live")


def card_errors(channels: dict[str, Any], name: str, today: date) -> list[str]:
    card = channels.get(name)
    if not isinstance(card, dict):
        return [f"CHANNEL_CARD_MISSING:{name}"]
    errors: list[str] = []
    expires = parse_day(card.get("expires_at"))
    if expires is None or today > expires:
        errors.append(f"CHANNEL_CARD_EXPIRED:{name}")
    for field in CARD_BOOLEAN_ANSWERS + CARD_TEXT_ANSWERS + CARD_QUOTA_ANSWERS:
        row = section(card, field)
        if not valid_card_value(field, row.get("value")) or parse_day(row.get("verified_at")) is None:
            errors.append(f"CHANNEL_CARD_INCOMPLETE:{name}:{field}")
    return errors


def one_shot_tier(drama: dict[str, Any]) -> str | None:
    record = section(section(drama, "budget"), "one_shot")
    return record.get("tier") if nonempty(record.get("user_words")) else None


def has_reviewed_take(manifest: dict[str, Any], shot_id: str,
                      spec: dict[str, Any] | None = None, spec_dir: Path | None = None) -> bool:
    for take in take_rows(manifest):
        if take.get("shot_id") != shot_id or take.get("status") != "approved" or take.get("stale") is True:
            continue
        if take.get("tier") not in REVIEW_TIERS and take.get("origin") != "reused":
            continue
        if spec is not None and spec_dir is not None and not take_matches_current_refs(spec, spec_dir, take):
            continue
        return True
    return False


def tier_errors(manifest: dict[str, Any], card: dict[str, Any], channel: str,
                shot_id: str, tier: str,
                spec: dict[str, Any] | None = None, spec_dir: Path | None = None,
                project: Path | None = None) -> list[str]:
    drama = drama_block(manifest)
    wanted = one_shot_tier(drama)
    if wanted is not None:
        return [] if tier == wanted else [f"ONE_SHOT_TIER_MISMATCH:{wanted}"]
    if tier == "final":
        errors = []
        draft_cut_app = section(section(drama, "approvals"), "draft_cut")
        if draft_cut_app.get("approved") is not True or draft_cut_app.get("stale") is True:
            errors.append("FINAL_WITHOUT_APPROVED_DRAFT_CUT")
        else:
            cut_rel = draft_cut_app.get("file") or section(section(drama, "cuts"), "draft").get("file")
            expected_sha = draft_cut_app.get("file_sha256")
            if drama.get("sop_version") in {"2.0", "3.0"} and not (nonempty(cut_rel) and nonempty(expected_sha)):
                errors.append("FINAL_WITHOUT_BOUND_DRAFT_CUT_FILE")
            if nonempty(cut_rel) and project is not None:
                cut_path = resolve_in_project(project, cut_rel)
                if cut_path is None or not cut_path.is_file():
                    errors.append("APPROVED_DRAFT_CUT_CHANGED_OR_MISSING")
                elif nonempty(expected_sha) and sha256_file(cut_path) != expected_sha:
                    errors.append("APPROVED_DRAFT_CUT_CHANGED_OR_MISSING")
        if not has_reviewed_take(manifest, shot_id, spec, spec_dir):
            errors.append(f"FINAL_SHOT_WITHOUT_APPROVED_DRAFT:{shot_id}")
        return errors
    has_draft = answer(card, "draft_tier") is True
    if tier == "draft" and not has_draft:
        return [f"DRAFT_TIER_UNAVAILABLE_USE_LOWRES:{channel}"]
    if tier == "lowres" and has_draft:
        return [f"DRAFT_TIER_AVAILABLE_USE_DRAFT:{channel}"]
    return []


def channel_takes(manifest: dict[str, Any], channel: str, tier: str | None = None) -> list[dict[str, Any]]:
    return [take for take in take_rows(manifest)
            if take.get("provider") == channel and take.get("origin") != "reused"
            and (tier is None or take.get("tier") == tier)]


def pending_shots(manifest: dict[str, Any], spec: dict[str, Any], channel: str, tier: str) -> list[dict[str, Any]]:
    rows = shot_rows(spec)
    live = {take.get("shot_id") for take in take_rows(manifest)
            if take.get("tier") == tier and take.get("status") != "rejected" and take.get("stale") is not True
            and take.get("job_state") in LIVE_JOB_STATES}
    return [shot for shot in active_shots(rows)
            if not is_reuse(shot, tier) and channel_of(spec, shot) == channel
            and positive_number(shot.get("duration")) and root_id(rows, shot["id"]) not in live]


def trial_errors(manifest: dict[str, Any], spec: dict[str, Any], shot: dict[str, Any],
                 channel: str, tier: str) -> tuple[list[str], bool]:
    takes = channel_takes(manifest, channel, tier)
    if any(take.get("job_state") == "succeeded" for take in takes):
        return [], True
    flying = [take for take in takes if take.get("job_state") in {"preparing", "submitted", "unknown"}]
    if flying:
        return [f"TRIAL_IN_FLIGHT:{flying[0].get('take_id')}"], False
    pending = pending_shots(manifest, spec, channel, tier)
    shortest = min((row["duration"] for row in pending), default=None)
    allowed = sorted(row["id"] for row in pending if row["duration"] == shortest)
    if shot["id"] not in allowed:
        return ["TRIAL_MUST_BE_SHORTEST_SHOT:" + ",".join(allowed)], False
    return [], False


def unit_price(takes: list[dict[str, Any]]) -> tuple[float, str] | None:
    best: tuple[float, str] | None = None
    for take in takes:
        cost, seconds = take.get("cost"), take.get("duration_s")
        if not isinstance(cost, dict) or not positive_number(seconds):
            continue
        if not positive_number(cost.get("amount")) or not nonempty(cost.get("unit")):
            continue
        rate = cost["amount"] / seconds
        if best is None or rate > best[0]:
            best = (rate, cost["unit"])
    return best


def spent_since(manifest: dict[str, Any], channel: str, checked: datetime) -> float:
    total = 0.0
    for take in channel_takes(manifest, channel):
        moment = parse_time(take.get("settled_at")) or parse_time(take.get("submitted_at"))
        cost = take.get("cost")
        if moment and moment > checked and isinstance(cost, dict) and positive_number(cost.get("amount")):
            total += cost["amount"]
    return total


def balance_proof_ok(record: dict[str, Any], project: Path | None) -> bool:
    rel, expected = record.get("readback_file"), record.get("readback_sha256")
    if not nonempty(rel) or not nonempty(expected):
        return False
    if project is None:
        return True
    path = resolve_in_project(project, rel)
    return path is not None and path.is_file() and path.stat().st_size > 0 and sha256_file(path) == expected


def post_failure_balance_errors(manifest: dict[str, Any], channel: str, project: Path | None) -> list[str]:
    bad_times = [
        stamp for take in channel_takes(manifest, channel)
        if take.get("job_state") in {"failed", "unknown"}
        and (stamp := (parse_time(take.get("settled_at")) or parse_time(take.get("submitted_at"))
                       or parse_time(take.get("prepared_at")))) is not None
    ]
    if not bad_times:
        return []
    record = section(section(section(drama_block(manifest), "budget"), "balances"), channel)
    checked = parse_time(record.get("checked_at"))
    if (not positive_number(record.get("amount")) or checked is None or not nonempty(record.get("source"))
            or not balance_proof_ok(record, project) or checked <= max(bad_times)):
        return [f"BALANCE_REQUIRED_AFTER_FAILURE_OR_UNKNOWN:{channel}"]
    return []


def balance_errors(manifest: dict[str, Any], spec: dict[str, Any], channel: str, tier: str,
                   project: Path | None = None) -> list[str]:
    settled = [take for take in channel_takes(manifest, channel, tier) if take.get("job_state") == "succeeded"]
    price = unit_price(settled)
    if price is None:
        return [f"TRIAL_COST_NOT_RECORDED:{channel}"]
    record = section(section(section(drama_block(manifest), "budget"), "balances"), channel)
    checked = parse_time(record.get("checked_at"))
    if not positive_number(record.get("amount")) or checked is None or not nonempty(record.get("source")):
        return [f"BALANCE_NOT_RECORDED:{channel}"]
    if not balance_proof_ok(record, project):
        return [f"BALANCE_READBACK_PROOF_MISSING:{channel}"]
    if record.get("unit") != price[1]:
        return [f"COST_UNIT_MISMATCH:{channel}:{price[1]}!={record.get('unit')}"]
    first_settled = min((parse_time(take.get("settled_at")) for take in settled
                         if parse_time(take.get("settled_at"))), default=None)
    if first_settled is not None and checked < first_settled:
        return [f"BALANCE_STALE:{channel}"]
    seconds = sum(row["duration"] for row in pending_shots(manifest, spec, channel, tier))
    estimate = price[0] * seconds
    available = record["amount"] - spent_since(manifest, channel, checked)
    if estimate > available:
        return [f"ESTIMATE_EXCEEDS_BALANCE:{channel}:{estimate:g}>{available:g}{price[1]}"]
    return []


def daily_cap(card: dict[str, Any]) -> int | None:
    value = answer(card, "daily_limit")
    if not isinstance(value, bool) and isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0:
        return int(value.strip())
    return None


def daily_limit_errors(manifest: dict[str, Any], card: dict[str, Any], channel: str, today: date) -> list[str]:
    cap = daily_cap(card)
    if cap is None:
        return []
    used = sum(
        1 for take in channel_takes(manifest, channel)
        if take.get("job_state") != "preparing"
        and (stamp := (parse_time(take.get("submitted_at")) or parse_time(take.get("settled_at"))
                       or parse_time(take.get("prepared_at")))) is not None
        and stamp.date() == today
    )
    return [f"DAILY_LIMIT_REACHED:{channel}:{cap}"] if used >= cap else []


def batch_errors(manifest: dict[str, Any], spec: dict[str, Any], card: dict[str, Any],
                 channel: str, tier: str, project: Path | None = None) -> list[str]:
    errors = balance_errors(manifest, spec, channel, tier, project) if answer(card, "balance_query") is True else []
    needs_confirm = (answer(card, "balance_query") is not True
                     or is_unknown_value(answer(card, "plan_required"))
                     or is_unknown_value(answer(card, "daily_limit")))
    if needs_confirm:
        confirmed = section(section(section(drama_block(manifest), "budget"), "unknown_cost_confirmations"), channel)
        if not nonempty(confirmed.get("user_words")):
            errors.append(f"UNKNOWN_COST_NOT_CONFIRMED:{channel}")
    return errors


def mixed_channel_warnings(spec: dict[str, Any], channels: dict[str, Any]) -> list[str]:
    names = sorted({name for shot in active_shots(shot_rows(spec))
                    if not is_reuse(shot) and (name := channel_of(spec, shot))})
    kinds = {answer(channels[name], "draft_upgradable") for name in names if isinstance(channels.get(name), dict)}
    if len(kinds) > 1:
        return ["MIXED_DRAFT_UPGRADE_CHANNELS:" + ",".join(names)]
    return []


def is_pre_submit_refusal_take(take: dict[str, Any]) -> bool:
    has_id = any(nonempty(str(value)) for value in (take.get("job_ids") or {}).values())
    return take.get("job_state") == "failed" and not has_id and take.get("failure_reason") == "PRE_SUBMIT_INSUFFICIENT_BALANCE"


def counted_attempt(take: dict[str, Any]) -> bool:
    """Every reserved (`preparing`) or provider-reached generated take counts irreversibly.

    Reused clips and confirmed pre-submit balance refusals without a job ID do not count.
    Marking an already-rendered take `stale: True` NEVER erases its historical spend."""
    if take.get("origin") == "reused":
        return False
    state = take.get("job_state")
    if state in {"preparing", "submitted", "unknown", "succeeded"}:
        return True
    has_id = any(nonempty(str(value)) for value in (take.get("job_ids") or {}).values())
    return state == "failed" and has_id and take.get("failure_reason") != "PRE_SUBMIT_INSUFFICIENT_BALANCE"


def record_spend_attempt(manifest: dict[str, Any], root_shot_id: str, tier: str, take_id: str) -> dict[str, Any]:
    """Append `take_id` to `drama.spend_history.shots[root_shot_id][tier]` so historical spend cannot be erased."""
    drama = drama_block(manifest)
    hist = dict(section(drama, "spend_history"))
    shots_hist = dict(section(hist, "shots"))
    per_shot = dict(section(shots_hist, root_shot_id))
    cur = sorted(set(per_shot.get(tier) or []) | {take_id})
    per_shot[tier] = cur
    shots_hist[root_shot_id] = per_shot
    hist["shots"] = shots_hist
    return {**manifest, "drama": {**drama, "spend_history": hist}}


def release_presubmit_reservation(manifest: dict[str, Any], root_shot_id: str, tier: str, take_id: str) -> dict[str, Any]:
    """Withdraw a `preparing` reservation ONLY when confirmed pre-submit insufficient balance occurred."""
    drama = drama_block(manifest)
    hist = dict(section(drama, "spend_history"))
    shots_hist = dict(section(hist, "shots"))
    per_shot = dict(section(shots_hist, root_shot_id))
    if tier in per_shot:
        per_shot[tier] = [tid for tid in (per_shot.get(tier) or []) if tid != take_id]
        shots_hist[root_shot_id] = per_shot
        hist["shots"] = shots_hist
    return {**manifest, "drama": {**drama, "spend_history": hist}}


def rerender_status(manifest: dict[str, Any], spec: dict[str, Any], tier: str) -> dict[str, Any]:
    """Per-shot attempts at `tier`, film-wide cumulative re-renders across ALL tiers, and the global cap."""
    rows = shot_rows(spec)
    active_gen_roots = {root_id(rows, shot["id"]) for shot in active_shots(rows) if not is_reuse(shot)}
    shots_hist = section(section(drama_block(manifest), "spend_history"), "shots")
    pre_refused = {str(t.get("take_id")) for t in take_rows(manifest) if is_pre_submit_refusal_take(t)}

    all_roots = set(active_gen_roots) | set(shots_hist)
    for idx, take in enumerate(take_rows(manifest)):
        if counted_attempt(take) and nonempty(take.get("shot_id")):
            all_roots.add(str(take["shot_id"]))

    by_root_tier: dict[str, dict[str, int]] = {}
    for rid in sorted(all_roots):
        by_root_tier[rid] = {}
        hist_row = section(shots_hist, rid)
        for t_name in TIERS:
            live_ids = {
                str(tk.get("take_id") or f"{rid}@{t_name}#{i}")
                for i, tk in enumerate(take_rows(manifest))
                if tk.get("shot_id") == rid and tk.get("tier") == t_name and counted_attempt(tk)
            }
            saved_ids = {str(tid) for tid in (hist_row.get(t_name) or []) if str(tid) not in pre_refused}
            by_root_tier[rid][t_name] = len(live_ids | saved_ids)

    attempts_at_tier = {rid: by_root_tier[rid].get(tier, 0) for rid in sorted(all_roots)}
    reruns_by_root = {rid: sum(max(0, n - 1) for n in by_root_tier[rid].values()) for rid in sorted(all_roots)}
    used_film_wide = sum(reruns_by_root.values())
    total_shots = len(active_gen_roots)
    cap = min(GLOBAL_RERUN_HARD_CAP, math.floor(total_shots * GLOBAL_RERUN_RATIO))
    if drama_block(manifest).get("sop_version") == "3.0":
        cap = max(1, cap)
    return {
        "tier": tier,
        "total_shots": total_shots,
        "cap": cap,
        "local_cap": LOCAL_RERUN_CAP,
        "used": used_film_wide,
        "attempts": attempts_at_tier,
        "reruns_by_root": reruns_by_root,
        "by_tier": {t_name: sum(max(0, by_root_tier[r][t_name] - 1) for r in all_roots) for t_name in TIERS},
    }


def circuit_breaker_errors(manifest: dict[str, Any], spec: dict[str, Any], shot: dict[str, Any],
                           tier: str) -> list[str]:
    """SPEC v2.0 double budget breaker: local <= 2 reruns per root shot (across tiers), global <= min(5, 30% of shots)."""
    if drama_block(manifest).get("sop_version") not in {"2.0", "3.0"}:
        return []
    status = rerender_status(manifest, spec, tier)
    sid = root_id(shot_rows(spec), shot["id"])
    done = status["attempts"].get(sid, 0)
    if done == 0:
        return []
    shot_reruns = status["reruns_by_root"].get(sid, max(0, done - 1))
    if shot_reruns >= LOCAL_RERUN_CAP:
        return [f"CIRCUIT_BREAKER_LOCAL_LIMIT:{sid}:{tier}:reruns={shot_reruns}_max={LOCAL_RERUN_CAP}"]
    if status["used"] + 1 > status["cap"]:
        return [f"CIRCUIT_BREAKER_GLOBAL_LIMIT:{tier}:rerenders={status['used']}_max={status['cap']}"
                f"_total_shots={status['total_shots']}"]
    return []


def check_submit(manifest: dict[str, Any], spec: dict[str, Any], shot: dict[str, Any],
                 tier: str, today: date, project: Path | None = None,
                 spec_dir: Path | None = None) -> tuple[list[str], list[str]]:
    """Gate errors and warnings for submitting one spec shot at one tier."""
    if tier not in TIERS:
        return [f"INVALID_TIER:{tier}"], []
    channels = section(drama_block(manifest), "channels")
    channel = channel_of(spec, shot)
    if channel is None:
        return [f"SHOT_WITHOUT_CHANNEL:{shot['id']}"], []
    errors = card_errors(channels, channel, today)
    if errors:
        return errors, []
    card = channels[channel]
    shot_id = root_id(shot_rows(spec), shot["id"])
    s_dir = spec_dir or project
    errors = tier_errors(manifest, card, channel, shot_id, tier, spec, s_dir, project)
    warnings = mixed_channel_warnings(spec, channels)
    if errors:
        return errors, warnings
    errors = post_failure_balance_errors(manifest, channel, project)
    errors += daily_limit_errors(manifest, card, channel, today)
    errors += likeness_probe_errors(project, manifest, spec, shot, channel, tier)
    errors += circuit_breaker_errors(manifest, spec, shot, tier)
    if errors or one_shot_tier(drama_block(manifest)) is not None:
        return errors, warnings
    errors, trial_settled = trial_errors(manifest, spec, shot, channel, tier)
    if not errors and trial_settled:
        errors = batch_errors(manifest, spec, card, channel, tier, project)
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Exit codes: 0 may submit; 1 gate refused; 3 file or JSON error.",
    )
    parser.add_argument("--project", required=True, type=Path, help="project directory")
    parser.add_argument("--shot", required=True, help="spec shot id")
    parser.add_argument("--tier", required=True, choices=TIERS)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD, for card expiry")
    args = parser.parse_args()
    try:
        proj = args.project.expanduser()
        spec, spec_dir, manifest = load_project_spec(proj)
        shot = next((row for row in shot_rows(spec) if row.get("id") == args.shot), None)
        if shot is None:
            raise ProjectError("UNKNOWN_SHOT", args.shot)
        errors, warnings = check_submit(manifest, spec, shot, args.tier, args.today, proj, spec_dir)
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 3 if exc.code == "INPUT_ERROR" else 1
    print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
