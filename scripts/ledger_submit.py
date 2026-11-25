#!/usr/bin/env python3
"""The only paid-submission entry for an AI short drama: gates first, ledger before the call.

  submit   run every gate (including Pre-Gen eval & L1 guardrail compilation), atomically reserve
           a `preparing` take under the ledger lock, then run the adapter command given after `--`.
  settle   record what a read-back showed (recovered ID, finished file, confirmed failure).
  accept   verify the four per-shot checks AND Clean-Room Post-Gen PASS (no mock/FAIL/SKIPPED),
           then approve or reject a take.
  reuse    register an existing non-stale clip instead of generating one.
  balance  record a balance that was just read from the channel.
  confirm  record the user's own words: unknown-cost, one-shot, or draft-cut approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import drama_ledger as ledger
from change_impact import (
    clear_stale_shot, pending_gate2_errors, stale_previs_scenes, stale_shot_ids,
    stale_take_errors, take_matches_current_refs, verify_and_collect_take_anchors,
)
from check_budget_gate import check_submit, record_spend_attempt, release_presubmit_reservation
from check_release_intent import check_intent, lexicon_violations
from check_script_coverage import check_spec_coverage
from drama_project import (
    ACCEPTANCE_CHECKS, ACCEPTANCE_RESULTS, RECOVER_JOB_STATES, TIERS, ProjectError, drama_block,
    nonempty, now_iso, read_json, resolve_in_project, section,
    sha256_file, take_rows, update_manifest,
)
from harness_rules import (
    active_rules_of, compile_guardrail_prompt, custom_rules_of, evaluate, load_book, rubric_for,
)
from lock_script import locked_script_text, verify_lock
from make_continuity_sheet import previous_shot_id
from model_gate import delivery_mode, gate_required, model_gate_errors, model_gate_execution_errors
from PIL import Image, UnidentifiedImageError
from previs_coverage import (
    identity_gate_errors, locked_views, previs_gate_errors, shot_previs_errors, shot_ref_provenance_errors,
)
from validate_shot_spec import (
    active_shots, channel_of, compose_prompt, inherited_text, is_reuse, load_project_spec,
    model_of, resolve_ref, root_id, shot_rows, superseded_ids, validate_spec,
)

EXIT_OK, EXIT_REFUSED, EXIT_UNKNOWN, EXIT_INPUT = 0, 1, 2, 3
DEFAULT_BOOK = Path(__file__).resolve().parent.parent / "references" / "mistake-book.jsonl"
REFS_FLAG_RE = re.compile(r"\{(?P<kind>refs|ref_urls):(?P<flag>[^{}]+)\}")
DRAFT_ID_RE = re.compile(r"\{draft:(?P<name>[A-Za-z0-9_.-]+)\}")
REVIEW_TIERS = ("draft", "lowres")
PRE_SUBMIT_BALANCE_TOKENS = (
    "insufficient balance", "insufficient credits", "insufficient quota",
    "not enough credits", "balance is insufficient",
    "余额不足", "积分不足", "算力不足", "配额不足",
)


@dataclass(frozen=True)
class Context:
    project: Path
    manifest: dict[str, Any]
    spec: dict[str, Any]
    spec_dir: Path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_context(project: Path) -> Context:
    spec, spec_dir, manifest = load_project_spec(project)
    return Context(project, manifest, spec, spec_dir)


def find_shot(ctx: Context, shot_id: str) -> dict[str, Any]:
    shot = next((row for row in shot_rows(ctx.spec) if row.get("id") == shot_id), None)
    if shot is None:
        raise ProjectError("UNKNOWN_SHOT", shot_id)
    return shot


def load_translations(ctx: Context) -> Any:
    relative = drama_block(ctx.manifest).get("translations")
    if not nonempty(relative):
        return None
    path = resolve_in_project(ctx.project, relative)
    if path is None or not path.is_file():
        raise ProjectError("TRANSLATIONS_MISSING", str(relative))
    return read_json(path)


def spec_lexicon_errors(ctx: Context, intent: dict[str, Any], translations: Any) -> list[str]:
    lexicon = intent.get("lexicon")
    if not isinstance(lexicon, list) or not lexicon:
        return []
    errors: list[str] = []
    for shot in active_shots(shot_rows(ctx.spec)):
        line = shot.get("line", "")
        line_text = " ".join(line) if isinstance(line, list) else str(line)
        errors += lexicon_violations(lexicon, f"{line_text}\n{shot.get('prompt', '')}", shot["id"])
    if translations is not None:
        errors += lexicon_violations(lexicon, json.dumps(translations, ensure_ascii=False), "translations")
    return errors


def _project_actor_views(drama: dict[str, Any]) -> dict[str, list[str]]:
    chars = section(section(drama, "identity_assets"), "characters")
    return {name.lower(): sorted(locked_views(row)) for name, row in chars.items() if isinstance(row, dict)}


def evaluate_shot_pre_gen(ctx: Context, shot: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    """Run deterministic Pre-Gen on one spec shot, returning (report, compiled_prompt, book_sha256)."""
    drama = drama_block(ctx.manifest)
    rows = active_shots(shot_rows(ctx.spec))
    idx = next((i for i, r in enumerate(rows) if r.get("id") == shot["id"]), None)
    prev = {**rows[idx - 1], "shot_id": rows[idx - 1]["id"]} if idx is not None and idx > 0 else None
    base_prompt = compose_prompt(ctx.spec, ctx.spec_dir, shot)
    book_rows = load_book(DEFAULT_BOOK) if DEFAULT_BOOK.is_file() else []
    book_sha = sha256_file(DEFAULT_BOOK) if DEFAULT_BOOK.is_file() else "builtin"
    active = active_rules_of(book_rows) if book_rows else None
    custom = custom_rules_of(book_rows)

    raw_prompt = shot.get("prompt")
    raw_missing = not nonempty(raw_prompt)
    shot_case = {**shot, "shot_id": shot["id"], "duration_s": shot.get("duration"), "prompt": base_prompt,
                 **({"_raw_prompt_missing": True} if raw_missing else {})}
    intent = section(drama, "release_intent")
    extra: dict[str, Any] = {"project_actor_views": _project_actor_views(drama), "creative_mode": drama.get("creative_mode")}
    first = evaluate({"synthetic_input_prompt_or_spec": {"curr_shot": shot_case, "prev_shot": prev,
                                                         "release_intent": intent}}, active, extra, book_rows)
    if drama.get("sop_version") in {"2.0", "3.0"}:
        compiled, mounted = compile_guardrail_prompt(base_prompt, first["triggered_l1_rules"], custom)
        verified = evaluate(
            {"synthetic_input_prompt_or_spec": {"curr_shot": shot_case, "prev_shot": prev, "release_intent": intent},
             "l1_injected": shot.get("l1_injected", mounted)},
            active, {**extra, "require_l1_injection": True}, book_rows,
        )
        return verified, compiled, book_sha
    return first, base_prompt, book_sha


def spec_errors(ctx: Context, script_text: str, today: date) -> list[str]:
    """Shot-spec gate: covers the locked script, obeys the channel cards, matches the release ratio."""
    drama = drama_block(ctx.manifest)
    intent = section(drama, "release_intent")
    translations = load_translations(ctx)
    errors = list(check_spec_coverage(script_text, ctx.spec, translations)["errors"])
    errors += validate_spec(ctx.spec, ctx.spec_dir, section(drama, "channels"), today)
    errors += spec_lexicon_errors(ctx, intent, translations)
    errors += shot_previs_errors(ctx.project, drama, ctx.spec, ctx.spec_dir)
    errors += shot_ref_provenance_errors(ctx.project, drama, ctx.spec, ctx.spec_dir)
    ratio, wanted = inherited_text(ctx.spec, ctx.spec_dir, "ratio"), intent.get("aspect_ratio")
    if ratio != wanted:
        errors.append(f"SPEC_RATIO_DIFFERS_FROM_RELEASE_INTENT:{ratio or 'missing'}!={wanted}")
    return errors


def run_gates(ctx: Context, shot: dict[str, Any], tier: str, today: date) -> tuple[list[str], list[str]]:
    """Every gate a paid submission must pass; the script lock comes first."""
    errors = verify_lock(ctx.project)
    if errors:
        return errors, []
    script_text = locked_script_text(ctx.project)
    drama = drama_block(ctx.manifest)
    errors = check_intent(section(drama, "release_intent"), script_text)
    errors += [f"STALE_PREVIS_SCENE:{sc}" for sc in sorted(stale_previs_scenes(drama))]
    errors += previs_gate_errors(ctx.project, drama)
    errors += identity_gate_errors(ctx.project, drama)
    errors += spec_errors(ctx, script_text, today)
    if not is_reuse(shot, tier):
        pre_rep, _, _ = evaluate_shot_pre_gen(ctx, shot)
        if pre_rep["verdict"] != "PASS":
            errors += pre_rep["blocking_errors"]
    budget_errors, warnings = check_submit(ctx.manifest, ctx.spec, shot, tier, today, ctx.project, ctx.spec_dir)
    return list(dict.fromkeys(errors + budget_errors)), warnings


def adapter_consumes_prompt(adapter: list[str] | None) -> bool:
    if not adapter:
        return True
    return any("{prompt}" in arg or "{prompt_file}" in arg for arg in adapter)


def harness_gates(drama: dict[str, Any], dry_run: bool,
                  resolved_model: str | None = None,
                  intent_ratio: str | None = None,
                  adapter: list[str] | None = None,
                  is_reuse_shot: bool = False) -> tuple[list[str], list[str]]:
    """SPEC v2.0 gates around a paid call: (errors, warnings).
    Open incremental Human Gate #2 and locked model-gate mismatches always block; `MODEL_GATE_MISSING`
    and `DELIVERY_MODE_PROMPT_ONLY` warn on `--dry-run` and block on real submissions."""
    errors = pending_gate2_errors(drama)
    errors += model_gate_execution_errors(drama, resolved_model, intent_ratio)
    soft = model_gate_errors(drama) if gate_required(drama) else []
    if delivery_mode(drama) == "prompt_only":
        soft.append("DELIVERY_MODE_PROMPT_ONLY")
    if delivery_mode(drama) == "images_only":
        soft.append("DELIVERY_MODE_IMAGES_ONLY")
    if drama.get("sop_version") in {"2.0", "3.0"} and not is_reuse_shot and adapter and not adapter_consumes_prompt(adapter):
        prompt_err = "ADAPTER_PROMPT_NOT_BOUND:adapter command must consume {prompt} or {prompt_file}"
        if not dry_run or ("model_gate" in drama and not model_gate_errors(drama)):
            errors.append(prompt_err)
        else:
            soft.append(prompt_err)
    return (errors, soft) if dry_run else (errors + soft, [])


def handle_circuit_breaker(ctx: Context, shot_id: str, tier: str, errors: list[str],
                           dry_run: bool) -> dict[str, Any]:
    if not any(err.startswith("CIRCUIT_BREAKER_") for err in errors):
        return {}
    from eval_harness import escalation_pack, pack_markdown

    pack = escalation_pack(ctx.project, shot_id, tier)
    command = shlex.join(["python3", str(Path(__file__).resolve().parent / "eval_harness.py"), "escalate",
                          "--project", str(ctx.project), "--shot", shot_id, "--tier", tier])
    extra: dict[str, Any] = {
        "next": f"Circuit breaker tripped: stop automatic retries and give the user the decision pack: {command}",
        "escalation_pack": pack,
    }
    if not dry_run:
        qc = ctx.project / "qc"
        qc.mkdir(parents=True, exist_ok=True)
        md_path = qc / f"escalation_{shot_id}_{tier}.md"
        json_path = qc / f"escalation_{shot_id}_{tier}.json"
        md_path.write_text(pack_markdown(pack), encoding="utf-8")
        json_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
        extra["escalation_pack_file"] = str(md_path.resolve().relative_to(ctx.project.resolve()))
    return extra


def tier_model(owner: dict[str, Any], tier: str) -> str | None:
    per_tier = owner.get("models")
    value = per_tier.get(tier) if isinstance(per_tier, dict) else None
    return value if nonempty(value) else None


def model_for(ctx: Context, shot: dict[str, Any], tier: str, override: str | None) -> str:
    model = (override or tier_model(shot, tier) or (shot.get("model") if nonempty(shot.get("model")) else None)
             or tier_model(ctx.spec, tier) or model_of(ctx.spec, shot))
    if not nonempty(model):
        raise ProjectError("MODEL_NOT_DECLARED", f"{shot['id']}:{tier}")
    return model


def plan_take(ctx: Context, shot: dict[str, Any], tier: str, model: str,
              compiled_prompt: str, pre_gen_meta: dict[str, Any]) -> dict[str, Any]:
    rows = shot_rows(ctx.spec)
    spec_id = shot["id"]
    if spec_id in superseded_ids(rows):
        raise ProjectError("SHOT_SUPERSEDED", spec_id)
    if is_reuse(shot, tier):
        raise ProjectError("SHOT_IS_REUSE", f"{spec_id}: register it with the reuse subcommand")
    shot_id = root_id(rows, spec_id)
    rejected = [take for take in ledger.takes_for(ctx.manifest, shot_id, tier)
                if take.get("status") == "rejected" and take.get("stale") is not True]
    supersedes, changed = None, []
    if rejected:
        if rejected[-1].get("spec_id") == spec_id:
            raise ProjectError("RETAKE_NEEDS_NEW_SPEC_ENTRY",
                               f"{spec_id}: add an entry that supersedes it and changes exactly one variable")
        supersedes, changed = rejected[-1]["take_id"], list(shot.get("changed_variables") or [])
        if len(changed) != 1:
            raise ProjectError("RETAKE_CHANGED_VARIABLES_NOT_ONE", f"{spec_id}:{len(changed)}")
    take_id = ledger.next_take_id(ctx.manifest, spec_id, tier)
    plans = section(drama_block(ctx.manifest), "redo_plans")
    used = {t.get("take_id") for t in take_rows(ctx.manifest)}
    lineage = next((p for tid, p in plans.items() if tid not in used and
                    p.get("shot_id") == shot_id and p.get("tier") == tier), {})
    if lineage:
        take_id = lineage["take_id"]
        if not isinstance(take_id, str) or Path(take_id).name != take_id:
            raise ProjectError("INVALID_TAKE_ID")
        supersedes, changed = lineage["parent_take_id"], [lineage["changed_factor"]]
    ref_shas = [
        sha256_file(resolved) for name in shot.get("refs", [])
        if (resolved := resolve_ref(ctx.spec, ctx.spec_dir, name)) is not None and resolved.is_file()
    ]
    return ledger.new_take(
        take_id, shot_id, spec_id, tier,
        **{k: lineage[k] for k in ("parent_take_id", "changed_factor", "change_value", "downstream_stale") if k in lineage},
        provider=channel_of(ctx.spec, shot), exact_model_id=model, requested_model=model,
        supersedes=supersedes, changed_variables=changed, ref_sha256s=ref_shas,
        pre_gen={**pre_gen_meta, "prompt_sha256": sha256_text(compiled_prompt)},
        prepared_at=now_iso(),
    )


def draft_job_id(ctx: Context, shot_id: str, name: str) -> str:
    for tier in REVIEW_TIERS:
        take = ledger.approved_take(ctx.manifest, shot_id, tier)
        if take is None or not take_matches_current_refs(ctx.spec, ctx.spec_dir, take):
            continue
        value = (take or {}).get("job_ids", {}).get(name)
        if nonempty(value):
            return value
    raise ProjectError("DRAFT_JOB_ID_MISSING", f"{shot_id}:{name}")


def ref_urls(ctx: Context, shot: dict[str, Any]) -> list[str]:
    table = ctx.spec.get("refs") if isinstance(ctx.spec.get("refs"), dict) else {}
    urls = []
    for name in shot.get("refs", []):
        entry = table.get(name)
        url = entry.get("url") if isinstance(entry, dict) else None
        if not nonempty(url):
            raise ProjectError("REF_URL_MISSING", f"{shot['id']}:{name}: upload it and record `url` in the spec refs")
        urls.append(url)
    return urls


def expand_command(ctx: Context, shot: dict[str, Any], take: dict[str, Any], argv: list[str],
                   compiled_prompt: str, prompt_file: Path | None = None) -> list[str]:
    lists = {"refs": lambda: [str(resolve_ref(ctx.spec, ctx.spec_dir, name)) for name in shot.get("refs", [])],
             "ref_urls": lambda: ref_urls(ctx, shot)}
    plain = {
        "{prompt}": compiled_prompt,
        "{prompt_file}": str(prompt_file) if prompt_file is not None else "",
        "{duration}": f"{shot['duration']:g}",
        "{ratio}": inherited_text(ctx.spec, ctx.spec_dir, "ratio"),
        "{model}": take["exact_model_id"], "{shot_id}": take["spec_id"], "{tier}": take["tier"],
    }
    expanded: list[str] = []
    for arg in argv:
        if arg in ("{refs}", "{ref_urls}"):
            expanded.extend(lists[arg[1:-1]]())
            continue
        flag = REFS_FLAG_RE.fullmatch(arg)
        if flag:
            expanded.extend(part for ref in lists[flag["kind"]]() for part in (flag["flag"], ref))
            continue
        for key, value in plain.items():
            arg = arg.replace(key, value)
        expanded.append(DRAFT_ID_RE.sub(lambda m: draft_job_id(ctx, take["shot_id"], m["name"]), arg))
    return expanded


def find_key(payload: Any, name: str) -> str | None:
    if isinstance(payload, dict):
        value = payload.get(name)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip():
            return str(value)
        payload = list(payload.values())
    if isinstance(payload, list):
        return next((found for item in payload if (found := find_key(item, name))), None)
    return None


def extract_ids(stdout: str, fields: list[str]) -> dict[str, str]:
    documents = []
    for chunk in [stdout, *stdout.splitlines()]:
        try:
            documents.append(json.loads(chunk))
        except json.JSONDecodeError:
            continue
    found: dict[str, str] = {}
    for name in fields:
        value = next((hit for doc in documents if (hit := find_key(doc, name))), None)
        if value is None:
            match = re.search(rf"{re.escape(name)}[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9][A-Za-z0-9_.:/-]*)", stdout)
            value = match.group(1) if match else None
        if value is not None:
            found[name] = value
    return found


def is_pre_submit_balance_refusal(output: str) -> bool:
    lowered = output.casefold()
    return any(token in lowered for token in PRE_SUBMIT_BALANCE_TOKENS)


def run_adapter(argv: list[str], timeout: float) -> tuple[str, str | None]:
    try:
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return output, "ADAPTER_TIMEOUT"
    return done.stdout or "", None if done.returncode == 0 else f"ADAPTER_EXIT_{done.returncode}"


def emit(payload: dict[str, Any], code: int) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def prepare(ctx: Context, shot: dict[str, Any], record: dict[str, Any], today: date,
            adapter: list[str] | None = None) -> None:
    """Atomically re-verify ALL gates (including model gate, prompt binding & prompt_only) under the ledger lock, then reserve."""
    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        drama = drama_block(manifest)
        intent_ratio = section(drama, "release_intent").get("aspect_ratio")
        h_errors, _ = harness_gates(
            drama, dry_run=False, resolved_model=record["exact_model_id"],
            intent_ratio=intent_ratio, adapter=adapter, is_reuse_shot=is_reuse(shot, record["tier"]),
        )
        if h_errors:
            raise ProjectError(h_errors[0])
        fresh_ctx = Context(ctx.project, manifest, ctx.spec, ctx.spec_dir)
        g_errors, _ = run_gates(fresh_ctx, shot, record["tier"], today)
        if g_errors:
            raise ProjectError(g_errors[0])
        added = ledger.add_take(manifest, record)
        return record_spend_attempt(added, record["shot_id"], record["tier"], record["take_id"])

    update_manifest(ctx.project, mutate)


def cmd_submit(args: argparse.Namespace) -> int:
    ctx = load_context(args.project)
    shot = find_shot(ctx, args.shot)
    root_sid = root_id(shot_rows(ctx.spec), shot["id"])
    blocker = ledger.blocking_take(ctx.manifest, root_sid, args.tier)
    if blocker is not None:
        recover = blocker.get("job_state") in RECOVER_JOB_STATES
        return emit({"ok": not recover, "skipped": True, "take_id": blocker["take_id"],
                     "reason": "RECOVER_FIRST" if recover else "TAKE_ALREADY_LIVE",
                     "job_state": blocker.get("job_state")}, EXIT_REFUSED if recover else EXIT_OK)

    reuse_flag = is_reuse(shot, args.tier)
    resolved_model: str | None = None
    if not reuse_flag:
        try:
            resolved_model = model_for(ctx, shot, args.tier, args.model)
        except ProjectError as exc:
            return emit({"ok": False, "errors": [str(exc)]}, EXIT_REFUSED)

    drama = drama_block(ctx.manifest)
    intent_ratio = section(drama, "release_intent").get("aspect_ratio")
    errors, warnings = run_gates(ctx, shot, args.tier, args.today)
    extra_errors, extra_warnings = harness_gates(
        drama, args.dry_run, resolved_model, intent_ratio, args.adapter, reuse_flag
    )
    errors, warnings = list(dict.fromkeys(extra_errors + errors)), list(dict.fromkeys(warnings + extra_warnings))
    if errors:
        breaker_info = handle_circuit_breaker(ctx, root_sid, args.tier, errors, args.dry_run)
        return emit({"ok": False, "errors": errors, "warnings": warnings, **breaker_info}, EXIT_REFUSED)
    if not args.adapter or not args.id_field:
        raise ProjectError("INPUT_ERROR", "give --id-field and the adapter command after --")

    pre_rep, compiled_prompt, book_sha = evaluate_shot_pre_gen(ctx, shot)
    pre_meta = {
        "verdict": pre_rep["verdict"],
        "book_sha256": book_sha,
        "triggered_l1_rules": pre_rep["triggered_l1_rules"],
    }
    record = plan_take(ctx, shot, args.tier, resolved_model or model_for(ctx, shot, args.tier, args.model),
                       compiled_prompt, pre_meta)
    prompt_file: Path | None = None
    if not args.dry_run:
        qc = ctx.project / "qc"
        qc.mkdir(parents=True, exist_ok=True)
        safe_tid = record["take_id"].replace("@", "_").replace("#", "_")
        prompt_file = qc / f"{safe_tid}.compiled_prompt.txt"
        prompt_file.write_text(compiled_prompt, encoding="utf-8")
    else:
        safe_tid = record["take_id"].replace("@", "_").replace("#", "_")
        prompt_file = ctx.project / "qc" / f"{safe_tid}.compiled_prompt.txt"
    command = expand_command(ctx, shot, record, args.adapter, compiled_prompt, prompt_file)
    if drama.get("sop_version") in {"2.0", "3.0"} and not reuse_flag and adapter_consumes_prompt(args.adapter):
        bound_in_argv = any(compiled_prompt in part for part in command)
        bound_in_file = (
            any(str(prompt_file) in part for part in command)
            and (args.dry_run or (prompt_file.is_file() and sha256_file(prompt_file) == sha256_text(compiled_prompt)))
        )
        if not (bound_in_argv or bound_in_file):
            return emit({"ok": False, "errors": ["ADAPTER_PROMPT_NOT_BOUND:expanded command lost compiled prompt"]},
                        EXIT_REFUSED)
    record = {**record, "pre_gen": {**record["pre_gen"], "dispatched_argv_sha256": sha256_text(json.dumps(command, ensure_ascii=False))}}
    if args.dry_run:
        return emit({"dry_run": True, "gates_passed": True, "take_id": record["take_id"],
                     "would_run": command, "pre_gen": record["pre_gen"], "warnings": warnings}, EXIT_OK)
    if shutil.which(command[0]) is None:
        raise ProjectError("INPUT_ERROR", f"adapter not found: {command[0]}")
    try:
        prepare(ctx, shot, record, args.today, args.adapter)
    except ProjectError as exc:
        fresh_ctx = load_context(args.project)
        breaker_info = handle_circuit_breaker(fresh_ctx, root_sid, args.tier, [str(exc)], False)
        return emit({"ok": False, "errors": [str(exc)], **breaker_info}, EXIT_REFUSED)

    take_id = record["take_id"]
    try:
        stdout, problem = run_adapter(command, args.timeout)
    except OSError as exc:
        stdout, problem = "", f"ADAPTER_NOT_RUNNABLE:{type(exc).__name__}"
    job_ids = extract_ids(stdout, args.id_field)
    if job_ids:
        update_manifest(ctx.project, lambda m: ledger.mark_submitted(m, take_id, job_ids, now_iso()))
        missing = sorted(set(args.id_field) - set(job_ids))
        return emit({"ok": True, "take_id": take_id, "job_state": "submitted", "job_ids": job_ids,
                     "missing_id_fields": missing, "warnings": warnings}, EXIT_OK)
    if problem != "ADAPTER_TIMEOUT" and is_pre_submit_balance_refusal(stdout):
        def settle_refused(m: dict[str, Any]) -> dict[str, Any]:
            settled = ledger.settle_take(m, take_id, "failed", now_iso(),
                                         failure_reason="PRE_SUBMIT_INSUFFICIENT_BALANCE", retry_eligible=True)
            return release_presubmit_reservation(settled, record["shot_id"], record["tier"], take_id)
        update_manifest(ctx.project, settle_refused)
        return emit({"ok": False, "take_id": take_id, "job_state": "failed",
                     "reason": "PRE_SUBMIT_INSUFFICIENT_BALANCE", "retry_eligible": True,
                     "next": "Top up balance and record a fresh balance readback before retrying."},
                    EXIT_REFUSED)
    reason = problem or "NO_JOB_ID_IN_ADAPTER_OUTPUT"
    update_manifest(ctx.project, lambda m: ledger.mark_unknown(m, take_id, reason, now_iso()))
    return emit({"ok": False, "take_id": take_id, "job_state": "unknown", "reason": reason,
                 "next": "Recover the job by ID or provider history, then `settle`. Do not submit again."},
                EXIT_UNKNOWN)


def pairs(items: list[str], label: str) -> dict[str, str]:
    result = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key.strip() or not value.strip():
            raise ProjectError("INPUT_ERROR", f"{label} expects name=value: {item}")
        result[key.strip()] = value.strip()
    return result


def file_fields(project: Path, relative: str | None) -> dict[str, Any]:
    if relative is None:
        return {}
    path = resolve_in_project(project, relative)
    if path is None or not path.is_file():
        raise ProjectError("CLIP_FILE_MISSING", relative)
    return {"file": str(path.relative_to(project.resolve())), "file_sha256": sha256_file(path)}


def cmd_settle(args: argparse.Namespace) -> int:
    if args.state == "failed" and not args.terminal_confirmed:
        raise ProjectError("FAILURE_NOT_TERMINAL_CONFIRMED",
                           "read the terminal status back first; an unconfirmed failure stays unknown")
    cost = None
    if args.cost_amount is not None:
        if not nonempty(args.cost_unit):
            raise ProjectError("INPUT_ERROR", "--cost-amount needs --cost-unit")
        cost = {"amount": args.cost_amount, "unit": args.cost_unit}
    fields = {**file_fields(args.project, args.file), "job_ids": pairs(args.job_id, "--job-id"),
              "duration_s": args.duration_s, "cost": cost, "reported_model": args.reported_model,
              "failure_reason": args.reason,
              "retry_eligible": args.retry_eligible if args.state == "failed" else None}

    def mutate(m: dict[str, Any]) -> dict[str, Any]:
        settled = ledger.settle_take(m, args.take, args.state, now_iso(), **fields)
        cur = ledger.find_take(settled, args.take)
        drama = drama_block(settled)
        stale_sec = section(drama, "stale")
        inv_shas = set(stale_sec.get("invalidated_shas") or [])
        shot_stale_row = section(section(stale_sec, "shots"), str(cur.get("shot_id") or ""))
        inv_at = str(shot_stale_row.get("invalidated_at") or "")
        prep_at = str(cur.get("prepared_at") or cur.get("submitted_at") or "")
        try:
            spec_obj, spec_dir_obj, _ = load_project_spec(args.project)
            refs_current = take_matches_current_refs(spec_obj, spec_dir_obj, cur)
        except ProjectError:
            refs_current = True
        late_stale = (
            cur.get("stale") is True
            or not refs_current
            or bool(inv_shas and (set(cur.get("ref_sha256s") or []) & inv_shas))
            or bool(inv_at and prep_at and inv_at > prep_at)
        )
        mismatch = bool(nonempty(args.reported_model) and nonempty(cur.get("exact_model_id"))
                        and args.reported_model.strip() != str(cur["exact_model_id"]).strip())
        if late_stale or mismatch:
            settled = ledger.replace_take(settled, args.take, lambda row: {
                **row,
                **({"stale": True, "stale_mandatory": True, "stale_reason": "upstream invalidated while in flight"} if late_stale else {}),
                **({"model_mismatch": True} if mismatch else {}),
            })
        if args.state == "failed" and args.reason == "PRE_SUBMIT_INSUFFICIENT_BALANCE" and not cur.get("job_ids"):
            settled = release_presubmit_reservation(settled, cur["shot_id"], cur["tier"], args.take)
        elif cur.get("origin") != "reused":
            settled = record_spend_attempt(settled, cur["shot_id"], cur["tier"], args.take)
        return settled

    updated = update_manifest(args.project, mutate)
    take = ledger.find_take(updated, args.take)
    return emit({"ok": True, "take_id": args.take, "job_state": take["job_state"]}, EXIT_OK)


def parse_checks(items: list[str]) -> dict[str, Any]:
    acceptance: dict[str, Any] = {}
    for item in items:
        name, sep, rest = item.partition("=")
        result, sep2, evidence = rest.partition(":")
        if not sep or name not in ACCEPTANCE_CHECKS or result not in ACCEPTANCE_RESULTS:
            raise ProjectError("INPUT_ERROR", f"--check expects one of {ACCEPTANCE_CHECKS}=pass|deviation|fail:evidence")
        acceptance[name] = {"result": result, "evidence": evidence.strip() if sep2 else ""}
    return acceptance


def is_readable_image(path: Path) -> bool:
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except (OSError, UnidentifiedImageError):
        return False


def sheet_evidence_errors(project: Path, take: dict[str, Any], rel: str, tool: str, prefix: str,
                          expected_prev_sha: str | None = None) -> list[str]:
    path = resolve_in_project(project, rel)
    if path is None or not path.is_file():
        return [f"{prefix}_EVIDENCE_FILE_MISSING"]
    sidecar = path.with_name(path.name + ".json")
    meta = read_json(sidecar) if sidecar.is_file() else None
    if (not is_readable_image(path) or not isinstance(meta, dict) or meta.get("tool") != tool
            or meta.get("clip_sha256") != take.get("file_sha256")
            or meta.get("sheet_sha256") != sha256_file(path)):
        return [f"{prefix}_EVIDENCE_NOT_BOUND_TO_TAKE"]
    if expected_prev_sha is not None and meta.get("prev_clip_sha256") != expected_prev_sha:
        return [f"{prefix}_EVIDENCE_NOT_BOUND_TO_TAKE"]
    return []


def expected_prev_clip_sha(project: Path, manifest: dict[str, Any], take: dict[str, Any]) -> str | None:
    try:
        spec, _, _ = load_project_spec(project)
    except ProjectError:
        return None
    prev_id = previous_shot_id(shot_rows(spec), take["shot_id"])
    prev_app = ledger.approved_take(manifest, prev_id, take["tier"]) if prev_id else None
    return prev_app.get("file_sha256") if prev_app else None


def cleanroom_acceptance_errors(project: Path, manifest: dict[str, Any], take: dict[str, Any],
                                explicit_report: str | None = None) -> list[str]:
    """Enforce Clean-Room Post-Gen PASS before approving a take."""
    drama = drama_block(manifest)
    v2_required = drama.get("sop_version") in {"2.0", "3.0"}
    stem = Path(str(take.get("file") or "")).stem
    candidates: list[Path] = []
    if nonempty(explicit_report):
        resolved = resolve_in_project(project, explicit_report)
        if resolved is None or not resolved.is_file():
            return ["POST_GEN_CLEANROOM_MISSING"]
        candidates = [resolved]
    elif stem and (project / "qc").is_dir():
        candidates = sorted((project / "qc").glob(f"{stem}*.cleanroom.json"))

    if not candidates:
        return ["POST_GEN_CLEANROOM_MISSING"] if v2_required else []

    # Check ALL matching cleanroom reports for this take file digest; pick the latest bound one
    bound_reports = []
    for cpath in candidates:
        data = read_json(cpath)
        if isinstance(data, dict) and data.get("clip_sha256") == [take.get("file_sha256")]:
            bound_reports.append(data)
    if not bound_reports:
        if v2_required or nonempty(explicit_report):
            return ["POST_GEN_CLEANROOM_NOT_BOUND:clip_sha256"]
        # Even in v1, if a same-stem report exists with non-PASS verdict, block it
        latest_any = read_json(candidates[-1])
        if isinstance(latest_any, dict) and (latest_any.get("mock") is True or latest_any.get("verdict") != "PASS"):
            return [f"POST_GEN_CLEANROOM_NOT_PASSED:{latest_any.get('verdict')}"]
        return []

    report = bound_reports[-1]
    if report.get("mock") is True or report.get("clean_room_verified") is not True:
        return ["POST_GEN_MOCK_FORBIDDEN"]
    j_name = str(report.get("judge") or "")
    j_meta = section(report, "judge_meta")
    j_sid = str(j_meta.get("judge_session_id") or "").strip()
    recognized_ok = (
        report.get("recognized_multimodal_judge") is True
        and j_name.startswith("agy:")
        and bool(j_sid)
        and j_meta.get("judge_cwd_isolated") is True
        and j_meta.get("returncode") == 0
    )
    if v2_required and not recognized_ok:
        return ["POST_GEN_UNVERIFIED_JUDGE_FORBIDDEN"]
    if report.get("verdict") != "PASS":
        return [f"POST_GEN_CLEANROOM_NOT_PASSED:{report.get('verdict')}"]

    if v2_required:
        spec, spec_dir, _ = load_project_spec(project)
        ctx = Context(project, manifest, spec, spec_dir)
        shot = next((r for r in shot_rows(spec) if r.get("id") == take.get("spec_id")), None)
        if shot is not None:
            req_anchors, anchor_errs = verify_and_collect_take_anchors(project, drama, spec, spec_dir, shot)
            if anchor_errs:
                return [f"POST_GEN_LOCKED_ANCHOR_INVALID:{anchor_errs[0]}"]
            ref_shas = {sha256_file(p) for p in req_anchors}
            rep_anchors = set(report.get("anchor_sha256s") or [])
            if ref_shas and not (ref_shas <= rep_anchors):
                return ["POST_GEN_CLEANROOM_NOT_BOUND:anchor_sha256s"]
            pre_rep, _, _ = evaluate_shot_pre_gen(ctx, shot)
            book_rows = load_book(DEFAULT_BOOK) if DEFAULT_BOOK.is_file() else []
            active_set = active_rules_of(book_rows) if book_rows else None
            expected_ids = {item["id"] for item in rubric_for(pre_rep["triggered_l1_rules"], active_set, book_rows)}
            passed_ids = {str(item.get("id")) for item in (report.get("items") or [])
                          if isinstance(item, dict) and item.get("verdict") == "PASS"}
            if not (expected_ids <= passed_ids):
                return ["POST_GEN_CLEANROOM_NOT_BOUND:rubric_items"]
    return []


def evidence_errors(project: Path, manifest: dict[str, Any], take: dict[str, Any],
                    acceptance: dict[str, Any], cleanroom_report: str | None = None) -> list[str]:
    errors = cleanroom_acceptance_errors(project, manifest, take, cleanroom_report)
    errors += sheet_evidence_errors(project, take, acceptance["identity"]["evidence"],
                                    "make_identity_sheet", "IDENTITY")
    prev_sha = expected_prev_clip_sha(project, manifest, take)
    errors += sheet_evidence_errors(project, take, acceptance["continuity"]["evidence"],
                                    "make_continuity_sheet", "CONTINUITY", prev_sha)
    lines = acceptance["lines"]
    path = resolve_in_project(project, lines["evidence"])
    report = read_json(path) if path is not None and path.is_file() else None
    if not isinstance(report, dict) or report.get("tool") != "check_spoken_lines":
        return errors + ["LINES_EVIDENCE_NOT_A_SPOKEN_LINES_REPORT"]
    if report.get("clip_sha256") != take.get("file_sha256"):
        errors.append("LINES_EVIDENCE_FOR_ANOTHER_FILE")
    if lines["result"] == "pass" and report.get("ok") is not True:
        errors.append("SPOKEN_LINES_DO_NOT_MATCH_SCRIPT")
    return errors


def cmd_accept(args: argparse.Namespace) -> int:
    acceptance = parse_checks(args.check)

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        take = ledger.find_take(manifest, args.take)
        if args.verdict == "approved":
            if take.get("stale") is True:
                raise ProjectError("STALE_TAKE_INVALIDATED", args.take)
            if take.get("model_mismatch") is True or (
                nonempty(take.get("reported_model")) and nonempty(take.get("exact_model_id"))
                and str(take["reported_model"]).strip() != str(take["exact_model_id"]).strip()
            ):
                raise ProjectError("REPORTED_MODEL_MISMATCH",
                                   f"{args.take}:{take.get('reported_model')}!={take.get('exact_model_id')}")
            try:
                spec, spec_dir, _ = load_project_spec(args.project)
                if not take_matches_current_refs(spec, spec_dir, take):
                    raise ProjectError("TAKE_REF_DIGEST_STALE", args.take)
                shot_row = next((r for r in shot_rows(spec) if r.get("id") == take.get("spec_id")), None)
                if shot_row is not None:
                    _, anc_errs = verify_and_collect_take_anchors(args.project, drama_block(manifest), spec, spec_dir, shot_row)
                    if anc_errs:
                        raise ProjectError("LOCKED_ANCHOR_INVALID", f"{args.take}:{anc_errs[0]}")
            except ProjectError as exc:
                if exc.code != "SHOT_SPEC_MISSING":
                    raise
            errors = ledger.check_acceptance(acceptance)
            path = resolve_in_project(args.project, take.get("file"))
            if path is None or not path.is_file() or sha256_file(path) != take.get("file_sha256"):
                errors.append("APPROVED_FILE_MISSING_OR_CHANGED")
            errors = errors or evidence_errors(args.project, manifest, take, acceptance, args.cleanroom_report)
            if errors:
                raise ProjectError(errors[0], args.take)
            manifest = retire_stale_approved(manifest, take)
        judged = ledger.judge_take(manifest, args.take, args.verdict, acceptance, args.reason, now_iso())
        return clear_stale_shot(judged, take["shot_id"], args.take) if args.verdict == "approved" else judged

    update_manifest(args.project, mutate)
    return emit({"ok": True, "take_id": args.take, "status": args.verdict}, EXIT_OK)


def retire_stale_approved(manifest: dict[str, Any], take: dict[str, Any]) -> dict[str, Any]:
    old = ledger.approved_take(manifest, take["shot_id"], take["tier"])
    if old is None or old.get("take_id") == take.get("take_id"):
        return manifest
    if old.get("stale") is not True:
        return manifest
    reason = f"STALE superseded by {take['take_id']}: {old.get('stale_reason') or 'upstream source changed'}"
    return ledger.replace_take(manifest, old["take_id"], lambda row: {
        **row, "status": "rejected", "reject_reason": reason, "judged_at": now_iso()})


def reuse_job_ids(shot: dict[str, Any], given: list[str]) -> dict[str, str]:
    declared = shot.get("reuse_job_ids") or {}
    if not isinstance(declared, dict) or not all(nonempty(str(v)) for v in declared.values()):
        raise ProjectError("INPUT_ERROR", f"{shot['id']}: reuse_job_ids must map names to IDs")
    return {**{key: str(value) for key, value in declared.items()}, **pairs(given, "--job-id")}


def cmd_reuse(args: argparse.Namespace) -> int:
    ctx = load_context(args.project)
    shot = find_shot(ctx, args.shot)
    rows = shot_rows(ctx.spec)
    if shot["id"] in superseded_ids(rows):
        raise ProjectError("SHOT_SUPERSEDED", shot["id"])
    if not args.file and nonempty(shot.get("reuse")) and not is_reuse(shot, args.tier):
        raise ProjectError("REUSE_NOT_FOR_TIER", f"{shot['id']}:{args.tier}: reuse_tiers excludes it; submit instead")
    relative = args.file or shot.get("reuse")
    if not nonempty(relative):
        raise ProjectError("INPUT_ERROR", "give --file or declare `reuse` on the spec shot")
    f_fields = file_fields(args.project, relative)
    clip_sha = f_fields.get("file_sha256")
    for old in take_rows(ctx.manifest):
        if clip_sha and old.get("file_sha256") == clip_sha and (old.get("stale") is True or old.get("status") == "rejected"):
            raise ProjectError("STALE_CLIP_REUSE_FORBIDDEN", f"{relative}:{old.get('take_id')}")
    record = ledger.new_take(
        ledger.next_take_id(ctx.manifest, shot["id"], args.tier), root_id(rows, shot["id"]), shot["id"], args.tier,
        origin="reused", job_state="succeeded", settled_at=now_iso(), duration_s=args.duration_s,
        reuse_note=args.note, job_ids=reuse_job_ids(shot, args.job_id), **f_fields)
    update_manifest(args.project, lambda m: ledger.add_take(m, record))
    return emit({"ok": True, "take_id": record["take_id"], "origin": "reused"}, EXIT_OK)


def with_drama(manifest: dict[str, Any], group: str, change: dict[str, Any]) -> dict[str, Any]:
    drama = drama_block(manifest)
    return {**manifest, "drama": {**drama, group: {**section(drama, group), **change}}}


def cmd_balance(args: argparse.Namespace) -> int:
    proof = resolve_in_project(args.project, args.readback_file)
    if proof is None or not proof.is_file() or proof.stat().st_size == 0:
        raise ProjectError("BALANCE_READBACK_FILE_MISSING",
                           str(args.readback_file or "pass --readback-file <saved balance output>"))
    rel = str(proof.relative_to(args.project.resolve()))
    row = {"amount": args.amount, "unit": args.unit, "checked_at": now_iso(), "source": args.source,
           "readback_file": rel, "readback_sha256": sha256_file(proof)}

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        balances = section(section(drama_block(manifest), "budget"), "balances")
        return with_drama(manifest, "budget", {"balances": {**balances, args.channel: row}})
    update_manifest(args.project, mutate)
    return emit({"ok": True, "channel": args.channel, "balance": row}, EXIT_OK)


def unreviewed_shots(ctx: Context) -> list[str]:
    rows = shot_rows(ctx.spec)
    reviewed = {
        take.get("shot_id") for take in take_rows(ctx.manifest)
        if take.get("status") == "approved"
        and take.get("stale") is not True
        and (take.get("tier") in REVIEW_TIERS or take.get("origin") == "reused")
        and take_matches_current_refs(ctx.spec, ctx.spec_dir, take)
    }
    return sorted(shot["id"] for shot in active_shots(rows) if root_id(rows, shot["id"]) not in reviewed)


def confirmation(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    words = {"user_words": args.user_words.strip(), "confirmed_at": now_iso()}
    if args.kind == "unknown-cost":
        if not nonempty(args.channel):
            raise ProjectError("INPUT_ERROR", "unknown-cost needs --channel")
        return "budget", {"unknown_cost_confirmations": {args.channel: words}}
    if args.kind == "one-shot":
        if args.tier not in TIERS:
            raise ProjectError("INPUT_ERROR", "one-shot needs --tier")
        return "budget", {"one_shot": {**words, "tier": args.tier}}
    ctx = load_context(args.project)
    drama = drama_block(ctx.manifest)
    upstream = (verify_lock(ctx.project)
                + previs_gate_errors(ctx.project, drama)
                + identity_gate_errors(ctx.project, drama)
                + shot_ref_provenance_errors(ctx.project, drama, ctx.spec, ctx.spec_dir))
    blocked = (pending_gate2_errors(drama)
               + [f"STALE_PREVIS_SCENE:{sc}" for sc in sorted(stale_previs_scenes(drama))]
               + [f"STALE_SHOT_NOT_REGENERATED:{sid}" for sid in sorted(stale_shot_ids(drama))]
               + stale_take_errors([take for take in take_rows(ctx.manifest) if take.get("status") == "approved"])
               + upstream)
    if blocked:
        head, _, detail = blocked[0].partition(":")
        raise ProjectError(head, detail)
    missing = unreviewed_shots(ctx)
    if missing:
        raise ProjectError("DRAFT_CUT_NOT_READY", ",".join(missing))
    cut_arg = args.file or section(section(drama, "cuts"), "draft").get("file") or ""
    if drama.get("sop_version") in {"2.0", "3.0"} and not nonempty(cut_arg):
        raise ProjectError("DRAFT_CUT_FILE_REQUIRED", "pass --file <draft_cut.mp4> to bind the approved draft cut")
    cut = file_fields(args.project, cut_arg)
    return "approvals", {"draft_cut": {"approved": True, "stale": False, "approved_at": words["confirmed_at"],
                                       "user_words": words["user_words"], **cut}}


def cmd_confirm(args: argparse.Namespace) -> int:
    if not nonempty(args.user_words):
        raise ProjectError("USER_CONFIRMATION_REQUIRED", "quote the user's own words")
    group, change = confirmation(args)

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        current = section(drama_block(manifest), group)
        merged = {key: {**section(current, key), **value} if key == "unknown_cost_confirmations" else value
                  for key, value in change.items()}
        return with_drama(manifest, group, merged)
    update_manifest(args.project, mutate)
    return emit({"ok": True, "recorded": args.kind}, EXIT_OK)


def add_execution_commands(add: Any) -> None:
    submit = add("submit", cmd_submit, "gate, record, then run the adapter command given after --")
    submit.add_argument("--shot", required=True, help="spec shot id")
    submit.add_argument("--tier", required=True, choices=TIERS)
    submit.add_argument("--model", help="exact model id; default: the spec's models[tier] or model")
    submit.add_argument("--id-field", action="append", default=[], help="job ID key the adapter prints (repeatable)")
    submit.add_argument("--timeout", type=float, default=300.0, help="seconds to wait for the adapter")
    submit.add_argument("--dry-run", action="store_true", help="print the command; run and record nothing")
    submit.add_argument("--today", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD, for card expiry")

    settle = add("settle", cmd_settle, "record a read-back result for an open take")
    settle.add_argument("--take", required=True)
    settle.add_argument("--state", required=True, choices=("submitted", "succeeded", "failed"))
    settle.add_argument("--job-id", action="append", default=[], help="name=value (repeatable)")
    settle.add_argument("--file", help="downloaded clip, relative to the project")
    settle.add_argument("--duration-s", type=float)
    settle.add_argument("--cost-amount", type=float)
    settle.add_argument("--cost-unit")
    settle.add_argument("--reported-model")
    settle.add_argument("--reason", help="failure reason as reported")
    settle.add_argument("--terminal-confirmed", action="store_true", help="the failure was read back as terminal")
    settle.add_argument("--retry-eligible", action="store_true")

    accept = add("accept", cmd_accept, "record per-shot acceptance")
    accept.add_argument("--take", required=True)
    accept.add_argument("--verdict", required=True, choices=("approved", "rejected"))
    accept.add_argument("--check", action="append", default=[], help="lines|identity|beat_action|continuity=result:evidence")
    accept.add_argument("--cleanroom-report", help="optional path to Clean-Room post-gen JSON report")
    accept.add_argument("--reason", help="why the take was rejected")


def add_ledger_commands(add: Any) -> None:
    reuse = add("reuse", cmd_reuse, "register an existing clip for a shot")
    reuse.add_argument("--shot", required=True)
    reuse.add_argument("--tier", required=True, choices=TIERS)
    reuse.add_argument("--file", help="clip relative to the project; default: the spec shot's `reuse`")
    reuse.add_argument("--duration-s", type=float)
    reuse.add_argument("--note", help="where the clip came from")
    reuse.add_argument("--job-id", action="append", default=[],
                       help="name=value job ID the earlier ledger recorded for this clip (repeatable)")

    balance = add("balance", cmd_balance, "record a balance just read from the channel")
    balance.add_argument("--channel", required=True)
    balance.add_argument("--amount", required=True, type=float)
    balance.add_argument("--unit", required=True)
    balance.add_argument("--source", required=True, help="how it was read, e.g. the channel's own balance command")
    balance.add_argument("--readback-file", "--proof-file", dest="readback_file",
                         help="project-relative file saving the raw balance command output (digest is recorded)")

    confirm = add("confirm", cmd_confirm, "record the user's own words")
    confirm.add_argument("--kind", required=True, choices=("unknown-cost", "one-shot", "draft-cut"))
    confirm.add_argument("--user-words", required=True)
    confirm.add_argument("--channel")
    confirm.add_argument("--tier")
    confirm.add_argument("--file", help="draft cut file, relative to the project")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes: 0 done, skipped or dry run; 1 gate refused; 2 outcome unknown (recover, "
               "do not resubmit); 3 input error.")
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name: str, handler: Any, text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=text)
        sub.add_argument("--project", required=True, type=Path, help="project directory")
        sub.set_defaults(handler=handler)
        return sub

    add_execution_commands(add)
    add_ledger_commands(add)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    adapter: list[str] = []
    if "--" in argv:
        split = argv.index("--")
        argv, adapter = argv[:split], argv[split + 1:]
    args = build_parser().parse_args(argv)
    args.project = args.project.expanduser()
    args.adapter = adapter
    try:
        return args.handler(args)
    except ProjectError as exc:
        return emit({"ok": False, "errors": [str(exc)]}, EXIT_INPUT if exc.code == "INPUT_ERROR" else EXIT_REFUSED)


if __name__ == "__main__":
    sys.exit(main())
