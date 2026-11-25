#!/usr/bin/env python3
"""Shared project I/O for the AI short-drama gates: paths, hashes, locked atomic manifest writes.

Library only. Nothing here calls a provider or knows a provider name.
"""
from __future__ import annotations

import contextlib
import copy
import fcntl
import hashlib
import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterator

MANIFEST_NAME = "resume-manifest.json"
SCRIPT_LOCK_NAME = "script.lock.json"
MANIFEST_VERSION = "1.0"
DEFAULT_FILE_MODE = 0o644
VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".webm", ".mkv", ".m4v"})
TIERS = ("draft", "lowres", "final")
JOB_STATES = frozenset({"preparing", "submitted", "unknown", "failed", "succeeded"})
# A take in one of these job states may already have cost money: never submit the shot again.
LIVE_JOB_STATES = frozenset({"preparing", "submitted", "unknown", "succeeded"})
RECOVER_JOB_STATES = frozenset({"preparing", "unknown"})
ACCEPTANCE_CHECKS = ("lines", "identity", "beat_action", "continuity")
ACCEPTANCE_RESULTS = frozenset({"pass", "deviation", "fail"})
NON_FRONT_ANGLES = frozenset({"three_quarter", "3_4", "profile", "side", "back", "rear", "turnaround"})
VALID_ANGLES = frozenset({"front"}) | NON_FRONT_ANGLES


class ProjectError(Exception):
    """A gate or input problem with a stable machine-readable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def parse_day(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectError("INPUT_ERROR", f"{path.name}:{type(exc).__name__}") from exc


def manifest_path(project: Path) -> Path:
    return project / MANIFEST_NAME


def load_manifest(project: Path) -> dict[str, Any]:
    path = manifest_path(project)
    if not path.is_file():
        raise ProjectError("MANIFEST_MISSING", MANIFEST_NAME)
    manifest = read_json(path)
    if not isinstance(manifest, dict):
        raise ProjectError("INPUT_ERROR", f"{MANIFEST_NAME}:not an object")
    return manifest


def drama_block(manifest: dict[str, Any]) -> dict[str, Any]:
    block = manifest.get("drama")
    block = block if isinstance(block, dict) else {}
    version = block.get("sop_version", manifest.get("sop_version"))
    mode = block.get("delivery_mode", manifest.get("delivery_mode"))
    if version == "3.0" or version is None and mode in ("images_only", "video_clips", "full_film"):
        fields = ("delivery_mode", "creative_mode", "story_mode", "image_model", "video_model", "audio_plan", "aspect_ratio")
        return {**{k: manifest[k] for k in fields if k in manifest}, **block, "sop_version": "3.0"}
    return block


def section(block: dict[str, Any], name: str) -> dict[str, Any]:
    value = block.get(name)
    return value if isinstance(value, dict) else {}


def take_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("takes")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def resolve_in_project(project: Path, relative: object) -> Path | None:
    """Resolve a recorded relative path; None when it is absent or escapes the project."""
    if not nonempty(relative):
        return None
    root = project.resolve()
    candidate = (root / str(relative)).resolve()
    return candidate if candidate == root or root in candidate.parents else None


def character_view_errors(assets: dict[str, Any]) -> list[str]:
    if assets.get("waived_multi_angle") is True:
        return []
    characters = assets.get("characters")
    if not isinstance(characters, dict) or not characters:
        return ["CHARACTER_VIEWS_NOT_LOCKED"]
    errors: list[str] = []
    for name, row in characters.items():
        angles = set(row.get("angles") or []) if isinstance(row, dict) else set()
        if not angles or not angles <= VALID_ANGLES:
            errors.append(f"CHARACTER_ANGLES_INVALID:{name}")
        elif "front" not in angles or not (angles & NON_FRONT_ANGLES):
            errors.append(f"CHARACTER_MULTI_ANGLE_MISSING:{name}")
    return errors


def scene_anchor_errors(project: Path, assets: dict[str, Any]) -> list[str]:
    if assets.get("waived_scenes") is True:
        return []
    scenes = assets.get("scenes")
    if not isinstance(scenes, dict) or not scenes:
        return ["SCENE_ANCHORS_NOT_LOCKED"]
    errors: list[str] = []
    for name, row in scenes.items():
        rel = row.get("path") if isinstance(row, dict) else None
        path = resolve_in_project(project, rel)
        if path is None or not path.is_file() or sha256_file(path) != row.get("sha256"):
            errors.append(f"SCENE_ASSET_CHANGED:{name}")
    return errors


def decision_errors(project: Path, record: dict[str, Any], chosen: list[dict[str, Any]], prefix: str) -> list[str]:
    """A lock must carry the consumed presentation it was decided from, and choose only presented files."""
    decision = section(record, "decision")
    sheets = decision.get("sheets")
    if (not all(nonempty(decision.get(k)) for k in ("presented_at", "decided_at", "salt", "code_hash"))
            or not isinstance(sheets, list) or not sheets or not isinstance(decision.get("candidates"), list)):
        return [f"{prefix}_DECISION_MISSING"]
    errors = []
    for row in sheets:
        path = resolve_in_project(project, row.get("path") if isinstance(row, dict) else None)
        if path is None or not path.is_file() or sha256_file(path) != row.get("sha256"):
            errors.append(f"DECISION_SHEET_CHANGED:{row.get('path') if isinstance(row, dict) else row}")
    shown = {(row.get("path"), row.get("sha256")) for row in decision["candidates"] if isinstance(row, dict)}
    errors += [f"CHOICE_NOT_PRESENTED:{row.get('path')}" for row in chosen
               if (row.get("path"), row.get("sha256")) not in shown]
    return errors


def identity_errors(project: Path, drama: dict[str, Any], require_decision: bool = True) -> list[str]:
    """Multi-angle character refs and scene anchors must be user-chosen, locked, and unchanged."""
    assets = section(drama, "identity_assets")
    refs = assets.get("refs")
    if (not nonempty(assets.get("locked_at")) or not nonempty(assets.get("user_words"))
            or not isinstance(refs, list) or not refs):
        return ["IDENTITY_ASSETS_NOT_LOCKED"]
    if require_decision:
        found = decision_errors(project, assets, [r for r in refs if isinstance(r, dict)], "IDENTITY")
        if found:
            return found
    errors: list[str] = []
    for row in refs:
        name = row.get("path") if isinstance(row, dict) else None
        path = resolve_in_project(project, name)
        if path is None or not path.is_file() or sha256_file(path) != row.get("sha256"):
            errors.append(f"IDENTITY_ASSET_CHANGED:{name}")
    errors += character_view_errors(assets) + scene_anchor_errors(project, assets)
    if section(drama, "release_intent").get("real_public_figures") is True:
        if not nonempty(assets.get("likeness_preflight")):
            errors.append("LIKENESS_MODERATION_PREFLIGHT_MISSING")
    return errors


def previs_errors(project: Path, drama: dict[str, Any], require_decision: bool = True) -> list[str]:
    """Whitemodel & spatial blocking boards in 00_previs/ must be user-approved before shot spec."""
    previs = section(drama, "previs")
    if not nonempty(previs.get("locked_at")) or not nonempty(previs.get("user_words")):
        return ["PREVIS_NOT_LOCKED"]
    extra_refs = [row for row in (previs.get("extra_refs") or []) if isinstance(row, dict)]
    if require_decision:
        chosen = [row for row in [*section(previs, "scenes").values(), *extra_refs] if isinstance(row, dict)]
        found = decision_errors(project, previs, chosen, "PREVIS")
        if found:
            return found
    if previs.get("waived") is True:
        return []
    scenes = previs.get("scenes")
    if not isinstance(scenes, dict) or not (scenes or previs.get("waived_scenes")):
        return ["PREVIS_SCENES_EMPTY"]
    errors: list[str] = []
    entries = [(str(scene_id), row) for scene_id, row in scenes.items()]
    entries += [(f"ref_{idx}", row) for idx, row in enumerate(extra_refs, 1)]
    for label, row in entries:
        rel = row.get("path") if isinstance(row, dict) else None
        path = resolve_in_project(project, rel)
        if not nonempty(rel) or not str(rel).replace("\\", "/").startswith("00_previs/"):
            errors.append(f"PREVIS_OUTSIDE_00_PREVIS:{label}")
        elif path is None or not path.is_file() or sha256_file(path) != row.get("sha256"):
            errors.append(f"PREVIS_ASSET_CHANGED:{label}")
    return errors


def write_json_atomic(path: Path, payload: Any) -> None:
    """Write through a temp file in the same directory, then rename over the target."""
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    mode = path.stat().st_mode & 0o777 if path.exists() else DEFAULT_FILE_MODE
    try:
        os.chmod(temp_name, mode)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise


@contextlib.contextmanager
def file_lock(target: Path) -> Iterator[None]:
    """Exclusive advisory lock so parallel submitters cannot interleave ledger writes."""
    lock_path = target.with_name(f".{target.name}.lock")
    with lock_path.open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def update_manifest(
    project: Path, mutate: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Read, transform and atomically rewrite the manifest under the ledger lock.

    `mutate` receives a private copy and returns the new manifest; raising aborts the write.
    """
    path = manifest_path(project)
    with file_lock(path):
        updated = mutate(copy.deepcopy(load_manifest(project)))
        write_json_atomic(path, updated)
    return updated
