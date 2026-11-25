"""Normalize the flat review format into a strict NBP v2 prompt and ordered media bindings."""
import re

from drama_project import ProjectError

DISPLAY_FIELDS = {"subject", "action", "scene", "camera", "light", "style", "negative", "motion", "duration",
                  "audio", "continuity_ref", "refs", "id", "shot_id", "revision", "mode", "creative_mode",
                  "aspect_ratio", "prompt", "kf_prompt", "speaker", "zh", "en", "dialogue", "duration_s",
                  "task_mode", "live_params", "beats", "type", "story_mode", "model", "resolution", "route",
                  "endpoint", "tier", "audio_route", "dialogue_lang", "requirements"}
# Shared v1 fields and stray translation keys alone cannot identify a flat prompt.
MARKERS = {"mode", "refs", "kf_prompt", "task_mode", "duration_s", "creative_mode", "aspect_ratio",
           "live_params", "beats", "story_mode", "endpoint"}
CHAR_TAG = re.compile(r"@char_[a-zA-Z0-9_]+_v\d+")
ROLES = {"char": "character", "location": "location", "prop": "prop", "style": "style",
         "motion": "motion", "audio": "audio"}


def schema_of(data, requested="auto"):
    if not isinstance(data, dict):
        return "invalid"
    version = data.get("nbp_version")
    if version is not None:
        actual = {"1": "nbp_v1", "2": "nbp_v2"}.get(version, "invalid")
    elif requested == "simplified" or (set(data) <= DISPLAY_FIELDS
            and any(data.get(k) for k in ("prompt", "subject", "action", "scene", "kf_prompt"))
            and (set(data) & MARKERS or set(data) == {"prompt"})):
        actual = "simplified"
    else:
        actual = "nbp_v1"
    return actual if requested in ("auto", actual) else "invalid"


def character_rows(subject, references):
    descriptions = {row["ref"]: row["use"] for row in references if row["role"] == "character"}
    for tag in CHAR_TAG.findall(subject):
        descriptions.setdefault(tag, "")
    characters = []
    for tag, description in descriptions.items():
        if not isinstance(description, str):
            raise ProjectError("INVALID_CHARACTER_DESCRIPTION", tag)
        name_pattern = r"([\u3400-\u9fff]{1,6}?|[A-Za-z][A-Za-z'-]*)"
        following = re.search(re.escape(tag) + r"\s+[（(]?" + name_pattern + r"(?=[\s，,；;。（）().]|$)", subject)
        preceding = re.search(name_pattern + r"\s*[（(]\s*" + re.escape(tag), subject)
        identity = re.match(r"(?:身份|角色|姓名|name)\s*[:：]\s*" + name_pattern + r"(?=的|[\s，,；;。]|$)", description, re.I)
        before_tag = re.search(r"(?:^|[，,；;])\s*" + name_pattern + r"\s+" + re.escape(tag), subject)
        match = following or preceding or identity or before_tag
        name = match[1] if match else re.sub(r"_v\d+$", "", tag.removeprefix("@char_"))
        characters.append({"ref": tag, "name": name, "state": description or "unspecified", "wardrobe": "unspecified"})
    return characters


def camera_fields(value, fields):
    if isinstance(value, dict):
        return {**dict.fromkeys(fields, "unspecified"), **value}
    if not isinstance(value, str):
        raise ProjectError("INVALID_CAMERA")
    parts = {key: [] for key in fields}
    for clause in re.split(r"[，,；;]", value):
        clause = clause.strip()
        if not clause:
            continue
        if re.search(r"mm|焦距|深焦|浅焦|lens", clause, re.I):
            key = "lens_note"
        elif re.search(r"机位|侧拍|仰拍|俯拍|越轴|angle", clause, re.I):
            key = "angle"
        elif re.search(r"近景|中景|全景|远景|特写|close.up|wide shot", clause, re.I):
            key = "shot_size"
        else:
            key = "movement"
        parts[key].append(clause)
    return {k: "，".join(v) or "unspecified" for k, v in parts.items()}


def normalize(data, kind):
    from validate_nbp_prompt import CANONICAL_TAG_RE, V2_CAMERA_FIELDS
    unknown = set(data) - DISPLAY_FIELDS
    if unknown:
        raise ProjectError("SIMPLIFIED_UNKNOWN_FIELDS", ",".join(sorted(unknown)))
    if data.get("type", kind) != kind or data.get("mode") in {"image", "video"} and data["mode"] != kind:
        raise ProjectError("PROMPT_TYPE_MISMATCH")
    if not any(isinstance(data.get(k), str) and data[k].strip() for k in ("action", "subject", "scene", "kf_prompt", "prompt")):
        raise ProjectError("PROMPT_CONTENT_REQUIRED")
    forbidden = {"audio", "duration", "duration_s", "motion", "dialogue", "beats", "zh", "en"}
    if kind == "image" and set(data) & forbidden:
        raise ProjectError("IMAGE_VIDEO_FIELD", ",".join(sorted(set(data) & forbidden)))
    controls = data.get("live_params", {})
    if not isinstance(controls, dict):
        raise ProjectError("INVALID_LIVE_PARAMS")
    controls = {**controls, **{k: data[k] for k in ("model", "resolution", "route", "endpoint", "tier",
                                                     "requirements", "audio_route") if k in data}}
    ratio = data.get("aspect_ratio", "16:9")
    camera = data.get("camera", "unspecified")
    ir = {"nbp_version": "2", "references": [], "scene": data.get("scene", "unspecified"),
          "action": data.get("action") or data.get("prompt") or data.get("kf_prompt") or data.get("subject") or data["scene"],
          "camera": camera_fields(camera, V2_CAMERA_FIELDS), "aspect_ratio": ratio, "live_params": controls}
    for key in ("subject", "light", "style", "motion", "beats"):
        if key in data:
            ir[key] = data[key]
    if "negative" in data:
        ir["negative"] = [data["negative"]] if isinstance(data["negative"], str) else data["negative"]
    mode = data.get("task_mode")
    if not mode and data.get("endpoint") in {"first_frame", "first_last_frame", "edit", "extend"}:
        mode = data["endpoint"]
    if not mode and data.get("mode") in {"first_frame", "first_last_frame", "edit", "extend", "omni_reference"}:
        mode = data["mode"]
    refs = data.get("refs", [])
    if isinstance(refs, dict):
        refs = [{"ref": tag, "use": description} for tag, description in refs.items()]
    continuity = data.get("continuity_ref", [])
    if not isinstance(refs, list) or not isinstance(continuity, list):
        raise ProjectError("REFERENCE_LIST_REQUIRED")
    binding_sources = {}
    for i, ref in enumerate([*refs, *continuity]):
        row = ref if isinstance(ref, dict) else {"ref": ref}
        if set(row) - {"ref", "path", "role", "use", "type", "url"}:
            raise ProjectError("UNKNOWN_REFERENCE_FIELD")
        source = row.get("ref") or row.get("path") or row.get("url")
        if not isinstance(source, str) or not source.strip():
            raise ProjectError("EMPTY_REFERENCE", str(i))
        tag = source if CANONICAL_TAG_RE.fullmatch(source) else f"@asset_binding{i+1}_v01"
        prefix = tag[1:].split("_", 1)[0]
        role = row.get("role") or ROLES.get(prefix, "ref")
        use = row.get("use", role)
        role = {"ref": "prop", "image": "prop", "first_frame": "prop", "last_frame": "prop",
                "video": "motion", "voice": "audio", "scene": "location"}.get(role, role)
        if row.get("type") in {"video", "audio"}:
            role = {"video": "motion", "audio": "audio"}[row["type"]]
        binding_sources[tag] = row.get("path") or row.get("url") or source
        ir["references"].append({"ref": tag, "role": role, "use": use})
    if not mode:
        frame_uses = [ref["use"] for ref in ir["references"]]
        if "last_frame" in frame_uses:
            mode = "first_last_frame"
        elif "first_frame" in frame_uses:
            mode = "first_frame"
    if mode:
        ir["task_mode"] = mode
    ir["characters"] = character_rows(data.get("subject", ""), ir["references"])
    if kind == "video":
        from validate_nbp_prompt import parse_dialogue_line, unbound_speakers, v2_dialogue
        duration = data.get("duration_s", data.get("duration", 5))
        if isinstance(duration, str):
            match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:s|秒|seconds?)?\s*", duration, re.I)
            if not match:
                raise ProjectError("INVALID_DURATION", duration)
            duration = float(match[1])
        ir["duration"] = {"target_s": duration, "live_check": "verify before submission"}
        audio = data.get("audio", "")
        ir["audio"] = {"dialogue": [], "ambience": "", "music": "", "sfx": ""}
        if isinstance(audio, dict):
            ir["audio"].update(audio)
        else:
            if not isinstance(audio, str):
                raise ProjectError("INVALID_AUDIO")
            ambience = []
            for segment in re.split(r"[｜|\n]", audio):
                segment = segment.strip()
                if not segment:
                    continue
                parsed = parse_dialogue_line(segment)
                if parsed and re.fullmatch(r"字幕|subtitles?|captions?", parsed[0], re.I):
                    continue
                if parsed and not re.fullmatch(r"现场|环境音?|环境声|音效|音乐|配乐|ambience|sfx|music", parsed[0], re.I):
                    ir["audio"]["dialogue"].append(segment)
                else:
                    ambience.append(segment)
            ir["audio"]["ambience"] = "｜".join(ambience)
        dialogue = data.get("dialogue", {})
        if isinstance(dialogue, str):
            ir["audio"]["dialogue"] = [dialogue]
        elif isinstance(dialogue, list):
            ir["audio"]["dialogue"] = dialogue
        elif not isinstance(dialogue, dict) or set(dialogue) - {"speaker", "zh", "en"}:
            raise ProjectError("INVALID_DIALOGUE")
        translations = {k: data.get(k) or (dialogue.get(k) if isinstance(dialogue, dict) else None) for k in ("zh", "en")}
        if any(translations.values()):
            lang = data.get("dialogue_lang") or ("zh" if translations["zh"] else "en")
            if not translations.get(lang):
                raise ProjectError("REQUESTED_DIALOGUE_LANGUAGE_MISSING")
            speaker = data.get("speaker") or (dialogue.get("speaker") if isinstance(dialogue, dict) else "")
            line = translations[lang]
            ir["audio"]["dialogue"].append(f"{speaker}: {line}" if speaker else line)
            ir["audio"]["dialogue_lang"] = lang
            controls["dialogue_translations"] = translations
        lines = v2_dialogue(ir) or []
        beat_lines = [b["say"] for b in ir.get("beats", []) if isinstance(b, dict) and isinstance(b.get("say"), str)]
        unbound = unbound_speakers(ir, [*lines, *beat_lines], [])
        if unbound:
            raise ProjectError("UNKNOWN_DIALOGUE_SPEAKER", ", ".join(unbound))
    controls["binding_sources"] = binding_sources
    controls["display_metadata"] = {k: data[k] for k in ("mode", "creative_mode", "story_mode", "shot_id", "id", "revision",
                                                           "prompt", "kf_prompt") if k in data}
    return ir
