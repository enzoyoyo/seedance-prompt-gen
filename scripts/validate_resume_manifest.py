#!/usr/bin/env python3
"""Read-only resume planning: no provider access, submissions, or semantic/video QC.

Parent snapshots bind the selected source_take, revision and observed_end_state.
Only explicit advances_beats are compared with ancestors' completed_beats;
coverage of the same story time need not declare a new advancement.
The optional takes ledger isolates rejected takes: they may not enter edit_list
or any continuation input, and one shot keeps at most one approved take.
Takes that carry a `tier` are the short-drama submission ledger: a submitted take needs a
job ID, an approved one needs the four acceptance checks, a retake changes exactly one
variable, and a final-tier take needs the approved draft cut. `--clips-dir` additionally
requires every clip file on disk to have such a record.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from drama_project import ACCEPTANCE_CHECKS, JOB_STATES, TIERS, VIDEO_SUFFIXES


ACCEPTED = {"accepted", "accept_with_deviation"}
PENDING = {"submitted", "running", "unknown"}
STAGES = {
    "planned": {"planning"},
    "submitted": {"execution"},
    "running": {"execution"},
    "unknown": {"execution"},
    "failed": {"execution"},
    "succeeded": {"execution", "qc"},
    "accepted": {"qc"},
    "accept_with_deviation": {"qc"},
    "rejected": {"qc"},
    "repair": {"qc"},
}
SNAPSHOT_FIELDS = ("source_take", "revision", "observed_end_state")
BEAT_FIELDS = ("completed_beats", "reserved_beats", "advances_beats")
TAKE_STATUSES = {"candidate", "approved", "rejected"}
TAKE_STRING_FIELDS = ("reject_reason", "supersedes", "requested_model", "reported_model")
SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: object) -> bool:
    return (isinstance(value, list) and all(nonempty(item) for item in value)
            and len(value) == len(set(value)))


def state_of(shot: dict) -> str:
    value = shot.get("state")
    return value if isinstance(value, str) else ""


def empty_report() -> dict:
    return {"ok": False, "planning_only": True, "semantics_checked": False,
            "submissions_performed": 0, "errors": [], "warnings": [], "shots": []}


def read_takes(manifest: dict, errors: list[str], warnings: list[str]) -> dict[str, dict]:
    """Read the optional take ledger; per-take record problems are reported here."""
    rows = manifest.get("takes", [])
    if not isinstance(rows, list):
        errors.append("INVALID_TAKES")
        return {}
    takes: dict[str, dict] = {}
    for index, take in enumerate(rows):
        if not isinstance(take, dict) or not nonempty(take.get("take_id")):
            errors.append(f"INVALID_TAKE:{index}")
            continue
        tid = take["take_id"]
        if tid in takes:
            errors.append(f"DUPLICATE_TAKE_ID:{tid}")
            continue
        takes[tid] = take
        status = take.get("status")
        if status not in TAKE_STATUSES:
            errors.append(f"INVALID_TAKE_STATUS:{tid}")
        elif status == "rejected" and not nonempty(take.get("reject_reason")):
            errors.append(f"REJECTED_TAKE_REQUIRES_REASON:{tid}")
        if not nonempty(take.get("shot_id")):
            errors.append(f"INVALID_TAKE_SHOT_ID:{tid}")
        for field in TAKE_STRING_FIELDS:
            value = take.get(field)
            if value is not None and not nonempty(value):
                errors.append(f"INVALID_TAKE_{field.upper()}:{tid}")
        digest = take.get("file_sha256")
        if digest is not None and not (isinstance(digest, str) and SHA256_RE.fullmatch(digest)):
            errors.append(f"INVALID_TAKE_FILE_SHA256:{tid}")
        requested, reported = take.get("requested_model"), take.get("reported_model")
        if nonempty(requested) and nonempty(reported) and requested != reported:
            warnings.append(f"MODEL_DOWNGRADED:{tid}:{requested}->{reported}")
    return takes


def has_job_id(take: dict) -> bool:
    ids = take.get("job_ids")
    return isinstance(ids, dict) and any(nonempty(value) for value in ids.values())


def final_tier_allowed(manifest: dict) -> bool:
    """Final-tier spending needs the user's approval of the draft cut, or a one-take-only order."""
    drama = manifest.get("drama") if isinstance(manifest.get("drama"), dict) else {}
    approvals = drama.get("approvals") if isinstance(drama.get("approvals"), dict) else {}
    cut = approvals.get("draft_cut") if isinstance(approvals.get("draft_cut"), dict) else {}
    budget = drama.get("budget") if isinstance(drama.get("budget"), dict) else {}
    one_shot = budget.get("one_shot") if isinstance(budget.get("one_shot"), dict) else {}
    return cut.get("approved") is True or (nonempty(one_shot.get("user_words")) and one_shot.get("tier") == "final")


def acceptance_errors(tid: str, take: dict) -> list[str]:
    acceptance = take.get("acceptance") if isinstance(take.get("acceptance"), dict) else {}
    errors = []
    for name in ACCEPTANCE_CHECKS:
        row = acceptance.get(name) if isinstance(acceptance.get(name), dict) else {}
        if row.get("result") not in {"pass", "deviation", "fail"} or not nonempty(row.get("evidence")):
            errors.append(f"APPROVED_TAKE_WITHOUT_ACCEPTANCE:{tid}:{name}")
        elif row["result"] == "fail":
            errors.append(f"APPROVED_TAKE_WITH_FAILED_CHECK:{tid}:{name}")
    if take.get("job_state") != "succeeded" or not nonempty(take.get("file")):
        errors.append(f"APPROVED_TAKE_WITHOUT_FILE:{tid}")
    return errors


def tiered_take_errors(tid: str, take: dict, final_allowed: bool) -> list[str]:
    """Invariants of one submission-ledger take; shot counts and wording are not its business."""
    errors = []
    generated = take.get("origin") != "reused"
    if take.get("tier") not in TIERS:
        errors.append(f"INVALID_TAKE_TIER:{tid}")
    if take.get("job_state") not in JOB_STATES:
        errors.append(f"INVALID_TAKE_JOB_STATE:{tid}")
    elif take["job_state"] in {"submitted", "succeeded"} and generated and not has_job_id(take):
        errors.append(f"SUBMITTED_TAKE_WITHOUT_JOB_ID:{tid}")
    if take.get("status") == "approved":
        errors.extend(acceptance_errors(tid, take))
    if nonempty(take.get("supersedes")):
        changed = take.get("changed_variables")
        count = len(changed) if string_list(changed) else 0
        if count != 1:
            errors.append(f"RETAKE_CHANGED_VARIABLES_NOT_ONE:{tid}:{count}")
    if take.get("tier") == "final" and generated and not final_allowed:
        errors.append(f"FINAL_TAKE_WITHOUT_APPROVED_DRAFT_CUT:{tid}")
    return errors


def clip_errors(manifest: dict, clips_dir: Path) -> list[str]:
    """Every clip file on disk must have a ledger record with a job ID (or be a declared reuse)."""
    if not clips_dir.is_dir():
        return [f"CLIPS_DIR_MISSING:{clips_dir.name}"]
    rows = manifest.get("takes") if isinstance(manifest.get("takes"), list) else []
    records: dict[str, list[dict]] = {}
    for take in rows:
        if isinstance(take, dict) and nonempty(take.get("file")):
            records.setdefault(Path(take["file"]).name, []).append(take)
    errors = []
    for path in sorted(clips_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES:
            continue
        found = records.get(path.name, [])
        if not found:
            errors.append(f"CLIP_WITHOUT_LEDGER_RECORD:{path.name}")
        elif not any(has_job_id(take) or take.get("origin") == "reused" for take in found):
            errors.append(f"CLIP_RECORD_WITHOUT_JOB_ID:{path.name}")
    return errors


def validate_takes(manifest: dict, shots: dict, report: dict) -> None:
    """A rejected take may not reach an edit list or any continuation input."""
    errors, warnings = report["errors"], report["warnings"]
    takes = read_takes(manifest, errors, warnings)
    approved: dict[str, list[str]] = {}
    final_allowed = final_tier_allowed(manifest)
    for tid, take in takes.items():
        if "tier" in take:
            errors.extend(tiered_take_errors(tid, take, final_allowed))
        parent = take.get("supersedes")
        if nonempty(parent) and parent not in takes:
            errors.append(f"UNKNOWN_SUPERSEDED_TAKE:{tid}:{parent}")
        sid = take.get("shot_id")
        if nonempty(sid) and sid not in shots:
            errors.append(f"TAKE_UNKNOWN_SHOT:{tid}:{sid}")
        elif nonempty(sid) and take.get("status") == "approved":
            # A drama shot may keep one approved take per tier (draft review, then final).
            key = f"{sid}@{take['tier']}" if "tier" in take else sid
            approved.setdefault(key, []).append(tid)
    for sid, ids in sorted(approved.items()):
        if len(ids) > 1:
            errors.append(f"MULTIPLE_APPROVED_TAKES:{sid}:" + ",".join(sorted(ids)))

    rejected = {tid for tid, take in takes.items() if take.get("status") == "rejected"}
    edit_list = manifest.get("edit_list", [])
    if not isinstance(edit_list, list):
        errors.append("INVALID_EDIT_LIST")
        edit_list = []
    for position, entry in enumerate(edit_list):
        if not nonempty(entry):
            errors.append(f"INVALID_EDIT_LIST_ENTRY:{position}")
        elif entry not in takes:
            errors.append(f"EDIT_LIST_UNKNOWN_TAKE:{entry}")
        elif entry in rejected:
            errors.append(f"REJECTED_TAKE_IN_EDIT_LIST:{entry}")
    if not rejected:
        return
    for sid in sorted(shots):
        shot = shots[sid]
        if shot.get("source_take") in rejected:
            errors.append(f"REJECTED_TAKE_AS_SOURCE:{sid}:{shot['source_take']}")
        refs = shot.get("parents")
        for ref in refs if isinstance(refs, list) else []:
            if isinstance(ref, dict) and ref.get("source_take") in rejected:
                errors.append(f"REJECTED_TAKE_AS_PARENT_INPUT:{sid}:{ref['source_take']}")


def validate(manifest: object) -> dict:
    """Check declared records and dependencies; never open referenced assets."""
    report = empty_report()
    if not isinstance(manifest, dict) or manifest.get("version") != "1.0":
        report["errors"].append("INVALID_MANIFEST_VERSION")
        return report
    rows = manifest.get("shots")
    if not isinstance(rows, list) or not rows:
        report["errors"].append("SHOTS_MUST_BE_NONEMPTY_LIST")
        return report

    shots, issues, warnings, parents = {}, {}, {}, {}
    for index, shot in enumerate(rows):
        if not isinstance(shot, dict) or not nonempty(shot.get("shot_id")):
            report["errors"].append(f"INVALID_SHOT:{index}")
            continue
        sid = shot["shot_id"]
        if sid in shots:
            issues[sid].append("DUPLICATE_SHOT_ID")
            continue
        shots[sid], issues[sid], warnings[sid], parents[sid] = shot, [], [], []
        errors = issues[sid]
        state = state_of(shot)
        if state not in STAGES:
            errors.append("INVALID_STATE")
        elif not isinstance(shot.get("stage"), str) or shot["stage"] not in STAGES[state]:
            errors.append("STAGE_STATE_MISMATCH")
        for field in ("revision", "next_action"):
            if not nonempty(shot.get(field)):
                errors.append(f"MISSING_{field.upper()}")
        for field in BEAT_FIELDS + ("changed_variables",):
            if not string_list(shot.get(field)):
                errors.append(f"INVALID_{field.upper()}")
        for field in ("requested_end_state", "observed_end_state"):
            value = shot.get(field)
            if field not in shot or (value is not None and not isinstance(value, dict)):
                errors.append(f"INVALID_{field.upper()}")
        if "source_take" not in shot or (
                shot["source_take"] is not None and not nonempty(shot["source_take"])):
            errors.append("INVALID_SOURCE_TAKE")
        submitted = shot.get("submitted")
        if not isinstance(submitted, bool):
            errors.append("SUBMITTED_MUST_BE_BOOLEAN")
        if state in PENDING | {"succeeded", "failed"} and submitted is not True:
            errors.append("EXECUTION_STATE_REQUIRES_SUBMITTED")
        if state == "planned" and submitted is True:
            errors.append("PLANNED_CANNOT_BE_SUBMITTED")
        if submitted is True:
            for field in ("provider", "exact_model_id", "job_id"):
                if not nonempty(shot.get(field)):
                    errors.append(f"MISSING_{field.upper()}")
        if isinstance(state, str) and state in ACCEPTED:
            if not nonempty(shot.get("source_take")) or not nonempty(shot.get("qc_record")):
                errors.append("ACCEPTED_REQUIRES_TAKE_AND_QC_RECORD")
            if not isinstance(shot.get("observed_end_state"), dict) or not shot["observed_end_state"]:
                errors.append("ACCEPTED_REQUIRES_OBSERVED_END_STATE")
        failure = shot.get("failure")
        if "failure" not in shot or (failure is not None and not isinstance(failure, dict)):
            errors.append("INVALID_FAILURE")
        elif failure is not None:
            if not nonempty(failure.get("kind")) or not nonempty(failure.get("reason")):
                errors.append("FAILURE_REQUIRES_KIND_AND_REASON")
            for field in ("terminal_confirmed", "retry_eligible"):
                if not isinstance(failure.get(field), bool):
                    errors.append(f"FAILURE_{field.upper()}_MUST_BE_BOOLEAN")
        if state == "failed" and (not isinstance(failure, dict)
                                  or failure.get("terminal_confirmed") is not True):
            errors.append("FAILED_REQUIRES_CONFIRMED_TERMINAL_STATUS")
        refs = shot.get("parents")
        if not isinstance(refs, list):
            errors.append("INVALID_PARENTS")
            continue
        seen = set()
        for ref in refs:
            if not isinstance(ref, dict) or not nonempty(ref.get("shot_id")):
                errors.append("INVALID_PARENT")
                continue
            pid = ref["shot_id"]
            if pid in seen:
                errors.append(f"DUPLICATE_PARENT:{pid}")
            seen.add(pid)
            parents[sid].append(ref)
            if not nonempty(ref.get("revision")) or any(f not in ref for f in SNAPSHOT_FIELDS):
                errors.append(f"INCOMPLETE_PARENT_SNAPSHOT:{pid}")
            if ref.get("source_take") is not None and not nonempty(ref["source_take"]):
                errors.append(f"INVALID_PARENT_TAKE:{pid}")
            if ref.get("observed_end_state") is not None and not isinstance(ref["observed_end_state"], dict):
                errors.append(f"INVALID_PARENT_END_STATE:{pid}")
            if "deviation_reviewed" in ref and not isinstance(ref["deviation_reviewed"], bool):
                errors.append(f"INVALID_DEVIATION_REVIEW:{pid}")

    # Small DAG, stable input order; unresolved nodes include cycles and dependents.
    dependencies = {sid: {ref["shot_id"] for ref in refs} for sid, refs in parents.items()}
    for sid, deps in dependencies.items():
        issues[sid].extend(f"MISSING_PARENT:{pid}" for pid in sorted(deps - shots.keys()))
    order, remaining = [], set(shots)
    while remaining:
        ready = [sid for sid in shots if sid in remaining
                 and not (dependencies[sid] & remaining)]
        if not ready:
            for sid in shots:
                if sid in remaining:
                    issues[sid].append("DEPENDENCY_CYCLE_OR_DOWNSTREAM")
            order.extend(sid for sid in shots if sid in remaining)
            break
        order.extend(ready)
        remaining.difference_update(ready)

    ancestors, stale, waiting, early = {}, {}, {}, {}
    for sid in order:
        shot = shots[sid]
        ancestors[sid], waiting[sid] = set(), False
        completed = shot.get("completed_beats", [])
        reserved = shot.get("reserved_beats", [])
        early[sid] = (set(completed) & set(reserved)
                      if string_list(completed) and string_list(reserved) else set())
        if early[sid]:
            warnings[sid].append("RESERVED_BEATS_ALREADY_COMPLETED:" + ",".join(sorted(early[sid])))
        for ref in parents[sid]:
            pid = ref["shot_id"]
            if pid not in shots:
                continue
            parent = shots[pid]
            ancestors[sid].add(pid)
            ancestors[sid].update(ancestors.get(pid, set()))
            if any(ref.get(field) != parent.get(field) for field in SNAPSHOT_FIELDS):
                issues[sid].append(f"STALE_PARENT_SNAPSHOT:{pid}")
            pstate = state_of(parent)
            if stale.get(pid) or issues[pid] or pstate in ("rejected", "repair", "failed"):
                issues[sid].append(f"INVALID_PARENT:{pid}")
            elif pstate not in ACCEPTED:
                waiting[sid] = True
            if waiting.get(pid):
                waiting[sid] = True
            if pstate == "accept_with_deviation" and ref.get("deviation_reviewed") is not True:
                issues[sid].append(f"PARENT_DEVIATION_NEEDS_REPLAN:{pid}")
            if early.get(pid):
                issues[sid].append(f"PARENT_RESERVED_BEAT_OCCURRED:{pid}")
        prior_beats = set()
        for aid in ancestors[sid]:
            beats = shots[aid].get("completed_beats", [])
            if string_list(beats):
                prior_beats.update(beats)
        advances = shot.get("advances_beats", [])
        duplicate = set(advances) & prior_beats if string_list(advances) else set()
        if duplicate:
            issues[sid].append("DUPLICATE_BEAT_ADVANCEMENT:" + ",".join(sorted(duplicate)))
        state = state_of(shot)
        if waiting[sid] and state != "planned":
            issues[sid].append("EXECUTED_WITH_UNACCEPTED_PARENT")
        stale[sid] = bool(issues[sid])

    for sid, shot in shots.items():
        state = state_of(shot)
        if stale[sid]:
            action = "needs_replan"
            next_action = "Review the listed record/dependency problems and update the plan."
        elif state in ACCEPTED:
            action, next_action = "keep_accepted", "Keep the selected QC take."
        elif state in PENDING:
            action, next_action = "poll_existing", "Read back the existing job; do not resubmit."
        elif state == "succeeded":
            action, next_action = "review_qc", "Review the downloaded take and record usable in/out and QC."
        elif state == "failed":
            eligible = shot["failure"]["retry_eligible"]
            action = "retry_eligible" if eligible else "review_failure"
            next_action = ("Plan a retry using the recorded failure and changed variables; no submission."
                           if eligible else "Review the terminal failure before deciding a next attempt.")
        elif state in {"rejected", "repair"}:
            action, next_action = "needs_replan", "Plan the repair; this take cannot be a continuity parent."
        elif waiting[sid]:
            action, next_action = "wait_for_parent", "Wait for parent QC, then refresh the parent snapshot."
        else:
            action, next_action = "prepare", "Prepare the declared next action; no submission."
        failure = shot.get("failure")
        unconfirmed_failure = state == "failed" and (
            not isinstance(failure, dict) or failure.get("terminal_confirmed") is not True)
        poll = state in PENDING or (unconfirmed_failure and shot.get("submitted") is True)
        if poll and action != "poll_existing":
            next_action += " First reconcile/poll the existing job; never submit another job on uncertainty."
        report["shots"].append({"shot_id": sid, "source_take": shot.get("source_take"),
                                "action": action, "stale": stale[sid],
                                "poll_existing_first": poll, "next_action": next_action,
                                "errors": issues[sid], "warnings": warnings[sid]})
        report["errors"].extend(f"{sid}:{error}" for error in issues[sid])
        report["warnings"].extend(f"{sid}:{warning}" for warning in warnings[sid])
    validate_takes(manifest, shots, report)
    report["ok"] = not report["errors"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="Print the full planning report as JSON")
    parser.add_argument("--clips-dir", type=Path,
                        help="Also require a ledger record with a job ID for every clip file in this directory")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.input.read_text(encoding="utf-8"))
        report = validate(manifest)
        if args.clips_dir is not None and isinstance(manifest, dict):
            report["errors"].extend(clip_errors(manifest, args.clips_dir.expanduser()))
            report["ok"] = not report["errors"]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report = empty_report()
        report["errors"].append(f"INPUT_ERROR:{type(exc).__name__}")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Read-only planning; semantics/QC not checked; submissions performed: 0")
        for shot in report["shots"]:
            print(f"{shot['shot_id']}: {shot['action']} — {shot['next_action']}")
        for error in report["errors"]:
            print(f"ERROR {error}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
