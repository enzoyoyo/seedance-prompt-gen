#!/usr/bin/env python3
"""Record the non-paying facts of an AI short-drama project in its resume manifest.

  init            create resume-manifest.json (`sop_version: "2.0"`) and set project paths
  intake          record the confirmed brief
  model-gate      lock Human Gate #1: image model, video model, audio plan, global spec & delivery mode,
                  each chosen by the user (their own words; agent placeholders and defaults are refused)
  release-intent  record a complete release-intent block (refused while incomplete)
  present         compose candidates into a decision sheet in 00_previs/ with a confirmation code
  identity        lock user-selected multi-angle character & scene reference assets (sha256 each)
  previs          lock user-approved 00_previs/ whitemodel & spatial blocking boards (sha256 each)
  impact          record the user's keep/redo words on a legacy change impact (v2 mandatory STALE forbids keep)
  invalidate      a root cause in Step 2/3/4 found downstream: atomically mark affected previs, shots and takes
                  STALE and open an incremental Human Gate #2 for the changed source(s)
  channel         record a channel capability card (five dated answers and live limits)
  post-done       record finished post-production outputs (verifying upstream gates and video decode)
  deliver         record delivered files after upstream completion, STALE clearance and decode verification
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import decision_sheet
import intake_choices
from change_impact import (
    apply_invalidation, close_pending_gate2, compute_impact, invalidation_scope, mark_impact_stale,
    open_impacts, pending_gate2, pending_gate2_errors, set_take_stale_state, stale_previs_scenes,
    stale_shot_ids, stale_take_errors, take_matches_current_refs, verify_incremental_gate2_lock,
)
from check_budget_gate import card_errors, one_shot_tier
from check_release_intent import check_applied_labels, check_intent
from drama_project import (
    MANIFEST_VERSION, VALID_ANGLES, ProjectError, file_lock, decision_errors, drama_block, load_manifest,
    manifest_path, nonempty, now_iso, read_json, resolve_in_project, section,
    sha256_file, take_rows, update_manifest, write_json_atomic,
)
from lock_script import locked_script_text, read_lock, verify_lock
from model_gate import (
    DELIVERY_MODES, delivery_mode, gate_required, is_placeholder, model_gate_errors, model_gate_execution_errors,
)
from previs_coverage import identity_gate_errors, previs_gate_errors, script_scenes, shot_ref_provenance_errors
from validate_shot_spec import active_shots, card_limit, load_project_spec, root_id, shot_beats, shot_rows

PATH_FIELDS = ("script", "shot_spec", "clips_dir", "translations")
DECISION_GATES = ("identity", "previs")
SOP_VERSION = "2.0"
MAX_WRONG_CODES = 3
WAIVE_FLAGS = {
    "identity": [("waive_multi_angle", ("跳过角色多角度：本集只用正面图", "skip character turnaround views")),
                 ("waive_scenes", ("跳过场景基准图：不锁空场主景", "skip scene master plates"))],
    "previs": [("waive", ("跳过白模站位：本集不做站位预演", "skip whitemodel blocking for this episode"))],
}
WAIVE_CHOICES = {gate: [text for _, text in rows] for gate, rows in WAIVE_FLAGS.items()}
STOP_TEXT = ("Show the decision sheet to the user, ask which candidates they choose, and STOP until they reply "
             "with their choice and the confirmation code. The code belongs to the user: never read it from the "
             "image, relay it, or fill it in.")
PRESENT_NEXT = ("Show these sheet file(s) to the user and STOP. Then run identity/previs with --user-words set to "
                "the user's own reply, which must contain the code they read on the sheet. " + STOP_TEXT)


def set_drama(project: Path, change: dict[str, Any]) -> dict[str, Any]:
    return update_manifest(project, lambda m: {**m, "drama": {**drama_block(m), **change}})


def cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    if not args.project.is_dir():
        raise ProjectError("INPUT_ERROR", "project directory does not exist")
    paths = {field: getattr(args, field) for field in PATH_FIELDS if getattr(args, field)}
    for field, value in paths.items():
        if resolve_in_project(args.project, value) is None:
            raise ProjectError("PATH_OUTSIDE_PROJECT", f"{field}:{value}")
    path = manifest_path(args.project)
    with file_lock(path):
        manifest = load_manifest(args.project) if path.exists() else {
            "version": MANIFEST_VERSION, "project_id": args.project_id or args.project.name,
            "shots": [], "takes": [], "edit_list": [], "drama": {"sop_version": SOP_VERSION}}
        drama = drama_block(manifest)
        version = args.sop_version or ("3.0" if not path.exists() and (args.delivery_mode or args.creative_mode)
                                       else drama.get("sop_version"))
        if version:
            drama["sop_version"] = version
        if args.delivery_mode or args.creative_mode:
            if version != "3.0":
                raise ProjectError("V7_MODE_REQUIRES_SOP_3")
            selections = {"delivery_mode": args.delivery_mode, "creative_mode": intake_choices.normalize_creative(args.creative_mode)}
            selections = {k: v for k, v in selections.items() if v}
            old = section(drama, "model_gate")
            prior = section(drama, "choice_resolution")
            changed = any(section(prior, "resolved").get(k, old.get(k, drama.get(k))) != v for k, v in selections.items())
            if changed:
                drama.update({k: v for k, v in {**old, **section(prior, "resolved")}.items() if k in intake_choices.FIELDS})
                drama.pop("choice_resolution", None)
                drama.pop("model_gate", None)
                for key in ("post", "delivery"):
                    if drama.get(key):
                        drama[key]["stale"] = True
            drama.update(selections)
        drama.update(paths)
        write_json_atomic(path, {**manifest, "drama": drama})
    return {"paths": {field: drama.get(field) for field in PATH_FIELDS}, "sop_version": version}


def cmd_intake(args: argparse.Namespace) -> dict[str, Any]:
    if not nonempty(args.brief) or not nonempty(args.user_words):
        raise ProjectError("USER_CONFIRMATION_REQUIRED", "give the brief and the user's own confirming words")
    record = {"brief": args.brief.strip(), "user_words": args.user_words.strip(), "confirmed_at": now_iso()}
    set_drama(args.project, {"intake": record})
    return {"intake": record}


def cmd_model_gate(args: argparse.Namespace) -> dict[str, Any]:
    """Human Gate #1: every field comes from the user's reply; placeholders and defaults are refused."""
    if drama_block(load_manifest(args.project)).get("sop_version") == "3.0":
        if is_placeholder(args.user_words):
            raise ProjectError("MODEL_GATE_USER_WORDS_INVALID")

        def lock(manifest):
            prev = section(drama_block(manifest), "choice_resolution")
            words = (args.user_words or "").strip()
            numeric = bool(re.fullmatch(r"\d+(?:\s*[,，]\s*\d+)*", words))
            if numeric and prev and not prev.get("missing") and not prev.get("conflicts") and not prev.get("text_only"):
                if args.request_id != prev.get("request_id") or args.revision != prev.get("revision"):
                    raise intake_choices.StaleMenu(prev)
                for key in intake_choices.FIELDS:
                    explicit = getattr(args, key, None)
                    if explicit:
                        norm_val = intake_choices.normalize_creative(explicit) if key == "creative_mode" else explicit
                        if norm_val != prev.get("resolved", {}).get(key):
                            raise ProjectError("CONFLICTING_EXPLICIT_AND_MENU_CHOICE",
                                               f"{key}:{prev.get('resolved', {}).get(key)}!={norm_val}")
                result = prev
            else:
                result = intake_choices.resolve(args, manifest)
                if result["conflicts"] or result["missing"] or result["text_only"]:
                    raise ProjectError("MODEL_GATE_INCOMPLETE", ",".join(result["missing"]))
            staged = intake_choices.apply_resolution(manifest, result)
            drama = staged["drama"]
            confirmed = {k: v for k, v in result["resolved"].items() if result["evidence"].get(k) != "default"}
            drama.update(confirmed)
            drama["model_gate"] = {**confirmed, "confirmed_at": now_iso(), "user_words": words}
            return staged
        return {"model_gate": drama_block(update_manifest(args.project, lock))["model_gate"]}
    raw_words = args.user_words.strip() if nonempty(args.user_words) else ""
    record: dict[str, Any] = {
        "image_model": args.image_model, "video_model": args.video_model, "audio_plan": args.audio_plan,
        "delivery_mode": args.delivery_mode, "aspect_ratio": args.aspect_ratio, "pacing": args.pacing,
        "style_tone": args.style_tone,
        "user_words": decision_sheet.redact_codes(raw_words),
        "confirmed_at": now_iso(),
    }
    record = {key: value.strip() if isinstance(value, str) else value for key, value in record.items()}

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        drama = drama_block(manifest)
        shown_gate = section(section(drama, "presentations"), "model_gate")
        if shown_gate.get("nonce"):
            record["nonce"] = shown_gate["nonce"]
        probe_drama = {**drama, "model_gate": record}
        intent_ratio = section(drama, "release_intent").get("aspect_ratio")
        errors = model_gate_errors(probe_drama) + model_gate_execution_errors(probe_drama, None, intent_ratio)
        if errors:
            raise ProjectError(errors[0], "; ".join(errors[1:]) + " -- show `model_gate.py render` and STOP & WAIT")
        log = [*(drama.get("model_gate_log") or []), *([drama["model_gate"]] if drama.get("model_gate") else [])]
        shown = {k: v for k, v in section(drama, "presentations").items() if k != "model_gate"}
        return {**manifest, "drama": {**drama, "model_gate": record, "model_gate_log": log, "presentations": shown}}

    update_manifest(args.project, mutate)
    return {"model_gate": record}


def cmd_release_intent(args: argparse.Namespace) -> dict[str, Any]:
    intent = read_json(args.file.expanduser())
    script_text = locked_script_text(args.project) if read_lock(args.project) is not None else None
    errors = check_intent(intent, script_text)
    if errors:
        raise ProjectError(errors[0], "; ".join(errors[1:]))

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        drama = drama_block(manifest)
        exec_errs = model_gate_execution_errors(drama, None, intent.get("aspect_ratio"))
        if exec_errs:
            raise ProjectError(exec_errs[0], "; ".join(exec_errs[1:]))
        return {**manifest, "drama": {**drama, "release_intent": {**intent, "recorded_at": now_iso()}}}

    update_manifest(args.project, mutate)
    return {"release_intent": "recorded", "checked_against_locked_script": script_text is not None}


def hash_project_file(project: Path, name: str, err_code: str) -> tuple[str, str]:
    path = resolve_in_project(project, name)
    if path is None or not path.is_file():
        raise ProjectError(err_code, name)
    return str(path.relative_to(project.resolve())), sha256_file(path)


def split_view_specs(item: str, rest: str) -> list[tuple[list[str], str]]:
    pairs: list[tuple[list[str], str]] = []
    pending: list[str] = []
    for chunk in rest.split(","):
        head, colon, path = chunk.partition(":")
        if not colon:
            pending.append(head.strip())
            continue
        angles = [*pending, head.strip()]
        if not all(nonempty(a) for a in angles) or not nonempty(path):
            raise ProjectError("INPUT_ERROR", f"--char-view expects CHAR=angle:path: {item}")
        pairs.append((angles, path.strip()))
        pending = []
    if pending or not pairs:
        raise ProjectError("INPUT_ERROR", f"--char-view expects CHAR=angle:path: {item}")
    return pairs


def parse_char_views(project: Path, items: list[str]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    characters: dict[str, dict[str, Any]] = {}
    refs: list[dict[str, str]] = []
    for item in items:
        char_id, eq, rest = item.partition("=")
        if not eq or not nonempty(char_id):
            raise ProjectError("INPUT_ERROR", f"--char-view expects CHAR=angle:path: {item}")
        entry = characters.setdefault(char_id.strip(), {"angles": [], "paths": []})
        for angles, file_name in split_view_specs(item, rest):
            if not set(angles) <= VALID_ANGLES:
                raise ProjectError("CHARACTER_ANGLES_INVALID", f"{char_id}:{','.join(angles)}")
            rel, digest = hash_project_file(project, file_name, "IDENTITY_ASSET_MISSING")
            entry["angles"] = sorted(set(entry["angles"]) | set(angles))
            entry["paths"] = [*entry["paths"], *([rel] if rel not in entry["paths"] else [])]
            refs.append({"path": rel, "sha256": digest})
    return characters, refs


def parse_named_files(project: Path, items: list[str], flag: str, code: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for item in items:
        key, sep, name = item.partition("=")
        if not sep or not nonempty(key) or not nonempty(name):
            raise ProjectError("INPUT_ERROR", f"{flag} expects ID=path: {item}")
        rel, digest = hash_project_file(project, name.strip(), code)
        out[key.strip()] = {"path": rel, "sha256": digest}
    return out


def parse_candidates(project: Path, items: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        key, eq, name = item.partition("=")
        group, slash, label = key.rpartition("/")
        if not eq or not slash or not all(nonempty(v) for v in (group, label, name)):
            raise ProjectError("INPUT_ERROR", f"--candidate expects GROUP/LABEL=path: {item}")
        rel, digest = hash_project_file(project, name.strip(), "CANDIDATE_MISSING")
        if any((r["group"], r["label"]) == (group.strip(), label.strip()) for r in rows):
            raise ProjectError("CANDIDATE_DUPLICATE", f"{group}/{label}")
        rows.append({"group": group.strip(), "label": label.strip(), "path": rel, "sha256": digest,
                     "abs": project.resolve() / rel})
    return rows


def sheet_waivers(project: Path, gate: str, candidates: list[dict[str, Any]]) -> list[tuple[str, str]]:
    if gate != "previs":
        return WAIVE_CHOICES[gate]
    scenes = script_scenes(project)
    if scenes is None:
        raise ProjectError("SCRIPT_NOT_LOCKED", "lock the script before presenting previs boards")
    unknown = sorted({row["group"] for row in candidates} - set(scenes))
    if unknown:
        raise ProjectError("PREVIS_SCENE_UNKNOWN", f"{','.join(unknown)}: groups must be script scene ids "
                           f"({','.join(scenes)})")
    return [*WAIVE_CHOICES[gate], *((f"只跳过 {scene} 这一场的白模", f"skip whitemodel for scene {scene} only")
                                    for scene in scenes)]


def cmd_present(args: argparse.Namespace) -> dict[str, Any]:
    """Compose the decision sheet and bind any open incremental invalidation IDs for `args.gate`."""
    current_manifest = load_manifest(args.project)
    candidates = parse_candidates(args.project, args.candidate)
    waivers = sheet_waivers(args.project, args.gate, candidates)
    folder = args.project / "00_previs"
    folder.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    salt = decision_sheet.new_salt()
    code = decision_sheet.new_code()
    digest = decision_sheet.code_digest(salt, code)
    pages = decision_sheet.render_sheets(args.gate, candidates, waivers, code,
                                         folder / f"decision_{args.gate}_{stamp}")
    open_inv_ids = [str(r["invalidation_id"]) for r in pending_gate2(drama_block(current_manifest))
                    if r.get("gate") == args.gate and r.get("invalidation_id")]
    record = {
        "gate": args.gate,
        "presented_at": now_iso(),
        "salt": salt,
        "code_hash": digest,
        "sheets": [{"path": str(p.relative_to(args.project.resolve())), "sha256": sha256_file(p)}
                   for p in (page.resolve() for page in pages)],
        "candidates": [{k: v for k, v in row.items() if k != "abs"} for row in candidates],
        "waive_choices": [flag for flag, _ in WAIVE_FLAGS[args.gate]],
        **({"covers_invalidations": open_inv_ids} if open_inv_ids else {}),
    }

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        drama = drama_block(manifest)
        fresh_inv = [str(r["invalidation_id"]) for r in pending_gate2(drama)
                     if r.get("gate") == args.gate and r.get("invalidation_id")]
        rec = {**record, **({"covers_invalidations": fresh_inv} if fresh_inv else {})}
        return {**manifest, "drama": {**drama, "presentations": {**section(drama, "presentations"),
                                                                 args.gate: rec}}}
    update_manifest(args.project, mutate)
    return {"gate": args.gate, "sheets": [row["path"] for row in record["sheets"]],
            "candidates": len(candidates), "next": PRESENT_NEXT}


def code_waived(project: Path) -> bool:
    waiver = section(drama_block(load_manifest(project)), "code_waiver")
    return nonempty(waiver.get("user_words")) and nonempty(waiver.get("recorded_at"))


def cmd_code_waiver(args: argparse.Namespace) -> dict[str, Any]:
    if not nonempty(args.user_words):
        raise ProjectError("USER_CONFIRMATION_REQUIRED", "quote the user's own words turning confirmation codes off")
    record = {"user_words": args.user_words.strip(), "recorded_at": now_iso()}
    set_drama(args.project, {"code_waiver": record})
    return {"code_waiver": record}


def check_code(project: Path, gate: str, pending: dict[str, Any], words: str) -> None:
    if code_waived(project):
        return
    typed = decision_sheet.codes_in(words)
    if not typed:
        raise ProjectError("CONFIRMATION_CODE_MISSING", f"{gate}: " + STOP_TEXT)
    if any(decision_sheet.code_digest(pending["salt"], token) == pending["code_hash"] for token in typed):
        return

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        drama = drama_block(manifest)
        shown = section(drama, "presentations")
        row = {**section(shown, gate), "wrong_attempts": int(section(shown, gate).get("wrong_attempts", 0)) + 1}
        return {**manifest, "drama": {**drama, "presentations": {**shown, gate: row}}}
    attempts = section(section(drama_block(update_manifest(project, mutate)), "presentations"), gate)["wrong_attempts"]
    left = max(0, MAX_WRONG_CODES - attempts)
    raise ProjectError("CONFIRMATION_CODE_WRONG", f"{gate}: {left} attempt(s) left before this sheet is void. "
                       + STOP_TEXT)


def verify_decision(project: Path, gate: str, chosen: list[dict[str, str]], words: str,
                    proposed_record: dict[str, Any]) -> dict[str, Any]:
    """Verify presentation sheet, confirmation code, and any open incremental Human Gate #2 constraints."""
    drama = drama_block(load_manifest(project))
    pending = section(section(drama, "presentations"), gate)
    if not pending:
        raise ProjectError("PRESENTATION_MISSING", f"{gate}: run `drama_setup.py present --gate {gate}` first. "
                           + STOP_TEXT)
    if int(pending.get("wrong_attempts", 0)) >= MAX_WRONG_CODES:
        raise ProjectError("PRESENTATION_VOID", f"{gate}: {MAX_WRONG_CODES} wrong codes; run `drama_setup.py "
                           f"present --gate {gate}` again (new sheet, new code) and show it to the user. " + STOP_TEXT)
    sheet_errors = decision_errors(project, {"decision": {**pending, "decided_at": "pending"}}, [], gate.upper())
    if sheet_errors:
        raise ProjectError(sheet_errors[0].split(":", 1)[0], f"{gate}: present again. " + STOP_TEXT)
    shown = {row["path"]: row["sha256"] for row in pending["candidates"]}
    for row in chosen:
        if row["path"] not in shown:
            raise ProjectError("CHOICE_NOT_PRESENTED", f"{row['path']}: present it first. " + STOP_TEXT)
        if row["sha256"] != shown[row["path"]]:
            raise ProjectError("CANDIDATE_CHANGED", f"{row['path']}: changed since shown; present again. " + STOP_TEXT)
    check_code(project, gate, pending, words)
    verify_incremental_gate2_lock(drama, gate, pending, proposed_record)
    return {**pending, "decided_at": now_iso(), "chosen": sorted({row["path"] for row in chosen})}


def commit_decision(project: Path, gate: str, key: str, record: dict[str, Any]) -> dict[str, Any] | None:
    holder: dict[str, Any] = {}

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        drama = drama_block(manifest)
        pending_pres = section(section(drama, "presentations"), gate)
        verify_incremental_gate2_lock(drama, gate, pending_pres, record)
        impact = compute_impact(project, manifest, gate, key, record)
        holder["impact"] = impact
        pending = {k: v for k, v in section(drama, "presentations").items() if k != gate}
        log = [*(drama.get("presentation_log") or []), record["decision"]]
        impacts = [*(drama.get("impacts") or []), *([impact] if impact else [])]
        locked = {**manifest, "drama": {**drama, key: record, "presentations": pending, "presentation_log": log,
                                        "impacts": impacts}}
        return close_pending_gate2(mark_impact_stale(locked, impact), gate, record)
    update_manifest(project, mutate)
    return holder.get("impact")


def cmd_impact(args: argparse.Namespace) -> dict[str, Any]:
    if not nonempty(args.user_words):
        raise ProjectError("USER_CONFIRMATION_REQUIRED", "quote the user's own keep/redo reply")
    found: dict[str, Any] = {}

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        drama = drama_block(manifest)
        if args.decision == "keep" and drama.get("sop_version") in {"2.0", "3.0"}:
            raise ProjectError("STALE_MANDATORY_REGENERATION_REQUIRED",
                               "SPEC v2.0 requires regenerating affected STALE shots; `keep` is forbidden")
        rows = [row for row in drama.get("impacts") or [] if isinstance(row, dict)]
        row = next((r for r in rows if r.get("id") == args.id), None)
        if row is None:
            raise ProjectError("IMPACT_UNKNOWN", args.id)
        if row.get("resolution"):
            raise ProjectError("IMPACT_ALREADY_RESOLVED", args.id)
        stamp = now_iso()
        row["resolution"] = {"decision": args.decision, "user_words": args.user_words.strip(), "resolved_at": stamp}
        found.update(row)
        updated = {**manifest, "drama": {**drama, "impacts": rows}}
        impact_takes = {t.get("take_id") for t in (row.get("takes") or []) if isinstance(t, dict) and t.get("take_id")}
        state = "WAIVED" if args.decision == "keep" else "REJECTED"
        updated = set_take_stale_state(updated, impact_takes, state, f"impact {args.id} {args.decision}: "
                                       f"{args.user_words.strip()}")
        if args.decision == "redo":
            import drama_ledger
            reason = f"impact {args.id} redo: {args.user_words.strip()}"
            for tid in sorted(impact_takes):
                cur = drama_ledger.find_take(updated, tid)
                if cur.get("job_state") == "succeeded" and cur.get("status") != "rejected":
                    updated = drama_ledger.replace_take(
                        updated, tid,
                        lambda old, r=reason, ts=stamp: {**old, "status": "rejected", "reject_reason": r, "judged_at": ts},
                    )
        return updated
    update_manifest(args.project, mutate)
    return {"impact": found["id"], "decision": args.decision, "shots": found.get("shots", [])}


def cmd_invalidate(args: argparse.Namespace) -> dict[str, Any]:
    """Atomic cross-stage rollback under the manifest lock: previs -> shots -> takes go STALE, Gate #2 reopens."""
    if not nonempty(args.reason):
        raise ProjectError("INPUT_ERROR", "--reason must name the root cause")
    target = args.target.strip()
    reason = f"{args.stage}:{target}: {args.reason.strip()}"
    holder: dict[str, Any] = {}

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        scope = invalidation_scope(args.project, manifest, args.stage, target)
        holder["scope"] = scope
        return apply_invalidation(manifest, args.stage, target, reason, scope)

    update_manifest(args.project, mutate)
    scope = holder["scope"]
    return {
        "stage": args.stage,
        "target": target,
        "gate": scope["gate"],
        "stale_previs_scenes": scope["previs_scenes"],
        "stale_shots": scope["shots"],
        "stale_takes": scope["takes"],
        "untouched_shots": scope["untouched"],
        "next": (f"Fix the {args.stage} source (and any affected whitemodel boards), put the updated candidates on "
                 f"`present --gate {scope['gate']}`, and STOP for the user's code (incremental Human Gate #2). "
                 "Batch video and assembly stay blocked until re-signed and regenerated."),
    }


def cmd_identity(args: argparse.Namespace) -> dict[str, Any]:
    if not nonempty(args.user_words):
        raise ProjectError("USER_CONFIRMATION_REQUIRED", "quote the user's choice of character & scene assets")
    characters, view_refs = parse_char_views(args.project, args.char_view)
    scenes = parse_named_files(args.project, args.scene_ref, "--scene-ref", "SCENE_ASSET_MISSING")
    extra_refs = [{"path": r, "sha256": d} for r, d in
                  (hash_project_file(args.project, name, "IDENTITY_ASSET_MISSING") for name in args.ref)]
    by_path = {row["path"]: row for row in [*view_refs, *scenes.values(), *extra_refs]}
    record: dict[str, Any] = {
        "locked_at": now_iso(), "user_words": decision_sheet.redact_codes(args.user_words.strip()),
        "refs": list(by_path.values()), "characters": characters, "scenes": scenes,
        "waived_multi_angle": bool(args.waive_multi_angle), "waived_scenes": bool(args.waive_scenes),
    }
    if nonempty(args.likeness_preflight):
        record["likeness_preflight"] = args.likeness_preflight.strip()
    current_drama = {**drama_block(load_manifest(args.project)), "identity_assets": record}
    errors = identity_gate_errors(args.project, current_drama, require_decision=False)
    if errors:
        raise ProjectError(errors[0], "; ".join(errors[1:]))
    record["decision"] = verify_decision(args.project, "identity", list(by_path.values()), args.user_words, record)
    record["decision"]["waived"] = [flag for flag in ("waive_multi_angle", "waive_scenes") if getattr(args, flag)]
    impact = commit_decision(args.project, "identity", "identity_assets", record)
    return {"identity_assets": len(record["refs"]), "characters": len(characters), "scenes": len(scenes),
            "impact": impact}


def cmd_previs(args: argparse.Namespace) -> dict[str, Any]:
    if not nonempty(args.user_words):
        raise ProjectError("USER_CONFIRMATION_REQUIRED", "quote the user's approval or waiver of 00_previs blocking")
    scenes = parse_named_files(args.project, args.scene, "--scene", "PREVIS_ASSET_MISSING")
    waived_scenes = sorted({name.strip() for name in args.waive_scene if nonempty(name)})
    if args.waive and args.ref:
        raise ProjectError("INPUT_ERROR", "--ref cannot be combined with --waive")
    extra_refs: list[dict[str, str]] = []
    seen_refs: set[str] = set()
    for name in args.ref:
        rel, digest = hash_project_file(args.project, name.strip(), "PREVIS_ASSET_MISSING")
        if not str(rel).replace("\\", "/").startswith("00_previs/"):
            raise ProjectError("PREVIS_OUTSIDE_00_PREVIS", rel)
        if rel not in seen_refs:
            seen_refs.add(rel)
            extra_refs.append({"path": rel, "sha256": digest})
    record: dict[str, Any] = {"locked_at": now_iso(), "user_words": decision_sheet.redact_codes(args.user_words.strip()),
                              "tool": args.tool, "waived": bool(args.waive), "scenes": scenes, "waived_scenes": waived_scenes,
                              **({"extra_refs": extra_refs} if extra_refs else {})}
    errors = previs_gate_errors(args.project, {"previs": record}, require_decision=False)
    if errors:
        raise ProjectError(errors[0], "; ".join(errors[1:]))
    record["decision"] = verify_decision(args.project, "previs", [*scenes.values(), *extra_refs],
                                         args.user_words, record)
    record["decision"]["waived"] = (["waive"] if args.waive else []) + [f"waive_scene:{s}" for s in waived_scenes]
    impact = commit_decision(args.project, "previs", "previs", record)
    return {"previs_scenes": len(scenes), "extra_refs": len(extra_refs), "waived": bool(args.waive),
            "waived_scenes": waived_scenes, "impact": impact}


def cmd_channel(args: argparse.Namespace) -> dict[str, Any]:
    card = read_json(args.card.expanduser())
    errors = card_errors({args.name: card}, args.name, args.today)
    errors += card_limit(card, args.name, args.today)[1] if not errors else []
    if errors:
        raise ProjectError(errors[0], "; ".join(errors[1:]))
    update_manifest(args.project, lambda m: {**m, "drama": {
        **drama_block(m), "channels": {**section(drama_block(m), "channels"), args.name: card}}})
    return {"channel": args.name}


def existing_files(project: Path, names: list[str]) -> list[str]:
    found = []
    for name in names:
        path = resolve_in_project(project, name)
        if path is None or not path.is_file():
            raise ProjectError("OUTPUT_FILE_MISSING", name)
        found.append(str(path.relative_to(project.resolve())))
    return found


def stream_duration(rows: list[dict[str, Any]], codec: str) -> float | None:
    for row in rows:
        if row.get("codec_type") != codec:
            continue
        try:
            dur = float(row["duration"])
        except (KeyError, TypeError, ValueError):
            continue
        if dur > 0:
            return dur
    return None


def verify_video_output(path: Path, rel: str) -> bool:
    if path.stat().st_size <= 1:
        raise ProjectError("POST_OUTPUT_INVALID_VIDEO", f"{rel}: empty or 1-byte file")
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "V:0", "-read_intervals", "%+#1",
         "-show_frames", "-show_streams", "-print_format", "json", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
    )
    try:
        data = json.loads(done.stdout) if done.returncode == 0 else {}
    except json.JSONDecodeError:
        data = {}
    streams = [row for row in data.get("streams") or [] if row.get("codec_type") == "video"
               and int(row.get("width") or 0) > 0 and int(row.get("height") or 0) > 0]
    frames = data.get("frames") or []
    if not streams or not frames:
        raise ProjectError("POST_OUTPUT_INVALID_VIDEO", f"{rel}: unreadable or has no decodable video stream")
    meta = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-print_format", "json", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
    )
    try:
        all_streams = (json.loads(meta.stdout).get("streams") or []) if meta.returncode == 0 and meta.stdout else []
    except json.JSONDecodeError:
        all_streams = []
    v_dur, a_dur = stream_duration(all_streams, "video"), stream_duration(all_streams, "audio")
    if v_dur is not None and a_dur is not None and abs(v_dur - a_dur) > 0.25:
        raise ProjectError("POST_OUTPUT_AV_DURATION_MISMATCH", f"{rel}: video={v_dur:.3f}s audio={a_dur:.3f}s")
    return any(row.get("codec_type") == "audio" for row in all_streams)


def verify_remix_evidence(out: Path, rel: str) -> None:
    candidates = [out.with_suffix(".remix.json"), out.with_name(out.name + ".remix.json")]
    sidecar_path = next((p for p in candidates if p.is_file()), None)
    if sidecar_path is None:
        raise ProjectError("POST_REMIX_EVIDENCE_MISSING", rel)
    sidecar = read_json(sidecar_path)
    if not isinstance(sidecar, dict) or sidecar.get("tool") != "remix_score" or sidecar.get("output_sha256") != sha256_file(out):
        raise ProjectError("POST_REMIX_EVIDENCE_MISMATCH", rel)


def _all_final_shots_approved_errors(project: Path, manifest: dict[str, Any]) -> list[str]:
    spec, spec_dir, _ = load_project_spec(project)
    drama = drama_block(manifest)
    target_tier = one_shot_tier(drama) or "final"
    rows = shot_rows(spec)
    post = set(spec.get("post_beats") or [])
    errors: list[str] = []
    for shot in active_shots(rows):
        if set(shot_beats(shot, [])) and set(shot_beats(shot, [])) <= post:
            continue
        root = root_id(rows, shot["id"])
        take = next((t for t in take_rows(manifest) if t.get("shot_id") == root and t.get("status") == "approved"
                     and (t.get("tier") == target_tier or t.get("origin") == "reused")), None)
        if take is None:
            errors.append(f"FINAL_SHOT_NOT_APPROVED:{shot['id']}")
        elif drama.get("sop_version") == "3.0" and (not (path := resolve_in_project(project, take.get("file")))
                or not path.is_file() or sha256_file(path) != take.get("file_sha256")):
            errors.append(f"APPROVED_FILE_MISSING_OR_CHANGED:{take.get('take_id')}")
        elif not take_matches_current_refs(spec, spec_dir, take):
            errors.append(f"STALE_TAKE_INVALIDATED:{take.get('take_id')}")
    return errors


def _common_stale_and_upstream_errors(project: Path, manifest: dict[str, Any]) -> list[str]:
    drama = drama_block(manifest)
    errors = verify_lock(project)
    if errors:
        return errors
    errors += check_intent(section(drama, "release_intent"), locked_script_text(project))
    errors += pending_gate2_errors(drama)
    errors += [f"STALE_PREVIS_SCENE:{sc}" for sc in sorted(stale_previs_scenes(drama))]
    errors += [f"STALE_SHOT_NOT_REGENERATED:{sid}" for sid in sorted(stale_shot_ids(drama))]
    errors += stale_take_errors([t for t in take_rows(manifest) if t.get("status") == "approved"])
    errors += [f"UNRESOLVED_CHANGE_IMPACT:{row['id']}" for row in open_impacts(drama)]
    errors += previs_gate_errors(project, drama)
    errors += identity_gate_errors(project, drama)
    return errors


def cmd_post_done(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.project)
    drama = drama_block(manifest)
    if drama.get("sop_version") == "3.0" and delivery_mode(drama) != "full_film":
        raise ProjectError("POST_NOT_REQUIRED", str(delivery_mode(drama)))
    outputs = existing_files(args.project, args.output)
    if shutil.which("ffprobe") is None:
        raise ProjectError("FFPROBE_MISSING", "install ffmpeg to verify post-production video outputs")
    upstream = _common_stale_and_upstream_errors(args.project, manifest)
    if gate_required(drama):
        upstream += model_gate_errors(drama)
        if delivery_mode(drama) == "prompt_only":
            upstream.append("DELIVERY_MODE_PROMPT_ONLY")
        upstream += _all_final_shots_approved_errors(args.project, manifest)
    if upstream:
        head, _, detail = upstream[0].partition(":")
        raise ProjectError(head, detail)

    native_bgm = section(drama, "release_intent").get("native_bgm")
    root = args.project.resolve()
    hashes: dict[str, str] = {}
    reports = {}
    for rel in outputs:
        out = root / rel
        before = sha256_file(out) if drama.get("sop_version") == "3.0" else None
        has_audio = verify_video_output(out, rel)
        if drama.get("sop_version") == "3.0":
            from media_inspection import inspect
            qc = inspect(out, delivery_mode="full_film", creative_mode=drama.get("creative_mode"),
                         audio_route=args.audio_route, subtitle=args.subtitle, voice_source=args.voice_source,
                         claimed_resolution=args.claimed_resolution, upscaled_from=args.upscaled_from,
                         raw_clip=args.raw_clip, cutlist=args.cutlist, locks=section(drama, "release_intent"))
            reports[rel] = qc
            if not qc["ok"]:
                raise ProjectError(qc["errors"][0], ", ".join(qc["errors"][1:]))
        if has_audio and native_bgm is False and not args.waive_remix:
            verify_remix_evidence(out, rel)
        hashes[rel] = sha256_file(out)
        if before is not None and before != hashes[rel]:
            raise ProjectError("POST_CHANGED_DURING_CHECK", rel)
    record: dict[str, Any] = {"done_at": now_iso(), "outputs": outputs, "output_sha256s": hashes}
    if reports:
        record["media_qc"] = reports
    if args.waive_remix:
        record["waived_remix"] = True
    if reports:
        def finish(current):
            if current != manifest:
                raise ProjectError("PROJECT_CHANGED_DURING_POST_CHECK")
            return {**current, "drama": {**drama_block(current), "post": record}}
        update_manifest(args.project, finish)
    else:
        set_drama(args.project, {"post": record})
    return {"post": record}


def _prompt_only_deliver_errors(project: Path, manifest: dict[str, Any]) -> list[str]:
    from eval_harness import DEFAULT_BOOK, project_shot_case
    from harness_rules import active_rules_from, evaluate, load_book
    from ledger_submit import Context, spec_errors

    spec, spec_dir, _ = load_project_spec(project)
    drama = drama_block(manifest)
    errors = shot_ref_provenance_errors(project, drama, spec, spec_dir)
    errors += spec_errors(Context(project, manifest, spec, spec_dir), locked_script_text(project), date.today())
    active = active_rules_from(DEFAULT_BOOK)
    book_rows = load_book(DEFAULT_BOOK) if DEFAULT_BOOK.is_file() else []
    for shot in active_shots(shot_rows(spec)):
        if is_reuse_shot := bool(shot.get("reuse")):
            _ = is_reuse_shot
            continue
        payload, extra, _ = project_shot_case(project, shot["id"])
        rep = evaluate(payload, active, extra, book_rows)
        if rep["verdict"] != "PASS":
            errors += [f"PRE_GEN_EVAL_FAILED:{shot['id']}:{e}" for e in rep["blocking_errors"]]
    return errors


def cmd_deliver(args: argparse.Namespace) -> dict[str, Any]:
    files = existing_files(args.project, args.file)

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        drama = drama_block(manifest)
        mode = delivery_mode(drama)
        if drama.get("sop_version") == "3.0" and mode != "full_film":
            from delivery_graph import verify_artifacts
            errors = model_gate_errors(drama) + check_applied_labels(section(drama, "release_intent"), args.label)
            if errors:
                raise ProjectError(errors[0])
            if not section(drama, "intake").get("confirmed_at"):
                raise ProjectError("BRIEF_NOT_CONFIRMED")
            if stale_shot_ids(drama) or open_impacts(drama):
                raise ProjectError("DELIVERY_UPSTREAM_STALE")
            if mode == "video_clips":
                upstream = _common_stale_and_upstream_errors(args.project, manifest)
                if upstream:
                    raise ProjectError(upstream[0])
            hashes = {f: sha256_file(args.project / f) for f in files}
            verify_artifacts(args.project, mode, files, manifest, run_qc=True)
            if any(sha256_file(args.project / f) != hashes[f] for f in files):
                raise ProjectError("OUTPUT_CHANGED_DURING_CHECK")
            record = {"delivered_at": now_iso(), "delivery_mode": mode, "files": files, "labels_applied": args.label,
                      "file_sha256s": hashes}
            return {**manifest, "drama": {**drama, "delivery": record}}
        if drama.get("sop_version") == "3.0":
            from delivery_graph import verified_spec
            if not section(drama, "intake").get("confirmed_at"):
                raise ProjectError("BRIEF_NOT_CONFIRMED")
            verified_spec(args.project, manifest)
        errors = _common_stale_and_upstream_errors(args.project, manifest)
        if gate_required(drama):
            errors += model_gate_errors(drama)
        errors += check_applied_labels(section(drama, "release_intent"), args.label)
        if errors:
            head, _, detail = errors[0].partition(":")
            raise ProjectError(head, detail)

        if delivery_mode(drama) == "prompt_only":
            p_errs = _prompt_only_deliver_errors(args.project, manifest)
            if p_errs:
                head, _, detail = p_errs[0].partition(":")
                raise ProjectError(head, detail)
        else:
            post = section(drama, "post")
            if post.get("stale"):
                raise ProjectError("POST_STALE")
            if not nonempty(post.get("done_at")):
                raise ProjectError("POST_NOT_DONE", "run `drama_setup.py post-done` before delivering video")
            shot_errs = _all_final_shots_approved_errors(args.project, manifest)
            if shot_errs:
                head, _, detail = shot_errs[0].partition(":")
                raise ProjectError(head, detail)
            if shutil.which("ffprobe") is None:
                raise ProjectError("FFPROBE_MISSING", "install ffmpeg to verify delivered video files")
            root = args.project.resolve()
            post_outputs = set(post.get("outputs") or [])
            post_shas = section(post, "output_sha256s")
            for rel in files:
                verify_video_output(root / rel, rel)
                if rel not in post_outputs or not nonempty(post_shas.get(rel)):
                    raise ProjectError("DELIVER_FILE_NOT_POST_VERIFIED", rel)
                if drama.get("sop_version") == "3.0" and not section(section(post, "media_qc"), rel).get("ok"):
                    raise ProjectError("POST_MEDIA_QC_MISSING", rel)
                if sha256_file(root / rel) != post_shas.get(rel):
                    raise ProjectError("POST_OUTPUT_CHANGED_AFTER_CHECK", rel)

        record = {
            "delivered_at": now_iso(), "delivery_mode": mode,
            "files": files,
            "file_sha256s": {rel: sha256_file(args.project.resolve() / rel) for rel in files},
            "labels_applied": args.label,
        }
        return {**manifest, "drama": {**drama, "delivery": record}}

    update_manifest(args.project, mutate)
    return {"delivered": files, "labels_applied": args.label}


def add_preproduction_commands(add: Any) -> None:
    init = add("init", cmd_init, "create the manifest and set project paths")
    init.add_argument("--project-id")
    init.add_argument("--sop-version", choices=("2.0", "3.0"))
    init.add_argument("--delivery-mode", choices=intake_choices.MODES)
    init.add_argument("--creative-mode", "--story-mode", choices=(*intake_choices.CREATIVE, "film"))
    for field in PATH_FIELDS:
        init.add_argument(f"--{field.replace('_', '-')}", help="path relative to the project")
    intake = add("intake", cmd_intake, "record the confirmed brief")
    intake.add_argument("--brief", required=True)
    intake.add_argument("--user-words", required=True)
    intent = add("release-intent", cmd_release_intent, "record a complete release-intent block")
    intent.add_argument("--file", required=True, type=Path, help="JSON file holding the block")
    present = add("present", cmd_present, "show candidates to the user on one decision sheet with a code")
    present.add_argument("--gate", required=True, choices=DECISION_GATES)
    present.add_argument("--candidate", action="append", default=[],
                         help="GROUP/LABEL=path, e.g. lead.front/A=refs/lead_a.png or S01/B=00_previs/S01_B.png")
    identity = add("identity", cmd_identity, "lock user-selected multi-angle character & scene assets")
    identity.add_argument("--char-view", action="append", default=[],
                          help="CHAR=angle[,angle]:path (need front + non-front per character)")
    identity.add_argument("--scene-ref", action="append", default=[], help="SCENE=path master location anchor")
    identity.add_argument("--ref", action="append", default=[], help="extra prop or style ref relative to project")
    identity.add_argument("--likeness-preflight", help="moderation/subject-library verification when real_public_figures=true")
    identity.add_argument("--waive-multi-angle", action="store_true", help="only when user explicitly waived turnaround views")
    identity.add_argument("--waive-scenes", action="store_true", help="only when user explicitly waived scene master plates")
    identity.add_argument("--user-words", required=True, help="the user's own reply, including the sheet's code")
    previs = add("previs", cmd_previs, "lock user-approved 00_previs/ whitemodel & scene blocking boards")
    previs.add_argument("--scene", action="append", default=[],
                        help="SCENE_ID=00_previs/board.png (repeatable); SCENE_ID is the script's scene id, e.g. S1")
    previs.add_argument("--ref", action="append", default=[],
                        help="extra 00_previs/ still approved on the same decision sheet (repeatable)")
    previs.add_argument("--waive-scene", action="append", default=[],
                        help="script scene id the user chose to skip (repeatable); every scene needs --scene or this")
    previs.add_argument("--tool", default="whitemodel_board", help="whitemodel_board | stage_desk | blender | jutsu")
    previs.add_argument("--waive", action="store_true", help="only when user explicitly waived whitemodel previs")
    previs.add_argument("--user-words", required=True, help="the user's own reply, including the sheet's code")
    impact = add("impact", cmd_impact, "record the user's keep/redo decision on a legacy change impact")
    impact.add_argument("--id", required=True, help="impact id printed by identity/previs, e.g. previs-1")
    impact.add_argument("--decision", required=True, choices=("keep", "redo"),
                        help="keep (legacy v1 only) or redo affected shots and takes")
    impact.add_argument("--user-words", required=True,
                        help="the user's own words choosing keep or redo; never written by the agent")
    waiver = add("code-waiver", cmd_code_waiver,
                 "user turned confirmation codes off for this project; sheets are still presented")
    waiver.add_argument("--user-words", required=True,
                        help="the user's own words turning codes off; never written by the agent")


def add_harness_commands(add: Any) -> None:
    """SPEC v2.0: Human Gate #1 model lock and cross-stage invalidation."""
    gate = add("model-gate", cmd_model_gate, "lock Human Gate #1 with the user's four choices")
    gate.add_argument("--image-model", required=False)
    gate.add_argument("--video-model", required=False)
    gate.add_argument("--audio-plan", required=False,
                      help="none | 本项目无需生成音频 | bgm:<model> | tts_sfx:<model> | bgm:<m>+tts_sfx:<m>")
    gate.add_argument("--delivery-mode", choices=(*intake_choices.MODES, "tool_render"))
    gate.add_argument("--creative-mode", "--story-mode", choices=(*intake_choices.CREATIVE, "film"))
    gate.add_argument("--revision", type=int)
    gate.add_argument("--request-id")
    gate.add_argument("--aspect-ratio", required=False)
    gate.add_argument("--pacing", required=False, help="total duration and shot rhythm, in the user's terms")
    gate.add_argument("--style-tone", required=False)
    gate.add_argument("--user-words", required=True, help="the user's own reply choosing these; never the agent's")
    invalidate = add("invalidate", cmd_invalidate, "cross-stage rollback: mark affected artifacts STALE, reopen Gate #2")
    invalidate.add_argument("--stage", required=True, choices=("character", "scene", "previs"))
    invalidate.add_argument("--target", required=True,
                            help="character id, scene asset id or locked asset path; script scene id for previs")
    invalidate.add_argument("--reason", required=True, help="root cause found downstream")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes: 0 recorded; 1 refused; 3 file or JSON error.")
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name: str, handler: Any, text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=text)
        sub.add_argument("--project", required=True, type=Path, help="project directory")
        sub.set_defaults(handler=handler)
        return sub

    add_preproduction_commands(add)
    add_harness_commands(add)
    channel = add("channel", cmd_channel, "record a channel capability card")
    channel.add_argument("--name", required=True)
    channel.add_argument("--card", required=True, type=Path, help="JSON file holding the card")
    channel.add_argument("--today", type=date.fromisoformat, default=date.today())
    post = add("post-done", cmd_post_done, "record finished post-production outputs")
    from media_inspection import ROUTES
    post.add_argument("--audio-route", choices=ROUTES)
    post.add_argument("--subtitle", type=Path)
    post.add_argument("--voice-source")
    post.add_argument("--raw-clip", type=Path)
    post.add_argument("--cutlist", type=Path)
    post.add_argument("--claimed-resolution")
    post.add_argument("--upscaled-from")
    post.add_argument("--output", action="append", required=True)
    post.add_argument("--waive-remix", action="store_true",
                      help="only when user explicitly waived stem separation/remix despite native_bgm=false")
    deliver = add("deliver", cmd_deliver, "record delivered files and applied labels")
    deliver.add_argument("--file", action="append", required=True)
    deliver.add_argument("--label", action="append", default=[], help="a label the user asked for (repeatable)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.project = args.project.expanduser()
    try:
        result = args.handler(args)
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 3 if exc.code == "INPUT_ERROR" else 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
