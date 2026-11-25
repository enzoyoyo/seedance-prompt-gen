#!/usr/bin/env python3
"""Validate a Seedance prompt package without provider calls.

This proves the declared planning/provider-ready gate, canonical asset
resolution, the explicitly selected continuity mode, in-shot state changes,
and adjacent shot handoffs. It does not semantically interpret free-form
prompt prose and does not claim that generated pixels passed QC.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ALLOWED_CLASSES = {
    "single-shot",
    "multi-shot",
    "product-ad",
    "short-drama",
    "source-vfx",
    "finished-video",
    "faceless-batch",
}
ALLOWED_CONTINUITY_MODES = {"sparse", "tracked"}
ALLOWED_PACKAGE_STATUSES = {"planning", "provider_ready"}
ALLOWED_APPROVAL_STATUSES = {"candidate", "approved", "rejected", "superseded"}
ALLOWED_ROLES = {
    "character",
    "wardrobe",
    "product",
    "prop",
    "location",
    "style",
    "motion",
    "first-frame",
    "end-frame",
    "audio",
    "ui",
    "source-video",
    "brand-kit",
}
ALLOWED_FACING = {"north", "south", "east", "west", "camera", "away"}
ALLOWED_SCREEN_DIRECTIONS = {"left", "right", "center", "offscreen"}
ALLOWED_HANDS = {"left", "right", "both", "none", "inside", "attached", "environment"}
ALLOWED_AXIS_SIDES = {"left", "right", "on_axis"}
ALLOWED_AXIS_TRANSITIONS = {"none", "visible_cross", "neutral_reset", "along_axis", "new_axis"}
FORBIDDEN_SKILL = "unregistered-external-skill"
CANONICAL_TAG_RE = re.compile(r"^@[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*_v[0-9]+$")
ASCII_TAG_BODY_RE = re.compile(r"[A-Za-z0-9_-]+")
FALLBACK_TAG_TOKEN_RE = re.compile(r"@[^\s,;:.!?，。；：！？、()（）\[\]【】{}\"'‘’“”<>《》]+")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
ROLE_TAG_KINDS = {
    "character": {"char"},
    "wardrobe": {"outfit", "wardrobe"},
    "product": {"product"},
    "prop": {"prop"},
    "location": {"location"},
    "style": {"style"},
    "motion": {"motion"},
    "first-frame": {"frame"},
    "end-frame": {"frame"},
    "audio": {"audio"},
    "ui": {"ui"},
    "source-video": {"video"},
    "brand-kit": {"brand"},
}
MISSING = object()


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def warn(warnings: list[str], message: str) -> None:
    warnings.append(message)


def is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def canonical_tag_kind(tag: str) -> str | None:
    match = re.match(r"^@([A-Za-z][A-Za-z0-9]*)_", tag)
    return match.group(1) if match else None


def extract_tag_tokens(text: str) -> list[str]:
    """Read only the ASCII canonical-tag alphabet after @.

    This stops a valid tag before adjacent Chinese text or Unicode punctuation,
    while still returning a non-ASCII @ token as malformed instead of silently
    ignoring it.
    """
    tokens: list[str] = []
    for marker in re.finditer(r"@", text):
        body = ASCII_TAG_BODY_RE.match(text, marker.end())
        if body:
            tokens.append("@" + body.group(0))
            continue
        fallback = FALLBACK_TAG_TOKEN_RE.match(text, marker.start())
        tokens.append(fallback.group(0) if fallback else "@")
    return tokens


def validate_string_list(
    value: object,
    field: str,
    errors: list[str],
    *,
    allow_empty: bool,
) -> list[str]:
    if not isinstance(value, list):
        fail(errors, f"{field} must be an array")
        return []
    if not allow_empty and not value:
        fail(errors, f"{field} must not be empty")
    if any(not is_nonempty_string(item) for item in value):
        fail(errors, f"{field} entries must be non-empty strings")
        return []
    if len(value) != len(set(value)):
        fail(errors, f"{field} must not contain duplicates")
    return value


def validate_coord(value: object, field: str, errors: list[str], *, dimensions: tuple[int, ...] = (2, 3)) -> bool:
    if not isinstance(value, list) or len(value) not in dimensions:
        allowed = " or ".join(str(item) for item in dimensions)
        fail(errors, f"{field} must contain {allowed} finite coordinates")
        return False
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        for item in value
    ):
        fail(errors, f"{field} must contain only finite numbers")
        return False
    return True


def resolve_source_path(source_path: str, input_path: Path | None) -> Path | None:
    candidate = Path(source_path).expanduser()
    if candidate.is_absolute():
        return candidate
    if input_path is None:
        return None
    return input_path.parent / candidate


def validate_source(
    ref: dict[str, Any],
    field: str,
    input_path: Path | None,
    errors: list[str],
) -> None:
    source_path = ref.get("source_path")
    source_sha256 = ref.get("source_sha256")
    if not is_nonempty_string(source_path):
        fail(errors, f"{field}.source_path is required in provider_ready packages")
        return
    if not is_nonempty_string(source_sha256) or not SHA256_RE.fullmatch(source_sha256):
        fail(errors, f"{field}.source_sha256 must be a 64-character hexadecimal digest")
        return
    resolved = resolve_source_path(source_path, input_path)
    if resolved is None:
        fail(errors, f"{field}.source_path cannot be resolved without an input file path")
        return
    if not resolved.is_file():
        fail(errors, f"{field}.source_path does not exist or is not a file: {source_path}")
        return
    actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
    if actual.lower() != source_sha256.lower():
        fail(errors, f"{field}.source_sha256 does not match file contents: {source_path}")


def validate_references(
    refs: object,
    package_status: object,
    input_path: Path | None,
    errors: list[str],
    warnings: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(refs, list):
        fail(errors, "references must be an array")
        return {}

    refs_by_tag: dict[str, dict[str, Any]] = {}
    seen_versions: set[tuple[str, int]] = set()
    seen_ready_entities: set[tuple[str, str]] = set()
    for index, ref in enumerate(refs):
        field = f"references[{index}]"
        if not isinstance(ref, dict):
            fail(errors, f"{field} must be an object")
            continue

        asset_id = ref.get("canonical_asset_id")
        entity_id = ref.get("entity_id")
        tag = ref.get("canonical_tag")
        version = ref.get("version")
        role = ref.get("semantic_role")
        approval = ref.get("approval_status")
        duties = ref.get("responsibilities")

        if not is_nonempty_string(asset_id):
            fail(errors, f"{field}.canonical_asset_id is required")
        if not is_nonempty_string(entity_id):
            fail(errors, f"{field}.entity_id is required")
        if not is_nonempty_string(tag) or not CANONICAL_TAG_RE.fullmatch(tag):
            fail(errors, f"{field}.canonical_tag must match {CANONICAL_TAG_RE.pattern}")
        elif tag in refs_by_tag:
            fail(errors, f"duplicate canonical_tag: {tag}")
        else:
            refs_by_tag[tag] = ref
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            fail(errors, f"{field}.version must be a positive integer")
        elif is_nonempty_string(asset_id):
            version_key = (asset_id, version)
            if version_key in seen_versions:
                fail(errors, f"duplicate canonical asset version: {asset_id} v{version}")
            seen_versions.add(version_key)
            if is_nonempty_string(tag):
                match = re.search(r"_v([0-9]+)$", tag)
                if match and int(match.group(1)) != version:
                    fail(errors, f"{field}.version does not match canonical_tag suffix")
        if not isinstance(role, str) or role not in ALLOWED_ROLES:
            fail(errors, f"{field}.semantic_role must be one of {sorted(ALLOWED_ROLES)}")
        elif is_nonempty_string(tag) and CANONICAL_TAG_RE.fullmatch(tag):
            kind = canonical_tag_kind(tag)
            if kind not in ROLE_TAG_KINDS[role]:
                fail(
                    errors,
                    f"{field}.canonical_tag kind {kind!r} is incompatible with semantic_role {role!r}; "
                    f"expected {sorted(ROLE_TAG_KINDS[role])}",
                )
        if role == "wardrobe" and not is_nonempty_string(ref.get("subject_id")):
            fail(errors, f"{field}.subject_id is required for wardrobe references")
        if not isinstance(approval, str) or approval not in ALLOWED_APPROVAL_STATUSES:
            fail(errors, f"{field}.approval_status must be one of {sorted(ALLOWED_APPROVAL_STATUSES)}")
        elif package_status == "provider_ready" and approval != "approved":
            fail(errors, f"{field}.approval_status must be approved in provider_ready packages; got {approval}")
        elif package_status == "planning" and approval == "candidate":
            warn(warnings, f"{field} is candidate; package cannot enter a provider adapter")
        elif package_status == "planning" and approval in {"rejected", "superseded"}:
            fail(errors, f"{field} cites an inactive asset: {approval}")

        if not isinstance(duties, list) or not duties:
            fail(errors, f"{field}.responsibilities must be a non-empty string array")
        elif any(not is_nonempty_string(duty) for duty in duties):
            fail(errors, f"{field}.responsibilities entries must be non-empty strings")
        elif len(duties) != len(set(duties)):
            fail(errors, f"{field}.responsibilities must not contain duplicates")

        if package_status == "provider_ready":
            if isinstance(role, str) and role in ALLOWED_ROLES and is_nonempty_string(entity_id):
                entity_key = (role, entity_id)
                if entity_key in seen_ready_entities:
                    fail(errors, f"provider_ready package has more than one active {role} version for entity {entity_id}")
                seen_ready_entities.add(entity_key)
            validate_source(ref, field, input_path, errors)
        else:
            source_path = ref.get("source_path")
            source_sha256 = ref.get("source_sha256")
            if source_path is not None and not is_nonempty_string(source_path):
                fail(errors, f"{field}.source_path must be null or a non-empty string")
            if source_sha256 is not None and (
                not is_nonempty_string(source_sha256) or not SHA256_RE.fullmatch(source_sha256)
            ):
                fail(errors, f"{field}.source_sha256 must be null or a 64-character hexadecimal digest")
    return refs_by_tag


def resolve_tag(
    tag: object,
    field: str,
    refs_by_tag: dict[str, dict[str, Any]],
    errors: list[str],
    expected_roles: set[str],
    *,
    entity_id: str | None = None,
    subject_id: str | None = None,
) -> dict[str, Any] | None:
    if not is_nonempty_string(tag) or not CANONICAL_TAG_RE.fullmatch(tag):
        fail(errors, f"{field} must be a canonical tag matching {CANONICAL_TAG_RE.pattern}")
        return None
    ref = refs_by_tag.get(tag)
    if ref is None:
        fail(errors, f"{field} does not resolve to references: {tag}")
        return None
    ref_role = ref.get("semantic_role")
    if not isinstance(ref_role, str) or ref_role not in expected_roles:
        fail(errors, f"{field} resolves to role {ref_role}, expected {sorted(expected_roles)}")
    if entity_id is not None and ref.get("entity_id") != entity_id:
        fail(errors, f"{field} resolves to entity {ref.get('entity_id')}, expected {entity_id}")
    if subject_id is not None and ref.get("subject_id") != subject_id:
        fail(errors, f"{field} resolves to subject {ref.get('subject_id')}, expected {subject_id}")
    return ref


def validate_continuity_rules(
    value: object,
    refs_by_tag: dict[str, dict[str, Any]],
    errors: list[str],
    *,
    require_full: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "characters": {},
        "tracked_props": {},
        "scene_variants": {},
        "scene_transitions": set(),
        "axes": {},
    }
    if not isinstance(value, dict):
        fail(errors, "continuity_rules must be an object")
        return result
    allowed = {"characters", "tracked_props", "scene_variants", "scene_transitions", "axes"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        fail(errors, f"continuity_rules has unknown fields: {unknown}")

    characters = value.get("characters", MISSING)
    if characters is MISSING:
        if require_full:
            fail(errors, "continuity_rules.characters must be an array")
        characters = []
    elif not isinstance(characters, list):
        fail(errors, "continuity_rules.characters must be an array")
        characters = []
    for index, character in enumerate(characters):
        field = f"continuity_rules.characters[{index}]"
        if not isinstance(character, dict):
            fail(errors, f"{field} must be an object")
            continue
        if set(character) - {"id", "asset_versions", "wardrobe_variants"}:
            fail(errors, f"{field} has unknown fields: {sorted(set(character) - {'id', 'asset_versions', 'wardrobe_variants'})}")
        char_id = character.get("id")
        if not is_nonempty_string(char_id):
            fail(errors, f"{field}.id is required")
            continue
        if char_id in result["characters"]:
            fail(errors, f"duplicate continuity character id: {char_id}")
        asset_versions = validate_string_list(
            character.get("asset_versions"), f"{field}.asset_versions", errors, allow_empty=False
        )
        wardrobe_variants = validate_string_list(
            character.get("wardrobe_variants"), f"{field}.wardrobe_variants", errors, allow_empty=False
        )
        for tag in asset_versions:
            resolve_tag(tag, f"{field}.asset_versions", refs_by_tag, errors, {"character"}, entity_id=char_id)
        for tag in wardrobe_variants:
            resolve_tag(tag, f"{field}.wardrobe_variants", refs_by_tag, errors, {"wardrobe"}, subject_id=char_id)
        result["characters"][char_id] = {
            "asset_versions": set(asset_versions),
            "wardrobe_variants": set(wardrobe_variants),
        }

    tracked_props = value.get("tracked_props", MISSING)
    if tracked_props is MISSING:
        if require_full:
            fail(errors, "continuity_rules.tracked_props must be an array")
        tracked_props = []
    elif not isinstance(tracked_props, list):
        fail(errors, "continuity_rules.tracked_props must be an array")
        tracked_props = []
    for index, prop in enumerate(tracked_props):
        field = f"continuity_rules.tracked_props[{index}]"
        if not isinstance(prop, dict):
            fail(errors, f"{field} must be an object")
            continue
        allowed_prop = {"id", "asset_versions", "allowed_configurations"}
        if set(prop) - allowed_prop:
            fail(errors, f"{field} has unknown fields: {sorted(set(prop) - allowed_prop)}")
        prop_id = prop.get("id")
        if not is_nonempty_string(prop_id):
            fail(errors, f"{field}.id is required")
            continue
        if prop_id in result["tracked_props"]:
            fail(errors, f"duplicate tracked prop id: {prop_id}")
        asset_versions = validate_string_list(
            prop.get("asset_versions"), f"{field}.asset_versions", errors, allow_empty=False
        )
        for tag in asset_versions:
            resolve_tag(tag, f"{field}.asset_versions", refs_by_tag, errors, {"prop", "product"}, entity_id=prop_id)
        configurations = prop.get("allowed_configurations")
        allowed_configurations: set[tuple[str, str, str, str]] = set()
        if not isinstance(configurations, list) or not configurations:
            fail(errors, f"{field}.allowed_configurations must be a non-empty array")
            configurations = []
        for config_index, configuration in enumerate(configurations):
            config_field = f"{field}.allowed_configurations[{config_index}]"
            required_config = {"asset_version", "owner", "hand", "state"}
            if not isinstance(configuration, dict) or set(configuration) != required_config:
                fail(errors, f"{config_field} must contain exactly {sorted(required_config)}")
                continue
            config_asset = configuration.get("asset_version")
            owner = configuration.get("owner")
            hand = configuration.get("hand")
            state = configuration.get("state")
            if config_asset not in asset_versions:
                fail(errors, f"{config_field}.asset_version must be listed in {field}.asset_versions")
            if not is_nonempty_string(owner):
                fail(errors, f"{config_field}.owner is required")
            if not isinstance(hand, str) or hand not in ALLOWED_HANDS:
                fail(errors, f"{config_field}.hand must be one of {sorted(ALLOWED_HANDS)}")
            if not is_nonempty_string(state):
                fail(errors, f"{config_field}.state is required")
            if (
                is_nonempty_string(config_asset)
                and is_nonempty_string(owner)
                and isinstance(hand, str)
                and hand in ALLOWED_HANDS
                and is_nonempty_string(state)
            ):
                normalized = (config_asset, owner, hand, state)
                if normalized in allowed_configurations:
                    fail(errors, f"{field}.allowed_configurations has duplicate configuration: {normalized}")
                allowed_configurations.add(normalized)
        result["tracked_props"][prop_id] = {
            "asset_versions": set(asset_versions),
            "allowed_configurations": allowed_configurations,
        }

    known_owners = set(result["characters"]) | set(result["tracked_props"]) | {"environment"}
    for prop_id, prop_rule in result["tracked_props"].items():
        for _, owner, _, _ in prop_rule["allowed_configurations"]:
            if owner not in known_owners:
                fail(errors, f"tracked prop {prop_id} has unknown allowed owner: {owner}")

    scene_variants = value.get("scene_variants", MISSING)
    if scene_variants is MISSING:
        if require_full:
            fail(errors, "continuity_rules.scene_variants must contain at least one scene variant")
        scene_variants = []
    elif not isinstance(scene_variants, list) or (require_full and not scene_variants):
        fail(errors, "continuity_rules.scene_variants must contain at least one scene variant")
        scene_variants = []
    for index, scene in enumerate(scene_variants):
        field = f"continuity_rules.scene_variants[{index}]"
        if not isinstance(scene, dict) or set(scene) != {"scene_variant", "allowed_light_profiles"}:
            fail(errors, f"{field} must contain exactly scene_variant and allowed_light_profiles")
            continue
        scene_tag = scene.get("scene_variant")
        resolve_tag(scene_tag, f"{field}.scene_variant", refs_by_tag, errors, {"location"})
        if is_nonempty_string(scene_tag) and scene_tag in result["scene_variants"]:
            fail(errors, f"duplicate scene variant rule: {scene_tag}")
        profiles = scene.get("allowed_light_profiles")
        normalized_profiles: set[tuple[str, ...]] = set()
        if not isinstance(profiles, list) or not profiles:
            fail(errors, f"{field}.allowed_light_profiles must be a non-empty array")
            profiles = []
        for profile_index, profile in enumerate(profiles):
            lights = validate_string_list(
                profile,
                f"{field}.allowed_light_profiles[{profile_index}]",
                errors,
                allow_empty=False,
            )
            normalized = tuple(sorted(lights))
            if normalized in normalized_profiles:
                fail(errors, f"{field}.allowed_light_profiles has a duplicate profile: {list(normalized)}")
            normalized_profiles.add(normalized)
        if is_nonempty_string(scene_tag):
            result["scene_variants"][scene_tag] = normalized_profiles

    scene_transitions = value.get("scene_transitions", MISSING)
    if scene_transitions is MISSING:
        if require_full:
            fail(errors, "continuity_rules.scene_transitions must be an array")
        scene_transitions = []
    elif not isinstance(scene_transitions, list):
        fail(errors, "continuity_rules.scene_transitions must be an array")
        scene_transitions = []
    for index, transition in enumerate(scene_transitions):
        field = f"continuity_rules.scene_transitions[{index}]"
        if not isinstance(transition, dict) or set(transition) != {"from", "to"}:
            fail(errors, f"{field} must contain exactly from and to")
            continue
        old_scene = transition.get("from")
        new_scene = transition.get("to")
        resolve_tag(old_scene, f"{field}.from", refs_by_tag, errors, {"location"})
        resolve_tag(new_scene, f"{field}.to", refs_by_tag, errors, {"location"})
        if old_scene == new_scene:
            fail(errors, f"{field} must change scene_variant")
        if is_nonempty_string(old_scene) and is_nonempty_string(new_scene):
            pair = (old_scene, new_scene)
            if pair in result["scene_transitions"]:
                fail(errors, f"duplicate scene transition: {old_scene} -> {new_scene}")
            result["scene_transitions"].add(pair)

    axes = value.get("axes", MISSING)
    if axes is MISSING:
        if require_full:
            fail(errors, "continuity_rules.axes must contain at least one axis")
        axes = []
    elif not isinstance(axes, list) or (require_full and not axes):
        fail(errors, "continuity_rules.axes must contain at least one axis")
        axes = []
    for index, axis in enumerate(axes):
        field = f"continuity_rules.axes[{index}]"
        if not isinstance(axis, dict):
            fail(errors, f"{field} must be an object")
            continue
        allowed_axis = {"axis_id", "start", "end", "allowed_sides"}
        if set(axis) - allowed_axis:
            fail(errors, f"{field} has unknown fields: {sorted(set(axis) - allowed_axis)}")
        axis_id = axis.get("axis_id")
        if not is_nonempty_string(axis_id):
            fail(errors, f"{field}.axis_id is required")
            continue
        if axis_id in result["axes"]:
            fail(errors, f"duplicate axis_id: {axis_id}")
        start_ok = validate_coord(axis.get("start"), f"{field}.start", errors, dimensions=(2,))
        end_ok = validate_coord(axis.get("end"), f"{field}.end", errors, dimensions=(2,))
        if start_ok and end_ok and axis.get("start") == axis.get("end"):
            fail(errors, f"{field}.start and end must be different")
        sides = validate_string_list(axis.get("allowed_sides"), f"{field}.allowed_sides", errors, allow_empty=False)
        if any(not isinstance(side, str) or side not in ALLOWED_AXIS_SIDES for side in sides):
            fail(errors, f"{field}.allowed_sides must use {sorted(ALLOWED_AXIS_SIDES)}")
        result["axes"][axis_id] = axis
    return result


def validate_character_state(
    value: object,
    field: str,
    rules: dict[str, Any],
    refs_by_tag: dict[str, dict[str, Any]],
    errors: list[str],
) -> str | None:
    if not isinstance(value, dict):
        fail(errors, f"{field} must be an object")
        return None
    allowed = {"id", "asset_version", "coord", "facing", "screen_direction", "eyeline_target", "wardrobe_variant"}
    if set(value) - allowed:
        fail(errors, f"{field} has unknown fields: {sorted(set(value) - allowed)}")
    char_id = value.get("id")
    if not is_nonempty_string(char_id):
        fail(errors, f"{field}.id is required")
        return None
    char_rule = rules["characters"].get(char_id)
    if char_rule is None:
        fail(errors, f"{field}.id is not registered in continuity_rules.characters: {char_id}")
        char_rule = {"asset_versions": set(), "wardrobe_variants": set()}
    asset_version = value.get("asset_version")
    resolve_tag(asset_version, f"{field}.asset_version", refs_by_tag, errors, {"character"}, entity_id=char_id)
    if not is_nonempty_string(asset_version) or asset_version not in char_rule["asset_versions"]:
        fail(errors, f"{field}.asset_version is not allowed for {char_id}: {asset_version}")
    wardrobe = value.get("wardrobe_variant")
    resolve_tag(wardrobe, f"{field}.wardrobe_variant", refs_by_tag, errors, {"wardrobe"}, subject_id=char_id)
    if not is_nonempty_string(wardrobe) or wardrobe not in char_rule["wardrobe_variants"]:
        fail(errors, f"{field}.wardrobe_variant is not allowed for {char_id}: {wardrobe}")
    validate_coord(value.get("coord"), f"{field}.coord", errors)
    if not isinstance(value.get("facing"), str) or value.get("facing") not in ALLOWED_FACING:
        fail(errors, f"{field}.facing must be one of {sorted(ALLOWED_FACING)}")
    if not isinstance(value.get("screen_direction"), str) or value.get("screen_direction") not in ALLOWED_SCREEN_DIRECTIONS:
        fail(errors, f"{field}.screen_direction must be one of {sorted(ALLOWED_SCREEN_DIRECTIONS)}")
    if not is_nonempty_string(value.get("eyeline_target")):
        fail(errors, f"{field}.eyeline_target is required; use none when no target applies")
    return char_id


def validate_prop_state(
    value: object,
    field: str,
    refs_by_tag: dict[str, dict[str, Any]],
    prop_rules: dict[str, Any],
    known_owners: set[str],
    errors: list[str],
) -> str | None:
    if not isinstance(value, dict):
        fail(errors, f"{field} must be an object")
        return None
    allowed = {"id", "asset_version", "owner", "hand", "state"}
    if set(value) - allowed:
        fail(errors, f"{field} has unknown fields: {sorted(set(value) - allowed)}")
    prop_id = value.get("id")
    if not is_nonempty_string(prop_id):
        fail(errors, f"{field}.id is required")
        return None
    prop_rule = prop_rules.get(prop_id)
    if prop_rule is None:
        fail(errors, f"{field}.id is not registered in continuity_rules.tracked_props: {prop_id}")
        prop_rule = {"asset_versions": set(), "allowed_configurations": set()}
    asset_version = value.get("asset_version")
    resolve_tag(
        asset_version,
        f"{field}.asset_version",
        refs_by_tag,
        errors,
        {"prop", "product"},
        entity_id=prop_id,
    )
    if not is_nonempty_string(asset_version) or asset_version not in prop_rule["asset_versions"]:
        fail(errors, f"{field}.asset_version is not allowed for {prop_id}: {asset_version}")
    owner = value.get("owner")
    if not is_nonempty_string(owner):
        fail(errors, f"{field}.owner is required")
    elif owner != "environment" and owner not in known_owners:
        fail(errors, f"{field}.owner must name a tracked character, tracked prop, or environment; got {owner}")
    if not isinstance(value.get("hand"), str) or value.get("hand") not in ALLOWED_HANDS:
        fail(errors, f"{field}.hand must be one of {sorted(ALLOWED_HANDS)}")
    state = value.get("state")
    if not is_nonempty_string(state):
        fail(errors, f"{field}.state is required")
    if (
        is_nonempty_string(asset_version)
        and is_nonempty_string(owner)
        and isinstance(value.get("hand"), str)
        and value.get("hand") in ALLOWED_HANDS
        and is_nonempty_string(state)
    ):
        configuration = (asset_version, owner, value.get("hand"), state)
        if configuration not in prop_rule["allowed_configurations"]:
            fail(errors, f"{field} configuration is not allowed for {prop_id}: {configuration}")
    return prop_id


def validate_eyelines(characters: list[dict[str, Any]], field: str, errors: list[str]) -> None:
    by_id = {
        character.get("id"): character
        for character in characters
        if isinstance(character, dict) and is_nonempty_string(character.get("id"))
    }
    for char_id, character in by_id.items():
        target = character.get("eyeline_target")
        if target == "none":
            continue
        if not is_nonempty_string(target):
            continue
        if target not in by_id:
            fail(errors, f"{field}.{char_id}.eyeline_target is not a tracked character: {target}")
            continue
        reciprocal = by_id[target].get("eyeline_target") == char_id
        direction = character.get("screen_direction")
        target_direction = by_id[target].get("screen_direction")
        if (
            reciprocal
            and isinstance(direction, str)
            and isinstance(target_direction, str)
            and direction in {"left", "right"}
            and target_direction in {"left", "right"}
        ):
            if direction == target_direction:
                fail(errors, f"{field} reciprocal eyelines {char_id}/{target} must use opposite screen directions")


def validate_state(
    state: object,
    field: str,
    rules: dict[str, Any],
    refs_by_tag: dict[str, dict[str, Any]],
    errors: list[str],
    *,
    require_full: bool,
) -> None:
    if not isinstance(state, dict):
        fail(errors, f"{field} must be a structured object")
        return
    allowed = {"characters", "props", "scene_variant", "light_sources", "persistent_world_state", "style_variant"}
    if set(state) - allowed:
        fail(errors, f"{field} has unknown fields: {sorted(set(state) - allowed)}")
    if require_full:
        for required in ("characters", "props", "scene_variant", "light_sources", "persistent_world_state"):
            if required not in state:
                fail(errors, f"{field}.{required} is required")

    characters = state.get("characters", MISSING)
    if characters is MISSING:
        characters = []
    elif not isinstance(characters, list):
        fail(errors, f"{field}.characters must be an array")
        characters = []
    char_ids: set[str] = set()
    for index, character in enumerate(characters):
        char_id = validate_character_state(character, f"{field}.characters[{index}]", rules, refs_by_tag, errors)
        if char_id:
            if char_id in char_ids:
                fail(errors, f"{field}.characters has duplicate id: {char_id}")
            char_ids.add(char_id)
    expected_chars = set(rules["characters"])
    if require_full and char_ids != expected_chars:
        fail(errors, f"{field}.characters ids must equal tracked characters; expected {sorted(expected_chars)}, got {sorted(char_ids)}")
    validate_eyelines(characters, f"{field}.characters", errors)

    props = state.get("props", MISSING)
    if props is MISSING:
        props = []
    elif not isinstance(props, list):
        fail(errors, f"{field}.props must be an array")
        props = []
    declared_prop_ids = {
        prop.get("id")
        for prop in props
        if isinstance(prop, dict) and is_nonempty_string(prop.get("id"))
    }
    known_owners = expected_chars | set(rules["tracked_props"])
    prop_ids: set[str] = set()
    for index, prop in enumerate(props):
        prop_id = validate_prop_state(
            prop,
            f"{field}.props[{index}]",
            refs_by_tag,
            rules["tracked_props"],
            known_owners,
            errors,
        )
        if prop_id:
            if prop_id in prop_ids:
                fail(errors, f"{field}.props has duplicate id: {prop_id}")
            prop_ids.add(prop_id)
    expected_props = set(rules["tracked_props"])
    if require_full and (prop_ids != expected_props or declared_prop_ids != expected_props):
        fail(
            errors,
            f"{field}.props ids must equal tracked_props; expected {sorted(expected_props)}, got {sorted(prop_ids)}",
        )

    scene_variant = state.get("scene_variant", MISSING)
    if scene_variant is not MISSING:
        resolve_tag(scene_variant, f"{field}.scene_variant", refs_by_tag, errors, {"location"})
    if "style_variant" in state:
        resolve_tag(state.get("style_variant"), f"{field}.style_variant", refs_by_tag, errors, {"style"})
    light_sources_value = state.get("light_sources", MISSING)
    light_sources: list[str] | None = None
    if light_sources_value is not MISSING:
        light_sources = validate_string_list(
            light_sources_value, f"{field}.light_sources", errors, allow_empty=False
        )
        if scene_variant is MISSING:
            fail(errors, f"{field}.light_sources requires scene_variant")
    if scene_variant is not MISSING:
        allowed_profiles = rules["scene_variants"].get(scene_variant) if is_nonempty_string(scene_variant) else None
        if allowed_profiles is None:
            fail(errors, f"{field}.scene_variant is not registered in continuity_rules.scene_variants: {scene_variant}")
        elif light_sources is not None and tuple(sorted(light_sources)) not in allowed_profiles:
            fail(
                errors,
                f"{field}.light_sources do not match an allowed profile for scene_variant {scene_variant}: {sorted(light_sources)}",
            )
    if "persistent_world_state" in state:
        validate_string_list(
            state.get("persistent_world_state"),
            f"{field}.persistent_world_state",
            errors,
            allow_empty=True,
        )


def canonical_state(state: object) -> dict[str, Any] | None:
    if not isinstance(state, dict):
        return None
    result: dict[str, Any] = {}
    characters = state.get("characters")
    if isinstance(characters, list):
        result["characters"] = {
            item.get("id"): {
                key: item.get(key)
                for key in ("asset_version", "coord", "facing", "screen_direction", "eyeline_target", "wardrobe_variant")
            }
            for item in characters
            if isinstance(item, dict) and is_nonempty_string(item.get("id"))
        }
    props = state.get("props")
    if isinstance(props, list):
        result["props"] = {
            item.get("id"): {
                key: item.get(key)
                for key in ("asset_version", "owner", "hand", "state")
            }
            for item in props
            if isinstance(item, dict) and is_nonempty_string(item.get("id"))
        }
    if "scene_variant" in state:
        result["scene_variant"] = state.get("scene_variant")
    if "light_sources" in state:
        result["light_sources"] = (
            sorted(state.get("light_sources", [])) if isinstance(state.get("light_sources"), list) else None
        )
    if "persistent_world_state" in state:
        result["persistent_world_state"] = (
            sorted(state.get("persistent_world_state", []))
            if isinstance(state.get("persistent_world_state"), list)
            else None
        )
    if "style_variant" in state:
        result["style_variant"] = state.get("style_variant")
    return result


def collect_changes(before: Any, after: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    changes: list[tuple[str, Any, Any]] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else key
            old = before.get(key, MISSING)
            new = after.get(key, MISSING)
            if old is MISSING:
                changes.append((child, None, new))
            elif new is MISSING:
                changes.append((child, old, None))
            else:
                changes.extend(collect_changes(old, new, child))
    elif before != after:
        changes.append((path, before, after))
    return changes


def validate_change_declarations(
    value: object,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    field: str,
    errors: list[str],
) -> None:
    if not isinstance(value, list):
        fail(errors, f"{field} must be an array")
        return
    actual = {path: (old, new) for path, old, new in collect_changes(before, after)} if before is not None and after is not None else {}
    declared: set[str] = set()
    for index, change in enumerate(value):
        item_field = f"{field}[{index}]"
        if not isinstance(change, dict):
            fail(errors, f"{item_field} must be an object")
            continue
        if set(change) != {"path", "from", "to"}:
            fail(errors, f"{item_field} must contain exactly path, from, and to")
        path = change.get("path")
        if not is_nonempty_string(path):
            fail(errors, f"{item_field}.path is required")
            continue
        if path in declared:
            fail(errors, f"{field} has duplicate path: {path}")
        declared.add(path)
        if path not in actual:
            fail(errors, f"{item_field} declares no real in-to-out change: {path}")
            continue
        old, new = actual[path]
        if change.get("from") != old or change.get("to") != new:
            fail(errors, f"{item_field} does not match actual change {path}: {old!r} -> {new!r}")
    for path, (old, new) in actual.items():
        if path not in declared:
            fail(errors, f"{field} is missing actual change {path}: {old!r} -> {new!r}")


def validate_camera(
    camera: object,
    field: str,
    axes: dict[str, dict[str, Any]],
    errors: list[str],
    *,
    require_full: bool,
) -> dict[str, Any] | None:
    if not isinstance(camera, dict):
        fail(errors, f"{field} must be an object")
        return None
    for key in ("placement", "primary_path", "narrative_job"):
        if not is_nonempty_string(camera.get(key)):
            fail(errors, f"{field}.{key} is required")

    axis_keys = ("axis_id", "side", "axis_transition", "axis_transition_reason")
    axis_declared = require_full or any(key in camera for key in axis_keys)
    coord_declared = "coord" in camera
    if axis_declared:
        for key in ("axis_id", "side", "axis_transition"):
            if not is_nonempty_string(camera.get(key)):
                fail(errors, f"{field}.{key} is required when camera axis state is declared")
        if not coord_declared:
            fail(errors, f"{field}.coord is required when camera axis state is declared")
    coord_ok = validate_coord(camera.get("coord"), f"{field}.coord", errors) if coord_declared else False
    axis_id = camera.get("axis_id")
    side = camera.get("side")
    transition = camera.get("axis_transition")
    if axis_declared:
        if not isinstance(side, str) or side not in ALLOWED_AXIS_SIDES:
            fail(errors, f"{field}.side must be one of {sorted(ALLOWED_AXIS_SIDES)}")
        if not isinstance(transition, str) or transition not in ALLOWED_AXIS_TRANSITIONS:
            fail(errors, f"{field}.axis_transition must be one of {sorted(ALLOWED_AXIS_TRANSITIONS)}")
        elif transition != "none" and not is_nonempty_string(camera.get("axis_transition_reason")):
            fail(errors, f"{field}.axis_transition_reason is required for {transition}")
        axis = axes.get(axis_id) if is_nonempty_string(axis_id) else None
        if axis is None and is_nonempty_string(axis_id):
            fail(errors, f"{field}.axis_id is not registered: {axis_id}")
        elif axis is not None and coord_ok:
            start = axis.get("start")
            end = axis.get("end")
            coord = camera.get("coord")
            if isinstance(start, list) and isinstance(end, list) and isinstance(coord, list):
                cross = (end[0] - start[0]) * (coord[1] - start[1]) - (end[1] - start[1]) * (coord[0] - start[0])
                computed = "on_axis" if abs(cross) < 1e-9 else ("left" if cross > 0 else "right")
                if side != computed:
                    fail(errors, f"{field}.side is {side!r}, but axis geometry resolves coord to {computed!r}")
                if side not in axis.get("allowed_sides", []):
                    fail(errors, f"{field}.side {side!r} is not allowed for axis {axis_id}")
    return camera


def validate_prompt_tags(prompt: object, field: str, refs_by_tag: dict[str, dict[str, Any]], errors: list[str]) -> None:
    if not is_nonempty_string(prompt):
        return
    for tag in extract_tag_tokens(prompt):
        if not CANONICAL_TAG_RE.fullmatch(tag):
            fail(errors, f"{field} contains malformed canonical tag: {tag}")
        elif tag not in refs_by_tag:
            fail(errors, f"{field} contains unresolved canonical tag: {tag}")


def validate_shots(
    shots: object,
    rules: dict[str, Any],
    refs_by_tag: dict[str, dict[str, Any]],
    errors: list[str],
    *,
    require_full: bool,
) -> list[dict[str, Any]]:
    if not isinstance(shots, list) or not shots:
        fail(errors, "shots must contain at least one shot")
        return []
    valid_shots: list[dict[str, Any]] = []
    seen_shots: set[str] = set()
    previous_out: dict[str, Any] | None = None
    previous_camera: dict[str, Any] | None = None
    previous_shot_id: str | None = None
    for index, shot in enumerate(shots):
        field = f"shots[{index}]"
        if not isinstance(shot, dict):
            fail(errors, f"{field} must be an object")
            continue
        valid_shots.append(shot)
        shot_id = shot.get("shot_id")
        if not is_nonempty_string(shot_id):
            fail(errors, f"{field}.shot_id is required")
            shot_id = f"index-{index}"
        elif shot_id in seen_shots:
            fail(errors, f"duplicate shot_id: {shot_id}")
        seen_shots.add(shot_id)
        for key in ("story_function", "visible_action", "prompt"):
            if not is_nonempty_string(shot.get(key)):
                fail(errors, f"{field}.{key} is required")

        has_continuity_in = "continuity_in" in shot
        has_continuity_out = "continuity_out" in shot
        if not require_full and has_continuity_in != has_continuity_out:
            fail(errors, f"{field} must declare continuity_in and continuity_out together")
        if require_full or has_continuity_in:
            validate_state(
                shot.get("continuity_in"),
                f"{field}.continuity_in",
                rules,
                refs_by_tag,
                errors,
                require_full=require_full,
            )
        if require_full or has_continuity_out:
            validate_state(
                shot.get("continuity_out"),
                f"{field}.continuity_out",
                rules,
                refs_by_tag,
                errors,
                require_full=require_full,
            )
        current_in = canonical_state(shot.get("continuity_in")) if has_continuity_in else None
        current_out = canonical_state(shot.get("continuity_out")) if has_continuity_out else None
        if current_in is not None and current_out is not None:
            old_scene = current_in.get("scene_variant")
            new_scene = current_out.get("scene_variant")
            scenes_are_tags = is_nonempty_string(old_scene) and is_nonempty_string(new_scene)
            transition_is_allowed = scenes_are_tags and (old_scene, new_scene) in rules["scene_transitions"]
            if old_scene != new_scene and not transition_is_allowed:
                fail(
                    errors,
                    f"scene transition is not allowed in shot {shot_id}: {old_scene} -> {new_scene}",
                )
        if previous_out is not None and current_in is not None:
            for path, old, new in collect_changes(previous_out, current_in):
                fail(
                    errors,
                    f"continuity mismatch {previous_shot_id} -> {shot_id}: {path}: previous out {old!r} != current in {new!r}",
                )
        if require_full or (has_continuity_in and has_continuity_out):
            validate_change_declarations(
                shot.get("continuity_changes", [] if not require_full else None),
                current_in,
                current_out,
                f"{field}.continuity_changes",
                errors,
            )
        elif "continuity_changes" in shot:
            changes = shot.get("continuity_changes")
            if not isinstance(changes, list):
                fail(errors, f"{field}.continuity_changes must be an array")
            elif changes:
                fail(errors, f"{field}.continuity_changes requires continuity_in and continuity_out")

        camera = None
        if require_full or "camera" in shot:
            camera = validate_camera(
                shot.get("camera"),
                f"{field}.camera",
                rules["axes"],
                errors,
                require_full=require_full,
            )
        previous_has_axis = previous_camera is not None and is_nonempty_string(previous_camera.get("axis_id"))
        current_has_axis = camera is not None and is_nonempty_string(camera.get("axis_id"))
        if previous_has_axis and current_has_axis and previous_camera is not None and camera is not None:
            old_axis = previous_camera.get("axis_id")
            new_axis = camera.get("axis_id")
            old_side = previous_camera.get("side")
            new_side = camera.get("side")
            transition = camera.get("axis_transition")
            if old_axis != new_axis and transition != "new_axis":
                fail(errors, f"camera axis changed before shot {shot_id}: {old_axis} -> {new_axis} without new_axis")
            elif old_axis == new_axis and transition == "new_axis":
                fail(errors, f"{field}.camera declares new_axis but axis_id did not change")
            elif old_axis == new_axis and old_side != new_side:
                if not isinstance(transition, str) or transition not in {"visible_cross", "neutral_reset", "along_axis"}:
                    fail(
                        errors,
                        f"camera axis side changed before shot {shot_id}: {old_side} -> {new_side} without a visible transition",
                    )
        elif current_has_axis and camera is not None and camera.get("axis_transition") != "none":
            fail(errors, f"{field}.camera must use axis_transition none on the first shot")

        validate_prompt_tags(shot.get("prompt"), f"{field}.prompt", refs_by_tag, errors)
        previous_out = current_out
        previous_camera = camera
        previous_shot_id = shot_id
    return valid_shots


def validate_package(data: object, input_path: Path | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return ["root must be a JSON object"], warnings

    required = (
        "version",
        "package_status",
        "objective",
        "production_class",
        "continuity_mode",
        "format_intent",
        "references",
        "shots",
        "provider",
        "post_responsibilities",
    )
    for key in required:
        if key not in data:
            fail(errors, f"missing required field: {key}")
    if not is_nonempty_string(data.get("version")):
        fail(errors, "version must be a non-empty string")
    package_status = data.get("package_status")
    if not isinstance(package_status, str) or package_status not in ALLOWED_PACKAGE_STATUSES:
        fail(errors, f"package_status must be one of {sorted(ALLOWED_PACKAGE_STATUSES)}")
    if not is_nonempty_string(data.get("objective")):
        fail(errors, "objective must be a non-empty string")
    if not isinstance(data.get("production_class"), str) or data.get("production_class") not in ALLOWED_CLASSES:
        fail(errors, f"production_class must be one of {sorted(ALLOWED_CLASSES)}")
    continuity_mode = data.get("continuity_mode")
    if not isinstance(continuity_mode, str) or continuity_mode not in ALLOWED_CONTINUITY_MODES:
        fail(errors, f"continuity_mode must be one of {sorted(ALLOWED_CONTINUITY_MODES)}")

    raw = json.dumps(data, ensure_ascii=False).lower()
    if FORBIDDEN_SKILL in raw:
        fail(errors, f"external skill boundary violation: {FORBIDDEN_SKILL}")

    fmt = data.get("format_intent")
    if not isinstance(fmt, dict):
        fail(errors, "format_intent must be an object")
    else:
        if fmt.get("live_schema_required") is not True:
            fail(errors, "format_intent.live_schema_required must be true")
        shot_count = fmt.get("shot_count")
        if isinstance(shot_count, bool) or not isinstance(shot_count, int) or shot_count < 1:
            fail(errors, "format_intent.shot_count must be a positive integer")

    require_full_continuity = continuity_mode != "sparse"
    if require_full_continuity and "continuity_rules" not in data:
        fail(errors, "missing required field: continuity_rules")
    refs_by_tag = validate_references(data.get("references"), package_status, input_path, errors, warnings)
    rules = validate_continuity_rules(
        data.get("continuity_rules", {}),
        refs_by_tag,
        errors,
        require_full=require_full_continuity,
    )
    valid_shots = validate_shots(
        data.get("shots"),
        rules,
        refs_by_tag,
        errors,
        require_full=require_full_continuity,
    )
    if isinstance(fmt, dict) and isinstance(fmt.get("shot_count"), int) and not isinstance(fmt.get("shot_count"), bool):
        if fmt.get("shot_count") != len(valid_shots):
            fail(errors, f"format_intent.shot_count is {fmt.get('shot_count')}, but package has {len(valid_shots)} shots")

    provider = data.get("provider")
    if not isinstance(provider, dict):
        fail(errors, "provider must be an object")
    else:
        adapter = provider.get("adapter")
        if adapter is not None and not is_nonempty_string(adapter):
            fail(errors, "provider.adapter must be null or one adapter name")
        if package_status == "planning" and adapter is not None:
            fail(errors, "planning packages cannot select a provider adapter")
        if adapter is not None and not is_nonempty_string(provider.get("schema_verified_at")):
            fail(errors, "provider.schema_verified_at is required when adapter is selected")

    post = data.get("post_responsibilities")
    if not isinstance(post, list) or any(not is_nonempty_string(item) for item in post):
        fail(errors, "post_responsibilities must be an array of non-empty strings")
    elif len(post) != len(set(post)):
        fail(errors, "post_responsibilities must not contain duplicates")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="prompt-package JSON path")
    args = parser.parse_args()
    path = Path(args.input).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "input": str(path),
                    "package_status": None,
                    "continuity_mode": None,
                    "provider_ready": False,
                    "structural_only": True,
                    "prompt_semantics_checked": False,
                    "warnings": [],
                    "errors": [f"invalid JSON: {exc}"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    errors, warnings = validate_package(data, path)
    package_status = data.get("package_status") if isinstance(data, dict) else None
    continuity_mode = data.get("continuity_mode") if isinstance(data, dict) else None
    provider_ready = package_status == "provider_ready" and not errors
    print(
        json.dumps(
            {
                "ok": not errors,
                "input": str(path),
                "package_status": package_status,
                "continuity_mode": continuity_mode,
                "provider_ready": provider_ready,
                "structural_only": True,
                "prompt_semantics_checked": False,
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
