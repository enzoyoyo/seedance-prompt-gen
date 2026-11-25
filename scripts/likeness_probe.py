#!/usr/bin/env python3
"""R2 likeness-moderation probe gate for `real_public_figures=true`.

Library only. When `release_intent.real_public_figures` is true, a text note alone cannot unlock
batch generation: each locked character used by a shot needs a settled `succeeded` take on the same
channel whose recorded `ref_sha256s` includes a current locked identity image of that character.
Re-locking a character's identity image changes its digest and invalidates old probes automatically.
The first shortest pending shot using an unprobed character serves as the single zero-extra-cost probe.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from drama_project import drama_block, resolve_in_project, section, sha256_file, take_rows
from validate_shot_spec import active_shots, channel_of, is_reuse, positive_number, resolve_ref, root_id, shot_rows

OPEN_STATES = frozenset({"preparing", "submitted", "unknown"})


def character_digests(project: Path, manifest: dict[str, Any]) -> dict[str, set[str]]:
    assets = section(drama_block(manifest), "identity_assets")
    chars = assets.get("characters")
    if not isinstance(chars, dict):
        return {}
    out: dict[str, set[str]] = {}
    for cid, row in chars.items():
        paths = row.get("paths") if isinstance(row, dict) else None
        digests = {
            sha256_file(p) for rel in (paths or [])
            if (p := resolve_in_project(project, rel)) is not None and p.is_file()
        }
        if digests:
            out[cid] = digests
    return out


def shot_ref_digests(project: Path, spec: dict[str, Any], shot: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for name in shot.get("refs") or []:
        resolved = resolve_ref(spec, project, name)
        if resolved is not None and resolved.is_file():
            found.add(sha256_file(resolved))
    return found


def shot_uses_character(project: Path, spec: dict[str, Any], shot: dict[str, Any],
                        cid: str, digests: set[str]) -> bool:
    if cid in (shot.get("actors") or []):
        return True
    return bool(shot_ref_digests(project, spec, shot) & digests)


def pending_for_char(project: Path, manifest: dict[str, Any], spec: dict[str, Any],
                     channel: str, tier: str, cid: str, digests: set[str]) -> list[dict[str, Any]]:
    rows = shot_rows(spec)
    live = {
        take.get("shot_id") for take in take_rows(manifest)
        if take.get("tier") == tier and take.get("status") != "rejected"
        and take.get("job_state") in (*OPEN_STATES, "succeeded")
    }
    return [
        row for row in active_shots(rows)
        if not is_reuse(row, tier) and channel_of(spec, row) == channel
        and positive_number(row.get("duration")) and root_id(rows, row["id"]) not in live
        and shot_uses_character(project, spec, row, cid, digests)
    ]


def char_probe_error(project: Path, manifest: dict[str, Any], spec: dict[str, Any],
                     shot: dict[str, Any], channel: str, tier: str, cid: str, digests: set[str]) -> str | None:
    same_channel = [
        t for t in take_rows(manifest)
        if t.get("provider") == channel and t.get("origin") != "reused"
        and bool(set(t.get("ref_sha256s") or []) & digests)
    ]
    if any(t.get("job_state") == "succeeded" for t in same_channel):
        return None
    # Only a non-retryable failure returned by the channel (a job ID exists and retry_eligible is not set)
    # is a likeness moderation verdict; local pre-submit or transient network failures remain retryable.
    if any(t.get("job_state") == "failed" and t.get("job_ids") and not t.get("retry_eligible") for t in same_channel):
        return f"LIKENESS_PROBE_FAILED:{channel}:{cid}"
    flying = [t for t in same_channel if t.get("job_state") in OPEN_STATES]
    if flying:
        return f"LIKENESS_PROBE_IN_FLIGHT:{channel}:{cid}:{flying[0].get('take_id')}"
    candidates = pending_for_char(project, manifest, spec, channel, tier, cid, digests)
    shortest = min((row["duration"] for row in candidates), default=None)
    allowed = sorted(row["id"] for row in candidates if row["duration"] == shortest)
    if shot["id"] not in allowed:
        return f"LIKENESS_PROBE_MISSING:{channel}:{cid}:probe_first={','.join(allowed)}"
    return None


def likeness_probe_errors(project: Path | None, manifest: dict[str, Any], spec: dict[str, Any],
                          shot: dict[str, Any], channel: str, tier: str) -> list[str]:
    if project is None:
        return []
    if section(drama_block(manifest), "release_intent").get("real_public_figures") is not True:
        return []
    errors: list[str] = []
    for cid, digests in sorted(character_digests(project, manifest).items()):
        if shot_uses_character(project, spec, shot, cid, digests):
            err = char_probe_error(project, manifest, spec, shot, channel, tier, cid, digests)
            if err:
                errors.append(err)
    return errors
