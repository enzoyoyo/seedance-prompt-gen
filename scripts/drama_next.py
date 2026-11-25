#!/usr/bin/env python3
"""State-machine entry for an AI short drama: where the project stands and the one next action.

Read-only. It never submits, never writes the manifest and never contacts a provider; it reads
the project's resume manifest, script lock, shot spec and take ledger, finds the first gate that
does not hold, and prints that gate, the single action allowed now, and the reference to read.

SPEC v2.0 projects (`sop_version: "2.0"`) enforce:
- Human Gate #1 (`model_gate.py render` -> STOP & WAIT -> `drama_setup.py model-gate`) before the first
  image generation and before any paid submission (`prompt_only` mode stops at structured prompt delivery);
- Incremental Human Gate #2 (`drama.stale.pending_gate2`) across affected `previs` and `identity` targets;
- Pre-Gen text eval (`eval_harness.py pre-gen`) before submission and Clean-Room Post-Gen blind review
  (`eval_harness.py post-gen`) before per-shot acceptance, plus `drama.repair_queue` & circuit-breaker
  escalation routing. The 14 gate names and their order are unchanged.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, Callable

from change_impact import (
    impact_note, open_impacts, pending_gate2, pending_gate2_errors, stale_previs_scenes,
    stale_shot_ids, stale_take_errors, take_matches_current_refs,
)
from check_budget_gate import answer, check_submit, one_shot_tier
from check_capability_expiry import has_active_writing_host_note
from check_release_intent import check_applied_labels, check_intent
from drama_project import (
    MANIFEST_NAME, RECOVER_JOB_STATES, VIDEO_SUFFIXES, ProjectError, drama_block, load_manifest,
    manifest_path, nonempty, resolve_in_project, section, take_rows,
)
from ledger_submit import Context, cleanroom_acceptance_errors, evaluate_shot_pre_gen, spec_errors
from lock_script import locked_script_text, verify_lock
from model_gate import delivery_mode, gate_required, model_gate_errors, model_gate_execution_errors
from previs_coverage import identity_gate_errors, previs_gate_errors, script_scenes, view_notes
from validate_shot_spec import active_shots, channel_of, is_reuse, load_project_spec, root_id, shot_rows

SCRIPTS = Path(__file__).resolve().parent
GATES = (
    ("intake", "接单"), ("script_lock", "剧本锁定"), ("release_intent", "发布意图"),
    ("previs", "白模与站位预演"), ("identity", "角色多角度与场景资产"), ("shot_spec", "镜头规格通过"),
    ("trial", "试价"), ("draft_batch", "草稿批次"), ("shot_acceptance", "逐镜验收"),
    ("draft_cut", "草稿整集"), ("approval", "你点头"), ("final", "成片"),
    ("post", "后期"), ("delivery", "交付"),
)
WRITING_HOST_NOTE = ("Writing stage: tell the user once about the dated writing-host observation in "
                     "references/cross-host-handoff.md; it is a suggestion, never a requirement.")
CODE_OWNERSHIP = ("The confirmation code on the sheet belongs to the user: never read it from the image, relay it, "
                  "or fill it in; --user-words must be the user's own reply.")
MODEL_GATE_ACTION = ("Human Gate #1 (STOP & WAIT): show the four required choices -- image model, video model, audio plan "
                     "(BGM / voice & SFX / no audio) and global spec & delivery mode (prompt only or tool render) -- "
                     "through the host's question tool or the numbered menu below, end this turn, and record only "
                     "the user's own answers with `drama_setup.py model-gate`. Never pick defaults or answer for them.")


@dataclass(frozen=True)
class Step:
    gate: str
    status: str
    action: str
    reference: str
    command: str = ""
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class State:
    project: Path
    today: date
    manifest: dict[str, Any]
    ctx: Context | None = None

    @property
    def drama(self) -> dict[str, Any]:
        return drama_block(self.manifest)


def cli(script: str, state: State, *args: str) -> str:
    head = list(args[:1]) if args and not args[0].startswith("-") else []
    return shlex.join(["python3", str(SCRIPTS / script), *head, "--project", str(state.project), *args[len(head):]])


def script_arg(state: State) -> str:
    recorded = state.drama.get("script")
    return recorded if nonempty(recorded) else "<script file>"


def takeover_notes(state: State) -> list[str]:
    folders = [state.project, *(path for path in state.project.iterdir() if path.is_dir())]
    found = any(item.suffix.lower() in VIDEO_SUFFIXES for folder in folders for item in folder.iterdir() if item.is_file())
    if not found:
        return []
    return ["Clips already exist here: this is a takeover. Before writing the shot spec run "
            + shlex.join(["python3", str(SCRIPTS / "audit_takeover.py"), "--script", "<script>",
                          "--clips-dir", "<clips dir>", "--records", "<old ledger json>"])
            + " and read references/cross-host-handoff.md; never regenerate what can be reused."]


def writing_notes(state: State) -> list[str]:
    day = state.today if isinstance(state.today, date) else date.fromisoformat(str(state.today))
    return [WRITING_HOST_NOTE] if has_active_writing_host_note(day) else []


def gate_intake(state: State) -> Step | None:
    reference = "references/script-intake-contract.md"
    if not state.manifest:
        return Step("intake", f"no {MANIFEST_NAME} in this directory", "Create the project manifest, then record the brief.",
                    reference, cli("drama_setup.py", state, "init"), notes=[*writing_notes(state), *takeover_notes(state)])
    if not nonempty(section(state.drama, "intake").get("confirmed_at")):
        return Step("intake", "the brief is not recorded", "Record the user's brief in their own words.", reference,
                    cli("drama_setup.py", state, "intake", "--brief", "<brief>", "--user-words", "<user words>"),
                    notes=writing_notes(state))
    return None


def gate_script_lock(state: State) -> Step | None:
    errors = verify_lock(state.project)
    if not errors:
        return None
    reference = "references/cross-host-handoff.md"
    if errors[0].startswith("SCRIPT_CHANGED_AFTER_LOCK"):
        return Step("script_lock", "the script differs from the locked version",
                    "Stop. Show the user what changed; restore the locked text, or relock only with their words.",
                    reference, cli("lock_script.py", state, "--script", script_arg(state), "--relock",
                                   "--confirmed-by-user", "<user words>"), errors)
    return Step("script_lock", "the script is not locked",
                "Prefix each beat with [S1-B1], [S1-B2]... without changing a single word of the script, show it to "
                "the user, and STOP until the user confirms before running lock_script.py (do not run "
                "validate_script_gate.py on user-supplied finished scripts; never invent --confirmed-by-user).",
                reference, cli("lock_script.py", state, "--script", script_arg(state),
                               "--confirmed-by-user", "<user words>"), errors)


def gate_release_intent(state: State) -> Step | None:
    errors = check_intent(section(state.drama, "release_intent"), locked_script_text(state.project))
    if not errors:
        return None
    return Step("release_intent", "release intent is incomplete",
                "Copy templates/release-intent.json, ask the user for any unstated items (target_duration_s, "
                "real_public_figures, on_screen_text, disclosure) and STOP until answered; then record it.",
                "references/drama-gates.md",
                cli("drama_setup.py", state, "release-intent", "--file", "<intent.json>"), errors,
                notes=model_gate_notes(state))


def model_gate_blockers(state: State, resolved_model: str | None = None) -> list[str]:
    if not gate_required(state.drama):
        return []
    intent_ratio = section(state.drama, "release_intent").get("aspect_ratio")
    return model_gate_errors(state.drama) + model_gate_execution_errors(state.drama, resolved_model, intent_ratio)


def model_gate_step(state: State, gate: str, resolved_model: str | None = None) -> Step | None:
    errors = model_gate_blockers(state, resolved_model)
    if not errors:
        return None
    return Step(gate, "Human Gate #1 model gate is not locked or mismatched", MODEL_GATE_ACTION,
                "references/provider-execution.md",
                shlex.join(["python3", str(SCRIPTS / "model_gate.py"), "render", "--project", str(state.project), "--format", "both"]),
                errors,
                notes=[f"Record it: {cli('drama_setup.py', state, 'model-gate', '--image-model', '<user choice>', '--video-model', '<user choice>', '--audio-plan', '<none|bgm:..|tts_sfx:..>', '--delivery-mode', '<prompt_only|tool_render>', '--aspect-ratio', '<ratio>', '--pacing', '<duration & rhythm>', '--style-tone', '<tone>', '--user-words', '<user words>')}"])


def model_gate_notes(state: State) -> list[str]:
    if not model_gate_blockers(state):
        return []
    return ["Human Gate #1 also needs the model gate before any image generation: "
            + shlex.join(["python3", str(SCRIPTS / "model_gate.py"), "render", "--project", str(state.project)]) + " (STOP & WAIT)."]


def gate_incremental_gate2(state: State) -> Step | None:
    rows = pending_gate2(state.drama)
    if not rows:
        return None
    # Prefer previs first when both previs and identity are open so required_views derive cleanly
    ordered = sorted(rows, key=lambda r: 0 if r.get("gate") == "previs" else 1)
    gate = str(ordered[0].get("gate"))
    errors = pending_gate2_errors(state.drama)
    stale = sorted(stale_shot_ids(state.drama))
    stale_prev = sorted(stale_previs_scenes(state.drama))
    notes = [
        f"STALE previs scenes: {', '.join(stale_prev) or 'none'}; STALE shots (regenerate after re-sign): "
        f"{', '.join(stale) or 'none'}; untouched shots keep their state."
    ]
    decide = cli("drama_setup.py", state, gate, "--user-words", "<the user's reply, including their code>")
    waiting = awaiting_user(state, gate, "references/harness-guardrails-and-eval.md", decide, errors, notes)
    if waiting:
        return waiting
    return Step(gate, "incremental Human Gate #2 is open after a cross-stage invalidation",
                "Regenerate/fix the invalidated source (new file digest required), put the changed candidates on one "
                f"decision sheet with `present --gate {gate}`, show it and STOP until the user replies with the code; "
                f"batch video stays blocked. {CODE_OWNERSHIP}",
                "references/harness-guardrails-and-eval.md",
                cli("drama_setup.py", state, "present", "--gate", gate, "--candidate", "<group>/<label>=<new file>"),
                errors, notes)


def presented_sheets(state: State, gate: str) -> list[str]:
    pending = section(section(state.drama, "presentations"), gate)
    sheets = pending.get("sheets") if isinstance(pending.get("sheets"), list) else []
    return [str(row["path"]) for row in sheets if isinstance(row, dict) and nonempty(row.get("path"))]


def awaiting_user(state: State, gate: str, reference: str, decide: str, errors: list[str],
                  notes: list[str] | None = None) -> Step | None:
    sheets = presented_sheets(state, gate)
    if not sheets:
        return None
    return Step(gate, "candidates presented; waiting for the user's choice",
                f"Show the decision sheet {', '.join(sheets)} to the user, ask which candidates they choose (or which "
                f"skip option), and STOP until they answer with their choice and the confirmation code. {CODE_OWNERSHIP}",
                reference, decide, errors,
                notes=[f"Decision sheet: {state.project / path}" for path in sheets] + (notes or []))


def gate_identity(state: State) -> Step | None:
    errors = identity_gate_errors(state.project, state.drama)
    if not errors:
        return None
    gate1 = model_gate_step(state, "identity")
    if gate1 is not None:
        return replace(gate1, notes=[*gate1.notes, *view_notes(state.project, state.drama)])
    decide = cli("drama_setup.py", state, "identity", "--char-view", "<char>=front:<front.png>",
                 "--char-view", "<char>=three_quarter:<side.png>",
                 "--scene-ref", "<scene>=<plate.png>", "--user-words", "<the user's reply, including their code>")
    waiting = awaiting_user(state, "identity", "references/keyframe-assets.md", decide, errors,
                            view_notes(state.project, state.drama))
    if waiting:
        return waiting
    return Step("identity", "multi-angle character & scene assets are not presented or not locked",
                "Prepare candidate character views and scene master plates inside the project: every character on a "
                "chosen whitemodel board needs front plus each view a board camera sees it from (listed below); "
                "the others need front plus one of three_quarter/profile/back. Put them all on one decision sheet "
                "with `present --gate identity`. "
                f"Do not lock anything yet. {CODE_OWNERSHIP}",
                "references/keyframe-assets.md",
                cli("drama_setup.py", state, "present", "--gate", "identity",
                    "--candidate", "<char>.front/A=<front_a.png>", "--candidate", "<char>.three_quarter/A=<side_a.png>",
                    "--candidate", "<scene>/A=<plate_a.png>"), errors,
                notes=view_notes(state.project, state.drama))


def gate_previs(state: State) -> Step | None:
    errors = previs_gate_errors(state.project, state.drama)
    stale_prev = sorted(stale_previs_scenes(state.drama))
    errors += [f"STALE_PREVIS_SCENE:{sc}" for sc in stale_prev]
    if not errors:
        return None
    board_cmd = shlex.join(["python3", str(SCRIPTS / "render_whitemodel_board.py"), "--plan", "<blocking.json>",
                            "--output", str(state.project / "00_previs" / "<scene>_whitemodel.png")])
    decide = cli("drama_setup.py", state, "previs", "--scene", "<scene_id>=00_previs/<board.png>",
                 "--waive-scene", "<scene_id the user skipped>", "--user-words", "<the user's reply, including their code>")
    scenes = script_scenes(state.project) or []
    scene_note = [f"Script scenes: {', '.join(scenes)}. Each needs `--scene <id>=<chosen board>` or, when the user "
                  "skipped it, `--waive-scene <id>`."] if scenes else []
    waiting = awaiting_user(state, "previs", "references/whitemodel-previs.md", decide, errors, scene_note)
    if waiting:
        return waiting
    pref = section(state.drama, "choice_resolution").get("previs_preference")
    notes = [*scene_note, f"Zero-cost whitemodel board generator: {board_cmd}",
             *([f"Staged user previs preference: {pref}"] if pref else []),
             *model_gate_notes(state)]
    return Step("previs", "whitemodel and scene spatial blocking are not presented or not locked",
                "Render zero-cost whitemodel & spatial blocking boards (with A/B options where blocking is open) into "
                "00_previs/ (copy templates/whitemodel-blocking-plan.json, or use stage-desk / Blender when requested), "
                "then put every scene's options on one decision sheet with `present --gate previs`. Do not lock "
                f"anything yet. {CODE_OWNERSHIP}",
                "references/whitemodel-previs.md",
                cli("drama_setup.py", state, "present", "--gate", "previs",
                    "--candidate", "<scene_id>/A=00_previs/<board_A.png>",
                    "--candidate", "<scene_id>/B=00_previs/<board_B.png>"), errors,
                notes=notes)


def gate_shot_spec(state: State) -> Step | None:
    reference = "references/shot-spec.md"
    if state.ctx is None:
        return Step("shot_spec", "no shot spec yet",
                    "Write shots.json from the locked beats (first sentence of each prompt must name every ref's key "
                    "or role), then validate it.",
                    reference, cli("validate_shot_spec.py", state), notes=takeover_notes(state))
    errors = spec_errors(state.ctx, locked_script_text(state.project), state.today)
    if state.drama.get("sop_version") == "2.0" and not errors:
        for shot in active_shots(shot_rows(state.ctx.spec)):
            if not is_reuse(shot):
                pre_rep, _, _ = evaluate_shot_pre_gen(state.ctx, shot)
                if pre_rep["verdict"] != "PASS":
                    errors += [f"{shot['id']}:{code}" for code in pre_rep["blocking_errors"]]
    if not errors:
        return None
    notes = ([f"Copy templates/channel-card.json (or the card in the channel's adapter reference) and register via: "
              f"{cli('drama_setup.py', state, 'channel', '--name', '<channel>', '--card', '<card.json>')}"
              " (see references/provider-execution.md)"]
             if any(err.startswith("CHANNEL_CARD_") for err in errors) else [])
    if state.drama.get("sop_version") == "2.0":
        notes.append("Pre-Gen check: " + cli("eval_harness.py", state, "pre-gen", "--shot", "<shot_id>"))
    return Step("shot_spec", f"{len(errors)} shot-spec / Pre-Gen problem(s)",
                "Fix the listed spec or Pre-Gen problems silently, then validate again.",
                reference, cli("validate_shot_spec.py", state), errors, notes)


def review_tier(state: State, shot: dict[str, Any]) -> str:
    card = section(section(state.drama, "channels"), channel_of(state.ctx.spec, shot) or "")
    return "draft" if answer(card, "draft_tier") is True else "lowres"


def stage_takes(state: State, tier_of: Callable[[dict[str, Any]], str]) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    rows = shot_rows(state.ctx.spec)
    stale = stale_shot_ids(state.drama)
    result = []
    for shot in active_shots(rows):
        tier, root = tier_of(shot), root_id(rows, shot["id"])
        usable = []
        for take in take_rows(state.manifest):
            if take.get("shot_id") != root or take.get("tier") != tier:
                continue
            if root in stale and take.get("stale") is True:
                continue
            if take.get("stale") is True or not take_matches_current_refs(state.ctx.spec, state.ctx.spec_dir, take):
                continue
            usable.append(take)
        result.append((shot, usable))
    return result


def recipe_of(state: State, shot: dict[str, Any]) -> tuple[str, list[str]]:
    name = channel_of(state.ctx.spec, shot) or ""
    recipe = section(section(state.drama, "channels"), name).get("recipe")
    if nonempty(recipe):
        return recipe, [f"Copy the {name} command template for this tier from {recipe}; fill only its placeholders."]
    return "references/provider-execution.md", [
        f"Channel card {name or '(none)'} names no submit recipe. Write the adapter command from that "
        "channel's adapter reference and add `recipe` to its card before submitting."]


def _resolved_shot_model(state: State, shot: dict[str, Any], tier: str) -> str | None:
    from ledger_submit import model_for
    try:
        return model_for(state.ctx, shot, tier, None)
    except ProjectError:
        return None


def submit_step(state: State, gate: str, shot: dict[str, Any], tier: str, takes: list[dict[str, Any]]) -> Step:
    reference = "references/provider-execution.md"
    root = root_id(shot_rows(state.ctx.spec), shot["id"])
    repair = section(section(state.drama, "repair_queue"), root)
    if repair and repair.get("status") == "ESCALATED_CIRCUIT_BREAKER":
        pack_note = ([f"Escalation pack: {state.project / repair['escalation_pack_file']}"]
                     if nonempty(repair.get("escalation_pack_file")) else [])
        return Step(gate, f"{shot['id']}@{tier}: budget circuit breaker tripped",
                    "Stop automatic retries. Present the escalation decision pack (problem frames, root causes, "
                    "variables tried, split/rewrite suggestions) to the user and STOP for their call.",
                    "references/harness-guardrails-and-eval.md",
                    cli("eval_harness.py", state, "escalate", "--shot", root, "--tier", tier),
                    list(repair.get("breaker_errors") or ["CIRCUIT_BREAKER_TRIPPED"]), pack_note)
    if repair and repair.get("status") == "AWAITING_CLIP_RETURN":
        return Step(gate, f"{shot['id']}@{tier}: awaiting user-returned clip/screenshot after prompt revision",
                    "Deliver the revised structured prompt (`single_variable` changed) and run Clean-Room blind review "
                    "on the returned clip or screenshot.",
                    "references/harness-guardrails-and-eval.md",
                    shlex.join(["python3", str(SCRIPTS / "eval_harness.py"), "post-gen", "--clip", "<returned clip>",
                                "--anchor", "<locked anchor>", "--expected-action", "<one sentence>"]),
                    ["AWAITING_CLIP_RETURN"])

    # Also check un-superseded rejected takes on this spec_id (including takes stored on manifest)
    all_shot_takes = [t for t in take_rows(state.manifest)
                      if t.get("shot_id") == root and t.get("tier") == tier and t.get("stale") is not True]
    if any(take.get("status") == "rejected" and take.get("spec_id") == shot["id"] for take in all_shot_takes):
        notes = ([f"Retake guidance ({repair.get('repair_route')}): change `{repair.get('single_variable')}` only"]
                 if repair else [])
        return Step("shot_acceptance" if gate != "final" else gate, f"{shot['id']} was rejected at {tier}",
                    "Add a retake entry to the spec that supersedes it and changes exactly one variable, then run Pre-Gen.",
                    "references/shot-spec.md", cli("validate_shot_spec.py", state), notes=notes)
    if is_reuse(shot, tier):
        return Step(gate, f"{shot['id']} reuses an existing clip", "Enter the reused clip into the ledger.", reference,
                    cli("ledger_submit.py", state, "reuse", "--shot", shot["id"], "--tier", tier))
    gate1 = model_gate_step(state, gate, _resolved_shot_model(state, shot, tier))
    if gate1 is not None:
        return gate1
    command = cli("ledger_submit.py", state, "submit", "--shot", shot["id"], "--tier", tier,
                  "--id-field", "<id key>", "--dry-run", "--", "<adapter command>")
    if delivery_mode(state.drama) == "prompt_only":
        return Step(gate, "delivery mode is prompt_only (the user chose structured prompts only)",
                    "Deliver the compiled prompt package; a dry run shows the exact adapter command. Do not submit. "
                    "When the user returns a rendered clip/screenshot, run `eval_harness.py post-gen --clip ...`.",
                    "references/provider-execution.md", command, ["DELIVERY_MODE_PROMPT_ONLY"])
    errors, warnings = check_submit(state.manifest, state.ctx.spec, shot, tier, state.today, state.project, state.ctx.spec_dir)
    recipe, recipe_notes = recipe_of(state, shot)
    breaker = [err for err in errors if err.startswith("CIRCUIT_BREAKER_")]
    if breaker:
        return Step(gate, f"{shot['id']}@{tier}: budget circuit breaker tripped",
                    "Stop automatic retries. Build the decision pack (problem frames, root causes, variables tried, "
                    "split/rewrite suggestions), give it to the user and STOP for their call.",
                    "references/harness-guardrails-and-eval.md",
                    shlex.join(["python3", str(SCRIPTS / "eval_harness.py"), "escalate", "--project", str(state.project),
                                "--shot", root, "--tier", tier]),
                    errors, warnings)
    if errors:
        return Step(gate, f"{shot['id']}@{tier} may not be submitted yet",
                    "Resolve the budget or likeness-probe blocker first (record balance with --readback-file, "
                    "settle the probe take, or get the user's go-ahead).",
                    recipe, cli("check_budget_gate.py", state, "--shot", shot["id"], "--tier", tier), errors,
                    [*warnings, *recipe_notes])
    pre_note = ([f"Pre-Gen verified: {cli('eval_harness.py', state, 'pre-gen', '--shot', shot['id'])}"]
                if state.drama.get("sop_version") == "2.0" else [])
    return Step(gate, f"{shot['id']}@{tier} is the next submission",
                "Dry-run, read the printed command, then run the same line without --dry-run. One shot only.",
                recipe, command, notes=[*warnings, *recipe_notes, *pre_note])


def take_step(gate: str, state: State, take: dict[str, Any]) -> Step | None:
    take_id, job_state = take["take_id"], take.get("job_state")
    if take.get("status") == "rejected" or job_state == "failed":
        return None
    if job_state in RECOVER_JOB_STATES:
        return Step(gate, f"{take_id} has no recorded outcome ({job_state})",
                    "Recover the job by ID or the provider's own history, then settle. Do not submit again.",
                    "references/sequence-resume.md",
                    cli("ledger_submit.py", state, "settle", "--take", take_id, "--state", "submitted", "--job-id", "<name=value>"))
    if job_state == "succeeded" and take.get("status") == "candidate":
        acc_gate = "shot_acceptance" if gate != "final" else gate
        if state.drama.get("sop_version") == "2.0":
            cr_errs = cleanroom_acceptance_errors(state.project, state.manifest, take)
            if cr_errs:
                return Step(
                    acc_gate,
                    f"{take_id} awaits Clean-Room Post-Gen blind review",
                    "Run stateless Clean-Room visual blind review (`eval_harness.py post-gen --track dual`) before "
                    "per-shot acceptance; FAIL automatically rejects the take and routes self-repair.",
                    "references/harness-guardrails-and-eval.md",
                    cli("eval_harness.py", state, "post-gen", "--take", take_id, "--track", "dual",
                        "--expected-action", "<one-sentence observable action>"),
                    cr_errs,
                )
        return Step(acc_gate, f"{take_id} awaits per-shot acceptance",
                    "Run check_spoken_lines.py, make_identity_sheet.py and make_continuity_sheet.py, watch the clip, "
                    "then record all four checks.",
                    "references/drama-gates.md", cli("check_spoken_lines.py", state, "--take", take_id, "--asr-model",
                                                     "<a model check_post_deps.py lists on disk>"),
                    notes=[f"Identity & continuity sheets: {cli('make_identity_sheet.py', state, '--take', take_id)} ; "
                           f"{cli('make_continuity_sheet.py', state, '--take', take_id)}"])
    return None


def stage_step(state: State, tier_of: Callable[[dict[str, Any]], str], gates: tuple[str, str]) -> Step | None:
    trial_gate, batch_gate = gates
    rows = stage_takes(state, tier_of)
    takes = [take for _, shot_takes in rows for take in shot_takes]
    for take in takes:
        step = take_step(batch_gate, state, take)
        if step is not None:
            return step
    settled = any(take.get("job_state") == "succeeded" and take.get("origin") != "reused" for take in takes)
    pending = [(shot, shot_takes) for shot, shot_takes in rows
               if not any(take.get("status") != "rejected" and take.get("job_state") != "failed" for take in shot_takes)]
    flying = next((take for take in takes if take.get("job_state") == "submitted"), None)
    if pending and (settled or flying is None):
        shot, shot_takes = min(pending, key=lambda row: (row[0].get("duration") or 0, row[0]["id"]))
        return submit_step(state, batch_gate if settled else trial_gate, shot, tier_of(shot), shot_takes)
    if flying is not None:
        return Step(batch_gate if settled else trial_gate, f"{flying['take_id']} is still running",
                    "Read the job back by its recorded ID, then settle it.", "references/sequence-resume.md",
                    cli("ledger_submit.py", state, "settle", "--take", flying["take_id"], "--state", "succeeded", "--file", "<clip>"))
    return None


def gate_review(state: State) -> Step | None:
    if one_shot_tier(state.drama) is not None:
        return None
    return stage_step(state, lambda shot: review_tier(state, shot), ("trial", "draft_batch"))


def gate_draft_cut(state: State) -> Step | None:
    draft_app = section(section(state.drama, "approvals"), "draft_cut")
    if one_shot_tier(state.drama) is not None or (draft_app.get("approved") is True and draft_app.get("stale") is not True):
        return None
    stale = stale_take_errors([take for take in take_rows(state.manifest) if take.get("status") == "approved"])
    if stale:
        if state.drama.get("sop_version") == "2.0":
            return Step("draft_cut", "approved takes built on a replaced asset or blocking are STALE",
                        "SPEC v2.0 requires regenerating affected STALE shots (resolve open impact with `redo`); "
                        "stale takes never enter a cut.", "references/harness-guardrails-and-eval.md",
                        cli("drama_setup.py", state, "impact", "--id", "<impact id>", "--decision", "redo",
                            "--user-words", "<user words>"), stale)
        return Step("draft_cut", "approved takes built on a replaced asset or blocking are stale",
                    "Ask the user to keep or redo the affected shots (resolve the open change impact with their own "
                    "words); stale takes never enter a cut.", "references/harness-guardrails-and-eval.md",
                    cli("drama_setup.py", state, "impact", "--id", "<impact id>", "--decision", "keep|redo",
                        "--user-words", "<user words>"), stale)
    cut_info = section(section(state.drama, "cuts"), "draft")
    cut = None if cut_info.get("stale") is True else resolve_in_project(state.project, cut_info.get("file"))
    if cut is None or not cut.is_file():
        return Step("draft_cut", "every shot has an approved draft; no draft cut yet",
                    "Assemble the approved draft takes into one cut.", "references/post-production.md",
                    cli("assemble_cut.py", state, "--tier", "draft", "--output", "<draft cut file>"))
    return Step("approval", f"draft cut ready: {cut.name}",
                "Show the draft cut to the user. Record approval only with their own words; no final-tier spend before it.",
                "references/drama-gates.md",
                cli("ledger_submit.py", state, "confirm", "--kind", "draft-cut", "--file", cut.name, "--user-words", "<user words>"))


def gate_final(state: State) -> Step | None:
    tier = one_shot_tier(state.drama) or "final"
    return stage_step(state, lambda shot: tier, ("final", "final"))


def gate_post(state: State) -> Step | None:
    if delivery_mode(state.drama) == "prompt_only":
        return None
    if nonempty(section(state.drama, "post").get("done_at")):
        return None
    return Step("post", "all shots approved; post-production not recorded",
                "Check post dependencies, assemble with `--check-seams`, then score and subtitles as the user asked; "
                "record the outputs.",
                "references/post-production.md", cli("check_post_deps.py", state))


def gate_delivery(state: State) -> Step | None:
    delivery = section(state.drama, "delivery")
    if nonempty(delivery.get("delivered_at")):
        return None
    blockers = check_applied_labels(section(state.drama, "release_intent"), delivery.get("labels_applied") or [])
    action = ("Put each open disclosure question to the user before delivery." if blockers
              else "Deliver the verified output file with only the labels the user asked for, then record it; "
                   "log any newly discovered recurring defect via `mistake_book.py add`.")
    return Step("delivery", "post-production done; not delivered", action, "references/drama-gates.md",
                cli("drama_setup.py", state, "deliver", "--file", "<final file>"), blockers)


CHECKS = (gate_intake, gate_script_lock, gate_release_intent, gate_incremental_gate2, gate_previs, gate_identity,
          gate_shot_spec, gate_review, gate_draft_cut, gate_final, gate_post, gate_delivery)


def load_state(project: Path, today: date) -> State:
    if not manifest_path(project).is_file():
        return State(project, today, {})
    try:
        spec, spec_dir, manifest = load_project_spec(project)
    except ProjectError as exc:
        if exc.code != "SHOT_SPEC_MISSING":
            raise
        return State(project, today, load_manifest(project))
    return State(project, today, manifest, Context(project, manifest, spec, spec_dir))


def next_step(project: Path, today: date) -> Step:
    state = load_state(project, today)
    for check in CHECKS:
        step = check(state)
        if step is not None:
            return replace(step, notes=[*step.notes, *(impact_note(row) for row in open_impacts(state.drama))])
    return Step("done", "delivered", "Nothing left. A new episode starts with its own project directory.",
                "references/episodes-serial.md")


def render(step: Step) -> str:
    names = [name for name, _ in GATES]
    position = f"{names.index(step.gate) + 1}/{len(GATES)} {dict(GATES)[step.gate]}" if step.gate in names else "complete"
    lines = [f"gate: {step.gate} ({position})", f"status: {step.status}", f"next: {step.action}"]
    lines += [f"command: {step.command}"] if step.command else []
    lines += [f"read: {step.reference}"]
    lines += [f"blocker: {item}" for item in step.blockers] + [f"note: {item}" for item in step.notes]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, epilog="Exit codes: 0 state printed; 3 file or JSON error.")
    parser.add_argument("project", nargs="?", type=Path, help="project directory (may be empty or new)")
    parser.add_argument("--project", dest="named_project", type=Path)
    parser.add_argument("--v7", action="store_true")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD, for card expiry")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    if not (args.named_project or args.project):
        parser.error("a project directory is required")
    project = (args.named_project or args.project).expanduser()
    try:
        if not project.is_dir():
            raise ProjectError("INPUT_ERROR", f"not a directory: {project}")
        manifest = load_manifest(project) if manifest_path(project).is_file() else {}
        drama = drama_block(manifest)
        if drama.get("sop_version") == "3.0" or (args.v7 and (delivery_mode(drama) or drama.get("delivery_mode") or manifest.get("delivery_mode")) in {"images_only", "video_clips", "full_film"}):
            from delivery_graph import plan
            graph = plan(project.resolve(), manifest, today=args.today)
            print(json.dumps(graph, indent=2) if args.json else graph["next_action"])
            return 0
        step = next_step(project, args.today)
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 3
    print(json.dumps(asdict(step), ensure_ascii=False, indent=2) if args.json else render(step))
    return 0


if __name__ == "__main__":
    sys.exit(main())
