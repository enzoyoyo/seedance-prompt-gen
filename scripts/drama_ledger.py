#!/usr/bin/env python3
"""Take-ledger record operations on the resume manifest.

Library only: every function returns a new manifest and performs no I/O. The ledger is the
existing `takes[]` list of templates/resume-manifest.json; nothing here knows a provider.
"""
from __future__ import annotations

from typing import Any, Callable

from drama_project import (
    ACCEPTANCE_CHECKS, ACCEPTANCE_RESULTS, LIVE_JOB_STATES, ProjectError, nonempty, take_rows,
)

OPEN_JOB_STATES = frozenset({"preparing", "submitted", "unknown"})
PASSING_RESULTS = frozenset({"pass", "deviation"})
UNRECOVERED_PREFIX = "UNRECOVERED:"
PRE_SUBMIT_REFUSED_PREFIX = "PRE_SUBMIT_REFUSED:"


def takes_for(manifest: dict[str, Any], shot_id: str, tier: str) -> list[dict[str, Any]]:
    return [take for take in take_rows(manifest)
            if take.get("shot_id") == shot_id and take.get("tier") == tier]


def find_take(manifest: dict[str, Any], take_id: str) -> dict[str, Any]:
    for take in take_rows(manifest):
        if take.get("take_id") == take_id:
            return take
    raise ProjectError("TAKE_NOT_FOUND", take_id)


def blocking_take(manifest: dict[str, Any], shot_id: str, tier: str) -> dict[str, Any] | None:
    """A non-rejected take that may already have cost money for this shot and tier.

    A take flagged `stale: True` (its upstream source was invalidated) no longer blocks a regeneration."""
    for take in takes_for(manifest, shot_id, tier):
        if take.get("status") != "rejected" and take.get("stale") is not True and take.get("job_state") in LIVE_JOB_STATES:
            return take
    return None


def approved_take(manifest: dict[str, Any], shot_id: str, tier: str) -> dict[str, Any] | None:
    return next((take for take in takes_for(manifest, shot_id, tier)
                 if take.get("status") == "approved"), None)


def next_take_id(manifest: dict[str, Any], spec_id: str, tier: str) -> str:
    used = {take.get("take_id") for take in take_rows(manifest)}
    base = f"{spec_id}@{tier}"
    if base not in used:
        return base
    attempt = 2
    while f"{base}#{attempt}" in used:
        attempt += 1
    return f"{base}#{attempt}"


def planned_shot_row(shot_id: str, revision: str) -> dict[str, Any]:
    return {
        "shot_id": shot_id, "source_take": None, "revision": revision, "stage": "planning",
        "state": "planned", "submitted": False, "provider": None, "exact_model_id": None,
        "job_id": None, "requested_end_state": None, "observed_end_state": None, "parents": [],
        "completed_beats": [], "reserved_beats": [], "advances_beats": [], "failure": None,
        "changed_variables": [], "next_action": "Submit through ledger_submit.py after the gates pass.",
    }


def new_take(take_id: str, shot_id: str, spec_id: str, tier: str, **fields: Any) -> dict[str, Any]:
    record = {
        "take_id": take_id, "shot_id": shot_id, "spec_id": spec_id, "tier": tier,
        "status": "candidate", "reject_reason": None, "supersedes": None,
        "provider": None, "exact_model_id": None, "job_state": "preparing", "job_ids": {},
        "origin": "generated", "prepared_at": None, "submitted_at": None, "settled_at": None,
        "file": None, "file_sha256": None, "duration_s": None, "cost": None,
        "changed_variables": [], "acceptance": None,
    }
    return {**record, **fields}


def first_job_id(take: dict[str, Any]) -> str | None:
    ids = take.get("job_ids")
    values = [value for value in ids.values() if nonempty(value)] if isinstance(ids, dict) else []
    return values[0] if values else None


def shot_fields(take: dict[str, Any]) -> dict[str, Any]:
    """Shot-row fields that mirror one take, in the vocabulary of validate_resume_manifest."""
    status, job_state = take.get("status"), take.get("job_state")
    sent = {"submitted": take.get("origin") != "reused", "provider": take.get("provider"),
            "exact_model_id": take.get("exact_model_id"), "job_id": first_job_id(take)}
    base = {"revision": take["spec_id"], "changed_variables": list(take.get("changed_variables") or []),
            "source_take": None, "failure": None}
    if status == "approved":
        results = {name: take["acceptance"][name]["result"] for name in ACCEPTANCE_CHECKS}
        state = "accept_with_deviation" if "deviation" in results.values() else "accepted"
        return {**base, **sent, "state": state, "stage": "qc", "source_take": take["take_id"],
                "qc_record": take["acceptance"]["lines"]["evidence"],
                "observed_end_state": {"acceptance": results},
                "next_action": "Keep the approved take."}
    if status == "rejected":
        return {**base, **sent, "state": "rejected", "stage": "qc",
                "next_action": "Plan a retake that changes exactly one variable."}
    if job_state == "failed":
        job_id = sent["job_id"] or f"{PRE_SUBMIT_REFUSED_PREFIX}{take['take_id']}"
        failure = {"kind": "provider_failed", "reason": take.get("failure_reason") or "failed",
                   "terminal_confirmed": True, "retry_eligible": bool(take.get("retry_eligible"))}
        return {**base, **sent, "job_id": job_id, "state": "failed", "stage": "execution",
                "failure": failure, "next_action": "Review the terminal failure before another attempt."}
    if take.get("origin") == "reused":
        return {**base, "state": "planned", "stage": "planning", "submitted": False,
                "next_action": "Run per-shot acceptance on the reused clip."}
    if job_state == "preparing":
        return {**base, "state": "planned", "stage": "planning", "submitted": False,
                "next_action": "A prepared take has no recorded outcome: recover it before anything else."}
    if job_state == "succeeded":
        return {**base, **sent, "state": "succeeded", "stage": "qc", "next_action": "Run per-shot acceptance."}
    # The generic resume validator needs a job_id on every execution row. An unknown outcome has
    # none yet, so the row carries an explicit marker instead of pretending to be unsubmitted.
    job_id = sent["job_id"] or f"{UNRECOVERED_PREFIX}{take['take_id']}"
    action = ("Read back the existing job; do not resubmit." if sent["job_id"]
              else "Recover the job ID from the provider's own history; do not resubmit.")
    return {**base, **sent, "job_id": job_id, "state": job_state, "stage": "execution", "next_action": action}


def sync_shot_row(manifest: dict[str, Any], take: dict[str, Any]) -> dict[str, Any]:
    """Create or refresh the shot row so the generic resume validator sees the same state."""
    rows = manifest.get("shots") if isinstance(manifest.get("shots"), list) else []
    shot_id = take["shot_id"]
    fields = shot_fields(take)
    if not any(isinstance(row, dict) and row.get("shot_id") == shot_id for row in rows):
        rows = [*rows, planned_shot_row(shot_id, take["spec_id"])]
    updated = [{**row, **fields} if isinstance(row, dict) and row.get("shot_id") == shot_id else row
               for row in rows]
    return {**manifest, "shots": updated}


def add_take(manifest: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Append a take; refuses when the shot already has a live take at this tier."""
    blocker = blocking_take(manifest, record["shot_id"], record["tier"])
    if blocker is not None:
        raise ProjectError("TAKE_ALREADY_LIVE", str(blocker.get("take_id")))
    if any(take.get("take_id") == record["take_id"] for take in take_rows(manifest)):
        raise ProjectError("DUPLICATE_TAKE_ID", record["take_id"])
    takes = [*(manifest.get("takes") if isinstance(manifest.get("takes"), list) else []), record]
    return sync_shot_row({**manifest, "takes": takes}, record)


def replace_take(manifest: dict[str, Any], take_id: str,
                 change: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    current = find_take(manifest, take_id)
    changed = change(current)
    takes = [changed if take is current else take for take in manifest["takes"]]
    return sync_shot_row({**manifest, "takes": takes}, changed)


def mark_submitted(manifest: dict[str, Any], take_id: str, job_ids: dict[str, str], when: str) -> dict[str, Any]:
    return replace_take(manifest, take_id, lambda take: {
        **take, "job_state": "submitted", "job_ids": {**take.get("job_ids", {}), **job_ids},
        "submitted_at": when})


def mark_unknown(manifest: dict[str, Any], take_id: str, reason: str, when: str) -> dict[str, Any]:
    return replace_take(manifest, take_id, lambda take: {
        **take, "job_state": "unknown", "unknown_reason": reason, "submitted_at": when})


def settle_take(manifest: dict[str, Any], take_id: str, state: str, when: str,
                **fields: Any) -> dict[str, Any]:
    """Move an open take to submitted (recovered by ID), succeeded or failed."""
    take = find_take(manifest, take_id)
    if take.get("job_state") not in OPEN_JOB_STATES:
        raise ProjectError("TAKE_ALREADY_SETTLED", f"{take_id}:{take.get('job_state')}")
    job_ids = {**(take.get("job_ids") or {}), **(fields.pop("job_ids", None) or {})}
    has_id = any(nonempty(value) for value in job_ids.values())
    if state in {"submitted", "succeeded"} and not has_id:
        raise ProjectError("SETTLE_REQUIRES_JOB_ID", take_id)
    if state == "succeeded" and not nonempty(fields.get("file")):
        raise ProjectError("SETTLE_REQUIRES_FILE", take_id)
    if state == "failed" and not nonempty(fields.get("failure_reason")):
        raise ProjectError("FAILED_REQUIRES_REASON", take_id)
    stamp = {"submitted_at": take.get("submitted_at") or when} if state == "submitted" else {"settled_at": when}
    kept = {key: value for key, value in fields.items() if value is not None}
    return replace_take(manifest, take_id, lambda old: {
        **old, **kept, **stamp, "job_state": state, "job_ids": job_ids})


def check_acceptance(acceptance: object) -> list[str]:
    """Problems that stop a take from being approved: all four checks, each with evidence."""
    if not isinstance(acceptance, dict):
        return [f"ACCEPTANCE_MISSING:{name}" for name in ACCEPTANCE_CHECKS]
    errors: list[str] = []
    for name in ACCEPTANCE_CHECKS:
        row = acceptance.get(name)
        if not isinstance(row, dict) or row.get("result") not in ACCEPTANCE_RESULTS:
            errors.append(f"ACCEPTANCE_MISSING:{name}")
        elif not nonempty(row.get("evidence")):
            errors.append(f"ACCEPTANCE_WITHOUT_EVIDENCE:{name}")
        elif row["result"] not in PASSING_RESULTS:
            errors.append(f"ACCEPTANCE_FAILED:{name}")
    return errors


def judge_take(manifest: dict[str, Any], take_id: str, verdict: str, acceptance: dict[str, Any],
               reason: str | None, when: str) -> dict[str, Any]:
    """Record per-shot acceptance and approve or reject the take."""
    take = find_take(manifest, take_id)
    if take.get("job_state") != "succeeded" or take.get("status") != "candidate":
        raise ProjectError("TAKE_NOT_AWAITING_ACCEPTANCE", f"{take_id}:{take.get('job_state')}:{take.get('status')}")
    if verdict == "approved":
        errors = check_acceptance(acceptance)
        if errors:
            raise ProjectError(errors[0], take_id)
        other = approved_take(manifest, take["shot_id"], take["tier"])
        if other is not None:
            raise ProjectError("MULTIPLE_APPROVED_TAKES", f"{take['shot_id']}:{other['take_id']}")
    elif not nonempty(reason):
        raise ProjectError("REJECTED_TAKE_REQUIRES_REASON", take_id)
    return replace_take(manifest, take_id, lambda old: {
        **old, "status": verdict, "reject_reason": reason if verdict == "rejected" else None,
        "acceptance": acceptance or None, "judged_at": when})
