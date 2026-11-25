"""Deterministic, offline target compilation using versioned capability receipts."""
import hashlib
import json
import math
import re
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from drama_project import ProjectError
from intake_choices import ALTERNATES, VIDEO_MODELS

MATRIX = Path(__file__).resolve().parents[1] / "references/model-capability-matrix.json"
TARGETS = ("seedance", "seedance_2_0", "seedance_2_5", "google_flow", "higgsfield", "kling",
           "grok_imagine", "xyq", "lovart", "elevenlabs")
IMAGE_MODELS = {"google_flow": "nano_banana_2_1", "higgsfield": "text2image_soul_v2",
                "grok_imagine": "grok-imagine-image-2.0", "xyq": "seedream_5_5"}
ALIASES = {"omni_1_2": "gemini_omni_flash_1_2", "veo_3_1": "veo-3.1-generate-001", "veo3_1": "veo-3.1-generate-001",
           "nano_banana_2_1": "nano_banana_2_1", "nb2_1": "nano_banana_2_1", "cinema_studio": "cinematic_studio_video_4_0"}
CONTROL_KEYS = {"model", "exact_model_id", "tier", "resolution", "route", "endpoint", "requirements",
                "dialogue_translations", "binding_sources", "display_metadata", "audio_route", "draft", "draft_id",
                "draft_job_id", "transport", "soul_id", "credit_rates", "budget_cap", "reported_resolution",
                "measured_resolution", "camera_model_id", "camera_lens_id", "camera_aperture_id"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def model_row(matrix, name):
    return next((r for r in matrix["models"] if name in r["model_id"].split(" / ")), None)


def lookup(name):
    return ALIASES.get(re.sub(r"[\s.]+", "_", str(name).lower()), name)


def bounds(ir, row, model):
    errors = []
    if ir["aspect_ratio"] not in row["aspect_ratios"]:
        errors.append("UNSUPPORTED_ASPECT_RATIO")
    duration = ir.get("duration", {}).get("target_s")
    limits = row.get("duration_range_s")
    if duration is not None and isinstance(limits, dict):
        if (duration < limits.get("min", 0) or duration > limits.get("max", limits.get("observed_lower_max", math.inf))
                or "enum" in limits and duration not in limits["enum"]
                or limits.get("step") == 1 and not float(duration).is_integer()):
            errors.append("UNSUPPORTED_DURATION")
    resolutions = row.get("native_resolutions", [])
    if isinstance(resolutions, dict):
        resolutions = resolutions.get(model, [])
    resolution = ir["live_params"].get("resolution")
    if resolution and str(resolution).casefold() not in [str(r).casefold() for r in resolutions]:
        errors.append("UNSUPPORTED_NATIVE_RESOLUTION")
    return errors


def matrix_ratios(matrix, kind):
    return {r for model in matrix["models"] if model.get("category") == kind
            for r in model.get("aspect_ratios") or [] if re.fullmatch(r"[1-9]\d*:[1-9]\d*", r)}


def validate_named_model(ir, kind, matrix):
    model = lookup(ir["live_params"]["model"])
    row = model_row(matrix, model)
    if not row or row["category"] != kind:
        return ["UNSUPPORTED_MODEL"]
    return bounds(ir, row, model)


def value_text(value):
    if isinstance(value, dict):
        return ", ".join(f"{k}: {value_text(v)}" for k, v in sorted(value.items()) if v and v != "unspecified")
    if isinstance(value, list):
        return "; ".join(value_text(v) for v in value)
    return str(value)


def render_text(ir, bindings, target):
    parts = []
    for k in ("subject", "characters", "scene", "action", "motion", "camera", "light", "style", "audio", "negative", "continuity"):
        if k in ir and ir[k] != "unspecified" and (value := value_text(ir[k])):
            parts.append(f"{k.capitalize()}: {value}")
    display = ir.get("live_params", {}).get("display_metadata", {})
    for key in ("prompt", "kf_prompt"):
        if display.get(key) and display[key] != ir["action"]:
            parts.append(f"{key}: {display[key]}")
    for i, b in enumerate(ir.get("beats", []), 1):
        interval = f"[{b['start_s']:g}-{b['end_s']:g}s]"
        if target == "seedance_2_0":
            interval = f"Shot {i}"
        parts.append(f"{interval} {b['action']} {b.get('camera', '')} {b.get('say', '')}".strip())
    if bindings:
        parts.append("References: " + "; ".join(f"{b['slot']} ({b['role']}, {b['use']})" for b in bindings))
    prompt = "\n".join(parts)
    for b in sorted(bindings, key=lambda x: -len(x["tag"])):
        prompt = re.sub(re.escape(b["tag"]) + r"(?![A-Za-z0-9_])", lambda _: b["slot"], prompt)
    if target == "lovart":
        prompt = "Generate one clip immediately using the supplied references.\n" + prompt
    return prompt


def ordered_bindings(refs, controls, target):
    bindings, counts = [], Counter()
    for ref in refs:
        kind = {"motion": "video", "audio": "audio"}.get(ref["role"], "image")
        counts[kind] += 1
        name = {"image": "Image", "video": "Video", "audio": "Audio"}[kind]
        slot = f"{name} {counts[kind]}"
        if target.startswith("seedance") or target == "higgsfield":
            slot = "@" + slot
        if target == "xyq" and kind == "image":
            slot = f"<Picture {counts[kind]}>"
        if controls.get("route") in ("openai_compat", "grok2api") and kind == "image":
            slot = f"<IMAGE_{counts[kind] - 1}>"
        bindings.append({"tag": ref["ref"], "source": controls.get("binding_sources", {}).get(ref["ref"], ref["ref"]),
                         "role": ref["role"], "use": ref["use"], "kind": kind, "slot": slot})
    return bindings, counts


def price(matrix, target, controls, duration, errors):
    tier = controls.get("resolution") or controls.get("tier")
    rates = matrix.get("pricing", {}).get(target, {})
    supplied = controls.get("credit_rates", {})
    if not isinstance(supplied, dict):
        raise ProjectError("INVALID_CREDIT_RATES")
    rate = supplied.get(tier, rates.get(tier))
    if rate is not None and (type(rate) not in (int, float) or not math.isfinite(rate) or rate < 0):
        raise ProjectError("INVALID_CREDIT_RATE")
    amount = float(Decimal(str(duration)) * Decimal(str(rate))) if duration and rate is not None else None
    if "budget_cap" in controls and (amount is None or amount > controls["budget_cap"]):
        errors.append("BUDGET_UNVERIFIED_OR_EXCEEDED")
    return {"tier": tier, "credits_per_second": rate, "estimated_credits": amount, "quoted": False}


def compile_ir(ir, kind, target, refs, matrix, warnings, *, today=None, allow_expired=False):
    controls = ir.get("live_params", {})
    requested = controls.get("exact_model_id") or controls.get("model")
    default = (IMAGE_MODELS if kind == "image" else VIDEO_MODELS).get(target)
    model = lookup(requested) if requested else default
    row = model_row(matrix, model)
    errors, notes = [], []
    bindings, counts = ordered_bindings(refs, controls, target)
    params = {"aspect_ratio": ir["aspect_ratio"], **{k: v for k, v in controls.items() if k not in
              {"binding_sources", "display_metadata", "requirements", "credit_rates"}}}
    duration = ir.get("duration", {}).get("target_s")
    if duration:
        params["duration"] = duration
    mode = ir.get("task_mode", "omni_reference")
    params["task_mode"] = mode
    endpoint = controls.get("endpoint")
    if endpoint in {"first_frame", "first_last_frame", "last_frame"} and endpoint != mode:
        errors.append("FRAME_SLOT_MISMATCH")
    if target != "grok_imagine" and controls.get("route"):
        errors.append("UNSUPPORTED_ROUTE")
    if controls.get("audio_route") and controls["audio_route"] not in ("keep_native", "native_no_dialogue", "mute", "replace_dialogue"):
        errors.append("UNSUPPORTED_AUDIO_ROUTE")
    if mode in {"edit", "extend"} and target not in {"seedance", "seedance_2_0", "seedance_2_5"}:
        errors.append("EDIT_OR_EXTEND_REQUIRES_ENDPOINT_RECEIPT")
    if not row or row["category"] != kind or model not in [default, *ALTERNATES.get(target, [])]:
        errors.append("UNSUPPORTED_MODEL")
        row = {}
    else:
        profile = row
        if target in {"seedance", "seedance_2_5"} and endpoint == "planning":
            profile = {**row, "duration_range_s": row["planning_duration_range_s"]}
        errors += bounds(ir, profile, model)
    allowed = CONTROL_KEYS - {"draft", "draft_id", "draft_job_id", "transport", "soul_id", "camera_model_id",
                              "camera_lens_id", "camera_aperture_id", "reported_resolution", "measured_resolution"}
    if target == "higgsfield":
        allowed |= {"draft", "draft_id", "draft_job_id", "transport", "soul_id", "camera_model_id",
                    "camera_lens_id", "camera_aperture_id"}
    if target == "grok_imagine":
        allowed |= {"reported_resolution", "measured_resolution"}
    if target == "kling" and model in row.get("dynamic_range_by_model", {}):
        allowed.add("dynamic_range")
    unsupported = sorted(set(controls) - allowed)
    errors.extend("UNKNOWN_PARAMETER:" + key for key in unsupported)
    if controls.get("requirements"):
        errors.append("UNMAPPED_REQUIREMENTS:" + value_text(controls["requirements"]))
    limits = row.get("ref_limits")
    has_limits = isinstance(limits, dict)
    limits = limits if has_limits else {}
    cap = limits.get("images", limits.get("images_including_keyframes", limits.get("images_including_mask",
                     limits.get("image_references"))))
    roles = [b["use"] for b in bindings]
    frames = [r for r in roles if r in ("first_frame", "last_frame")]
    if frames or mode in ("first_frame", "first_last_frame", "last_frame"):
        verified_modes = row.get("frame_modes_by_model", {}).get(model, row.get("frame_modes", []))
        if mode not in verified_modes:
            errors.append("FRAME_MODE_UNVERIFIED")
        expected = {"first_frame": ["first_frame"], "first_last_frame": ["first_frame", "last_frame"],
                    "last_frame": ["last_frame"]}.get(mode)
        if expected is None or sorted(roles) != expected or counts["image"] != len(roles):
            errors.append("FRAME_SLOT_MISMATCH")
    if target.startswith("seedance"):
        if endpoint not in {None, "ark", "volcengine_ark", "planning", "first_frame", "first_last_frame", "edit", "extend"}:
            errors.append("UNSUPPORTED_ENDPOINT")
        if target != "seedance_2_0" and any(not float(b[k]).is_integer() for b in ir.get("beats", []) for k in ("start_s", "end_s")):
            errors.append("INTEGER_SECOND_TIMESTAMPS_REQUIRED")
        if re.search(r"\[\s*\d+(?:\.\d+)\s*[-s]|\[\d+\s*-\s*\d+\.\d+", ir["action"]):
            errors.append("INTEGER_SECOND_TIMESTAMPS_REQUIRED")
        if mode in {"edit", "extend"}:
            errors.append("EDIT_OR_EXTEND_REQUIRES_ENDPOINT_RECEIPT")
    if target == "google_flow":
        params["input_mode"] = "Frames" if frames else ("Ingredients" if bindings else "Text")
        cap = limits.get("google_flow_ui_observed", cap)
        if model == "veo-3.1-generate-001" and duration != 8 and (bindings and not frames or controls.get("resolution") == "1080p"):
            errors.append("VEO_REFERENCE_OR_1080P_REQUIRES_8S")
        if model == "gemini_omni_flash_1_2" and bindings and duration and duration > row["duration_range_s"]["ref_flf_extend_max_s"]:
            errors.append("FLOW_REFERENCE_DURATION_EXCEEDED")
        if counts["video"] or counts["audio"]:
            errors.append("FLOW_INPUT_MEDIA_UNVERIFIED")
    if target == "higgsfield":
        rest = controls.get("transport", "cli") == "rest"
        field = "draft_id" if rest else "draft_job_id"
        if ("draft_job_id" if rest else "draft_id") in controls or (controls.get("draft") and field in controls):
            errors.append("DRAFT_HANDLE_MISMATCH")
        if controls.get("draft") or field in controls:
            if row.get("draft_upgradable") is not True:
                errors.append("DRAFT_UPGRADE_UNAVAILABLE")
        if controls.get("soul_id") and model not in ("text2image_soul_v2", "soul_id"):
            errors.append("SOUL_ID_MODEL_MISMATCH")
        if any(k.startswith("camera_") for k in controls) and model != "cinematic_studio_video_4_0":
            errors.append("CINEMA_STUDIO_HANDLE_REQUIRED")
        notes.append("CLI --draft_job_id and REST finalize-draft draft_id identify different jobs. Ledger both charges.")
    if target == "grok_imagine":
        route = controls.get("route", "xai_api")
        params.update(route=route, requested=controls.get("resolution"), reported=controls.get("reported_resolution"),
                      measured=controls.get("measured_resolution"))
        if route not in ("xai_api", "grok_web", "openai_compat", "grok2api"):
            errors.append("UNSUPPORTED_GROK_ROUTE")
        if route == "grok_web":
            params["observed_web_sizes"] = ["736x400", "672x448"]
            notes.append("Web model identity and native resolution require independent evidence.")
            if requested or controls.get("resolution"):
                errors.append("WEB_MODEL_OR_RESOLUTION_UNVERIFIED")
        if kind == "video" and model and model.endswith("-lite"):
            if controls.get("resolution") == "1080p_upscaled":
                params["upscaled_from"] = "720p"
                notes.append("1080p is an upscale output for the Lite model.")
            cap = limits.get("start_image")
            if bindings and roles != ["first_frame"]:
                errors.append("LITE_REQUIRES_START_FRAME")
        elif kind == "video":
            subgroup = "openai_compat_proxy" if route in ("openai_compat", "grok2api") else "xai_official_docs"
            limit_group = limits.get(subgroup) or (limits.get("local_grok2api_observed") if subgroup == "openai_compat_proxy" else {}) or {}
            cap = limit_group.get("images")
            if counts["video"] or counts["audio"] > limit_group.get("voices", 0):
                errors.append("GROK_MEDIA_LIMIT")
            if frames and roles != ["first_frame"]:
                errors.append("GROK_FRAME_SLOT_UNSUPPORTED")
    if target == "kling":
        if len(bindings) > limits.get("total_images_videos_elements", math.inf):
            errors.append("KLING_ELEMENT_LIMIT")
        if controls.get("resolution") == "4k" and model == "kling_4_0_flash":
            errors.append("FLASH_RESOLUTION_LIMIT")
        params["mode"] = "image-to-video" if frames else ("reference-to-video" if bindings else "text-to-video")
        if params["mode"] == "text-to-video" and ir["aspect_ratio"] == "auto":
            errors.append("KLING_TEXT_REQUIRES_FIXED_RATIO")
        slots = row.get("frame_slots", {})
        for binding in bindings:
            if binding["use"] in slots:
                params[slots[binding["use"]]] = binding["source"]
            elif binding["kind"] in {"image", "video"}:
                params.setdefault(binding["kind"] + "_references", []).append(binding["source"])
        if "dynamic_range" in controls and "dynamic_range" in allowed:
            dynamic = str(controls["dynamic_range"]).lower()
            supported = row["dynamic_range_by_model"][model].get(dynamic, [])
            if controls.get("resolution", "1080p") not in supported:
                errors.append("KLING_DYNAMIC_RANGE_UNSUPPORTED")
            params["dynamic_range"] = dynamic
    if target == "xyq":
        if kind == "image":
            ratios = row.get("xyq_ratio_enum", {})
            if ir["aspect_ratio"] not in ratios:
                errors.append("XYQ_RATIO_ENUM_UNVERIFIED")
            else:
                params["ratio"] = ratios[ir["aspect_ratio"]]
        else:
            params["ratio"] = ir["aspect_ratio"]
            params["task_type"] = "first_last_frame" if frames else "reference_generation"
    if target == "lovart":
        params["attachments"] = [b["source"] for b in bindings]
        notes.append("Verify reported_tool on the receipt. Model preference is advisory.")
    if target == "kling" and counts["audio"]:
        errors.append("KLING_AUDIO_REF_UNVERIFIED")
    for key in ("videos", "audios"):
        if counts[key[:-1]] > limits.get(key, math.inf):
            errors.append("REFERENCE_LIMIT:" + key)
    if kind == "image" and target != "google_flow":
        if counts["video"] and type(limits.get("videos")) is not int:
            errors.append("UNSUPPORTED_IMAGE_MEDIA_REF:video")
        if counts["audio"] and type(limits.get("audios")) is not int:
            errors.append("UNSUPPORTED_IMAGE_MEDIA_REF:audio")
    has_image_cap = type(cap) is int and cap >= 0
    if (bindings and not has_limits) or (counts["image"] and not has_image_cap):
        errors.append("REF_LIMITS_UNVERIFIED")
    if (has_image_cap and counts["image"] > cap) or len(bindings) > limits.get("total_media", math.inf):
        errors.append("REFERENCE_LIMIT")
    params["budget_estimate"] = price(matrix, target, controls, duration, errors)
    if target in {"seedance", "seedance_2_0", "seedance_2_5"}:
        params["content"] = [{"type": b["kind"], "source": b["source"], "role":
                              {"first_frame": "first_frame", "last_frame": "last_frame"}.get(b["use"], "reference_" + b["kind"])}
                             for b in bindings]
    if target == "higgsfield":
        params["media_roles"] = [{"handle": b["source"], "role": b["use"] if b["use"] in {"first_frame", "last_frame"}
                                 else b["kind"] + "_reference"} for b in bindings]
    today = date.fromisoformat(today) if isinstance(today, str) else today or date.today()
    if date.fromisoformat(matrix["expires_at"]) < today:
        (warnings if allow_expired else errors).append("CAPABILITY_RECEIPT_EXPIRED")
    prompt = render_text(ir, bindings, target)
    if target == "google_flow":
        prompt = params["input_mode"] + ": " + prompt
    if target == "higgsfield" and prompt.lstrip().startswith("@"):
        prompt = "Prompt: " + prompt
    exact = None if params.get("route") == "grok_web" else model
    receipt = {"matrix_digest": digest(matrix), "target": target, "exact_model_id": exact,
               "capability_row": row, "parameters": params}
    return {"ok": not errors, "target": target, "exact_model_id": exact,
            "prompt_text": prompt if not errors else "", "parameters": params, "params": params,
            "ordered_bindings": bindings, "unsupported_requirements": errors, "errors": errors,
            "capability_receipt_hash": digest(receipt), "warnings": warnings, "notes": notes}
