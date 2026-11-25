#!/usr/bin/env python3
"""Render a validated NBP v2 video prompt for a provider adapter."""
from __future__ import annotations

import argparse
from drama_project import ProjectError
from simplified_prompt import normalize, schema_of
import target_compiler
import json
import math
import re
import sys
from datetime import date, datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

from validate_nbp_prompt import (
    CANONICAL_TAG_RE,
    is_nonempty_string,
    parse_dialogue_line,
    v2_task_mode,
    validate_prompt, validate_v2_prompt,
)
from validate_prompt_package import canonical_tag_kind, extract_tag_tokens


XYQ_MODEL_FALLBACK_KEYS = {"min_duration_s", "max_duration_s"}
FRAME_TASK_MODES = {"first_frame", "first_last_frame"}
SPECIAL_SEEDANCE_TASK_MODES = {"edit", "extend"}
IMAGE_REFERENCE_ROLES = {"character", "prop", "location", "style"}
REFERENCE_ROLE_GROUPS = {
    "character": "image",
    "prop": "image",
    "location": "image",
    "style": "image",
    "motion": "video",
    "audio": "audio",
}
TAG_KIND_ROLES = {
    "char": "character",
    "outfit": "character",
    "wardrobe": "character",
    "prop": "prop",
    "product": "prop",
    "location": "location",
    "style": "style",
    "motion": "motion",
    "video": "motion",
    "audio": "audio",
}
XYQ_SOURCE_NOTE = (
    "参数名对齐依据：xyq-skill / pippit-tool-cli 官方参数定义（只读）"
)
PROVIDER_ALIASES = {
    "seedance": {"seedance", "volcengine", "ark", "byteplus", "dreamina", "jimeng"},
    "higgsfield": {"higgsfield"},
    "xyq": {"xyq", "pippit", "xiaoyunque"},
}
PLANNING_SCOPE = {
    "validation_scope": "planning_only",
    "provider_ready": False,
    "live_submission_checked": False,
}
RULE_SOURCE_CLASSES = {"official", "official_schema", "live_schema", "provider_schema", "account_probe"}


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def emit_error(
    target: str,
    errors: list[str],
    json_output: bool,
    warnings: list[str] | None = None,
) -> None:
    warnings = warnings or []
    if json_output:
        print(
            json.dumps(
                {
                    **PLANNING_SCOPE,
                    "ok": False, "target": target, "unsupported_requirements": errors,
                    "exact_model_id": None, "prompt_text": "", "parameters": {}, "ordered_bindings": [],
                    "capability_receipt_hash": None, "notes": [],
                    "errors": errors,
                    "warnings": warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    for error in errors:
        print(error)


def emit_result(result: dict[str, Any], json_output: bool) -> None:
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"Target: {result['target']}")
    print("Scope: planning_only; provider_ready=false; live_submission_checked=false")
    print("Prompt:")
    print(result["prompt_text"])
    print("Params:")
    print(json.dumps(result["params"], ensure_ascii=False, indent=2))
    if result["warnings"]:
        print("Warnings:")
        for warning in result["warnings"]:
            print(f"- {warning}")
    if result["notes"]:
        print("Notes:")
        for note in result["notes"]:
            print(f"- {note}")


def receipt_time(value: object) -> datetime | None:
    if not is_nonempty_string(value):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
    except ValueError:
        return None


def checked_capabilities(
    capabilities: object | None, target: str, warnings: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep legacy planning limits separate from evidence-bound parameter rules.

    This checks receipt metadata only, never account access or live availability.
    Per-claim model binding is required because a platform receipt can mix models.
    """
    receipt = capabilities if isinstance(capabilities, dict) else {}
    planning = {**receipt, "claims": []}
    verified = {**receipt, "claims": []}
    now = datetime.now(timezone.utc)
    model_id = receipt.get("exact_model_id")
    raw_claims = receipt.get("claims", [])
    if not isinstance(raw_claims, list):
        append_unique(warnings, "CAP_RECEIPT_INVALID:claims")
        return planning, verified
    for claim in raw_claims:
        if not isinstance(claim, dict) or not is_nonempty_string(claim.get("key")):
            continue
        key = claim["key"]
        metadata = {**receipt, **claim}
        rejected: list[str] = []
        missing: list[str] = []
        status = claim.get("status")
        if status is not None and status != "verified":
            rejected.append("status")
        elif status is None:
            missing.append("status")
        for record in (receipt, claim):
            provider = record.get("provider")
            if provider is not None and (
                not isinstance(provider, str)
                or provider.strip().lower() not in PROVIDER_ALIASES[target]
            ):
                rejected.append("provider")
        if (is_nonempty_string(receipt.get("provider"))
                and is_nonempty_string(claim.get("provider"))
                and receipt["provider"].strip().lower() != claim["provider"].strip().lower()):
            rejected.append("provider_binding")
        if ("account_or_endpoint_scope" in receipt and "account_or_endpoint_scope" in claim
                and receipt["account_or_endpoint_scope"] != claim["account_or_endpoint_scope"]):
            rejected.append("endpoint_binding")
        if not is_nonempty_string(metadata.get("provider")):
            missing.append("provider")
        claim_model = claim.get("exact_model_id", claim.get("model_id", claim.get("model")))
        if claim_model is not None and claim_model != model_id:
            rejected.append("model")
        if (not is_nonempty_string(claim_model)
                or not is_nonempty_string(model_id)
                or str(model_id).lower() in {"unknown", "todo_verify_live"}):
            missing.append("exact_model_binding")
        for field in ("captured_at", "expires_at"):
            stamp = receipt_time(metadata.get(field))
            if field in metadata and stamp is None:
                rejected.append(field)
            elif stamp is None:
                missing.append(field)
            elif ((field == "expires_at" and stamp <= now)
                  or (field == "captured_at" and stamp > now)):
                rejected.append(field)
        captured = receipt_time(metadata.get("captured_at"))
        expires = receipt_time(metadata.get("expires_at"))
        if captured and expires and expires <= captured:
            rejected.append("time_order")
        source_class = metadata.get("source_class")
        if not isinstance(source_class, str) or source_class not in RULE_SOURCE_CLASSES:
            missing.append("source_class")
        if not is_nonempty_string(metadata.get("account_or_endpoint_scope")):
            missing.append("account_or_endpoint_scope")
        url = claim.get("url", claim.get("source_url", receipt.get("url")))
        if not isinstance(url, str) or not re.match(r"^https?://[^/\s]+", url):
            missing.append("source_url")
        if rejected:
            append_unique(warnings, f"CAP_EVIDENCE_REJECTED:{key}:{','.join(sorted(set(rejected)))}")
            continue
        planning["claims"].append(claim)
        if missing:
            append_unique(warnings, f"CAP_EVIDENCE_UNVERIFIED:{key}:{','.join(missing)}")
        else:
            verified["claims"].append(claim)
    for selected in (planning, verified):
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for claim in selected["claims"]:
            scope = claim.get("scope")
            scope = scope if isinstance(scope, str) and scope in {"cli", "model", "platform"} else "unscoped"
            grouped.setdefault((claim["key"], scope), []).append(claim)
        selected["claims"] = []
        for (key, scope), claims in grouped.items():
            first = claims[0].get("value")
            if any(claim.get("value") != first or type(claim.get("value")) is not type(first)
                   for claim in claims[1:]):
                append_unique(warnings, f"CAP_EVIDENCE_CONFLICT:{key}:{scope}")
            else:
                selected["claims"].extend(claims)
    return planning, verified


def scoped_capability_claims(
    capabilities: object | None,
) -> dict[str, dict[str, object]]:
    if not isinstance(capabilities, dict):
        return {}
    raw_claims = capabilities.get("claims")
    if not isinstance(raw_claims, list):
        return {}
    claims: dict[str, dict[str, object]] = {}
    for claim in raw_claims:
        if not isinstance(claim, dict):
            continue
        key = claim.get("key")
        if not is_nonempty_string(key):
            continue
        scope = claim.get("scope")
        scope_key = scope if isinstance(scope, str) and scope in {"cli", "model", "platform"} else "unscoped"
        claims.setdefault(key, {}).setdefault(scope_key, claim.get("value"))
    return claims


def capability_claims(
    capabilities: object | None,
    target: str,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    scoped = scoped_capability_claims(capabilities)
    selected: dict[str, object] = {}
    for key, values in scoped.items():
        if target == "seedance":
            scope_order = ("model", "unscoped")
        elif target == "higgsfield":
            scope_order = ("platform", "model", "unscoped")
        elif key in XYQ_MODEL_FALLBACK_KEYS:
            scope_order = ("cli", "model", "unscoped")
        else:
            scope_order = ("cli", "unscoped")
        for scope in scope_order:
            if scope in values:
                selected[key] = values[scope]
                break
    return selected, scoped


def exact_model_id(capabilities: object | None, warnings: list[str]) -> str | None:
    value = capabilities.get("exact_model_id") if isinstance(capabilities, dict) else None
    if not is_nonempty_string(value):
        if "CAP_MISSING:exact_model_id" not in warnings:
            warnings.append("CAP_MISSING:exact_model_id")
        return None
    return value


def scalar_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def numeric_claim(
    claims: dict[str, object],
    key: str,
    warnings: list[str],
) -> int | float | None:
    value = claims.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (isinstance(value, float) and not math.isfinite(value))
    ):
        warnings.append(f"CAP_MISSING:{key}")
        return None
    return value


def list_claim(
    claims: dict[str, object],
    key: str,
    warnings: list[str],
) -> list[object] | None:
    value = claims.get(key)
    if not isinstance(value, list):
        warnings.append(f"CAP_MISSING:{key}")
        return None
    return value


def append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def seedance_task_mode_rules(
    data: dict[str, Any],
    capabilities: object | None,
    warnings: list[str],
) -> dict[str, object]:
    if v2_task_mode(data) not in SPECIAL_SEEDANCE_TASK_MODES:
        return {}
    model_id = exact_model_id(capabilities, warnings)
    rules: dict[str, object] = {}
    claims = capabilities.get("claims", []) if isinstance(capabilities, dict) else []
    for key, param in (("edit_extend_duration", "duration"), ("edit_extend_ratio", "ratio")):
        matches = [claim for claim in claims if claim.get("key") == key
                   and claim.get("scope") == "model"
                   and isinstance(claim.get("task_modes"), list)
                   and v2_task_mode(data) in claim["task_modes"]]
        values = [claim.get("value") for claim in matches]
        if not values or any(value != values[0] for value in values):
            append_unique(warnings, f"TASK_MODE_CLAIM_UNVERIFIED:{key}")
            continue
        value = values[0]
        valid = (isinstance(value, (int, float)) and not isinstance(value, bool)
                 and math.isfinite(value) and (value > 0 or value == -1)) if param == "duration" else (
                     is_nonempty_string(value) and (value == "adaptive" or aspect_fraction(value) is not None))
        if valid:
            rules[param] = value
        else:
            append_unique(warnings, f"TASK_MODE_CLAIM_UNVERIFIED:{key}")
    if len(rules) != 2:
        append_unique(warnings, f"TASK_MODE_RULE_UNVERIFIED:{model_id or 'unknown'}")
    return rules


def aspect_fraction(value: object) -> Fraction | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*([0-9]+)\s*[:/]\s*([0-9]+)\s*", value)
    if match and int(match[1]) > 0 and int(match[2]) > 0:
        return Fraction(int(match[1]), int(match[2]))
    return None


def frame_geometry_warnings(data: dict[str, Any], registry: object | None) -> list[str]:
    """Compare declared registry geometry without modifying or claiming pixel QC."""
    if v2_task_mode(data) not in FRAME_TASK_MODES:
        return []
    assets = registry.get("assets", []) if isinstance(registry, dict) else []
    by_tag = {asset.get("canonical_tag"): asset for asset in assets if isinstance(asset, dict)}
    ratios: dict[str, Fraction] = {}
    warnings: list[str] = []
    target_ratio = aspect_fraction(data.get("aspect_ratio"))
    for reference in data["references"]:
        tag = reference["ref"]
        asset = by_tag.get(tag, {})
        dimensions = asset.get("dimensions", asset)
        width = dimensions.get("width") if isinstance(dimensions, dict) else None
        height = dimensions.get("height") if isinstance(dimensions, dict) else None
        ratio = aspect_fraction(asset.get("aspect_ratio", asset.get("ratio")))
        if (type(width) is int and type(height) is int and width > 0 and height > 0):
            dimension_ratio = Fraction(width, height)
            if ratio is not None and ratio != dimension_ratio:
                warnings.append(f"FRAME_GEOMETRY_CONFLICT:{tag}")
            ratio = dimension_ratio
        if ratio is None:
            warnings.append(f"FRAME_GEOMETRY_UNVERIFIED:{reference['use']}:{tag}")
            continue
        ratios[reference["use"]] = ratio
        if target_ratio is not None and ratio != target_ratio:
            warnings.append(f"FRAME_OUTPUT_RATIO_MISMATCH:{reference['use']}:{tag}")
    if ("first_frame" in ratios and "last_frame" in ratios
            and ratios["first_frame"] != ratios["last_frame"]):
        warnings.append("FRAME_ASPECT_RATIO_MISMATCH:first_frame:last_frame")
    return warnings


def canonical_tags(value: object) -> list[str]:
    if isinstance(value, str):
        return [tag for tag in extract_tag_tokens(value) if CANONICAL_TAG_RE.fullmatch(tag)]
    if isinstance(value, list):
        return [tag for item in value for tag in canonical_tags(item)]
    if isinstance(value, dict):
        return [tag for item in value.values() for tag in canonical_tags(item)]
    return []


def adapter_references(data: dict[str, Any], *, legacy_roles: bool = False) -> list[dict[str, str]]:
    references = []
    seen = set()
    seen_tags = set()

    def add(reference):
        tag = reference["ref"]
        key = (tag, reference["role"]) if legacy_roles else tag
        if key not in seen:
            seen.add(key)
            seen_tags.add(tag)
            references.append(dict(reference))

    for reference in data["references"]:
        add(reference)
    if v2_task_mode(data) != "omni_reference":
        return references

    def add_contextual(value: object, role: str, use: str) -> None:
        for tag in canonical_tags(value):
            add({"ref": tag, "role": role, "use": use})

    for index, character in enumerate(data["characters"]):
        add_contextual(character["ref"], "character", f"characters[{index}].ref")
        add_contextual(character["wardrobe"], "character", f"characters[{index}].wardrobe")
    add_contextual(data.get("scene"), "location", "scene")
    add_contextual(data.get("style"), "style", "style")
    add_contextual(data.get("motion"), "motion", "motion")
    add_contextual(data.get("audio"), "audio", "audio")

    # script_ref is an operator note and never reaches the prompt, so it binds no media.
    for tag in canonical_tags({key: value for key, value in data.items() if key != "script_ref"}):
        if tag in seen_tags:
            continue
        kind = canonical_tag_kind(tag)
        role = TAG_KIND_ROLES.get(kind, kind or "unknown")
        add({"ref": tag, "role": role, "use": "embedded canonical tag"})
    return references


def role_unmapped(warnings: list[str], target: str, role: str, ref: str) -> None:
    warning = f"ROLE_UNMAPPED:{target}:{role}:{ref}"
    if warning not in warnings:
        warnings.append(warning)


def reference_groups(
    references: list[dict[str, str]],
    target: str,
    warnings: list[str],
) -> dict[str, list[str]]:
    groups = {"image": [], "video": [], "audio": []}
    for reference in references:
        role = reference["role"]
        group = REFERENCE_ROLE_GROUPS.get(role)
        if group is None:
            role_unmapped(warnings, target, role, reference["ref"])
            continue
        groups[group].append(reference["ref"])
    return groups


def frame_reference_groups(
    references: list[dict[str, str]],
) -> dict[str, list[str]]:
    return {
        "image": [reference["ref"] for reference in references],
        "video": [],
        "audio": [],
    }


def capability_issues(
    data: dict[str, Any],
    groups: dict[str, list[str]],
    capabilities: object | None,
    target: str,
    task_mode_rules: dict[str, object] | None = None,
) -> tuple[list[str], list[str], dict[str, object], dict[str, dict[str, object]]]:
    errors: list[str] = []
    warnings: list[str] = []
    claims, scoped_claims = capability_claims(capabilities, target)
    target_s = data["duration"]["target_s"]
    task_mode_rules = task_mode_rules or {}
    if "duration" not in task_mode_rules:
        maximum = numeric_claim(claims, "max_duration_s", warnings)
        if maximum is not None and target_s > maximum:
            errors.append(
                f"CAP_EXCEEDED:max_duration_s:{scalar_text(target_s)}>{scalar_text(maximum)}"
            )
        minimum = numeric_claim(claims, "min_duration_s", warnings)
        if minimum is not None and target_s < minimum:
            errors.append(
                f"CAP_EXCEEDED:min_duration_s:{scalar_text(target_s)}<{scalar_text(minimum)}"
            )

    count_checks = (
        ("max_ref_images", len(groups["image"])),
        ("max_ref_videos", len(groups["video"])),
        ("max_ref_audios", len(groups["audio"])),
    )
    for key, actual in count_checks:
        limit = numeric_claim(claims, key, warnings)
        if limit is not None and actual > limit:
            errors.append(f"CAP_EXCEEDED:{key}:{actual}>{scalar_text(limit)}")

    if "max_ref_slots" in claims or target == "higgsfield":
        slot_limit = numeric_claim(claims, "max_ref_slots", warnings)
        actual_slots = sum(len(values) for values in groups.values())
        if slot_limit is not None and actual_slots > slot_limit:
            errors.append(
                f"CAP_EXCEEDED:max_ref_slots:{actual_slots}>{scalar_text(slot_limit)}"
            )

    if "ratio" not in task_mode_rules:
        ratios = list_claim(claims, "aspect_ratios", warnings)
        if ratios is not None and data["aspect_ratio"] not in ratios:
            errors.append(
                "CAP_EXCEEDED:aspect_ratios:"
                f"{data['aspect_ratio']}>{scalar_text(ratios)}"
            )

    if target == "xyq":
        resolutions = list_claim(claims, "resolutions", warnings)
        resolution = data.get("live_params", {}).get("resolution")
        if resolutions is not None and resolution is not None and resolution not in resolutions:
            errors.append(
                f"CAP_EXCEEDED:resolutions:{resolution}>{scalar_text(resolutions)}"
            )
        for key, values in scoped_claims.items():
            cli_value = values.get("cli")
            model_value = values.get("model")
            if (
                not isinstance(cli_value, bool)
                and isinstance(cli_value, (int, float))
                and not isinstance(model_value, bool)
                and isinstance(model_value, (int, float))
                and model_value > cli_value
            ):
                warnings.append(
                    f"CAP_ENTRY_LOWER:{key}:{scalar_text(cli_value)}<{scalar_text(model_value)}"
                )
    return errors, warnings, claims, scoped_claims


def reference_placeholder(
    tag: str,
    groups: dict[str, list[str]],
    dialect: str,
) -> str:
    labels = {
        "image": "@图片" if dialect == "seedance" else "参考图",
        "video": "参考视频",
        "audio": "参考音频",
    }
    for group, values in groups.items():
        if tag in values:
            return f"{labels[group]}{values.index(tag) + 1}"
    return "已绑定参考素材"


def prompt_value(
    value: str,
    groups: dict[str, list[str]],
    dialect: str,
) -> str:
    tags = canonical_tags(value)
    if not tags:
        return value
    replacement_order = sorted(set(tags), key=len, reverse=True)
    if dialect == "seedance":
        result = value
        for tag in replacement_order:
            result = result.replace(tag, reference_placeholder(tag, groups, dialect))
        return result

    result = value
    for tag in replacement_order:
        result = result.replace(tag, "")
    result = re.sub(r"\s+", " ", result)
    connector_free = re.sub(r"\b(?:and|or)\b", "", result, flags=re.IGNORECASE)
    connector_free = re.sub(r"[与和或及]", "", connector_free)
    if re.sub(r"[\W_]+", "", connector_free):
        return result.strip(
            " \t\r\n,;:/|+&，。；：、()（）[]【】{}<>《》「」『』“”‘’\"'_-—–"
        )
    placeholders: list[str] = []
    for tag in tags:
        append_unique(placeholders, reference_placeholder(tag, groups, dialect))
    return "、".join(placeholders)


def character_module(
    data: dict[str, Any],
    groups: dict[str, list[str]],
    dialect: str,
) -> str:
    entries: list[str] = []
    for index, character in enumerate(data["characters"]):
        state = prompt_value(character["state"], groups, dialect)
        wardrobe = prompt_value(character["wardrobe"], groups, dialect)
        name = character.get("name")
        # The name is what dialogue lines use, so it must be the label bound to the reference slot.
        identity = prompt_value(name, groups, dialect) if name else f"角色{index + 1}"
        bound = any(character["ref"] in values for values in groups.values())
        if bound or dialect == "seedance":
            identity += f" {reference_placeholder(character['ref'], groups, dialect)}"
        entries.append(f"{identity}（状态：{state}；服装：{wardrobe}）")
    text = "人物：" + "；".join(entries)
    if "subject" in data:
        text += f"；主体补充：{prompt_value(data['subject'], groups, dialect)}"
    return text


def camera_module(
    data: dict[str, Any],
    groups: dict[str, list[str]],
    dialect: str,
) -> str:
    camera = data["camera"]
    return (
        f"摄影机：景别 {prompt_value(camera['shot_size'], groups, dialect)}；"
        f"角度 {prompt_value(camera['angle'], groups, dialect)}；"
        f"运动 {prompt_value(camera['movement'], groups, dialect)}；"
        f"镜头说明 {prompt_value(camera['lens_note'], groups, dialect)}"
    )


def spoken_line(line: str, groups: dict[str, list[str]], dialect: str) -> str:
    """Keep who speaks, how, and the exact words apart so only the quoted words get voiced."""
    parsed = parse_dialogue_line(line)
    if parsed is None:
        return prompt_value(line, groups, dialect)
    speaker, tone, words = parsed
    delivery = f"（{prompt_value(tone, groups, dialect)}）" if tone else ""
    return f"{prompt_value(speaker, groups, dialect)}{delivery}说：「{prompt_value(words, groups, dialect)}」"


def beats_module(
    data: dict[str, Any],
    groups: dict[str, list[str]],
    dialect: str,
) -> str | None:
    """Timed segments put each line inside the action it belongs to instead of after the shot."""
    entries: list[str] = []
    for beat in data.get("beats", []):
        parts = [prompt_value(beat["action"], groups, dialect)]
        if "camera" in beat:
            parts.append(f"镜头 {prompt_value(beat['camera'], groups, dialect)}")
        if "say" in beat:
            parts.append(spoken_line(beat["say"], groups, dialect))
        entries.append(f"[{beat['start_s']:g}–{beat['end_s']:g}秒] " + "，".join(parts))
    return "分段：" + "；".join(entries) if entries else None


def audio_module(
    data: dict[str, Any],
    groups: dict[str, list[str]],
    dialect: str,
    *,
    include_atmosphere: bool = True,
) -> str:
    audio = data["audio"]
    parts: list[str] = []
    if audio["dialogue"] and "beats" in data:
        # Lines already sit in their segments; the closing declaration counts them instead of
        # repeating the words, which could be voiced as a second take.
        parts.append(f"对白 共{len(audio['dialogue'])}句，只在上述分段中各说一次，逐字不改")
    elif audio["dialogue"]:
        dialogue = [spoken_line(line, groups, dialect) for line in audio["dialogue"]]
        parts.append("对白（依次）：" + " / ".join(dialogue))
    fields = [("音效", "sfx")]
    if include_atmosphere:
        fields = [("环境声", "ambience"), ("音乐", "music"), *fields]
    for label, key in fields:
        if audio[key]:
            parts.append(f"{label} {prompt_value(audio[key], groups, dialect)}")
    return "声音：" + "；".join(parts) if parts else "声音：无已声明内容"


def reference_use_module(
    data: dict[str, Any], groups: dict[str, list[str]], dialect: str,
) -> str | None:
    """Carry explicit reference intent into copyable text using local slot labels."""
    entries: list[str] = []
    for reference in data["references"]:
        group = "image" if v2_task_mode(data) in FRAME_TASK_MODES else REFERENCE_ROLE_GROUPS[reference["role"]]
        role_groups = {key: values if key == group else [] for key, values in groups.items()}
        identity = prompt_value(reference["ref"], role_groups, dialect)
        use = reference["use"]
        # Generic prose normally drops embedded tags; here their referents are part
        # of the input-use constraint and must survive as readable slot labels.
        for tag in sorted(set(canonical_tags(use)), key=len, reverse=True):
            bindings = role_groups if tag == reference["ref"] else groups
            use = use.replace(tag, prompt_value(tag, bindings, dialect))
        entries.append(f"{identity}（role={reference['role']}；use={use}）")
    return "参考职责（本地编号）：" + "；".join(entries) if entries else None


def action_modules(
    data: dict[str, Any],
    groups: dict[str, list[str]],
    dialect: str,
) -> list[str]:
    modules = [f"动作：{prompt_value(data['action'], groups, dialect)}"]
    if "motion" in data:
        modules.append(f"运动过程：{prompt_value(data['motion'], groups, dialect)}")
    modules.append(camera_module(data, groups, dialect))
    beats = beats_module(data, groups, dialect)
    if beats:
        modules.append(beats)
    return modules


def prompt_modules(
    data: dict[str, Any],
    groups: dict[str, list[str]],
    dialect: str,
) -> list[str]:
    modules = [
        character_module(data, groups, dialect),
        f"场景：{prompt_value(data['scene'], groups, dialect)}",
        *action_modules(data, groups, dialect),
    ]
    if "light" in data:
        modules.append(f"光线：{prompt_value(data['light'], groups, dialect)}")
    if "style" in data:
        modules.append(f"风格：{prompt_value(data['style'], groups, dialect)}")
    reference_uses = reference_use_module(data, groups, dialect)
    if reference_uses:
        modules.append(reference_uses)
    modules.append(audio_module(data, groups, dialect))
    return modules


def tag_map_note(buckets: dict[str, list[str]]) -> str:
    locations: dict[str, list[str]] = {}
    for bucket, tags in buckets.items():
        for index, tag in enumerate(tags):
            locations.setdefault(tag, []).append(f"{bucket}[{index}]")
    if not locations:
        return "tag_map: empty"
    return "tag_map: " + "; ".join(
        f"{tag} -> {', '.join(paths)}" for tag, paths in locations.items()
    )


def render_seedance(
    data: dict[str, Any],
    references: list[dict[str, str]],
    groups: dict[str, list[str]],
    capabilities: object | None,
    warnings: list[str],
    task_mode_rules: dict[str, object] | None = None,
) -> tuple[str, dict[str, Any], list[str]]:
    model_id = exact_model_id(capabilities, warnings)
    task_mode = v2_task_mode(data)
    params: dict[str, Any] = {
        "model": model_id,
        "duration": data["duration"]["target_s"],
        "ratio": data["aspect_ratio"],
        "negative": data.get("negative", []),
    }
    if task_mode in FRAME_TASK_MODES:
        frame_references = [
            {"ref": reference["ref"], "role": reference["use"]}
            for reference in references
        ]
        params["references"] = frame_references
        tag_buckets = {
            f"references.{reference['role']}": [reference["ref"]]
            for reference in frame_references
        }
    else:
        params.update(
            {
                "image_refs": groups["image"],
                "video_refs": groups["video"],
                "audio_refs": groups["audio"],
            }
        )
        tag_buckets = {
            "image_refs": groups["image"],
            "video_refs": groups["video"],
            "audio_refs": groups["audio"],
        }

    for key, value in (task_mode_rules or {}).items():
        if params[key] != value:
            params[key] = value
            warnings.append(f"FORCED_BY_TASK_MODE:{key}")

    notes = ["`@图片N` 槽位以 live UI 为准", tag_map_note(tag_buckets)]
    return "\n\n".join(prompt_modules(data, groups, "seedance")), params, notes


def higgsfield_media_roles(
    references: list[dict[str, str]],
    warnings: list[str],
    task_mode: object = "omni_reference",
    frame_slots: bool = False,
    model_id: str | None = None,
) -> dict[str, list[str]]:
    media_roles = {
        "character": [],
        "location": [],
        "style": [],
        "prop": [],
        "motion": [],
        "audio": [],
    }
    if task_mode in FRAME_TASK_MODES:
        if not frame_slots:
            warnings.append(f"NO_END_FRAME_SLOT:{model_id or 'unknown'}")
            for reference in references:
                warnings.append(
                    "FRAME_REFERENCE_NOT_MAPPED:"
                    f"{reference['use']}:{reference['ref']}"
                )
            return media_roles
        for reference in references:
            output_role = "first_frame" if reference["use"] == "first_frame" else "end_frame"
            media_roles.setdefault(output_role, []).append(reference["ref"])
        return media_roles

    for reference in references:
        role = reference["role"]
        ref = reference["ref"]
        if role not in media_roles:
            role_unmapped(warnings, "higgsfield", role, ref)
            continue
        append_unique(media_roles[role], ref)
    return media_roles


def render_higgsfield(
    data: dict[str, Any],
    references: list[dict[str, str]],
    groups: dict[str, list[str]],
    capabilities: object | None,
    scoped_claims: dict[str, dict[str, object]],
    warnings: list[str],
) -> tuple[str, dict[str, Any], list[str]]:
    model_id = exact_model_id(capabilities, warnings)
    frame_slots = (
        scoped_claims.get("first_last_frame_slots", {}).get("model") is True
    )
    media_roles = higgsfield_media_roles(
        references,
        warnings,
        v2_task_mode(data),
        frame_slots,
        model_id,
    )
    params = {
        "base_model": model_id,
        "media_roles": media_roles,
        "duration_s": data["duration"]["target_s"],
        "aspect_ratio": data["aspect_ratio"],
        "negative": data.get("negative", []),
    }
    tag_buckets = {
        "prompt_image": groups["image"],
        **{f"media_roles.{key}": value for key, value in media_roles.items()},
    }
    notes = [
        "参考图N 按 prompt_image 的一基顺序；media_roles 是实际交接桶",
        tag_map_note(tag_buckets),
    ]
    return "；".join(prompt_modules(data, groups, "generic")), params, notes


def xyq_prompt(data: dict[str, Any], groups: dict[str, list[str]]) -> str:
    content = [
        character_module(data, groups, "generic"),
        f"场景：{prompt_value(data['scene'], groups, 'generic')}",
        *action_modules(data, groups, "generic"),
    ]
    reference_uses = reference_use_module(data, groups, "generic")
    if reference_uses:
        content.append(reference_uses)
    audio = audio_module(data, groups, "generic", include_atmosphere=False)
    if audio != "声音：无已声明内容":
        content.append(audio)
    video_type = (
        prompt_value(data["style"], groups, "generic")
        if "style" in data
        else "短剧镜头"
    )
    sections = [f"视频类型：{video_type}", "内容要点：" + "；".join(content)]

    atmosphere: list[str] = []
    if "light" in data:
        atmosphere.append(prompt_value(data["light"], groups, "generic"))
    if data["audio"]["ambience"]:
        atmosphere.append(prompt_value(data["audio"]["ambience"], groups, "generic"))
    if data["audio"]["music"]:
        atmosphere.append(prompt_value(data["audio"]["music"], groups, "generic"))
    if atmosphere:
        sections.append("情绪氛围：" + "；".join(atmosphere))
    sections.append(f"时长：{data['duration']['target_s']}秒")
    return "。".join(sections) + "。"


def xyq_images(
    data: dict[str, Any],
    references: list[dict[str, str]],
    image_refs: list[str],
    warnings: list[str],
) -> list[str]:
    task_mode = v2_task_mode(data)
    if task_mode == "first_last_frame":
        first = next(
            reference["ref"] for reference in references if reference["use"] == "first_frame"
        )
        last = next(
            reference["ref"] for reference in references if reference["use"] == "last_frame"
        )
        return [first, last]
    if task_mode == "first_frame":
        warnings.append("XYQ_FIRST_FRAME_TYPE_UNVERIFIED")
        return [
            next(
                reference["ref"]
                for reference in references
                if reference["use"] == "first_frame"
            )
        ]
    return list(image_refs)


def render_xyq(
    data: dict[str, Any],
    references: list[dict[str, str]],
    groups: dict[str, list[str]],
    capabilities: object | None,
    warnings: list[str],
) -> tuple[str, dict[str, Any], list[str]]:
    images = xyq_images(data, references, groups["image"], warnings)
    prompt_groups = {**groups, "image": images}
    prompt_text = xyq_prompt(data, prompt_groups)
    params: dict[str, Any] = {
        "prompt": prompt_text,
        "model": exact_model_id(capabilities, warnings),
        "duration": data["duration"]["target_s"],
        "ratio": data["aspect_ratio"],
        "image": images,
        "video": groups["video"],
        "audio": groups["audio"],
    }
    live_params = data.get("live_params", {})
    if "resolution" in live_params:
        params["resolution"] = live_params["resolution"]
    if v2_task_mode(data) == "first_last_frame":
        params["generate_type"] = 1
    notes = [
        "交接 xyq-skill 时逐字传递 prompt，不扩写不翻译；模型枚举以 xyq-skill 与服务端为准",
        XYQ_SOURCE_NOTE,
        tag_map_note({"image": images, "video": groups["video"], "audio": groups["audio"]}),
    ]
    return prompt_text, params, notes


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "Exit codes: 0 rendered; 1 validation failed; 2 ADAPTER_REQUIRES_V2; "
            "3 input, registry, or capabilities file/JSON error."
        ),
    )
    parser.add_argument("command", nargs="?", choices=("compile",))
    parser.add_argument("--target", required=True, choices=target_compiler.TARGETS)
    parser.add_argument("--schema", choices=("auto", "simplified", "nbp_v2", "nbp_v1"))
    parser.add_argument("--today", type=date.fromisoformat)
    parser.add_argument("--allow-expired", action="store_true")
    parser.add_argument("--capabilities-matrix", type=Path)
    parser.add_argument("--type", choices=("image", "video"))
    parser.add_argument("--input", required=True, help="NBP v2 video JSON path")
    parser.add_argument("--capabilities", help="optional live capability receipt JSON path")
    parser.add_argument("--registry", help="optional canonical asset registry JSON path")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    try:
        data = load_json(input_path)
    except Exception as exc:
        emit_error(args.target, [f"INVALID_JSON:{exc}"], args.json_output)
        return 3
    schema = schema_of(data, args.schema or "auto")
    v7_controls = {"route", "draft_id", "draft_job_id", "transport", "requirements", "credit_rates", "budget_cap"}
    live = data.get("live_params") if isinstance(data, dict) else None
    new_compiler = (args.command or args.schema or args.capabilities_matrix or args.today or args.allow_expired or schema == "simplified"
                    or isinstance(live, dict) and v7_controls.intersection(live)
                    or args.target not in {"seedance", "higgsfield", "xyq"})
    if isinstance(data, dict) and data.get("nbp_version") == "1" or schema == "nbp_v1":
        emit_error(args.target, ["ADAPTER_REQUIRES_V2"], args.json_output)
        return 2
    if schema == "invalid":
        emit_error(args.target, ["SCHEMA_MISMATCH"], args.json_output)
        return 1
    kind = args.type or data.get("type") or (data.get("mode") if data.get("mode") in {"image", "video"} else None)
    if not kind:
        video_fields = {"duration", "duration_s", "motion", "audio", "dialogue", "zh", "en", "beats"}
        kind = "video" if video_fields.intersection(data) else "image"
    if schema == "simplified":
        try:
            data = normalize(data, kind)
        except (TypeError, ValueError, ProjectError) as exc:
            emit_error(args.target, [str(exc)], args.json_output)
            return 1
    if not isinstance(data, dict) or data.get("nbp_version") != "2":
        emit_error(args.target, ["ADAPTER_REQUIRES_V2"], args.json_output)
        return 2

    registry = None
    registry_path = None
    if args.registry:
        registry_path = Path(args.registry).expanduser()
        try:
            registry = load_json(registry_path)
        except Exception as exc:
            emit_error(args.target, [f"INVALID_REGISTRY_JSON:{exc}"], args.json_output)
            return 3

    matrix = None
    if new_compiler:
        try:
            matrix = load_json(args.capabilities_matrix or target_compiler.MATRIX)
            ratios = target_compiler.matrix_ratios(matrix, kind) if schema == "simplified" else None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            emit_error(args.target, [f"INVALID_CAPABILITIES_MATRIX:{exc}"], args.json_output)
            return 3
        errors, warnings, _, _ = validate_v2_prompt(data, kind, registry, registry_path, allowed_ratios=ratios)
    else:
        errors, warnings, _, _ = validate_prompt(data, kind, registry, registry_path)
    if errors:
        emit_error(args.target, errors, args.json_output)
        return 1

    capabilities = None
    if args.capabilities:
        capabilities_path = Path(args.capabilities).expanduser()
        try:
            capabilities = load_json(capabilities_path)
        except Exception as exc:
            emit_error(args.target, [f"INVALID_CAPABILITIES_JSON:{exc}"], args.json_output)
            return 3

    if new_compiler:
        try:
            result = target_compiler.compile_ir(data, kind, args.target, adapter_references(data), matrix, warnings,
                                                today=args.today, allow_expired=args.allow_expired)
            if capabilities is not None:
                result["unsupported_requirements"].append("LIVE_RECEIPT_REQUIRES_LEGACY_COMPILER")
                result["ok"] = False
            emit_result({**PLANNING_SCOPE, **result}, args.json_output)
            return int(not result["ok"])
        except (OSError, ValueError, KeyError, TypeError, ProjectError) as exc:
            emit_error(args.target, [f"COMPILATION_ERROR:{exc}"], args.json_output)
            return 1
    capabilities, verified_capabilities = checked_capabilities(capabilities, args.target, warnings)
    task_mode_rules = (
        seedance_task_mode_rules(data, verified_capabilities, warnings)
        if args.target == "seedance" else {}
    )
    warnings.extend(frame_geometry_warnings(data, registry))

    references = adapter_references(data, legacy_roles=True)
    if v2_task_mode(data) in FRAME_TASK_MODES:
        groups = frame_reference_groups(references)
    else:
        groups = reference_groups(references, args.target, warnings)
    capability_errors, capability_warnings, _, scoped_claims = capability_issues(
        data,
        groups,
        capabilities,
        args.target,
        task_mode_rules,
    )
    warnings.extend(capability_warnings)
    if capability_errors:
        emit_error(args.target, capability_errors, args.json_output, warnings)
        return 1
    if args.target == "seedance":
        prompt_text, params, notes = render_seedance(
            data,
            references,
            groups,
            capabilities,
            warnings,
            task_mode_rules,
        )
    elif args.target == "higgsfield":
        prompt_text, params, notes = render_higgsfield(
            data,
            references,
            groups,
            capabilities,
            scoped_capability_claims(verified_capabilities),
            warnings,
        )
    else:
        prompt_text, params, notes = render_xyq(
            data,
            references,
            groups,
            capabilities,
            warnings,
        )

    if "script_ref" in data:
        script_ref = data["script_ref"]
        notes.append(
            f"script_ref: {', '.join(script_ref['source_beats'])} | {script_ref['context']}"
        )

    emit_result(
        {
            **PLANNING_SCOPE,
            "target": args.target,
            "prompt_text": prompt_text,
            "params": params, "parameters": params, "ok": True, "exact_model_id": params.get("model"),
            "ordered_bindings": references, "unsupported_requirements": [],
            "capability_receipt_hash": target_compiler.digest(capabilities) if capabilities else None,
            "warnings": warnings,
            "notes": notes,
        },
        args.json_output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
