#!/usr/bin/env python3
"""Previs coverage and provenance: every script scene decided or waived, boards backed by their sidecar,
and shots tied to the chosen board of their scene.

Library only. A shot's scene comes from the beat ids it declares (`beat` / `beats`), and a beat's scene
is the part before `-B<n>` in the locked script's beat tags, e.g. beat `S3-B2` belongs to scene `S3`.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from check_script_coverage import parse_script
from drama_project import (
    ProjectError, decision_errors, drama_block, identity_errors, load_manifest, nonempty,
    previs_errors, read_json, resolve_in_project, section, sha256_file,
)
from lock_script import locked_script_text, read_lock
from validate_shot_spec import active_shots, is_reuse, resolve_ref, shot_beats, shot_rows

SCENE_OF_BEAT_RE = re.compile(r"^(?P<scene>[A-Za-z][A-Za-z0-9_]*)-B\d+[A-Za-z0-9_]*$")
SIDECAR_SUFFIX = ".blocking.json"
BOARD_TOOL = "whitemodel_board"
VIEW_ORDER = ("front", "three_quarter", "profile", "back")
ANGLE_ALIASES = {"3_4": "three_quarter", "side": "profile", "rear": "back"}


def scene_of_beat(beat: str) -> str | None:
    match = SCENE_OF_BEAT_RE.match(beat)
    return match.group("scene") if match else None


def script_beats(project: Path) -> list[str] | None:
    """Beat ids of the locked script in order; None while no script is locked."""
    lock = read_lock(project)
    if lock is None:
        return None
    beats = lock.get("beats")
    return beats if isinstance(beats, list) else parse_script(locked_script_text(project))[0]


def script_scenes(project: Path) -> list[str] | None:
    beats = script_beats(project)
    if beats is None:
        return None
    return list(dict.fromkeys(scene for scene in map(scene_of_beat, beats) if scene))


def sidecar_path(project: Path, board_rel: str) -> Path | None:
    board = resolve_in_project(project, board_rel)
    return board.with_name(board.name[: -len(board.suffix)] + SIDECAR_SUFFIX) if board else None


def load_sidecar(project: Path, board_rel: str) -> dict[str, Any] | None:
    path = sidecar_path(project, board_rel)
    if path is None or not path.is_file():
        return None
    try:
        data = read_json(path)
    except ProjectError:
        return {}
    return data if isinstance(data, dict) else {}


def sidecar_errors(project: Path, scene: str, row: dict[str, Any]) -> list[str]:
    """A `whitemodel_board` choice must be the board its own valid sidecar describes, digests intact."""
    meta = load_sidecar(project, str(row.get("path")))
    if meta is None:
        return [f"PREVIS_SIDECAR_MISSING:{scene}"]
    board = resolve_in_project(project, row.get("path"))
    if meta.get("ok") is not True or meta.get("renderer") != BOARD_TOOL or board is None:
        return [f"PREVIS_SIDECAR_INVALID:{scene}"]
    if meta.get("board") != board.name or meta.get("scene_id") != scene:
        return [f"PREVIS_SIDECAR_MISMATCH:{scene}"]
    files = [{"file": meta.get("board"), "sha256": meta.get("board_sha256")}, *(meta.get("pages") or []),
             *(section(meta, "frames").values())]
    errors = []
    for item in files:
        path = board.parent / str(item.get("file") if isinstance(item, dict) else "")
        if not isinstance(item, dict) or not path.is_file() or sha256_file(path) != item.get("sha256"):
            errors.append(f"PREVIS_SIDECAR_DIGEST_MISMATCH:{scene}:{path.name}")
    return errors


def coverage_errors(project: Path, previs: dict[str, Any]) -> list[str]:
    """Every scene of the locked script is decided or waived, and nothing else is named."""
    scenes = script_scenes(project)
    if scenes is None:
        return []
    decided = set(section(previs, "scenes"))
    waived = set(previs.get("waived_scenes") or [])
    errors = [f"PREVIS_SCENE_MISSING:{scene}" for scene in scenes if scene not in decided | waived]
    return errors + [f"PREVIS_SCENE_UNKNOWN:{scene}" for scene in sorted((decided | waived) - set(scenes))]


def previs_gate_errors(project: Path, drama: dict[str, Any], require_decision: bool = True) -> list[str]:
    """The previs lock plus scene coverage and, for rendered boards, sidecar provenance."""
    errors = previs_errors(project, drama, require_decision)
    previs = section(drama, "previs")
    if any(e.endswith(("_NOT_LOCKED", "_DECISION_MISSING")) for e in errors) or previs.get("waived") is True:
        return errors
    errors += coverage_errors(project, previs)
    if previs.get("tool", BOARD_TOOL) != BOARD_TOOL:
        return errors
    broken = {e.rsplit(":", 1)[-1] for e in errors if e.startswith(("PREVIS_ASSET_CHANGED", "PREVIS_OUTSIDE"))}
    for scene, row in section(previs, "scenes").items():
        if scene not in broken and isinstance(row, dict):
            errors += sidecar_errors(project, scene, row)
    return errors


def chosen_sidecars(project: Path, previs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Scene id -> sidecar of its chosen board (only for `whitemodel_board` locks), with its folder."""
    if previs.get("tool", BOARD_TOOL) != BOARD_TOOL:
        return {}
    out = {}
    for scene, row in section(previs, "scenes").items():
        meta = load_sidecar(project, str(row.get("path"))) if isinstance(row, dict) else None
        if meta:
            out[scene] = {**meta, "folder": str(Path(str(row["path"])).parent)}
    return out


def board_files(meta: dict[str, Any]) -> set[str]:
    names = [meta.get("board"), *(row.get("file") for row in section(meta, "frames").values() if isinstance(row, dict))]
    return {f"{meta['folder']}/{name}" for name in names if nonempty(name)}


def one_shot_errors(project: Path, spec_dir: Path, shot: dict[str, Any], boards: list[dict[str, Any]]) -> list[str]:
    sid = shot["id"]
    errors = [f"SHOT_{name.upper()}_MISSING:{sid}" for name in ("actors", "actor_count", "previs_ref") if name not in shot]
    if not boards or errors:
        return errors
    on_board = {actor for meta in boards for actor in meta.get("actors") or []}
    if isinstance(shot.get("actors"), list):
        errors += [f"SHOT_ACTOR_NOT_ON_BOARD:{sid}:{actor}" for actor in shot["actors"] if actor not in on_board]
    target = (spec_dir / str(shot["previs_ref"])).resolve()
    ref = str(target.relative_to(project.resolve())) if project.resolve() in target.parents else ""
    if ref not in set().union(*(board_files(meta) for meta in boards)):
        errors.append(f"SHOT_PREVIS_REF_NOT_ON_BOARD:{sid}:{shot['previs_ref']}")
    limit = max(int(meta.get("expected_actor_count", meta.get("actor_count", 0)) or 0) for meta in boards)
    if isinstance(shot["actor_count"], int) and shot["actor_count"] > limit:
        errors.append(f"SHOT_ACTOR_COUNT_EXCEEDS_BOARD:{sid}:{shot['actor_count']}>{limit}")
    cameras = {cam for meta in boards for cam in meta.get("cameras") or []}
    if "camera" in shot and shot["camera"] not in cameras:
        errors.append(f"SHOT_CAMERA_NOT_ON_BOARD:{sid}:{shot['camera']}")
    return errors


def shot_previs_errors(project: Path, drama: dict[str, Any], spec: dict[str, Any], spec_dir: Path) -> list[str]:
    """Each generated shot in a scene that is not waived names its headcount and a frame of the chosen board."""
    previs = section(drama, "previs")
    beats = script_beats(project)
    if previs.get("waived") is True or beats is None:
        return []
    waived = set(previs.get("waived_scenes") or [])
    sidecars = chosen_sidecars(project, previs)
    errors: list[str] = []
    for shot in active_shots(shot_rows(spec)):
        if is_reuse(shot):
            continue
        live = {scene_of_beat(beat) for beat in shot_beats(shot, beats)} - waived - {None}
        if live and previs.get("tool", BOARD_TOOL) == BOARD_TOOL:
            errors += one_shot_errors(project, spec_dir, shot, [sidecars[s] for s in sorted(live) if s in sidecars])
        elif live:
            errors += decided_file_errors(project, spec_dir, shot, decided_digests(project, previs, live))
    return errors


BUNDLE_TOOLS = frozenset({"blender", "stage_desk"})
BUNDLE_MEDIA_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm", ".mov"})


def bundle_digests(project: Path, rel_path: str, expected_sha: str, tool: str) -> set[str]:
    """Return SHA-256 digests of verified sibling media artifacts in a blender/stage_desk bundle."""
    locked = resolve_in_project(project, rel_path)
    previs_root = project.resolve() / "00_previs"
    if locked is None or not locked.is_file() or previs_root not in locked.parents or sha256_file(locked) != expected_sha:
        return set()
    if (locked.parent / "manifest.json").is_file():
        bundle_dir = locked.parent
    elif locked.parent.name == "frames" and (locked.parent.parent / "manifest.json").is_file():
        bundle_dir = locked.parent.parent
    else:
        return {expected_sha}
    if (bundle_dir / "failure.json").exists():
        return {expected_sha}
    try:
        bman = read_json(bundle_dir / "manifest.json")
    except ProjectError:
        return {expected_sha}
    artifacts = bman.get("artifacts") if isinstance(bman, dict) else None
    if not isinstance(artifacts, dict):
        return {expected_sha}
    bundle_root = bundle_dir.resolve()
    for name, meta in artifacts.items():
        if not isinstance(meta, dict) or not nonempty(meta.get("sha256")):
            return {expected_sha}
        art = (bundle_root / str(name)).resolve()
        if bundle_root not in art.parents or not art.is_file() or sha256_file(art) != meta["sha256"]:
            return {expected_sha}
    in_artifacts = (
        locked.parent == bundle_dir
        and locked.name in artifacts
        and isinstance(artifacts[locked.name], dict)
        and artifacts[locked.name].get("sha256") == expected_sha
    )
    is_blender_frame = (
        tool == "blender"
        and bman.get("purpose") == "planning_only"
        and "previz.mp4" in artifacts
        and locked.parent == bundle_dir / "frames"
        and bool(re.fullmatch(r"frame_\d+\.png", locked.name))
    )
    if not (in_artifacts or is_blender_frame):
        return {expected_sha}
    digests = {expected_sha} | {
        str(meta["sha256"])
        for name, meta in artifacts.items()
        if Path(str(name)).suffix.lower() in BUNDLE_MEDIA_EXTS
    }
    if tool == "blender" and (bundle_dir / "frames").is_dir():
        digests |= {sha256_file(f) for f in (bundle_dir / "frames").glob("frame_*.png") if f.is_file()}
    return digests


def decided_digests(project: Path, previs: dict[str, Any], scenes: set[str]) -> set[str]:
    rows = [section(previs, "scenes").get(scene) for scene in scenes]
    rows += [row for row in (previs.get("extra_refs") or []) if isinstance(row, dict)]
    tool = str(previs.get("tool") or "")
    out: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not nonempty(row.get("sha256")):
            continue
        if tool in BUNDLE_TOOLS and nonempty(row.get("path")):
            out |= bundle_digests(project, str(row["path"]), str(row["sha256"]), tool)
        else:
            out.add(str(row["sha256"]))
    return out


def decided_file_errors(project: Path, spec_dir: Path, shot: dict[str, Any], digests: set[str]) -> list[str]:
    """For tools without a sidecar: previs_ref must be a 00_previs/ file identical to a decided file of its scene."""
    sid = shot["id"]
    errors = [f"SHOT_{name.upper()}_MISSING:{sid}" for name in ("actors", "actor_count", "previs_ref") if name not in shot]
    if errors:
        return errors
    target = (spec_dir / str(shot["previs_ref"])).resolve()
    inside = (project.resolve() / "00_previs") in target.parents
    if not inside or not target.is_file() or sha256_file(target) not in digests:
        errors.append(f"SHOT_PREVIS_REF_NOT_DECIDED:{sid}:{shot['previs_ref']}")
    return errors


def identity_digests(project: Path, drama: dict[str, Any]) -> set[str]:
    assets = section(drama, "identity_assets")
    refs = [r for r in assets.get("refs") or [] if isinstance(r, dict)]
    if decision_errors(project, assets, refs, "IDENTITY"):
        return set()
    return {str(r["sha256"]) for r in refs if nonempty(r.get("sha256"))}


def sidecar_digests(sidecars: dict[str, dict[str, Any]]) -> set[str]:
    items = [item for meta in sidecars.values() for item in [*(meta.get("pages") or []), *section(meta, "frames").values()]]
    return {str(item["sha256"]) for item in items if isinstance(item, dict) and nonempty(item.get("sha256"))}


def approved_ref_digests(project: Path, drama: dict[str, Any], spec: dict[str, Any], spec_dir: Path) -> set[str]:
    """SHA-256 digests of every user-decided identity/scene asset and chosen 00_previs/ board or clean frame."""
    shas = identity_digests(project, drama)
    previs = section(drama, "previs")
    chosen = [r for r in section(previs, "scenes").values() if isinstance(r, dict)]
    extra_refs = [r for r in (previs.get("extra_refs") or []) if isinstance(r, dict)]
    all_chosen = [*chosen, *extra_refs]
    if nonempty(previs.get("locked_at")) and not decision_errors(project, previs, all_chosen, "PREVIS"):
        shas |= {str(r["sha256"]) for r in all_chosen if nonempty(r.get("sha256"))}
        shas |= sidecar_digests(chosen_sidecars(project, previs))
        tool = str(previs.get("tool") or "")
        if tool in BUNDLE_TOOLS:
            for row in all_chosen:
                if nonempty(row.get("path")) and nonempty(row.get("sha256")):
                    shas |= bundle_digests(project, str(row["path"]), str(row["sha256"]), tool)
    inherits = spec.get("inherits")
    parent_dir = (spec_dir / inherits).resolve().parent if nonempty(inherits) else None
    if parent_dir is not None and (parent_dir / "resume-manifest.json").is_file():
        shas |= identity_digests(parent_dir, drama_block(load_manifest(parent_dir)))
    return shas


def shot_ref_provenance_errors(project: Path, drama: dict[str, Any], spec: dict[str, Any],
                               spec_dir: Path) -> list[str]:
    """Every file in a shot's `refs` (including first-frame plates) must come from a code-confirmed decision."""
    assets = section(drama, "identity_assets")
    refs = [r for r in assets.get("refs") or [] if isinstance(r, dict)]
    if not nonempty(assets.get("locked_at")) or decision_errors(project, assets, refs, "IDENTITY"):
        return []
    allowed = approved_ref_digests(project, drama, spec, spec_dir)
    errors: list[str] = []
    for shot in active_shots(shot_rows(spec)):
        if is_reuse(shot):
            continue
        for name in shot.get("refs") or []:
            resolved = resolve_ref(spec, spec_dir, name) if nonempty(name) else None
            if resolved is not None and resolved.is_file() and sha256_file(resolved) not in allowed:
                errors.append(f"SHOT_REF_NOT_USER_DECIDED:{shot['id']}:{name}")
    return errors


def live_sidecars(project: Path, drama: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Chosen sidecars of the scenes that are not waived."""
    previs = section(drama, "previs")
    if previs.get("waived") is True:
        return {}
    waived = set(previs.get("waived_scenes") or [])
    return {scene: meta for scene, meta in chosen_sidecars(project, previs).items() if scene not in waived}


def add_scene_views(out: dict[str, dict[str, list[str]]], scene: str, meta: dict[str, Any]) -> None:
    extras = set(meta.get("extras") or [])
    for actor in meta.get("actors") or []:
        if actor not in extras:
            out.setdefault(actor, {}).setdefault("front", [])
    for cam, rows in section(meta, "coverage").items():
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and row.get("actor") not in extras:
                out.setdefault(row["actor"], {}).setdefault(row.get("view"), []).append(f"{scene}/{cam}")


def view_requirements(project: Path, drama: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """Board actor id -> required view -> the scene/camera that sees it; front is always required.

    Built from the chosen boards of non-waived scenes; actors flagged `extra` on the board are skipped."""
    out: dict[str, dict[str, list[str]]] = {}
    for scene, meta in sorted(live_sidecars(project, drama).items()):
        add_scene_views(out, scene, meta)
    return out


def locked_views(row: object) -> set[str]:
    angles = {ANGLE_ALIASES.get(a, a) for a in (row.get("angles") or [])} if isinstance(row, dict) else set()
    return set(VIEW_ORDER) if "turnaround" in angles else angles


def identity_view_errors(project: Path, drama: dict[str, Any]) -> list[str]:
    assets = section(drama, "identity_assets")
    characters = assets.get("characters") if isinstance(assets.get("characters"), dict) else {}
    needed = view_requirements(project, drama)
    errors = [f"IDENTITY_BOARD_ACTOR_UNLOCKED:{actor}" for actor in sorted(needed) if actor not in characters]
    if assets.get("waived_multi_angle") is True:
        return errors
    for actor, views in sorted(needed.items()):
        have = locked_views(characters.get(actor))
        missing = [view for view in VIEW_ORDER if view in views and view not in have]
        if actor in characters and missing:
            errors.append(f"CHARACTER_VIEWS_MISSING:{actor}:{','.join(missing)}")
    return errors


def identity_gate_errors(project: Path, drama: dict[str, Any], require_decision: bool = True) -> list[str]:
    """The identity lock, with each board actor's views taken from the chosen previs boards.

    Characters on a chosen board need front plus every view a board camera sees them from; the others
    keep the generic rule (front plus one non-front angle)."""
    errors = identity_errors(project, drama, require_decision)
    if any(e.endswith(("_NOT_LOCKED", "_DECISION_MISSING")) for e in errors):
        return errors
    on_board = {f"CHARACTER_MULTI_ANGLE_MISSING:{actor}" for actor in view_requirements(project, drama)}
    return [e for e in errors if e not in on_board] + identity_view_errors(project, drama)


def view_notes(project: Path, drama: dict[str, Any]) -> list[str]:
    """One line per board actor: the views it needs and which scene/camera needs each."""
    notes = []
    for actor, views in sorted(view_requirements(project, drama).items()):
        why = "; ".join(f"{view} <- {', '.join(views[view]) or 'always'}" for view in VIEW_ORDER if view in views)
        notes.append(f"Required views for {actor}: {why}")
    return notes
