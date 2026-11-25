"""Reverse dependency traversal and terminal artifact checks for SOP 3 projects."""
import re
from datetime import date

from change_impact import pending_gate2_errors, stale_previs_scenes
from check_release_intent import check_intent
from drama_project import (ProjectError, drama_block, read_json, resolve_in_project, section,
                           sha256_file, take_rows)
from intake_choices import MODES, required_choices
from lock_script import locked_script_text, verify_lock
from previs_coverage import identity_gate_errors, previs_gate_errors
from project_inventory import IMAGES, VIDEO_SUFFIXES, untracked

TERMINALS = dict(zip(MODES, ("prompt_package", "images", "clips", "master")))
BASE_DEPENDENCIES = {"decisions": (), "brief": (), "prompt_package": ("brief", "decisions"),
                     "images": ("prompt_package",), "clips": ("images",), "master": ("clips",)}
VIDEO_DEPENDENCIES = {
    "decisions": (),
    "brief": (),
    "script_lock": ("brief", "decisions"),
    "release_intent": ("script_lock",),
    "previs": ("release_intent",),
    "images": ("previs",),
    "prompt_package": ("images",),
    "clips": ("prompt_package",),
    "master": ("clips",),
}
DEPENDENCIES = BASE_DEPENDENCIES
VIDEO_MODES = frozenset({"video_clips", "full_film"})


class SpecValidationError(ProjectError):
    """Structured shot-spec failure carrying individual machine-readable error codes."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("SHOT_SPEC_INVALID", "; ".join(errors))
        self.errors = list(errors)


def choices(drama):
    latest = section(drama, "choice_resolution")
    if "resolved" in latest:
        return latest["resolved"]
    return {**drama, **section(drama, "model_gate")}


def verified_spec(project, manifest, *, mode=None, today=None):
    from check_script_coverage import check_spec_coverage, parse_script
    from ledger_submit import Context, load_translations, spec_errors
    from lock_script import read_lock
    from validate_shot_spec import DEFAULT_SPEC_NAME, validate_spec

    drama = drama_block(manifest)
    script = locked_script_text(project)
    if parse_script(script)[0] != read_lock(project)["beats"]:
        raise ProjectError("SCRIPT_LOCK_BEATS_CHANGED")
    path = resolve_in_project(project, drama.get("shot_spec") or DEFAULT_SPEC_NAME)
    if not path or not path.is_file():
        raise ProjectError("SHOT_SPEC_MISSING")
    spec = read_json(path)
    day = today or date.today()
    if mode in VIDEO_MODES:
        errors = spec_errors(Context(project, manifest, spec, path.parent), script, day)
    else:
        errors = validate_spec(spec, path.parent, section(drama, "channels"), day)
        if not errors:
            translations = load_translations(Context(project, manifest, spec, path.parent))
            errors = check_spec_coverage(script, spec, translations)["errors"]
    if errors:
        raise SpecValidationError(errors)
    return spec


def verify_artifacts(project, mode, names, manifest, *, run_qc=False, today=None):
    from media_inspection import inspect, probe
    from validate_shot_spec import active_shots, root_id, shot_beats, shot_rows
    from validate_prompt_package import validate_package
    if not names:
        raise ProjectError("TERMINAL_ARTIFACT_MISSING")
    drama = drama_block(manifest)
    spec = verified_spec(project, manifest, mode=mode, today=today)
    rows = shot_rows(spec)
    active = active_shots(rows)
    if not active:
        raise ProjectError("ACTIVE_SHOTS_MISSING")
    if mode == "video_clips":
        from lock_script import read_lock
        beats = read_lock(project)["beats"]
        post = set(spec.get("post_beats") or [])
        needed = {root_id(rows, r["id"]) for r in active
                  if not shot_beats(r, beats) or not set(shot_beats(r, beats)) <= post}
        submitted = {t.get("shot_id") for t in take_rows(manifest) if t.get("file") in names
                     and t.get("status") == "approved" and not t.get("stale")}
        if needed - submitted:
            raise ProjectError("MISSING_APPROVED_CLIPS", ",".join(sorted(needed - submitted)))
    for name in names:
        path = resolve_in_project(project, name)
        if not path or not path.is_file() or not path.stat().st_size:
            raise ProjectError("OUTPUT_FILE_MISSING", str(name))
        if mode == "prompt_only":
            if path.suffix.lower() == ".json":
                package = read_json(path)
                if package == spec:
                    continue
                errors, _ = validate_package(package, path)
                if errors or {s["shot_id"] for s in package["shots"]} != {s["id"] for s in active}:
                    raise ProjectError("PROMPT_PACKAGE_INVALID", name)
                by_shot_id = {s["shot_id"]: s for s in package["shots"]}
                for spec_shot in active:
                    pkg_shot = by_shot_id[spec_shot["id"]]
                    spec_prompt = re.sub(r"\s+", " ", str(spec_shot.get("prompt") or "").strip())
                    pkg_prompt = re.sub(r"\s+", " ", str(pkg_shot.get("prompt") or "").strip())
                    if not pkg_prompt or (spec_prompt and pkg_prompt != spec_prompt and spec_prompt not in pkg_prompt):
                        raise ProjectError("PROMPT_PACKAGE_CONTENT_MISMATCH", name)
            elif path.suffix.lower() in {".md", ".txt", ".html"}:
                content = path.read_text()
                if any(s["id"] not in content or not s.get("prompt") or s["prompt"] not in content for s in active):
                    raise ProjectError("PROMPT_PACKAGE_INVALID", name)
            else:
                raise ProjectError("PROMPT_PACKAGE_INVALID", name)
        elif mode == "images_only":
            from PIL import Image
            if path.suffix.lower() not in IMAGES:
                raise ProjectError("IMAGE_REQUIRED", name)
            try:
                with Image.open(path) as img:
                    img.verify()
            except OSError as exc:
                raise ProjectError("UNREADABLE_IMAGE", name) from exc
            assets = section(drama, "identity_assets")
            if not assets.get("locked_at") or not assets.get("user_words") or not any(
                    r.get("path") == name and r.get("sha256") == sha256_file(path)
                    for r in assets.get("refs", []) if isinstance(r, dict)):
                raise ProjectError("IMAGE_NOT_SELECTED", name)
        elif mode in {"video_clips", "full_film"}:
            if path.suffix.lower() not in VIDEO_SUFFIXES or not probe(path)["video_streams"]:
                raise ProjectError("VIDEO_REQUIRED", name)
            if mode == "video_clips" and not any(t.get("file") == name and t.get("status") == "approved"
                    and not t.get("stale") and t.get("file_sha256") == sha256_file(path) for t in take_rows(manifest)):
                raise ProjectError("CLIP_NOT_APPROVED", name)
            if run_qc:
                take = next((t for t in take_rows(manifest) if t.get("file") == name), {})
                report = inspect(path, delivery_mode=mode, creative_mode=drama.get("creative_mode"),
                                 voice_source=take.get("voice_source"), audio_route=take.get("audio_route"))
                if report["errors"]:
                    raise ProjectError(report["errors"][0], name)
        else:
            raise ProjectError("DELIVERY_MODE_UNRESOLVED")


def plan(project, manifest, *, today=None):
    day = today or date.today()
    drama = drama_block(manifest)
    config = choices(drama)
    mode = config.get("delivery_mode")
    terminal = TERMINALS.get(mode)
    deps = VIDEO_DEPENDENCIES if mode in VIDEO_MODES else BASE_DEPENDENCIES
    needed = []
    def visit(node):
        if node not in needed:
            for parent in deps[node]:
                visit(parent)
            needed.append(node)
    visit(terminal or "decisions")
    missing = [k for k in required_choices(mode) if not config.get(k)]
    if mode not in MODES and "delivery_mode" not in missing:
        missing.append("delivery_mode")
    gate = section(drama, "model_gate")
    if not missing and not gate.get("confirmed_at"):
        missing.append("confirmation")
    delivery = section(drama, "delivery")
    names = delivery.get("files") or []
    def current(record, hash_key):
        hashes = record.get(hash_key) or {}
        return not record.get("stale") and bool(hashes) and all((p := resolve_in_project(project, n)) and p.is_file()
                                    and sha256_file(p) == h for n, h in hashes.items())
    delivered = bool(not missing and delivery.get("delivered_at") and delivery.get("delivery_mode") == mode and
                     current(delivery, "file_sha256s"))
    delivered = delivered and bool(names) and set(names) == set(section(delivery, "file_sha256s"))
    node_blockers = {}
    spec_ready = False
    if "prompt_package" in needed:
        try:
            verified_spec(project, manifest, mode=mode, today=day)
            spec_ready = True
        except SpecValidationError as exc:
            node_blockers["prompt_package"] = exc.errors
        except ProjectError as exc:
            node_blockers["prompt_package"] = [str(exc)]
    images = section(drama, "identity_assets")
    takes = take_rows(manifest)
    approved = [t for t in takes if t.get("status") == "approved" and not t.get("stale")]
    clips_ready = bool(approved)
    if clips_ready and "clips" in needed:
        try:
            verify_artifacts(project, "video_clips", [t["file"] for t in approved], manifest, today=day)
        except (ProjectError, KeyError) as exc:
            clips_ready = False
            node_blockers["clips"] = [str(exc)]
    done = {"brief": bool(section(drama, "intake").get("confirmed_at")), "decisions": not missing,
            "prompt_package": spec_ready, "images": bool(images.get("locked_at") and images.get("refs")),
            "clips": clips_ready,
            "master": current(section(drama, "post"), "output_sha256s")}
    if mode in VIDEO_MODES:
        lock_errs = verify_lock(project)
        done["script_lock"] = not lock_errs
        node_blockers["script_lock"] = lock_errs
        intent_errs = check_intent(section(drama, "release_intent"), locked_script_text(project) if not lock_errs else None)
        done["release_intent"] = not lock_errs and not intent_errs
        node_blockers["release_intent"] = intent_errs or lock_errs
        prev_errs = (
            [f"STALE_PREVIS_SCENE:{sc}" for sc in sorted(stale_previs_scenes(drama))]
            + [e for e in pending_gate2_errors(drama) if ":previs" in e]
            + previs_gate_errors(project, drama)
        )
        if prev_errs and section(section(drama, "presentations"), "previs"):
            prev_errs.append("PREVIS_PRESENTED_AWAITING_USER_CODE")
        done["previs"] = not prev_errs
        node_blockers["previs"] = prev_errs
        id_errs = (
            [e for e in pending_gate2_errors(drama) if ":identity" in e]
            + identity_gate_errors(project, drama)
        )
        if id_errs and section(section(drama, "presentations"), "identity"):
            id_errs.append("IDENTITY_PRESENTED_AWAITING_USER_CODE")
        done["images"] = not id_errs
        node_blockers["images"] = id_errs
    ready, blocked = [], {}
    complete = set()
    for node in needed:
        parents = [p for p in deps[node] if p not in complete]
        if parents:
            blocked[node] = parents
        elif done[node]:
            complete.add(node)
        else:
            ready.append(node)
    delivered = delivered and terminal in complete
    if mode == "full_film":
        post = section(drama, "post")
        delivered = delivered and post.get("done_at") and all(
            section(section(post, "media_qc"), n).get("ok") and
            section(post, "output_sha256s").get(n) == section(delivery, "file_sha256s").get(n) for n in names)
    if delivered and mode != "full_film":
        try:
            verify_artifacts(project, mode, names, manifest, today=day)
        except ProjectError:
            delivered = False
    action = "done" if delivered else next(iter(ready), "deliver")
    pref = section(drama, "choice_resolution").get("previs_preference")
    out = {"delivery_mode": mode, "next_action": action,
           "ready_nodes": [] if delivered else ready or ["deliver"], "blocked_nodes": {} if delivered else blocked,
           "missing_decisions": missing, "gate_blockers": [] if delivered else node_blockers.get(action, []),
           "terminal_artifacts": [terminal] if terminal else [],
           "delivered_files": names if delivered else [], "reconcile_recommended": untracked(project, manifest)}
    if pref:
        out["previs_preference"] = pref
    return out
