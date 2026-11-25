#!/usr/bin/env python3
"""Validate the first-batch platform evidence ledger.

Repository and planning are implemented as deterministic offline stages. The
publish stage is intentionally fail-closed until a reachable, tested project
receipt pipeline exists. This module never fetches a URL, logs in, opens media,
or treats a repository pass as publication approval.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "references" / "platform-evidence-ledger.jsonl"
SCHEMA_VERSION = 1
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

MANIFEST_FIELDS = {
    "schema_version",
    "record_type",
    "ledger_id",
    "required_coverage_keys",
    "planning_source_classes",
    "authority_hosts",
    "coverage_requirements",
}
CLAIM_FIELDS = {
    "schema_version",
    "record_type",
    "claim_id",
    "rule_key",
    "revision",
    "coverage_key",
    "claim_class",
    "claim_text",
    "scope",
    "norm",
    "source",
    "temporal",
    "evidence",
    "notes",
}
REQUIREMENT_FIELDS = {"coverage_key", "required_for_publish", "scope"}
SCOPE_FIELDS = {"markets", "platforms", "product_modes", "actors"}
NORM_FIELDS = {"kind", "action"}
SOURCE_FIELDS = {"publisher", "source_class", "url", "title", "locator", "locale"}
TEMPORAL_FIELDS = {"published_at", "effective_from", "effective_until", "version_id"}
EVIDENCE_FIELDS = {
    "access",
    "observed_at",
    "review_ref",
    "review_locator",
    "review_sha256",
    "source_body_sha256",
    "semantic_digest",
    "reviewed_by",
}
SEMANTIC_FIELDS = {
    "rule_key",
    "coverage_key",
    "claim_class",
    "claim_text",
    "scope",
    "norm",
    "source",
    "temporal",
}
CLAIM_CLASSES = {"publish_rule", "ui_capability", "distribution_signal", "informational"}
ACCESS_VALUES = {
    "body",
    "rendered_ui",
    "official_url_only",
    "metadata_only",
    "blocked",
    "search_snippet",
}
BODY_ACCESS = {"body", "rendered_ui"}
NON_BODY_ACCESS = ACCESS_VALUES - BODY_ACCESS
NORM_KINDS = {"require", "prohibit", "permit", "informational"}
FORBIDDEN_DERIVED_FIELDS = {
    "fresh",
    "publishable",
    "material_change",
    "active_version",
    "content_usable",
}
SECRET_KEY_FRAGMENTS = {"token", "password", "cookie", "secret", "api_key", "authorization"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".tiff", ".bmp"}


def _problem(code: str, message: str, **context: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "message": message}
    item.update(context)
    return item


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _has_secret_key(value: Any) -> bool:
    for key in _walk_keys(value):
        normalized = key.lower().replace("-", "_")
        if any(fragment in normalized for fragment in SECRET_KEY_FRAGMENTS):
            return True
    return False


def _is_image_ref(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if value.lower().startswith("data:image/"):
        return True
    path = urlsplit(value).path if "://" in value else value.split("#", 1)[0]
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


def _has_screenshot_reference(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if "screenshot" in normalized:
                return True
            if normalized.endswith("_ref") and _is_image_ref(child):
                return True
            if _has_screenshot_reference(child):
                return True
    elif isinstance(value, list):
        return any(_has_screenshot_reference(child) for child in value)
    return False


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and HASH_RE.fullmatch(value) is not None


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _parse_rfc3339(value: Any, label: str, errors: list[dict[str, Any]]) -> datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(_problem("INVALID_TIMESTAMP", f"{label} must be RFC3339 with a timezone"))
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(_problem("INVALID_TIMESTAMP", f"{label} must be RFC3339 with a timezone"))
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        errors.append(_problem("TIMEZONE_REQUIRED", f"{label} must include a timezone offset"))
        return None
    return parsed


def _parse_date(value: Any, label: str, errors: list[dict[str, Any]]) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(_problem("INVALID_DATE", f"{label} must be YYYY-MM-DD or null"))
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(_problem("INVALID_DATE", f"{label} must be YYYY-MM-DD or null"))
        return None


def _unknown_fields(row: dict[str, Any], allowed: set[str], label: str) -> list[dict[str, Any]]:
    return [
        _problem("UNKNOWN_FIELD", f"{label} has unknown field: {name}")
        for name in sorted(set(row) - allowed)
    ]


def semantic_digest(claim: dict[str, Any]) -> str:
    """Hash proposition semantics; observation and publication dates are excluded."""
    source = claim.get("source") if isinstance(claim.get("source"), dict) else {}
    payload = {
        "claim_text": claim.get("claim_text"),
        "scope": claim.get("scope"),
        "norm": claim.get("norm"),
        "source": {
            "publisher": source.get("publisher"),
            "url": source.get("url"),
            "locator": source.get("locator"),
            "locale": source.get("locale"),
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [_problem("LEDGER_READ_ERROR", str(exc), path=str(path))]
    for line_number, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(_problem("INVALID_JSON", str(exc), line=line_number))
            continue
        if not isinstance(row, dict):
            errors.append(_problem("INVALID_RECORD", "each JSONL line must be an object", line=line_number))
            continue
        rows.append(row)
    return rows, errors


def _validate_scope(scope: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(scope, dict):
        return [_problem("INVALID_SCOPE", f"{label} must be an object")]
    errors = _unknown_fields(scope, SCOPE_FIELDS, label)
    for field in SCOPE_FIELDS:
        values = scope.get(field)
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(item, str) or not item for item in values)
            or len(values) != len(set(values))
        ):
            errors.append(_problem("INVALID_SCOPE", f"{label}.{field} must be a unique non-empty string list"))
    return errors


def _host_allowed(url: str, allowed: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == item.lower() or host.endswith(f".{item.lower()}") for item in allowed)


def _validate_manifest(row: dict[str, Any]) -> list[dict[str, Any]]:
    errors = _unknown_fields(row, MANIFEST_FIELDS, "manifest")
    if row.get("schema_version") != SCHEMA_VERSION or row.get("record_type") != "manifest":
        errors.append(_problem("INVALID_MANIFEST", "manifest schema_version or record_type is invalid"))
    if not isinstance(row.get("ledger_id"), str) or not row.get("ledger_id"):
        errors.append(_problem("INVALID_MANIFEST", "ledger_id is required"))

    coverage = row.get("required_coverage_keys")
    if (
        not isinstance(coverage, list)
        or not coverage
        or any(not isinstance(item, str) or not item for item in coverage)
        or len(coverage) != len(set(coverage))
    ):
        errors.append(_problem("INVALID_MANIFEST", "required_coverage_keys must be a unique non-empty string list"))
        coverage = []

    source_classes = row.get("planning_source_classes")
    if (
        not isinstance(source_classes, list)
        or not source_classes
        or any(not isinstance(item, str) or not item for item in source_classes)
        or len(source_classes) != len(set(source_classes))
    ):
        errors.append(_problem("INVALID_MANIFEST", "planning_source_classes must be a unique non-empty string list"))

    hosts = row.get("authority_hosts")
    if not isinstance(hosts, dict) or not hosts:
        errors.append(_problem("INVALID_MANIFEST", "authority_hosts must be a non-empty object"))
    else:
        for publisher, values in hosts.items():
            if (
                not isinstance(publisher, str)
                or not publisher
                or not isinstance(values, list)
                or not values
                or any(not isinstance(item, str) or not item for item in values)
            ):
                errors.append(_problem("INVALID_MANIFEST", "each authority must have a publisher and host list"))

    requirements = row.get("coverage_requirements")
    requirement_keys: list[str] = []
    if not isinstance(requirements, list) or not requirements:
        errors.append(_problem("INVALID_MANIFEST", "coverage_requirements must be non-empty"))
    else:
        for index, requirement in enumerate(requirements):
            label = f"coverage_requirements[{index}]"
            if not isinstance(requirement, dict):
                errors.append(_problem("INVALID_MANIFEST", f"{label} must be an object"))
                continue
            errors.extend(_unknown_fields(requirement, REQUIREMENT_FIELDS, label))
            if set(requirement) != REQUIREMENT_FIELDS:
                errors.append(_problem("INVALID_MANIFEST", f"{label} must contain the complete requirement schema"))
            key = requirement.get("coverage_key")
            if not isinstance(key, str) or key not in coverage:
                errors.append(_problem("INVALID_MANIFEST", f"{label} names an undeclared coverage key"))
            else:
                requirement_keys.append(key)
            if not isinstance(requirement.get("required_for_publish"), bool):
                errors.append(_problem("INVALID_MANIFEST", f"{label}.required_for_publish must be boolean"))
            errors.extend(_validate_scope(requirement.get("scope"), f"{label}.scope"))
    if coverage and (len(requirement_keys) != len(set(requirement_keys)) or set(requirement_keys) != set(coverage)):
        errors.append(_problem("INVALID_MANIFEST", "coverage_requirements must cover each required key exactly once"))
    return errors


def _review_path(review_ref: str, ledger_path: Path) -> tuple[Path | None, str | None]:
    raw = Path(review_ref)
    if raw.is_absolute():
        return None, "review_ref must be relative to the installed Skill"
    resolved = (ledger_path.parent / raw).resolve()
    skill_root = ledger_path.parent.parent.resolve()
    try:
        resolved.relative_to(skill_root)
    except ValueError:
        return None, "review_ref must resolve inside the installed Skill"
    return resolved, None


def _validate_claim(row: dict[str, Any], manifest: dict[str, Any], ledger_path: Path) -> list[dict[str, Any]]:
    claim_id = row.get("claim_id")
    label = f"claim {claim_id or '<missing>'}"
    errors = _unknown_fields(row, CLAIM_FIELDS, label)
    if row.get("schema_version") != SCHEMA_VERSION or row.get("record_type") != "claim":
        errors.append(_problem("INVALID_CLAIM", f"{label} schema_version or record_type is invalid"))
    for field in ("claim_id", "rule_key", "coverage_key"):
        if not isinstance(row.get(field), str) or not row.get(field):
            errors.append(_problem("INVALID_CLAIM", f"{label}.{field} is required"))
    revision = row.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        errors.append(_problem("INVALID_REVISION", f"{label}.revision must be a positive integer"))
    if row.get("coverage_key") not in manifest.get("required_coverage_keys", []):
        errors.append(_problem("UNKNOWN_COVERAGE", f"{label} uses an undeclared coverage key"))
    if row.get("claim_class") not in CLAIM_CLASSES:
        errors.append(_problem("INVALID_CLAIM_CLASS", f"{label}.claim_class is invalid"))
    errors.extend(_validate_scope(row.get("scope"), f"{label}.scope"))

    source = row.get("source")
    if not isinstance(source, dict):
        errors.append(_problem("INVALID_SOURCE", f"{label}.source must be an object"))
        source = {}
    else:
        errors.extend(_unknown_fields(source, SOURCE_FIELDS, f"{label}.source"))
    url = source.get("url")
    if not isinstance(url, str) or urlsplit(url).scheme != "https" or not urlsplit(url).hostname:
        errors.append(_problem("INVALID_SOURCE_URL", f"{label}.source.url must be an https URL"))
    publisher = source.get("publisher")
    hosts = manifest.get("authority_hosts", {}).get(publisher)
    if not isinstance(hosts, list):
        errors.append(_problem("UNKNOWN_AUTHORITY", f"{label}.source.publisher is not in authority_hosts"))
    elif isinstance(url, str) and not _host_allowed(url, hosts):
        errors.append(_problem("AUTHORITY_HOST_MISMATCH", f"{label} URL host does not match its publisher"))
    if source.get("source_class") not in manifest.get("planning_source_classes", []):
        errors.append(_problem("UNTRUSTED_SOURCE_CLASS", f"{label}.source.source_class is not planning-eligible"))
    if not isinstance(source.get("title"), str) or not source.get("title"):
        errors.append(_problem("INVALID_SOURCE", f"{label}.source.title is required"))
    if not isinstance(source.get("locator"), list):
        errors.append(_problem("INVALID_SOURCE", f"{label}.source.locator must be a list"))
    if source.get("locale") is not None and not isinstance(source.get("locale"), str):
        errors.append(_problem("INVALID_SOURCE", f"{label}.source.locale must be string or null"))

    temporal = row.get("temporal")
    if not isinstance(temporal, dict):
        errors.append(_problem("INVALID_TEMPORAL", f"{label}.temporal must be an object"))
        temporal = {}
    else:
        errors.extend(_unknown_fields(temporal, TEMPORAL_FIELDS, f"{label}.temporal"))
    _parse_date(temporal.get("published_at"), f"{label}.temporal.published_at", errors)
    effective_from = _parse_date(temporal.get("effective_from"), f"{label}.temporal.effective_from", errors)
    effective_until = _parse_date(temporal.get("effective_until"), f"{label}.temporal.effective_until", errors)
    if effective_from is not None and effective_until is not None and effective_until <= effective_from:
        errors.append(_problem("INVALID_EFFECTIVE_WINDOW", f"{label} effective_until must be later than effective_from"))
    if temporal.get("version_id") is not None and not isinstance(temporal.get("version_id"), str):
        errors.append(_problem("INVALID_TEMPORAL", f"{label}.temporal.version_id must be string or null"))

    evidence = row.get("evidence")
    if not isinstance(evidence, dict):
        errors.append(_problem("INVALID_EVIDENCE", f"{label}.evidence must be an object"))
        evidence = {}
    else:
        errors.extend(_unknown_fields(evidence, EVIDENCE_FIELDS, f"{label}.evidence"))
    access = evidence.get("access")
    if access not in ACCESS_VALUES:
        errors.append(_problem("INVALID_ACCESS", f"{label}.evidence.access is invalid"))
    _parse_rfc3339(evidence.get("observed_at"), f"{label}.evidence.observed_at", errors)
    if not isinstance(evidence.get("reviewed_by"), str) or not evidence.get("reviewed_by"):
        errors.append(_problem("INVALID_EVIDENCE", f"{label}.evidence.reviewed_by is required"))
    if not isinstance(evidence.get("review_locator"), str) or not evidence.get("review_locator"):
        errors.append(_problem("INVALID_EVIDENCE", f"{label}.evidence.review_locator is required"))

    review_ref = evidence.get("review_ref")
    if _is_image_ref(review_ref):
        errors.append(_problem("SCREENSHOT_FORBIDDEN", f"{label}.evidence.review_ref must be a text artifact"))
    elif not isinstance(review_ref, str) or not review_ref:
        errors.append(_problem("INVALID_REVIEW_REF", f"{label}.evidence.review_ref is required"))
    else:
        review_path, path_error = _review_path(review_ref, ledger_path)
        if path_error:
            errors.append(_problem("EXTERNAL_REVIEW_REF_FORBIDDEN", path_error))
        elif review_path is not None and not review_path.is_file():
            errors.append(_problem("MISSING_REVIEW_REF", f"{label}.evidence.review_ref does not exist", path=str(review_path)))
        elif review_path is not None and _valid_hash(evidence.get("review_sha256")) and _file_hash(review_path) != evidence.get("review_sha256"):
            errors.append(_problem("REVIEW_HASH_MISMATCH", f"{label}.evidence.review_sha256 does not match review_ref"))
    if not _valid_hash(evidence.get("review_sha256")):
        errors.append(_problem("INVALID_HASH", f"{label}.evidence.review_sha256 must be sha256:<hex>"))
    if evidence.get("source_body_sha256") is not None and not _valid_hash(evidence.get("source_body_sha256")):
        errors.append(_problem("INVALID_HASH", f"{label}.evidence.source_body_sha256 must be sha256:<hex> or null"))

    claim_text = row.get("claim_text")
    norm = row.get("norm")
    if access in BODY_ACCESS:
        if not isinstance(claim_text, str) or not claim_text.strip():
            errors.append(_problem("UNREAD_CLAIM_PROMOTED", f"{label} body evidence requires an atomic claim"))
        if (
            not isinstance(norm, dict)
            or set(norm) != NORM_FIELDS
            or norm.get("kind") not in NORM_KINDS
            or not isinstance(norm.get("action"), str)
            or not norm.get("action")
        ):
            errors.append(_problem("INVALID_NORM", f"{label}.norm must contain semantic kind and action"))
        if not source.get("locator"):
            errors.append(_problem("MISSING_LOCATOR", f"{label} body evidence requires an official-source locator"))
        if evidence.get("semantic_digest") != semantic_digest(row):
            errors.append(_problem("SEMANTIC_DIGEST_MISMATCH", f"{label}.evidence.semantic_digest does not match the proposition"))
    elif access in NON_BODY_ACCESS:
        if claim_text is not None or norm is not None or evidence.get("semantic_digest") is not None:
            errors.append(_problem("UNREAD_CLAIM_PROMOTED", f"{label} non-body evidence cannot carry an operative claim or digest"))
    if not isinstance(row.get("notes"), list) or any(not isinstance(item, str) for item in row.get("notes", [])):
        errors.append(_problem("INVALID_CLAIM", f"{label}.notes must be a string list"))
    return errors


def _scope_values_overlap(left: list[str], right: list[str]) -> bool:
    return "*" in left or "*" in right or bool(set(left) & set(right))


def _scopes_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    try:
        return all(_scope_values_overlap(left[field], right[field]) for field in SCOPE_FIELDS)
    except (KeyError, TypeError):
        return False


def _windows_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    try:
        left_start = date.fromisoformat(left["effective_from"]) if left.get("effective_from") else date.min
        right_start = date.fromisoformat(right["effective_from"]) if right.get("effective_from") else date.min
        left_end = date.fromisoformat(left["effective_until"]) if left.get("effective_until") else date.max
        right_end = date.fromisoformat(right["effective_until"]) if right.get("effective_until") else date.max
    except (TypeError, ValueError):
        return False
    return max(left_start, right_start) < min(left_end, right_end)


def validate_ledger(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    rows, errors = _load_jsonl(path)
    for row in rows:
        if _has_secret_key(row):
            errors.append(_problem("SECRET_FIELD_FORBIDDEN", "ledger records cannot contain credential-bearing fields"))
        if _has_screenshot_reference(row):
            errors.append(_problem("SCREENSHOT_FORBIDDEN", "ledger records cannot contain screenshot references"))
        forbidden = sorted(FORBIDDEN_DERIVED_FIELDS & set(_walk_keys(row)))
        if forbidden:
            errors.append(_problem("DERIVED_FIELD_FORBIDDEN", "derived gate fields cannot be stored", fields=forbidden))

    manifests = [row for row in rows if row.get("record_type") == "manifest"]
    if len(manifests) != 1:
        errors.append(_problem("MANIFEST_COUNT", "ledger must contain exactly one manifest"))
        return None, errors, []
    manifest = manifests[0]
    errors.extend(_validate_manifest(manifest))

    claims = [row for row in rows if row.get("record_type") == "claim"]
    unknown_types = [row.get("record_type") for row in rows if row.get("record_type") not in {"manifest", "claim"}]
    if unknown_types:
        errors.append(_problem("UNKNOWN_RECORD_TYPE", "ledger contains unknown record types", record_types=unknown_types))
    for claim in claims:
        errors.extend(_validate_claim(claim, manifest, path))

    by_claim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_pairs: set[tuple[str, int]] = set()
    for claim in claims:
        claim_id = claim.get("claim_id")
        revision = claim.get("revision")
        if not isinstance(claim_id, str) or not isinstance(revision, int) or isinstance(revision, bool):
            continue
        pair = (claim_id, revision)
        if pair in seen_pairs:
            errors.append(_problem("DUPLICATE_REVISION", "claim_id + revision must be unique", claim_id=claim_id, revision=revision))
        seen_pairs.add(pair)
        by_claim[claim_id].append(claim)

    for claim_id, revisions in by_claim.items():
        ordered = sorted(revisions, key=lambda row: row["revision"])
        if [row["revision"] for row in ordered] != list(range(1, len(ordered) + 1)):
            errors.append(_problem("REVISION_GAP", "claim revisions must start at 1 and be contiguous", claim_id=claim_id))
        first = ordered[0]
        previous_observed: datetime | None = None
        for revision in ordered:
            if any(revision.get(field) != first.get(field) for field in SEMANTIC_FIELDS):
                errors.append(_problem("SEMANTIC_CHANGE_REQUIRES_NEW_CLAIM", "a revision may refresh evidence but not change semantics", claim_id=claim_id))
            local_errors: list[dict[str, Any]] = []
            evidence = revision.get("evidence") if isinstance(revision.get("evidence"), dict) else {}
            observed = _parse_rfc3339(evidence.get("observed_at"), "observed_at", local_errors)
            if observed is not None and previous_observed is not None and observed <= previous_observed:
                errors.append(_problem("NON_MONOTONIC_OBSERVATION", "revision observed_at must increase", claim_id=claim_id))
            previous_observed = observed or previous_observed

    latest = [max(revisions, key=lambda row: row["revision"]) for revisions in by_claim.values()]
    by_rule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in latest:
        if isinstance(claim.get("rule_key"), str):
            by_rule[claim["rule_key"]].append(claim)
    for rule_key, versions in by_rule.items():
        for index, left in enumerate(versions):
            for right in versions[index + 1 :]:
                if (
                    left.get("claim_id") != right.get("claim_id")
                    and _scopes_overlap(left.get("scope", {}), right.get("scope", {}))
                    and _windows_overlap(left.get("temporal", {}), right.get("temporal", {}))
                ):
                    errors.append(_problem("OVERLAPPING_RULE_VERSIONS", "effective versions for one rule_key overlap", rule_key=rule_key, claims=[left.get("claim_id"), right.get("claim_id")]))

    present_coverage = {claim.get("coverage_key") for claim in claims}
    missing = sorted(set(manifest.get("required_coverage_keys", [])) - present_coverage)
    if missing:
        errors.append(_problem("MISSING_COVERAGE", "required coverage is absent", coverage_keys=missing))
    warnings = [
        _problem(
            "OFFICIAL_URL_ONLY",
            "the official pointer is registered but no operative body claim was accepted",
            coverage_key=claim.get("coverage_key"),
            claim_id=claim.get("claim_id"),
        )
        for claim in latest
        if isinstance(claim.get("evidence"), dict) and claim["evidence"].get("access") in NON_BODY_ACCESS
    ]
    return {"manifest": manifest, "claims": claims, "ledger_path": str(path)}, errors, warnings


def _scope_matches(scope: dict[str, Any], target: dict[str, str]) -> bool:
    mapping = {"platforms": "platform", "markets": "market", "product_modes": "product_mode", "actors": "actor"}
    try:
        return all("*" in scope[field] or target[key] in scope[field] for field, key in mapping.items())
    except (KeyError, TypeError):
        return False


def _active_on(claim: dict[str, Any], day: date) -> bool:
    temporal = claim["temporal"]
    start = date.fromisoformat(temporal["effective_from"]) if temporal.get("effective_from") else date.min
    end = date.fromisoformat(temporal["effective_until"]) if temporal.get("effective_until") else date.max
    return start <= day < end


def _latest_known(claims: list[dict[str, Any]], as_of: datetime) -> list[dict[str, Any]]:
    by_claim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        local_errors: list[dict[str, Any]] = []
        observed = _parse_rfc3339(claim["evidence"]["observed_at"], "observed_at", local_errors)
        if observed is not None and observed <= as_of:
            by_claim[claim["claim_id"]].append(claim)
    return [max(revisions, key=lambda row: row["revision"]) for revisions in by_claim.values()]


def _content_usable(claim: dict[str, Any], manifest: dict[str, Any]) -> bool:
    evidence = claim["evidence"]
    return (
        evidence.get("access") in BODY_ACCESS
        and claim["source"].get("source_class") in manifest.get("planning_source_classes", [])
        and bool(claim["source"].get("locator"))
        and _valid_hash(evidence.get("review_sha256"))
        and evidence.get("semantic_digest") == semantic_digest(claim)
    )


def evaluate(
    bundle: dict[str, Any],
    stage: str,
    as_of: datetime,
    target: dict[str, str] | None = None,
    account_context: str | None = None,
    authoritative: bool = False,
) -> dict[str, Any]:
    if stage == "repository":
        return {
            "verdict": "PASS",
            "stage": "repository",
            "authoritative": False,
            "as_of": as_of.isoformat(),
            "publishable": False,
            "applicable_claims": [],
            "blockers": [],
            "warnings": [],
        }
    if stage not in {"planning", "publish"} or target is None:
        raise ValueError("planning and publish require a complete target scope")

    manifest = bundle["manifest"]
    known = _latest_known(bundle["claims"], as_of)
    applicable = [claim for claim in known if _scope_matches(claim["scope"], target)]
    requirements = [
        item
        for item in manifest["coverage_requirements"]
        if item["required_for_publish"] and _scope_matches(item["scope"], target)
    ]
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    active_rules: list[dict[str, Any]] = []
    if not requirements:
        blockers.append(_problem("UNSUPPORTED_TARGET_SCOPE", "the ledger has no contract for this platform/market/product/actor"))
    for requirement in requirements:
        candidates = [
            claim
            for claim in applicable
            if claim["coverage_key"] == requirement["coverage_key"]
            and claim["claim_class"] == "publish_rule"
            and _active_on(claim, as_of.date())
        ]
        if not candidates:
            blockers.append(_problem("NO_ACTIVE_PUBLISH_RULE", "no active publish rule covers the target", coverage_key=requirement["coverage_key"]))
            continue
        active_rules.extend(candidates)
        for claim in candidates:
            if not _content_usable(claim, manifest):
                blockers.append(_problem("OFFICIAL_BODY_UNCONFIRMED", "an active rule has no usable reviewed body", claim_id=claim["claim_id"]))

    active_rules = list({(claim["claim_id"], claim["revision"]): claim for claim in active_rules}.values())
    for claim in applicable:
        if claim["evidence"].get("access") in NON_BODY_ACCESS:
            warnings.append(_problem("UNREAD_OFFICIAL_POINTER", "an official pointer has no operative body claim", claim_id=claim["claim_id"]))
        effective_from = claim["temporal"].get("effective_from")
        if effective_from and date.fromisoformat(effective_from) > as_of.date():
            warnings.append(_problem("PENDING_TRANSITION", "a later effective version is registered but not active", claim_id=claim["claim_id"], effective_from=effective_from))

    if stage == "planning":
        return {
            "verdict": "PLANNING_ONLY",
            "stage": "planning",
            "authoritative": False,
            "as_of": as_of.isoformat(),
            "publishable": False,
            "applicable_claims": sorted({claim["claim_id"] for claim in active_rules}),
            "blockers": blockers,
            "warnings": warnings,
        }

    if not isinstance(account_context, str) or not ALIAS_RE.fullmatch(account_context):
        blockers.append(_problem("ACCOUNT_CONTEXT_REQUIRED", "publish requires a non-secret account alias"))
    for claim in active_rules:
        if not _valid_hash(claim["evidence"].get("source_body_sha256")):
            blockers.append(_problem("DIRECT_BODY_CAPTURE_REQUIRED", "publish requires a reviewed normalized official-body hash", claim_id=claim["claim_id"]))
    blockers.append(
        _problem(
            "SAME_DAY_ACCOUNT_MARKET_PRODUCT_RECEIPT_REQUIRED",
            "publish requires a same-day receipt for the exact account, market, and product mode; receipt matching is intentionally deferred in the first batch",
        )
    )
    return {
        "verdict": "BLOCK",
        "stage": "publish",
        "authoritative": bool(authoritative),
        "as_of": as_of.isoformat(),
        "publishable": False,
        "applicable_claims": sorted({claim["claim_id"] for claim in active_rules}),
        "blockers": blockers,
        "warnings": warnings,
    }


def _target_from_args(args: argparse.Namespace) -> dict[str, str] | None:
    if args.stage == "repository":
        return None
    values = {
        "platform": args.platform,
        "market": args.market,
        "product_mode": args.product_mode,
        "actor": args.actor,
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ValueError(f"{args.stage} requires: {', '.join(missing)}")
    return values  # type: ignore[return-value]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--stage", choices=("repository", "planning", "publish"), required=True)
    parser.add_argument("--as-of", help="RFC3339 with timezone; forbidden for production publish")
    parser.add_argument("--platform")
    parser.add_argument("--market")
    parser.add_argument("--product-mode")
    parser.add_argument("--actor")
    parser.add_argument("--account-context")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.stage == "publish" and args.as_of:
        parser.error("production publish forbids --as-of; it uses the real current clock")

    parse_errors: list[dict[str, Any]] = []
    as_of = _parse_rfc3339(args.as_of, "--as-of", parse_errors) if args.as_of else datetime.now().astimezone()
    if as_of is None:
        print(json.dumps({"verdict": "INVALID", "stage": args.stage, "errors": parse_errors}, ensure_ascii=False, indent=2))
        return 1
    try:
        target = _target_from_args(args)
    except ValueError as exc:
        parser.error(str(exc))

    bundle, errors, ledger_warnings = validate_ledger(args.ledger)
    if bundle is None or errors:
        print(json.dumps({"verdict": "INVALID", "stage": args.stage, "errors": errors, "warnings": ledger_warnings}, ensure_ascii=False, indent=2))
        return 1
    result = evaluate(
        bundle,
        args.stage,
        as_of,
        target=target,
        account_context=args.account_context,
        authoritative=args.stage == "publish",
    )
    if args.stage == "repository":
        result["warnings"] = ledger_warnings + result["warnings"]
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result["verdict"])
    return 2 if args.stage == "publish" else 0


if __name__ == "__main__":
    raise SystemExit(main())
