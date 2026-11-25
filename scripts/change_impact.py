"""Change impact and cross-stage STALE invalidation across character / scene / previs / shots / takes.

Library only.
- A re-decided identity or previs gate stores its impact under `drama.impacts`, invalidates any prior
  draft cut approval on affected shots, and marks affected takes `stale: True` (including `preparing`
  and historical `ref_sha256s` matches, across root shots and `supersedes` revision chains).
- `drama_setup.py invalidate` atomically propagates `character | scene -> previs_scenes -> shots -> takes`,
  voids any pre-invalidation pending presentation sheets, records `invalidation_id` and `old_sha256s` in
  `drama.stale.pending_gate2`, and marks takes `stale_mandatory: True` so `impact keep` or `reuse` cannot
  wash away a mandatory regeneration.
- `close_pending_gate2` only closes targets presented AFTER `raised_at` whose locked SHA-256 actually changed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from drama_project import LIVE_JOB_STATES, ProjectError, drama_block, now_iso, section, sha256_file, take_rows
from previs_coverage import board_files, chosen_sidecars, load_sidecar, scene_of_beat, script_beats
from validate_shot_spec import (
    active_shots, is_reuse, load_project_spec, resolve_ref, root_id, shot_beats, shot_rows,
)

STALE_STATE = "STALE"
INVALIDATE_GATES = {"character": "identity", "scene": "identity", "previs": "previs"}


def scene_choice(record: dict[str, Any], scene: str) -> object:
    if record.get("waived") is True or scene in (record.get("waived_scenes") or []):
        return "waived"
    row = section(record, "scenes").get(scene)
    return (row.get("path"), row.get("sha256")) if isinstance(row, dict) else None


def changed_scenes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    names = set()
    for record in (old, new):
        names |= set(section(record, "scenes")) | set(record.get("waived_scenes") or [])
    return sorted(scene for scene in names if scene_choice(old, scene) != scene_choice(new, scene))


def old_board_files(project: Path, old: dict[str, Any], scenes: list[str]) -> set[str]:
    files = set()
    for scene in scenes:
        row = section(old, "scenes").get(scene)
        if isinstance(row, dict) and row.get("path"):
            files.add(str(row.get("path")))
            meta = load_sidecar(project, str(row.get("path")))
            files |= board_files({**meta, "folder": str(Path(str(row["path"])).parent)}) if meta else set()
    return files


def old_board_shas(project: Path, old: dict[str, Any], scenes: list[str]) -> set[str]:
    shas: set[str] = set()
    for scene in scenes:
        row = section(old, "scenes").get(scene)
        if isinstance(row, dict):
            if row.get("sha256"):
                shas.add(str(row["sha256"]))
            meta = load_sidecar(project, str(row.get("path") or ""))
            if isinstance(meta, dict):
                for frame in section(meta, "frames").values():
                    if isinstance(frame, dict) and frame.get("sha256"):
                        shas.add(str(frame["sha256"]))
    return shas


def replaced_refs_and_shas(old: dict[str, Any], new: dict[str, Any]) -> tuple[list[str], set[str]]:
    kept = {(row.get("path"), row.get("sha256")) for row in new.get("refs") or [] if isinstance(row, dict)}
    paths = sorted({str(row.get("path")) for row in old.get("refs") or []
                    if isinstance(row, dict) and row.get("path") and (row.get("path"), row.get("sha256")) not in kept})
    shas = {str(row.get("sha256")) for row in old.get("refs") or []
            if isinstance(row, dict) and row.get("sha256") and (row.get("path"), row.get("sha256")) not in kept}
    return paths, shas


def project_relative(project: Path, path: Path | None) -> str | None:
    root = project.resolve()
    return str(path.relative_to(root)) if path is not None and root in path.parents else None


def current_shot_ref_shas(spec: dict[str, Any], spec_dir: Path, shot: dict[str, Any]) -> list[str] | None:
    """Real-time SHA-256 list of a shot's current `refs`; None when any ref file is missing on disk."""
    if is_reuse(shot):
        return []
    shas: list[str] = []
    for name in shot.get("refs") or []:
        resolved = resolve_ref(spec, spec_dir, name)
        if resolved is None or not resolved.is_file():
            return None
        shas.append(sha256_file(resolved))
    return shas


def take_matches_current_refs(spec: dict[str, Any], spec_dir: Path, take: dict[str, Any]) -> bool:
    """False when a take is flagged `stale` or its `ref_sha256s` no longer match the active shot's current refs."""
    if take.get("stale") is True:
        return False
    if take.get("origin") == "reused":
        return True
    rows = shot_rows(spec)
    root = take.get("shot_id")
    active = next((row for row in active_shots(rows) if root_id(rows, row["id"]) == root), None)
    if active is None:
        return False
    expected = current_shot_ref_shas(spec, spec_dir, active)
    if expected is None:
        return False
    recorded = take.get("ref_sha256s")
    if isinstance(recorded, list):
        return recorded == expected
    return True


def verify_and_collect_take_anchors(project: Path, drama: dict[str, Any], spec: dict[str, Any],
                                    spec_dir: Path, shot: dict[str, Any]) -> tuple[list[Path], list[str]]:
    """Enumerate every locked anchor declared for `shot`, verify each file exists, decodes, and matches its
    locked SHA-256 digest, and return `(anchors, errors)`. Never silently skips a missing locked asset."""
    from PIL import Image, UnidentifiedImageError
    from drama_project import nonempty, resolve_in_project
    from previs_coverage import identity_gate_errors, previs_gate_errors

    errors: list[str] = []
    if nonempty(section(drama, "previs").get("locked_at")):
        errors += previs_gate_errors(project, drama)
    if nonempty(section(drama, "identity_assets").get("locked_at")):
        errors += identity_gate_errors(project, drama)

    assets = section(drama, "identity_assets")
    ref_sha_by_path = {
        str(r.get("path")): str(r.get("sha256"))
        for r in (assets.get("refs") or [])
        if isinstance(r, dict) and nonempty(r.get("path")) and nonempty(r.get("sha256"))
    }

    anchors: list[Path] = []

    def check_and_add(label: str, candidate: Path | None, expected_sha: str | None = None) -> None:
        if candidate is None or not candidate.is_file():
            errors.append(f"LOCKED_ANCHOR_MISSING:{label}")
            return
        try:
            with Image.open(candidate) as im:
                im.verify()
        except (OSError, UnidentifiedImageError, ValueError):
            errors.append(f"LOCKED_ANCHOR_UNDECODABLE:{label}")
            return
        actual_sha = sha256_file(candidate)
        rel = project_relative(project, candidate.resolve())
        lock_sha = expected_sha or (ref_sha_by_path.get(rel) if rel else None)
        if nonempty(lock_sha) and actual_sha != lock_sha:
            errors.append(f"LOCKED_ANCHOR_DIGEST_MISMATCH:{label}")
            return
        resolved = candidate.resolve()
        if all(existing.resolve() != resolved for existing in anchors):
            anchors.append(candidate)

    for name in shot.get("refs") or []:
        check_and_add(str(name), resolve_ref(spec, spec_dir, name))

    chars = section(assets, "characters")
    for actor in shot.get("actors") or []:
        c_row = chars.get(actor) or chars.get(str(actor).lower())
        if isinstance(c_row, dict):
            if nonempty(c_row.get("path")):
                rel_p = str(c_row["path"])
                check_and_add(rel_p, resolve_in_project(project, rel_p), c_row.get("sha256"))
            for rel in c_row.get("paths") or []:
                if nonempty(rel):
                    check_and_add(str(rel), resolve_in_project(project, rel))
            views = c_row.get("views")
            if isinstance(views, dict):
                for rel in views.values():
                    if nonempty(rel):
                        check_and_add(str(rel), resolve_in_project(project, rel))

    for sc_name, sc_row in section(assets, "scenes").items():
        if isinstance(sc_row, dict) and nonempty(sc_row.get("path")):
            rel_s = str(sc_row["path"])
            check_and_add(f"scene:{sc_name}:{rel_s}", resolve_in_project(project, rel_s), sc_row.get("sha256"))

    if nonempty(shot.get("previs_ref")):
        p_rel = str(shot["previs_ref"])
        check_and_add(p_rel, (spec_dir / p_rel).resolve())

    previs = section(drama, "previs")
    if previs.get("locked_at") and previs.get("waived") is not True:
        beats = script_beats(project) or []
        previs_scenes = section(previs, "scenes")
        shot_scs = [sc for b in shot_beats(shot, beats) if (sc := scene_of_beat(b)) and sc in previs_scenes]
        for sc in shot_scs:
            b_row = previs_scenes.get(sc)
            if isinstance(b_row, dict) and nonempty(b_row.get("path")):
                b_rel = str(b_row["path"])
                check_and_add(f"previs:{sc}:{b_rel}", resolve_in_project(project, b_rel), b_row.get("sha256"))

    return anchors, list(dict.fromkeys(errors))


def required_take_anchors(project: Path, drama: dict[str, Any], spec: dict[str, Any],
                          spec_dir: Path, shot: dict[str, Any]) -> list[Path]:
    return verify_and_collect_take_anchors(project, drama, spec, spec_dir, shot)[0]


def shot_ref_paths(project: Path, spec: dict[str, Any], spec_dir: Path, shot: dict[str, Any]) -> set[str]:
    table = spec.get("refs") if isinstance(spec.get("refs"), dict) else {}
    found: set[str] = set()
    for name in shot.get("refs") or []:
        resolved = resolve_ref(spec, spec_dir, name)
        if resolved is not None:
            rel = project_relative(project, resolved)
            if rel:
                found.add(rel)
            continue
        entry = table.get(name)
        declared = entry.get("path") if isinstance(entry, dict) and isinstance(entry.get("path"), str) else None
        for candidate in ([spec_dir / declared] if declared else []) + [spec_dir / "refs" / name, spec_dir / name]:
            rel = project_relative(project, candidate.resolve())
            if rel:
                found.add(rel)
    return found


def shot_hit(project: Path, spec: dict[str, Any], spec_dir: Path, shot: dict[str, Any], change: dict[str, Any]) -> bool:
    if change.get("scenes"):
        beats = script_beats(project) or []
        if {scene_of_beat(beat) for beat in shot_beats(shot, beats)} & set(change["scenes"]):
            return True
        previs_ref = shot.get("previs_ref")
        ref = project_relative(project, (spec_dir / str(previs_ref)).resolve()) if previs_ref else None
        if ref in change.get("files", set()):
            return True
    if change.get("actor") and change["actor"] in (shot.get("actors") or []):
        return True
    return bool(shot_ref_paths(project, spec, spec_dir, shot) & set(change.get("replaced_refs") or []))


def affected_shots_and_roots(project: Path, change: dict[str, Any]) -> tuple[list[str], set[str]]:
    """Return (active affected shot IDs, root shot IDs across all rows including superseded revisions)."""
    try:
        spec, spec_dir, _ = load_project_spec(project)
    except ProjectError as exc:
        if exc.code == "SHOT_SPEC_MISSING":
            return [], set()
        raise
    rows = shot_rows(spec)
    hit_all = [shot["id"] for shot in rows if shot_hit(project, spec, spec_dir, shot, change)]
    roots = {root_id(rows, sid) for sid in hit_all}
    active_hit = [shot["id"] for shot in active_shots(rows) if root_id(rows, shot["id"]) in roots]
    return active_hit, roots


def matching_takes(manifest: dict[str, Any], roots: set[str], spec_ids: set[str],
                   replaced_shas: set[str]) -> list[dict[str, Any]]:
    matched = []
    for row in take_rows(manifest):
        by_shot = row.get("shot_id") in roots or row.get("spec_id") in spec_ids
        by_sha = bool(replaced_shas and (set(row.get("ref_sha256s") or []) & replaced_shas))
        if by_shot or by_sha:
            matched.append(row)
    return matched


def change_of(project: Path, gate: str, old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    if gate == "previs":
        scenes = changed_scenes(old, new)
        return ({"scenes": scenes, "files": old_board_files(project, old, scenes),
                 "replaced_shas": old_board_shas(project, old, scenes)} if scenes else {})
    replaced, shas = replaced_refs_and_shas(old, new)
    if not replaced and not shas:
        return {}
    old_scenes = section(old, "scenes")
    changed_sc_names = [
        sc_name for sc_name, sc_row in old_scenes.items()
        if isinstance(sc_row, dict) and (sc_row.get("path") in replaced or sc_row.get("sha256") in shas)
    ]
    out: dict[str, Any] = {"replaced_refs": replaced, "replaced_shas": shas}
    if changed_sc_names:
        out["changed_scene_assets"] = sorted(changed_sc_names)
    return out


def scoped_character_origins(drama: dict[str, Any], gate: str, scenes: list[str]) -> set[str] | None:
    """When re-locking previs strictly to satisfy a character-scoped invalidation, keep non-target shots untouched."""
    if gate != "previs":
        return None
    rows = [r for r in pending_gate2(drama) if r.get("gate") == "previs" and set(r.get("targets") or []) & set(scenes)]
    if not rows or any(r.get("origin_stage") != "character" for r in rows):
        return None
    scoped: set[str] = set()
    for r in rows:
        scoped |= set(r.get("shots") or [])
    return scoped


def compute_impact(project: Path, manifest: dict[str, Any], gate: str, key: str,
                   new: dict[str, Any]) -> dict[str, Any] | None:
    """The impact of replacing the current `key` lock with `new`; None when nothing was locked or nothing changed."""
    drama = drama_block(manifest)
    old = section(drama, key)
    if not old.get("locked_at"):
        return None
    change = change_of(project, gate, old, new)
    if not change:
        return None
    shots, roots = affected_shots_and_roots(project, change)
    if change.get("changed_scene_assets"):
        try:
            spec, spec_dir, _ = load_project_spec(project)
            rows = shot_rows(spec)
            for sc_asset in change["changed_scene_assets"]:
                p_scs = affected_previs_for_source(project, drama, "scene", sc_asset, roots, spec)
                if p_scs:
                    sc_chg = {"scenes": p_scs, "files": old_board_files(project, section(drama, "previs"), p_scs)}
                    extra_shots, extra_roots = affected_shots_and_roots(project, sc_chg)
                    roots |= extra_roots
                    shots = sorted({*shots, *extra_shots}, key=lambda x: next((i for i, r in enumerate(rows) if r["id"] == x), 9999))
        except ProjectError:
            pass
    scoped = scoped_character_origins(drama, gate, change.get("scenes") or [])
    if scoped is not None:
        roots = roots & scoped
        shots = [sid for sid in shots if sid in roots]
    hit_takes = matching_takes(manifest, roots, set(shots), set(change.get("replaced_shas") or set()))
    takes = [{"take_id": row.get("take_id"), "shot_id": row.get("shot_id"), "tier": row.get("tier"),
              "job_state": row.get("job_state"), "status": row.get("status")}
             for row in hit_takes if row.get("take_id")]
    number = len(drama.get("impacts") or []) + 1
    changed = {k: v for k, v in change.items() if k not in ("files", "replaced_shas", "changed_scene_assets")}
    return {"id": f"{gate}-{number}", "gate": gate, "recorded_at": now_iso(), "changed": changed,
            "shots": shots, "roots": sorted(roots), "takes": takes, "resolution": None}


def open_impacts(drama: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in drama.get("impacts") or [] if isinstance(row, dict) and not row.get("resolution")]


def impact_note(row: dict[str, Any]) -> str:
    changed = "; ".join(f"{k}: {', '.join(v)}" for k, v in row.get("changed", {}).items())
    takes = ", ".join(f"{t['take_id']} ({t.get('tier')}, {t.get('status') or t.get('job_state')})"
                      for t in row.get("takes") or []) or "none"
    return (f"Unresolved change impact {row['id']} ({changed}): shots {', '.join(row.get('shots') or []) or 'none'}; "
            f"takes {takes}. Resolve with the user's own words via "
            f"`drama_setup.py impact --id {row['id']} --decision keep|redo --user-words ...` "
            "(SPEC v2.0 mandatory invalidations require redo/regeneration).")


# --------------------------------------------------------------------------- STALE invalidation


def stale_block(drama: dict[str, Any]) -> dict[str, Any]:
    return section(drama, "stale")


def stale_shot_ids(drama: dict[str, Any]) -> set[str]:
    return {sid for sid, row in section(stale_block(drama), "shots").items()
            if isinstance(row, dict) and row.get("state") == STALE_STATE}


def stale_previs_scenes(drama: dict[str, Any]) -> set[str]:
    return {sc for sc, row in section(stale_block(drama), "previs_scenes").items()
            if isinstance(row, dict) and row.get("state") == STALE_STATE}


def pending_gate2(drama: dict[str, Any]) -> list[dict[str, Any]]:
    rows = stale_block(drama).get("pending_gate2")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def pending_gate2_errors(drama: dict[str, Any]) -> list[str]:
    return [f"INCREMENTAL_HUMAN_GATE_2_REQUIRED:{row.get('gate')}:{target}"
            for row in pending_gate2(drama) for target in row.get("targets") or []]


def stale_take_errors(takes: list[dict[str, Any]]) -> list[str]:
    return [f"STALE_TAKE_INVALIDATED:{take.get('take_id')}" for take in takes if take.get("stale") is True]


def invalidate_downstream_cuts(drama: dict[str, Any], reason: str) -> dict[str, Any]:
    """Any upstream asset/previs invalidation voids existing draft-cut approvals and cut records."""
    approvals = dict(section(drama, "approvals"))
    draft_app = dict(section(approvals, "draft_cut"))
    if draft_app.get("approved") is True:
        approvals["draft_cut"] = {**draft_app, "approved": False, "stale": True, "invalidated_reason": reason}
    cuts = dict(section(drama, "cuts"))
    if "draft" in cuts and isinstance(cuts["draft"], dict):
        cuts["draft"] = {**cuts["draft"], "stale": True, "invalidated_reason": reason}
    return {**drama, "approvals": approvals, "cuts": cuts}


def mark_takes_stale(manifest: dict[str, Any], take_ids: set[str], reason: str,
                     source: dict[str, Any], mandatory: bool = False) -> dict[str, Any]:
    """Flag non-rejected live takes (including `preparing`) `stale: True` and log them under drama.stale.takes."""
    stamp = now_iso()
    hit = {t["take_id"] for t in take_rows(manifest) if t.get("take_id") in take_ids
           and t.get("status") != "rejected" and t.get("job_state") in LIVE_JOB_STATES}
    extra_flags = {"stale": True, "stale_reason": reason, **({"stale_mandatory": True} if mandatory else {})}
    takes = [{**t, **extra_flags} if t.get("take_id") in hit else t
             for t in manifest.get("takes") or []]
    drama = drama_block(manifest)
    if hit:
        drama = invalidate_downstream_cuts(drama, reason)
    block = stale_block(drama)
    log = {**section(block, "takes"), **{tid: {"state": STALE_STATE, "reason": reason, "mandatory": mandatory,
                                              "invalidated_at": stamp, **source} for tid in sorted(hit)}}
    return {**manifest, "takes": takes, "drama": {**drama, "stale": {**block, "takes": log}}}


def mark_impact_stale(manifest: dict[str, Any], impact: dict[str, Any] | None) -> dict[str, Any]:
    if not impact:
        return manifest
    mandatory = drama_block(manifest).get("sop_version") in {"2.0", "3.0"}
    ids = {t.get("take_id") for t in impact.get("takes") or [] if t.get("take_id")}
    updated = mark_takes_stale(manifest, ids, f"impact {impact['id']}", {"impact": impact["id"]}, mandatory=mandatory)
    if impact.get("shots") or ids:
        drama = invalidate_downstream_cuts(drama_block(updated), f"impact {impact['id']}")
        if mandatory:
            block = stale_block(drama)
            shots = {**section(block, "shots"),
                     **{sid: {"state": STALE_STATE, "reason": f"impact {impact['id']}", "invalidated_at": now_iso()}
                        for sid in (impact.get("roots") or impact.get("shots") or [])}}
            drama = {**drama, "stale": {**block, "shots": shots}}
        updated = {**updated, "drama": drama}
    return updated


def set_take_stale_state(manifest: dict[str, Any], take_ids: set[str], state: str, note: str) -> dict[str, Any]:
    """Close stale flags on WAIVED (only permitted for non-mandatory v1 impacts); REJECTED keeps `stale: True`."""
    drama = drama_block(manifest)
    if state == "WAIVED":
        if drama.get("sop_version") in {"2.0", "3.0"}:
            raise ProjectError("STALE_MANDATORY_REGENERATION_REQUIRED",
                               "SPEC v2.0 forbids waiving stale takes with `keep`; regenerate affected shots")
        for t in take_rows(manifest):
            if t.get("take_id") in take_ids and t.get("stale_mandatory") is True:
                raise ProjectError("STALE_MANDATORY_REGENERATION_REQUIRED", str(t.get("take_id")))

    def closed(take: dict[str, Any]) -> dict[str, Any]:
        if state != "WAIVED":
            return {**take, "stale_closed": note}
        kept = {key: value for key, value in take.items() if key not in ("stale", "stale_reason", "stale_mandatory")}
        return {**kept, "stale_waived": note}

    takes = [closed(t) if t.get("take_id") in take_ids and t.get("stale") is True else t
             for t in manifest.get("takes") or []]
    block = stale_block(drama)
    log = {tid: ({**row, "state": state, "closed_note": note} if tid in take_ids else row)
           for tid, row in section(block, "takes").items()}
    return {**manifest, "takes": takes, "drama": {**drama, "stale": {**block, "takes": log}}}


def affected_previs_for_source(project: Path, drama: dict[str, Any], stage: str, target: str,
                               shot_roots: set[str], spec: dict[str, Any]) -> list[str]:
    previs = section(drama, "previs")
    if stage == "previs":
        return [target]
    if not previs.get("locked_at") or previs.get("waived") is True:
        return []
    locked_scenes = set(section(previs, "scenes"))
    if not locked_scenes:
        return []
    found: set[str] = set()
    sidecars = chosen_sidecars(project, previs)
    if stage == "character":
        for sc, meta in sidecars.items():
            if target in (meta.get("actors") or []):
                found.add(sc)
    beats = script_beats(project) or []
    rows = shot_rows(spec)
    for row in rows:
        if root_id(rows, row["id"]) in shot_roots:
            for beat in shot_beats(row, beats):
                sc = scene_of_beat(beat)
                if sc in locked_scenes:
                    found.add(sc)
    if stage == "scene":
        if target in locked_scenes:
            found.add(target)
        t_low = target.lower()
        t_words = t_low.replace("_", " ").replace("-", " ")
        for row in rows:
            prompt_low = str(row.get("prompt") or "").lower()
            if str(row.get("scene") or "").lower() == t_low or t_low in prompt_low or (len(t_words) >= 3 and t_words in prompt_low):
                for beat in shot_beats(row, beats):
                    sc = scene_of_beat(beat)
                    if sc in locked_scenes:
                        found.add(sc)
        if not found:
            found |= locked_scenes
    return sorted(found & locked_scenes)


def source_old_shas(drama: dict[str, Any], stage: str, target: str, paths: list[str], project: Path) -> list[str]:
    if stage == "previs":
        return sorted(old_board_shas(project, section(drama, "previs"), [target]))
    assets = section(drama, "identity_assets")
    shas = {str(r["sha256"]) for r in assets.get("refs") or []
            if isinstance(r, dict) and r.get("path") in paths and r.get("sha256")}
    if stage == "scene":
        entry = section(assets, "scenes").get(target)
        if isinstance(entry, dict) and entry.get("sha256"):
            shas.add(str(entry["sha256"]))
    return sorted(shas)


def invalidation_change(project: Path, drama: dict[str, Any], stage: str, target: str) -> dict[str, Any]:
    if stage == "previs":
        previs = section(drama, "previs")
        if target not in section(previs, "scenes") and target not in (previs.get("waived_scenes") or []):
            raise ProjectError("INVALIDATE_TARGET_UNKNOWN", f"previs:{target}")
        shas = old_board_shas(project, previs, [target])
        return {"scenes": [target], "files": old_board_files(project, previs, [target]),
                "replaced_shas": shas, "old_shas": sorted(shas)}
    assets = section(drama, "identity_assets")
    table = section(assets, "characters" if stage == "character" else "scenes")
    entry = table.get(target)
    if isinstance(entry, dict):
        paths = list(entry.get("paths") or ([entry["path"]] if entry.get("path") else []))
    elif any(isinstance(r, dict) and r.get("path") == target for r in assets.get("refs") or []):
        paths = [target]
    else:
        raise ProjectError("INVALIDATE_TARGET_UNKNOWN", f"{stage}:{target}")
    shas = source_old_shas(drama, stage, target, paths, project)
    return {"replaced_refs": sorted(paths), "replaced_shas": set(shas), "old_shas": shas,
            "actor": target if stage == "character" else None}


def invalidation_scope(project: Path, manifest: dict[str, Any], stage: str, target: str) -> dict[str, Any]:
    """Affected previs scenes, spec shots (root + revisions), their live/historical takes, and untouched shots."""
    if stage not in INVALIDATE_GATES:
        raise ProjectError("INPUT_ERROR", f"--stage must be one of {', '.join(INVALIDATE_GATES)}")
    drama = drama_block(manifest)
    change = invalidation_change(project, drama, stage, target)
    try:
        spec, spec_dir, _ = load_project_spec(project)
    except ProjectError as exc:
        if exc.code != "SHOT_SPEC_MISSING":
            raise
        spec, spec_dir = {"shots": {}}, project
    rows = shot_rows(spec)
    hit_spec_ids = {shot["id"] for shot in rows if shot_hit(project, spec, spec_dir, shot, change)}
    roots = {root_id(rows, sid) for sid in hit_spec_ids}
    previs_scenes = affected_previs_for_source(project, drama, stage, target, roots, spec)
    if previs_scenes and stage in ("scene", "previs"):
        scene_change = {
            "scenes": previs_scenes,
            "files": old_board_files(project, section(drama, "previs"), previs_scenes),
        }
        hit_spec_ids |= {shot["id"] for shot in rows if shot_hit(project, spec, spec_dir, shot, scene_change)}
        roots = {root_id(rows, sid) for sid in hit_spec_ids}
    all_chain_ids = {shot["id"] for shot in rows if root_id(rows, shot["id"]) in roots} | hit_spec_ids
    board_shas = old_board_shas(project, section(drama, "previs"), previs_scenes) if stage in ("scene", "previs") else set()
    takes = sorted({t["take_id"] for t in matching_takes(manifest, roots, all_chain_ids, change["replaced_shas"] | board_shas)
                    if t.get("take_id")})
    previs_old = {sc: sorted(old_board_shas(project, section(drama, "previs"), [sc])) for sc in previs_scenes}
    active = active_shots(rows)
    return {
        "gate": INVALIDATE_GATES[stage],
        "shots": sorted(roots),
        "spec_ids": sorted(all_chain_ids),
        "takes": takes,
        "previs_scenes": previs_scenes,
        "previs_old_shas": previs_old,
        "old_shas": change["old_shas"],
        "untouched": sorted({root_id(rows, s["id"]) for s in active} - roots),
    }


def _next_invalidation_id(block: dict[str, Any]) -> str:
    seq = int(block.get("seq") or 0) + 1
    return f"inv-{seq}"


def apply_invalidation(manifest: dict[str, Any], stage: str, target: str, reason: str,
                       scope: dict[str, Any]) -> dict[str, Any]:
    stamp = now_iso()
    source = {"stage": stage, "target": target}
    updated = mark_takes_stale(manifest, set(scope["takes"]), reason, source, mandatory=True)
    drama = invalidate_downstream_cuts(drama_block(updated), reason)
    block = dict(stale_block(drama))
    seq = int(block.get("seq") or 0)

    shots = {**section(block, "shots"), **{sid: {"state": STALE_STATE, "reason": reason, "invalidated_at": stamp,
                                                 **source} for sid in scope["shots"]}}
    previs_map = dict(section(block, "previs_scenes"))
    for sc in scope.get("previs_scenes") or []:
        previs_map[sc] = {"state": STALE_STATE, "reason": reason, "invalidated_at": stamp, **source}

    pending = list(pending_gate2(drama))
    gates_opened: set[str] = {scope["gate"]}

    # If stage is character/scene and locked previs boards depend on it, open incremental previs Gate #2 as well
    if stage in ("character", "scene") and scope.get("previs_scenes"):
        gates_opened.add("previs")
        for sc in scope["previs_scenes"]:
            seq += 1
            pending.append({
                "invalidation_id": f"inv-{seq}",
                "gate": "previs",
                "targets": [sc],
                "stage": "previs",
                "origin_stage": stage,
                "origin_target": target,
                "old_sha256s": scope.get("previs_old_shas", {}).get(sc, []),
                "reason": reason,
                "shots": scope["shots"],
                "raised_at": stamp,
            })

    seq += 1
    pending.append({
        "invalidation_id": f"inv-{seq}",
        "gate": scope["gate"],
        "targets": [target],
        "stage": stage,
        "origin_stage": stage,
        "origin_target": target,
        "old_sha256s": scope.get("old_shas", []),
        "reason": reason,
        "shots": scope["shots"],
        "raised_at": stamp,
    })

    # Void any pre-invalidation pending presentations on affected gates so old sheets cannot clear new invalidations
    presentations = {k: v for k, v in section(drama, "presentations").items() if k not in gates_opened}
    new_stale = {**block, "seq": seq, "shots": shots, "previs_scenes": previs_map,
                 "pending_gate2": pending, "invalidated_shas": sorted(
                     set(block.get("invalidated_shas") or []) | set(scope.get("old_shas") or []))}
    return {**updated, "drama": {**drama, "presentations": presentations, "stale": new_stale}}


def _new_target_shas(gate: str, record: dict[str, Any], stage: str, target: str) -> tuple[set[str], bool]:
    """Return (new sha256 set for `target`, whether `target` was waived)."""
    if gate == "previs":
        waived = record.get("waived") is True or target in (record.get("waived_scenes") or [])
        row = section(record, "scenes").get(target)
        shas = {str(row["sha256"])} if isinstance(row, dict) and row.get("sha256") else set()
        return shas, waived
    refs_by_path = {str(r["path"]): str(r["sha256"]) for r in record.get("refs") or []
                    if isinstance(r, dict) and r.get("path") and r.get("sha256")}
    if stage == "character":
        waived = False
        char = section(record, "characters").get(target)
        paths = list(char.get("paths") or []) if isinstance(char, dict) else ([target] if target in refs_by_path else [])
        return {refs_by_path[p] for p in paths if p in refs_by_path}, waived
    waived = record.get("waived_scenes") is True
    sc = section(record, "scenes").get(target)
    if isinstance(sc, dict) and sc.get("sha256"):
        return {str(sc["sha256"])}, waived
    return ({refs_by_path[target]} if target in refs_by_path else set()), waived


def verify_incremental_gate2_lock(drama: dict[str, Any], gate: str, pending_pres: dict[str, Any],
                                  record: dict[str, Any]) -> None:
    """Refuse locking `gate` when open invalidations exist unless presented AFTER invalidation with new digests."""
    rows = [r for r in pending_gate2(drama) if r.get("gate") == gate]
    if not rows:
        return
    covered_ids = set(pending_pres.get("covers_invalidations") or [])
    presented_at = str(pending_pres.get("presented_at") or "")
    cand_groups = {str(c.get("group") or "").split(".")[0] for c in (pending_pres.get("candidates") or [])
                   if isinstance(c, dict)}
    cand_paths = {str(c.get("path") or "") for c in (pending_pres.get("candidates") or []) if isinstance(c, dict)}
    for row in rows:
        inv_id = row.get("invalidation_id")
        raised_at = str(row.get("raised_at") or "")
        if (inv_id and inv_id not in covered_ids) or (raised_at and presented_at < raised_at):
            raise ProjectError("PRESENTATION_STALE_AFTER_INVALIDATION",
                               f"{gate}:{inv_id or raised_at}: run `drama_setup.py present --gate {gate}` with the "
                               "updated candidates after invalidation")
        old_shas = set(row.get("old_sha256s") or [])
        stage = str(row.get("stage") or gate)
        for target in row.get("targets") or []:
            new_shas, waived = _new_target_shas(gate, record, stage, target)
            if waived:
                raise ProjectError("INVALIDATED_SOURCE_CANNOT_BE_WAIVED", f"{gate}:{target}")
            if target not in cand_groups and target not in cand_paths:
                raise ProjectError("INVALIDATED_TARGET_NOT_PRESENTED", f"{gate}:{target}")
            if not new_shas or (old_shas and new_shas <= old_shas):
                raise ProjectError("INVALIDATED_SOURCE_NOT_UPDATED",
                                   f"{gate}:{target}: locked digest is unchanged from invalidated asset")


def close_pending_gate2(manifest: dict[str, Any], gate: str, record: dict[str, Any]) -> dict[str, Any]:
    """Close only the pending_gate2 targets for `gate` verified in `record` and update previs_scenes state."""
    drama = drama_block(manifest)
    block = stale_block(drama)
    rows = pending_gate2(drama)
    if not any(row.get("gate") == gate for row in rows):
        return manifest
    stamp = now_iso()
    decision = section(record, "decision")
    covered_ids = set(decision.get("covers_invalidations") or [])
    resolved = list(block.get("resolved_gate2") or [])
    kept = []
    previs_map = dict(section(block, "previs_scenes"))
    for row in rows:
        if row.get("gate") != gate:
            kept.append(row)
            continue
        inv_id = row.get("invalidation_id")
        if inv_id and inv_id not in covered_ids:
            kept.append(row)
            continue
        resolved.append({**row, "resolved_at": stamp})
        if gate == "previs":
            for sc in row.get("targets") or []:
                if sc in previs_map:
                    previs_map[sc] = {**previs_map[sc], "state": "REGENERATED", "regenerated_at": stamp}
    return {**manifest, "drama": {**drama, "stale": {**block, "previs_scenes": previs_map,
                                                     "pending_gate2": kept, "resolved_gate2": resolved}}}


def clear_stale_shot(manifest: dict[str, Any], shot_id: str, take_id: str) -> dict[str, Any]:
    drama = drama_block(manifest)
    block = stale_block(drama)
    shots = section(block, "shots")
    repair_q = dict(section(drama, "repair_queue"))
    if shot_id in repair_q:
        repair_q.pop(shot_id, None)
    if shot_id not in shots:
        return {**manifest, "drama": {**drama, "repair_queue": repair_q}}
    row = {**shots[shot_id], "state": "REGENERATED", "regenerated_by": take_id, "regenerated_at": now_iso()}
    return {**manifest, "drama": {**drama, "repair_queue": repair_q,
                                  "stale": {**block, "shots": {**shots, shot_id: row}}}}
