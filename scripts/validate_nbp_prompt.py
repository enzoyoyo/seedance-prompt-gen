#!/usr/bin/env python3
"""Validate the simplified Nano Banana Pro prompt interchange format."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from validate_prompt_package import (
    ROLE_TAG_KINDS,
    SHA256_RE,
    canonical_tag_kind,
    extract_tag_tokens,
    validate_package,
)

MASTER_FIELDS = {
    "subject",
    "action",
    "scene",
    "camera",
    "light",
    "style",
    "motion",
    "duration",
    "audio",
    "continuity_ref",
    "negative",
}
IMAGE_FIELDS = MASTER_FIELDS - {"motion", "duration", "audio"}
VIDEO_FIELDS = MASTER_FIELDS
SCALAR_FIELDS = MASTER_FIELDS - {"continuity_ref", "negative"}
CANONICAL_TAG_RE = re.compile(r"^@[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*_v[0-9]+$")
ALLOWED_APPROVAL_STATUSES = {"candidate", "approved", "rejected", "superseded"}
ALLOWED_ASSET_TIERS = {"previs", "take", "final"}

V2_VIDEO_REQUIRED = (
    "characters",
    "scene",
    "action",
    "camera",
    "aspect_ratio",
    "duration",
    "audio",
    "references",
)
V2_IMAGE_REQUIRED = tuple(key for key in V2_VIDEO_REQUIRED if key not in {"duration", "audio"})
V2_OPTIONAL_FIELDS = {
    "task_mode",
    "subject",
    "light",
    "style",
    "motion",
    "negative",
    "continuity",
    "live_params",
    "beats",
    "script_ref",
}
V2_IMAGE_FORBIDDEN = {"duration", "audio", "motion", "beats"}
V2_ASPECT_RATIOS = {"9:16", "16:9", "21:9", "1:1", "4:5", "3:4", "4:3"}
V2_TASK_MODES = {"omni_reference", "first_frame", "first_last_frame", "edit", "extend"}
V2_DEFAULT_TASK_MODE = "omni_reference"
V2_REFERENCE_ROLES = {"character", "prop", "location", "style", "motion", "audio"}
V2_CAMERA_FIELDS = ("shot_size", "angle", "movement", "lens_note")
V2_AUDIO_FIELDS = ("dialogue", "ambience", "music", "sfx")
V2_AUDIO_OPTIONAL_FIELDS = ("dialogue_lang",)
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_RE = re.compile(r"[A-Za-z]")
V2_CONTINUITY_FIELDS = ("story_time_id", "in_state", "out_state", "mode")
V2_BEAT_FIELDS = ("start_s", "end_s", "action", "camera", "say")
V2_SCRIPT_REF_FIELDS = ("source_beats", "context")
# "说话者（语气）：台词" / "Mira (tight): Who opened it?"
DIALOGUE_LINE_RE = re.compile(
    r"^\s*(?P<speaker>[^:：（()）]{1,40}?)\s*"
    r"(?:[（(](?P<tone>[^）)]*)[）)])?\s*[:：]\s*(?P<words>\S.*?)\s*$",
    re.S,
)
OFFSCREEN_SPEAKERS = {"旁白", "画外音", "vo", "v.o.", "os", "o.s.", "narrator"}
OFFSCREEN_TONE_RE = re.compile(
    r"画外|旁白|off-?screen|(?<![A-Za-z])(?:v\.?o|o\.?s)\.?(?![A-Za-z])",
    re.I,
)
LATIN_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
# Heuristic spoken-density ceiling (Han chars, or 1.5 units per Latin word, per
# second). Not a measured model limit; tune it against real takes.
MAX_SPOKEN_UNITS_PER_S = 5.0


def is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_string_array(
    value: object,
    field: str,
    errors: list[str],
) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{field} must be a non-empty string array")
        return []
    if any(not is_nonempty_string(item) for item in value):
        errors.append(f"{field} entries must be non-empty strings")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{field} must not contain duplicates")
    return value


def find_tags(value: object) -> set[str]:
    tags: set[str] = set()
    if isinstance(value, str):
        tags.update(extract_tag_tokens(value))
    elif isinstance(value, list):
        for item in value:
            tags.update(find_tags(item))
    elif isinstance(value, dict):
        for item in value.values():
            tags.update(find_tags(item))
    return tags


def registry_records(
    registry: object,
    registry_path: Path | None,
    errors: list[str],
) -> tuple[str | None, list[dict[str, Any]]]:
    if not isinstance(registry, dict):
        errors.append("registry root must be a JSON object")
        return None, []
    records = registry.get("references")
    registry_kind = "prompt_package"
    if records is not None:
        if registry.get("package_status") != "provider_ready":
            errors.append("prompt-package registry must have package_status provider_ready")
        package_errors, _ = validate_package(registry, registry_path)
        errors.extend(f"prompt-package registry: {message}" for message in package_errors)
    else:
        records = registry.get("assets")
        registry_kind = "asset_manifest"
    if not isinstance(records, list):
        errors.append("registry must contain a references or assets array")
        return None, []
    result: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"registry record {index} must be an object")
        else:
            result.append(record)
    return registry_kind, result


def validate_registry_source(
    record: dict[str, Any],
    index: int,
    registry_kind: str,
    registry_path: Path | None,
    errors: list[str],
) -> None:
    path_key = "source_path" if registry_kind == "prompt_package" else "approved_source_path"
    source_path = record.get(path_key)
    source_sha256 = record.get("source_sha256")
    if not is_nonempty_string(source_path):
        errors.append(f"registry record {index}.{path_key} is required for approved resolution")
        return
    if not is_nonempty_string(source_sha256) or not SHA256_RE.fullmatch(source_sha256):
        errors.append(f"registry record {index}.source_sha256 must be a 64-character hexadecimal digest")
        return
    resolved = Path(source_path).expanduser()
    if not resolved.is_absolute():
        if registry_path is None:
            errors.append(f"registry record {index}.{path_key} cannot be resolved without a registry path")
            return
        resolved = registry_path.parent / resolved
    if not resolved.is_file():
        errors.append(f"registry record {index}.{path_key} does not exist or is not a file: {source_path}")
        return
    actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
    if actual.lower() != source_sha256.lower():
        errors.append(f"registry record {index}.source_sha256 does not match file contents: {source_path}")


def validate_registry_identity(
    record: dict[str, Any],
    index: int,
    registry_kind: str,
    errors: list[str],
) -> None:
    entity_id = record.get("entity_id")
    version = record.get("version")
    role_key = "semantic_role" if registry_kind == "prompt_package" else "asset_kind"
    role = record.get(role_key)
    tag = record.get("canonical_tag")
    if not is_nonempty_string(entity_id):
        errors.append(f"registry record {index}.entity_id is required")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        errors.append(f"registry record {index}.version must be a positive integer")
    elif is_nonempty_string(tag):
        match = re.search(r"_v([0-9]+)$", tag)
        if match and int(match.group(1)) != version:
            errors.append(f"registry record {index}.version does not match canonical_tag suffix")
    if not isinstance(role, str) or role not in ROLE_TAG_KINDS:
        errors.append(f"registry record {index}.{role_key} must be one of {sorted(ROLE_TAG_KINDS)}")
    elif is_nonempty_string(tag) and CANONICAL_TAG_RE.fullmatch(tag):
        kind = canonical_tag_kind(tag)
        if kind not in ROLE_TAG_KINDS[role]:
            errors.append(
                f"registry record {index}.canonical_tag kind {kind!r} is incompatible with "
                f"{role_key} {role!r}; expected {sorted(ROLE_TAG_KINDS[role])}"
            )


def validate_registry_tier(record: dict[str, Any], index: int, errors: list[str]) -> None:
    """Delivery tier is optional; `final` is reserved for approved assets only."""
    if "tier" not in record:
        return
    tier = record.get("tier")
    if not isinstance(tier, str) or tier not in ALLOWED_ASSET_TIERS:
        errors.append(f"registry record {index}.tier must be one of {sorted(ALLOWED_ASSET_TIERS)}")
    elif tier == "final" and record.get("approval_status") != "approved":
        errors.append(f"registry record {index}.tier final requires approval_status approved")


def resolve_registry_tags(
    registry: object,
    registry_path: Path | None,
    detected_tags: set[str],
    errors: list[str],
) -> None:
    by_tag: dict[str, list[dict[str, Any]]] = {}
    registry_kind, records = registry_records(registry, registry_path, errors)
    if registry_kind is None:
        return
    record_indices: dict[int, int] = {}
    for index, record in enumerate(records):
        record_indices[id(record)] = index
        validate_registry_tier(record, index, errors)
        tag = record.get("canonical_tag")
        if not is_nonempty_string(tag) or not CANONICAL_TAG_RE.fullmatch(tag):
            errors.append(f"registry record {index}.canonical_tag must match {CANONICAL_TAG_RE.pattern}")
            continue
        by_tag.setdefault(tag, []).append(record)
        approval = record.get("approval_status")
        if not isinstance(approval, str) or approval not in ALLOWED_APPROVAL_STATUSES:
            errors.append(
                f"registry record {index}.approval_status must be one of {sorted(ALLOWED_APPROVAL_STATUSES)}"
            )
    for tag in sorted(detected_tags):
        matches = by_tag.get(tag, [])
        if len(matches) != 1:
            errors.append(f"canonical tag {tag} must resolve exactly once in registry; found {len(matches)}")
        elif matches[0].get("approval_status") != "approved":
            errors.append(
                f"canonical tag {tag} resolves to {matches[0].get('approval_status')}, expected approved"
            )
        else:
            record = matches[0]
            index = record_indices[id(record)]
            validate_registry_identity(record, index, registry_kind, errors)
            validate_registry_source(record, index, registry_kind, registry_path, errors)


def validate_prompt(
    data: object,
    prompt_type: str,
    registry: object | None = None,
    registry_path: Path | None = None,
) -> tuple[list[str], list[str], set[str], str]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return ["root must be a JSON object"], warnings, set(), "not_applicable"
    if not data:
        errors.append("root prompt object must not be empty")

    allowed = IMAGE_FIELDS if prompt_type == "image" else VIDEO_FIELDS
    unknown = sorted(set(data) - allowed)
    if unknown:
        errors.append(f"unknown fields for {prompt_type}: {unknown}")
    for key, value in data.items():
        if key in SCALAR_FIELDS and not is_nonempty_string(value):
            errors.append(f"{key} must be a non-empty string")

    continuity_refs: list[str] = []
    if "continuity_ref" in data:
        continuity_refs = validate_string_array(data.get("continuity_ref"), "continuity_ref", errors)
        for index, tag in enumerate(continuity_refs):
            if not CANONICAL_TAG_RE.fullmatch(tag):
                errors.append(f"continuity_ref[{index}] must match {CANONICAL_TAG_RE.pattern}")

    if "negative" in data:
        validate_string_array(data.get("negative"), "negative", errors)

    detected_tags = find_tags(data)
    for tag in sorted(detected_tags):
        if not CANONICAL_TAG_RE.fullmatch(tag):
            errors.append(f"malformed canonical tag: {tag}")
    scalar_tags = set()
    for key, value in data.items():
        if key not in {"continuity_ref", "negative"}:
            scalar_tags.update(find_tags(value))
    for tag in sorted(scalar_tags - set(continuity_refs)):
        errors.append(f"canonical tag used outside continuity_ref is not registered there: {tag}")

    if detected_tags and registry is None:
        warnings.append("canonical tag syntax passed, but asset resolution was not checked; provide --registry")
        resolution_status = "syntax_only"
    elif detected_tags:
        resolve_registry_tags(registry, registry_path, detected_tags, errors)
        resolution_status = "resolved" if not errors else "failed"
    else:
        resolution_status = "not_applicable"
    return errors, warnings, detected_tags, resolution_status


validate_v1_prompt = validate_prompt


def find_v2_canonical_tags(value: object) -> set[str]:
    return {tag for tag in find_tags(value) if CANONICAL_TAG_RE.fullmatch(tag)}


def v2_bad_type(errors: list[str], path: str, detail: str) -> None:
    errors.append(f"V2_BAD_TYPE:{path} {detail}")


def v2_unknown_nested_fields(
    value: dict[str, Any],
    allowed: set[str],
    path: str,
    errors: list[str],
) -> None:
    for key in sorted(set(value) - allowed):
        errors.append(f"V2_UNKNOWN:{path}.{key}")


def validate_v2_characters(value: object, errors: list[str], warnings: list[str]) -> set[str]:
    tags: set[str] = set()
    if not isinstance(value, list):
        v2_bad_type(errors, "characters", "must be an array")
        return tags
    if not value:
        warnings.append("NO_CHARACTERS")
        return tags
    expected = {"ref", "name", "state", "wardrobe"}
    seen_names: set[str] = set()
    for index, character in enumerate(value):
        path = f"characters[{index}]"
        if not isinstance(character, dict):
            v2_bad_type(errors, path, "must be an object")
            continue
        v2_unknown_nested_fields(character, expected, path, errors)
        if "name" in character:
            name = character.get("name")
            if not is_nonempty_string(name):
                v2_bad_type(errors, f"{path}.name", "must be a non-empty string")
            elif name.strip().casefold() in seen_names:
                errors.append(f"V2_DUPLICATE_NAME:{name.strip()}")
            else:
                seen_names.add(name.strip().casefold())
        ref = character.get("ref")
        if not isinstance(ref, str):
            v2_bad_type(errors, f"{path}.ref", "must be a string")
        elif not CANONICAL_TAG_RE.fullmatch(ref):
            errors.append(f"V2_BAD_TAG:{path}.ref")
        else:
            tags.add(ref)
        for key in ("state", "wardrobe"):
            if not is_nonempty_string(character.get(key)):
                v2_bad_type(errors, f"{path}.{key}", "must be a non-empty string")
    return tags


def validate_v2_camera(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        v2_bad_type(errors, "camera", "must be an object")
        return
    v2_unknown_nested_fields(value, set(V2_CAMERA_FIELDS), "camera", errors)
    for key in V2_CAMERA_FIELDS:
        if not is_nonempty_string(value.get(key)):
            v2_bad_type(errors, f"camera.{key}", "must be a non-empty string")


def validate_v2_duration(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        v2_bad_type(errors, "duration", "must be an object")
        return
    v2_unknown_nested_fields(value, {"target_s", "live_check"}, "duration", errors)
    target = value.get("target_s")
    if (
        isinstance(target, bool)
        or not isinstance(target, (int, float))
        or (isinstance(target, float) and not math.isfinite(target))
        or target <= 0
    ):
        v2_bad_type(errors, "duration.target_s", "must be a positive number")
    if not is_nonempty_string(value.get("live_check")):
        errors.append("V2_DURATION_NO_LIVE_CHECK")


def dialogue_scripts(lines: list[str]) -> set[str]:
    """A non-empty dialogue line carries the spoken language; report which scripts it uses."""
    scripts: set[str] = set()
    for line in lines:
        # Drop the speaker prefix and the parenthetical delivery note; only the
        # spoken words decide the language.
        spoken = re.sub(r"[（(][^）)]*[）)]", "", re.sub(r"^[^:：]{0,40}[:：]", "", line))
        if HAN_RE.search(spoken):
            scripts.add("han")
        if LATIN_RE.search(spoken):
            scripts.add("latin")
    return scripts


def validate_v2_audio(value: object, errors: list[str], warnings: list[str]) -> None:
    if not isinstance(value, dict):
        v2_bad_type(errors, "audio", "must be an object")
        return
    allowed = set(V2_AUDIO_FIELDS) | set(V2_AUDIO_OPTIONAL_FIELDS)
    v2_unknown_nested_fields(value, allowed, "audio", errors)
    dialogue = value.get("dialogue")
    if not isinstance(dialogue, list) or any(not isinstance(item, str) for item in dialogue):
        v2_bad_type(errors, "audio.dialogue", "must be an array of strings")
        dialogue = []
    language = value.get("dialogue_lang")
    if "dialogue_lang" in value and not is_nonempty_string(language):
        v2_bad_type(errors, "audio.dialogue_lang", "must be a non-empty string")
    elif dialogue and not is_nonempty_string(language) and len(dialogue_scripts(dialogue)) != 1:
        warnings.append("DIALOGUE_LANG_UNSET")
    for key in ("ambience", "music", "sfx"):
        if not isinstance(value.get(key), str):
            v2_bad_type(errors, f"audio.{key}", "must be a string")


def validate_v2_references(value: object, errors: list[str]) -> set[str]:
    tags: set[str] = set()
    if not isinstance(value, list):
        v2_bad_type(errors, "references", "must be an array")
        return tags
    expected = {"ref", "role", "use"}
    for index, reference in enumerate(value):
        path = f"references[{index}]"
        if not isinstance(reference, dict):
            v2_bad_type(errors, path, "must be an object")
            continue
        v2_unknown_nested_fields(reference, expected, path, errors)
        ref = reference.get("ref")
        if not isinstance(ref, str):
            v2_bad_type(errors, f"{path}.ref", "must be a string")
        elif not CANONICAL_TAG_RE.fullmatch(ref):
            errors.append(f"V2_BAD_TAG:{path}.ref")
        else:
            tags.add(ref)
        role = reference.get("role")
        role_is_missing = (
            "role" not in reference
            or role is None
            or (isinstance(role, str) and not role.strip())
        )
        role_value = "missing" if role_is_missing else role
        if not isinstance(role, str) or role not in V2_REFERENCE_ROLES:
            errors.append(f"V2_BAD_ROLE:{path}.role:{role_value}")
        if not is_nonempty_string(reference.get("use")):
            v2_bad_type(errors, f"{path}.use", "must be a non-empty string")
    return tags


def v2_task_mode(data: dict[str, Any]) -> object:
    return data.get("task_mode", V2_DEFAULT_TASK_MODE)


def validate_v2_task_mode(data: dict[str, Any], errors: list[str]) -> None:
    task_mode = v2_task_mode(data)
    if not isinstance(task_mode, str) or task_mode not in V2_TASK_MODES:
        errors.append(f"V2_BAD_MODE:{task_mode}")
        return
    references = data.get("references")
    if not isinstance(references, list):
        return
    reference_items = [
        (index, reference)
        for index, reference in enumerate(references)
        if isinstance(reference, dict)
    ]
    first_frames = [
        index for index, reference in reference_items if reference.get("use") == "first_frame"
    ]
    last_frames = [
        index for index, reference in reference_items if reference.get("use") == "last_frame"
    ]
    frame_uses = {"first_frame", "last_frame"}

    if task_mode == "omni_reference":
        for index, reference in reference_items:
            if reference.get("use") in frame_uses:
                errors.append(f"V2_MODE_CONFLICT:frame_use_in_omni=references[{index}]")
        return

    if task_mode in {"first_frame", "first_last_frame"}:
        if len(first_frames) != 1:
            errors.append(f"V2_MODE_CONFLICT:first_frame_count={len(first_frames)}")
        expected_last_frames = 1 if task_mode == "first_last_frame" else 0
        if len(last_frames) != expected_last_frames:
            errors.append(f"V2_MODE_CONFLICT:last_frame_count={len(last_frames)}")
        for index, reference in reference_items:
            if reference.get("use") not in frame_uses:
                errors.append(f"V2_MODE_CONFLICT:non_frame_reference=references[{index}]")
        return

    if not any(reference.get("role") == "motion" for _, reference in reference_items):
        errors.append(f"V2_MODE_CONFLICT:{task_mode}_requires_motion")
    for index, reference in reference_items:
        if reference.get("role") != "motion":
            errors.append(f"V2_MODE_CONFLICT:non_motion_reference=references[{index}]")


def validate_v2_continuity(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        v2_bad_type(errors, "continuity", "must be an object")
        return
    v2_unknown_nested_fields(value, set(V2_CONTINUITY_FIELDS), "continuity", errors)
    for key in ("story_time_id", "in_state", "out_state"):
        if not is_nonempty_string(value.get(key)):
            v2_bad_type(errors, f"continuity.{key}", "must be a non-empty string")
    mode = value.get("mode")
    if not isinstance(mode, str) or mode not in {"sparse", "tracked"}:
        v2_bad_type(errors, "continuity.mode", "must be sparse or tracked")


def parse_dialogue_line(line: str) -> tuple[str, str, str] | None:
    """Split "说话者（语气）：台词" into (speaker, tone, words); None if unattributed."""
    match = DIALOGUE_LINE_RE.match(line)
    if not match:
        return None
    return match.group("speaker").strip(), (match.group("tone") or "").strip(), match.group("words")


def is_offscreen_speaker(speaker: str, tone: str) -> bool:
    return speaker.casefold() in OFFSCREEN_SPEAKERS or bool(OFFSCREEN_TONE_RE.search(tone))


def spoken_units(line: str) -> float:
    parsed = parse_dialogue_line(line)
    words = parsed[2] if parsed else line
    words = re.sub(r"[（(][^）)]*[）)]", "", words)
    return len(HAN_RE.findall(words)) + 1.5 * len(LATIN_WORD_RE.findall(words))


def is_finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def v2_dialogue(data: dict[str, Any]) -> list[str] | None:
    audio = data.get("audio")
    if not isinstance(audio, dict):
        return None
    dialogue = audio.get("dialogue")
    if not isinstance(dialogue, list) or any(not isinstance(item, str) for item in dialogue):
        return None
    return dialogue


def v2_target_seconds(data: dict[str, Any]) -> float | None:
    duration = data.get("duration")
    target = duration.get("target_s") if isinstance(duration, dict) else None
    return target if is_finite_number(target) and target > 0 else None


def unbound_speakers(data: dict[str, Any], dialogue: list[str], warnings: list[str]) -> list[str]:
    """Every spoken line should name an on-screen character or be marked off-screen."""
    characters = data.get("characters")
    names = {
        character["name"].strip().casefold()
        for character in (characters if isinstance(characters, list) else [])
        if isinstance(character, dict) and is_nonempty_string(character.get("name"))
    }
    unbound: list[str] = []
    for index, line in enumerate(dialogue):
        parsed = parse_dialogue_line(line)
        if parsed is None:
            warnings.append(f"DIALOGUE_SPEAKER_MISSING:audio.dialogue[{index}]")
            continue
        speaker, tone, _ = parsed
        if is_offscreen_speaker(speaker, tone) or speaker.casefold() in names:
            continue
        if speaker not in unbound:
            unbound.append(speaker)
    return unbound


def validate_v2_speakers(data: dict[str, Any], warnings: list[str]) -> None:
    speakers = unbound_speakers(data, v2_dialogue(data) or [], warnings)
    warnings.extend(f"DIALOGUE_SPEAKER_UNBOUND:{speaker}" for speaker in speakers)


def validate_v2_beats(data: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    beats = data.get("beats")
    if not isinstance(beats, list) or not beats:
        v2_bad_type(errors, "beats", "must be a non-empty array")
        return
    says: list[str] = []
    previous_end = 0.0
    last_end: float | None = None
    for index, beat in enumerate(beats):
        path = f"beats[{index}]"
        if not isinstance(beat, dict):
            v2_bad_type(errors, path, "must be an object")
            continue
        v2_unknown_nested_fields(beat, set(V2_BEAT_FIELDS), path, errors)
        start, end = beat.get("start_s"), beat.get("end_s")
        timed = is_finite_number(start) and is_finite_number(end)
        if not timed:
            v2_bad_type(errors, path, "start_s and end_s must be numbers")
        elif start < previous_end or end <= start:
            errors.append(f"V2_BEAT_TIME:{path}")
        else:
            previous_end = last_end = end
        if not is_nonempty_string(beat.get("action")):
            v2_bad_type(errors, f"{path}.action", "must be a non-empty string")
        for key in ("camera", "say"):
            if key in beat and not is_nonempty_string(beat.get(key)):
                v2_bad_type(errors, f"{path}.{key}", "must be a non-empty string")
        say = beat.get("say")
        if is_nonempty_string(say):
            says.append(say.strip())
            if timed and end > start and spoken_units(say) / (end - start) > MAX_SPOKEN_UNITS_PER_S:
                warnings.append(f"DIALOGUE_TOO_DENSE:{path}")
    target = v2_target_seconds(data)
    if target is not None and last_end is not None and last_end > target:
        errors.append(f"V2_BEAT_TIME:beats[{len(beats) - 1}].end_s>duration.target_s")
    dialogue = v2_dialogue(data)
    if dialogue is not None and says != [line.strip() for line in dialogue]:
        errors.append("V2_BEAT_DIALOGUE_MISMATCH:beats[].say must equal audio.dialogue in order")


def validate_v2_script_ref(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        v2_bad_type(errors, "script_ref", "must be an object")
        return
    v2_unknown_nested_fields(value, set(V2_SCRIPT_REF_FIELDS), "script_ref", errors)
    source_beats = value.get("source_beats")
    if (
        not isinstance(source_beats, list)
        or not source_beats
        or any(not is_nonempty_string(item) for item in source_beats)
    ):
        v2_bad_type(errors, "script_ref.source_beats", "must be a non-empty array of non-empty strings")
    if not is_nonempty_string(value.get("context")):
        v2_bad_type(errors, "script_ref.context", "must be a non-empty string")


def validate_v2_prompt(
    data: dict[str, Any],
    prompt_type: str,
    registry: object | None = None,
    registry_path: Path | None = None,
    *,
    allowed_ratios: set[str] | None = None,
) -> tuple[list[str], list[str], set[str], str]:
    errors: list[str] = []
    warnings: list[str] = []
    required = V2_IMAGE_REQUIRED if prompt_type == "image" else V2_VIDEO_REQUIRED
    allowed = {"nbp_version", *required, *V2_OPTIONAL_FIELDS}
    forbidden = V2_IMAGE_FORBIDDEN if prompt_type == "image" else set()

    for key in required:
        if key not in data:
            errors.append(f"V2_MISSING:{key}")
    for key in sorted(set(data) - allowed - forbidden):
        errors.append(f"V2_UNKNOWN:{key}")
    for key in sorted(set(data) & forbidden):
        errors.append(f"V2_IMAGE_FORBIDDEN:{key}")

    detected_tags: set[str] = set()
    if "characters" in data:
        detected_tags.update(validate_v2_characters(data.get("characters"), errors, warnings))
    for key in ("scene", "action"):
        if key in data and not is_nonempty_string(data.get(key)):
            v2_bad_type(errors, key, "must be a non-empty string")
    if "camera" in data:
        validate_v2_camera(data.get("camera"), errors)
    if "aspect_ratio" in data:
        ratio = data.get("aspect_ratio")
        if not isinstance(ratio, str):
            v2_bad_type(errors, "aspect_ratio", "must be a string")
        elif ratio not in (V2_ASPECT_RATIOS if allowed_ratios is None else allowed_ratios):
            errors.append(f"V2_BAD_RATIO:{ratio}")
    if prompt_type == "video" and "duration" in data:
        validate_v2_duration(data.get("duration"), errors)
    if prompt_type == "video" and "audio" in data:
        validate_v2_audio(data.get("audio"), errors, warnings)
    if "references" in data:
        detected_tags.update(validate_v2_references(data.get("references"), errors))
    validate_v2_task_mode(data, errors)

    for key in ("subject", "light", "style", "motion"):
        if key in data and key not in forbidden and not is_nonempty_string(data.get(key)):
            v2_bad_type(errors, key, "must be a non-empty string")
    if "negative" in data:
        negative = data.get("negative")
        if not isinstance(negative, list) or any(not is_nonempty_string(item) for item in negative):
            v2_bad_type(errors, "negative", "must be an array of non-empty strings")
    if "continuity" in data:
        validate_v2_continuity(data.get("continuity"), errors)
    if "live_params" in data and not isinstance(data.get("live_params"), dict):
        v2_bad_type(errors, "live_params", "must be an object")
    if "script_ref" in data:
        validate_v2_script_ref(data.get("script_ref"), errors)
    if prompt_type == "video":
        validate_v2_speakers(data, warnings)
        if "beats" in data:
            validate_v2_beats(data, errors, warnings)
        else:
            dialogue = v2_dialogue(data) or []
            target = v2_target_seconds(data)
            units = sum(spoken_units(line) for line in dialogue)
            if target is not None and units / target > MAX_SPOKEN_UNITS_PER_S:
                warnings.append("DIALOGUE_TOO_DENSE:audio.dialogue")

    detected_tags.update(find_v2_canonical_tags(data))
    if detected_tags and registry is None:
        warnings.append("canonical tag syntax passed, but asset resolution was not checked; provide --registry")
        resolution_status = "syntax_only"
    elif detected_tags:
        resolve_registry_tags(registry, registry_path, detected_tags, errors)
        resolution_status = "resolved" if not errors else "failed"
    else:
        resolution_status = "not_applicable"
    return errors, warnings, detected_tags, resolution_status


def validate_prompt(
    data: object,
    prompt_type: str,
    registry: object | None = None,
    registry_path: Path | None = None,
) -> tuple[list[str], list[str], set[str], str]:
    if isinstance(data, dict) and data.get("nbp_version") == "2":
        return validate_v2_prompt(data, prompt_type, registry, registry_path)
    if isinstance(data, dict) and data.get("nbp_version") == "1":
        v1_data = dict(data)
        v1_data.pop("nbp_version")
        return validate_v1_prompt(v1_data, prompt_type, registry, registry_path)
    return validate_v1_prompt(data, prompt_type, registry, registry_path)


def report_nbp_version(data: object) -> object:
    if not isinstance(data, dict):
        return None
    return data.get("nbp_version", "1")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", required=True, choices=("image", "video"), dest="prompt_type")
    parser.add_argument("--schema", choices=("auto", "simplified", "nbp_v2", "nbp_v1"), default="auto")
    parser.add_argument("--input", required=True, help="NBP JSON path")
    parser.add_argument(
        "--registry",
        help="optional prompt-package or asset-manifest JSON used to resolve canonical tags",
    )
    args = parser.parse_args()
    input_path = Path(args.input).expanduser()
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "input": str(input_path),
                    "prompt_type": args.prompt_type,
                    "nbp_version": None,
                    "tag_resolution": {"status": "not_applicable", "detected": 0},
                    "warnings": [],
                    "errors": [f"invalid JSON: {exc}"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    registry_data = None
    registry_path = None
    if args.registry:
        registry_path = Path(args.registry).expanduser()
        try:
            registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "input": str(input_path),
                        "prompt_type": args.prompt_type,
                        "nbp_version": report_nbp_version(data),
                        "tag_resolution": {
                            "status": "failed",
                            "detected": 0,
                            "registry": str(registry_path),
                        },
                        "warnings": [],
                        "errors": [f"invalid registry JSON: {exc}"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 2

    from drama_project import ProjectError
    from simplified_prompt import normalize, schema_of
    schema = schema_of(data, args.schema)
    try:
        if schema == "invalid":
            raise ProjectError("SCHEMA_MISMATCH")
        if schema == "simplified":
            from target_compiler import MATRIX, matrix_ratios, validate_named_model
            data = normalize(data, args.prompt_type)
            matrix = json.loads(MATRIX.read_text()) if MATRIX.is_file() else None
            ratios = matrix_ratios(matrix, args.prompt_type) if matrix else None
            errors, warnings, tags, resolution_status = validate_v2_prompt(
                data, args.prompt_type, registry_data, registry_path, allowed_ratios=ratios)
            if matrix and not errors and data["live_params"].get("model"):
                errors.extend(validate_named_model(data, args.prompt_type, matrix))
        else:
            errors, warnings, tags, resolution_status = validate_prompt(data, args.prompt_type, registry_data, registry_path)
    except (ProjectError, TypeError, ValueError) as exc:
        errors, warnings, tags, resolution_status = [str(exc)], [], set(), "failed"
    resolution: dict[str, Any] = {"status": resolution_status, "detected": len(tags)}
    if registry_path is not None:
        resolution["registry"] = str(registry_path)
    print(
        json.dumps(
            {
                "ok": not errors,
                "schema": schema,
                "input": str(input_path),
                "prompt_type": args.prompt_type,
                "nbp_version": report_nbp_version(data),
                "tag_resolution": resolution,
                "warnings": warnings,
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
