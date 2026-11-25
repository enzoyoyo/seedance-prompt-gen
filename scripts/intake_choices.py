"""Resolve current instructions against a revision-bound, project-local choice set."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from uuid import uuid4

from drama_project import (ProjectError, drama_block, file_lock, load_manifest, manifest_path,
                           section, write_json_atomic)

MODES = ("prompt_only", "images_only", "video_clips", "full_film")
CREATIVE = ("cinema", "short_drama")
VIDEO_MODELS = {"seedance": "doubao-seedance-2-5-260628", "seedance_2_5": "doubao-seedance-2-5-260628",
                "seedance_2_0": "doubao-seedance-2-0-260128", "google_flow": "gemini_omni_flash_1_2",
                "higgsfield": "seedance_2_5", "kling": "kling4_0", "grok_imagine": "grok-imagine-video-1.5",
                "xyq": "Seedance_2.5", "lovart": "generate_video_seedance_v2_5", "elevenlabs": "bytedance-seedance-v2.5"}
ALTERNATES = {"google_flow": ["veo-3.1-generate-001"], "higgsfield": ["cinematic_studio_video_4_0", "soul_id"],
              "grok_imagine": ["grok-imagine-video-1.5-lite"], "kling": ["kling_4_0_flash"],
              "xyq": ["Seedance_2.5_flash", "Seedance_2.5_draft"]}
MODEL_OPTIONS = ("grok_imagine", "google_flow", "seedance_2_5", "higgsfield", "kling", "xyq", "lovart")
VIDEO_ONLY = {"seedance", "seedance_2_0", "seedance_2_5", "veo"}
OPTIONS = {"delivery_mode": MODES, "image_model": tuple(m for m in MODEL_OPTIONS if m not in VIDEO_ONLY), "video_model": MODEL_OPTIONS,
           "audio_plan": ("keep_native", "native_no_dialogue", "replace_dialogue", "mute"),
           "creative_mode": CREATIVE, "aspect_ratio": ("16:9", "9:16", "1:1", "21:9", "4:3", "3:4", "4:5")}
FIELDS = tuple(OPTIONS)
DELIVERY = dict(zip(MODES, (r"只要提示词|提示词包|prompts?[- _]only|prompt package",
                            r"先出图|只要图|images?[- _]only", r"视频素材|video[- _]clips?",
                            r"完整成片|full[- _]film")))
PREVIS_HINTS = (
    ("waive", r"(?:跳过|不做|免掉|省掉|无需|skip|waive)\s*(?:本[场集]的?|这[场集]的?)?\s*(?:白模|站位预演|空间预演|预演|previs|whitemodel)"),
    ("blender", r"\bblender\b|\.blend\b"),
    ("stage_desk", r"stage[ _-]desk|本地片场|白模导演台|本地导演台"),
    ("jutsu", r"3d\s*jutsu|\bjutsu\b"),
    ("whitemodel_board", r"离线白模|whitemodel[ _-]board|render_whitemodel_board"),
)
MODELS = dict(zip(MODEL_OPTIONS, (r"grok(?:[- _]imagine)?", r"google\s*flow|(?<![a-z0-9_])flow(?![a-z0-9_])", r"seedance(?:[ _-]*2[._]5|(?![ _-]*\d))",
                                   r"higgsfield", r"kling|可灵", r"xyq|小云雀", r"lovart")))
MODELS["seedance_2_0"] = r"seedance[ _-]*2[._]0"
MODELS["veo"] = r"veo(?:[ _-]*3[._]1)?"
TEXT_ONLY = re.compile(r"文案|(?:给我|想|提供).{0,6}方向|(?:改|写|润色|调整).{0,6}台词|剧本|脚本|大纲|只谈想法|谈想法|聊想法|故事梗概|写故事|脑暴|头脑风暴|构思|brainstorm|outline|write (?:a |the )?script|screenplay", re.I)


class StaleMenu(ProjectError):
    def __init__(self, current):
        super().__init__("STALE_MENU_ANSWER", "use the request_id and revision of the displayed menu")
        self.current = current


def is_video_only(value):
    token = str(value or "").strip().casefold()
    return token in VIDEO_ONLY or token in {m.casefold() for m in VIDEO_MODELS.values()} or bool(
        re.match(r"^(?:doubao[-_])?(?:seedance|veo)(?:$|[-_ .0-9])", token))


def normalize_creative(value):
    return "cinema" if value == "film" else value


def required_choices(mode):
    result = ["delivery_mode"] if mode not in MODES else []
    if mode in MODES[1:]:
        result.append("image_model")
    if mode in MODES[2:]:
        result.append("video_model")
    if mode == "full_film":
        result.append("audio_plan")
    return result


def parse_turn(words):
    selected, rejected = {}, {}
    for field, patterns in (("delivery_mode", DELIVERY), ("model", MODELS),
                            ("creative_mode", {"cinema": r"电影模式|(?<![a-z0-9_])cinema\s+mode(?![a-z0-9_])|(?:story_mode|creative_mode)\s*=\s*(?:film|cinema)\b", "short_drama": r"短剧|short[ _-]drama"}),
                            ("aspect_ratio", {r: re.escape(r) for r in ("16:9", "9:16", "1:1", "21:9", "4:3", "3:4", "4:5")})):
        for value, pattern in patterns.items():
            for match in re.finditer(pattern, words, re.I):
                boundary = r"[,，、。;；\n]|但是|改用|\bbut\b"
                prefix = re.split(boundary, words[:match.start()], flags=re.I)[-1]
                suffix = re.split(boundary, words[match.end():], maxsplit=1, flags=re.I)[0]
                negative = re.search(r"(?:不要|不用|别用|不选|no|without|not|don't use)\s*(?:用|使用|选)?\s*$", prefix, re.I)
                negative = negative or re.match(r"\s*(?:不要|不用|不选|禁用|rejected\b)", suffix, re.I)
                keys = [field]
                if field == "model":
                    keys = ["image_model", "video_model"]
                    if value in VIDEO_ONLY:
                        keys = ["video_model"]
                    elif re.match(r"\s*(?:出图|生图|做图|生成图片|图片)", suffix) or re.search(r"(?:图片|图像|出图|生图|image)\s*(?:用|选|model)?\s*$", prefix, re.I):
                        keys = ["image_model"]
                    elif re.match(r"\s*(?:出片|出视频|视频|生成视频)", suffix) or re.search(r"(?:出片|视频|video)\s*(?:用|选|model)?\s*$", prefix, re.I):
                        keys = ["video_model"]
                for key in keys:
                    (rejected if negative else selected).setdefault(key, set()).add(value)
    return selected, rejected


def parse_previs_hint(words: str, previous_hint: str | None) -> str | None:
    """Detect optional user-stated previs tool or waiver without creating any mandatory prompt."""
    boundary = r"[,，、。;；\n]|但是|改用|\bbut\b"
    positive: list[str] = []
    negative: set[str] = set()
    for value, pattern in PREVIS_HINTS:
        for match in re.finditer(pattern, words, re.I):
            prefix = re.split(boundary, words[:match.start()], flags=re.I)[-1]
            suffix = re.split(boundary, words[match.end():], maxsplit=1, flags=re.I)[0]
            neg = re.search(r"(?:不要|不用|别用|不选|no|without|not|don't use)\s*(?:用|使用|选)?\s*$", prefix, re.I)
            neg = neg or re.match(r"\s*(?:不要|不用|不选|禁用|rejected\b)", suffix, re.I)
            if neg:
                negative.add(value)
            elif value not in positive:
                positive.append(value)
    if positive:
        return "waive" if "waive" in positive else positive[-1]
    if previous_hint in negative:
        return None
    return previous_hint


def initial_menu(manifest):
    encoded = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
    request_id = hashlib.sha256(encoded).hexdigest()
    return resolve(argparse.Namespace(user_words="", request_id=request_id, revision=0), manifest)


def resolve(args, manifest):
    drama = drama_block(manifest)
    previous = section(drama, "choice_resolution")
    if (not previous and getattr(args, "request_id", None) and
            re.fullmatch(r"\d+(?:\s*[,，]\s*\d+)*", (args.user_words or "").strip())):
        previous = initial_menu(manifest)
    old_gate = section(drama, "model_gate")
    sources = [section(drama, "release_intent"), manifest, drama]
    if old_gate.get("confirmed_at") or old_gate.get("confirmed") is True:
        sources.append(old_gate)
    if previous:
        sources = [section(previous, "resolved")]
    resolved = {k: source[k] for source in sources for k in FIELDS if source.get(k)}
    if "creative_mode" not in resolved:
        resolved["creative_mode"] = drama.get("story_mode") or manifest.get("story_mode") or "cinema"
    resolved["creative_mode"] = normalize_creative(resolved["creative_mode"])
    evidence = {k: "default" if section(previous, "evidence").get(k) == "default" else "project" for k in resolved}
    if not any(s.get("creative_mode") or s.get("story_mode") for s in sources):
        evidence["creative_mode"] = "default"
    words = (args.user_words or "").strip()
    current, denied = parse_turn(words)
    for value in OPTIONS["audio_plan"]:
        if re.search(r"(?<!\w)" + value.replace("_", r"[ _-]") + r"(?!\w)", words, re.I):
            current.setdefault("audio_plan", set()).add(value)
    conflicts = []
    request_id = previous.get("request_id") or getattr(args, "request_id", None) or uuid4().hex
    supplied_id, supplied_rev = getattr(args, "request_id", None), getattr(args, "revision", None)
    revision = previous.get("revision", supplied_rev if supplied_rev is not None else 0)
    numeric = bool(re.fullmatch(r"\d+(?:\s*[,，]\s*\d+)*", words))
    if (previous and (supplied_id is None) != (supplied_rev is None) or (supplied_id and supplied_id != request_id) or (supplied_rev is not None and supplied_rev != revision)
            or (numeric and (not previous or supplied_id != request_id or supplied_rev != revision))):
        raise StaleMenu(previous)
    menu_picks = {}
    if numeric:
        fields = previous["missing"]
        numbers = [int(s.strip()) for s in re.split("[,，]", words)]
        if len(numbers) > len(fields):
            raise ProjectError("INVALID_MENU_ANSWER")
        for key, number in zip(fields, numbers):
            if not 1 <= number <= len(OPTIONS[key]):
                raise ProjectError("INVALID_MENU_ANSWER", key)
            picked = OPTIONS[key][number - 1]
            current[key] = {picked}
            menu_picks[key] = picked
    for key in FIELDS:
        explicit = getattr(args, key, None)
        if explicit:
            norm_val = normalize_creative(explicit) if key == "creative_mode" else explicit
            if key in menu_picks and norm_val != menu_picks[key]:
                raise ProjectError("CONFLICTING_EXPLICIT_AND_MENU_CHOICE", f"{key}:{menu_picks[key]}!={norm_val}")
            current[key] = {norm_val}
        choices = current.get(key, set())
        if resolved.get(key) in denied.get(key, set()):
            resolved.pop(key)
            evidence.pop(key, None)
        if len(choices) > 1 or choices & denied.get(key, set()) or (not choices and key in previous.get("conflicts", [])):
            conflicts.append(key)
            resolved.pop(key, None)
        elif choices:
            resolved[key] = next(iter(choices))
            evidence[key] = "current_turn"
    instruction = re.sub(r"(?:不要|不用|别|don't |do not )(?:生成|出图|出视频|出片|成片|提示词|generate|render|prompts?)", "", words, flags=re.I)
    text_only = bool(TEXT_ONLY.search(words) and not current.get("delivery_mode") and not current.get("image_model") and not current.get("video_model")
                     and not re.search(r"生成|出图|出视频|出片|成片|提示词|generate|render|prompt", instruction, re.I))
    previs_hint = parse_previs_hint(words, previous.get("previs_preference"))
    if is_video_only(resolved.get("image_model")):
        if "image_model" in current:
            raise ProjectError("VIDEO_ONLY_IMAGE_MODEL")
        resolved.pop("image_model")
        evidence.pop("image_model", None)
    if not text_only and resolved.get("delivery_mode") and resolved["delivery_mode"] not in MODES:
        raise ProjectError("INVALID_DELIVERY_MODE", resolved["delivery_mode"])
    if "creative_mode" in resolved and resolved["creative_mode"] not in CREATIVE:
        raise ProjectError("INVALID_CREATIVE_MODE", resolved["creative_mode"])
    if resolved.get("aspect_ratio") and not re.fullmatch(r"[1-9]\d*:[1-9]\d*", resolved["aspect_ratio"]):
        raise ProjectError("INVALID_ASPECT_RATIO", resolved["aspect_ratio"])
    if "aspect_ratio" not in conflicts:
        resolved.setdefault("aspect_ratio", "16:9")
        evidence.setdefault("aspect_ratio", "default")
    missing = [] if text_only else [k for k in required_choices(resolved.get("delivery_mode")) if not resolved.get(k)]
    if not text_only:
        missing += [k for k in conflicts if k not in missing]
    menu = [{"field": k, "options": [{"number": i, "value": v} for i, v in enumerate(OPTIONS.get(k, ()), 1)]}
            for k in missing]
    binding = {"request_id": request_id, "revision": revision + 1 if previous or supplied_rev is None else revision}
    questions = [{"id": item["field"], "question": "Choose " + item["field"].replace("_", " ") + ".",
                  "required": True, "allow_custom": True, "options":
                  [{"label": o["value"].replace("_", " "), "value": o["value"]} for o in item["options"]]}
                 for item in menu]
    return {**binding, "resolved": resolved, "missing": missing, "conflicts": conflicts, "evidence": evidence,
            "ask_user": bool(missing), "previs_preference": None if text_only else previs_hint,
            "host_selector_payload": {**binding, "type": "ask_question", "questions": questions},
            "numbered_menu": menu, "text_only": text_only}


def add_arguments(parser):
    parser.add_argument("--user-words", default="")
    parser.add_argument("--delivery-mode", choices=MODES)
    parser.add_argument("--creative-mode", "--story-mode", choices=(*CREATIVE, "film"))
    for name in ("image-model", "video-model", "audio-plan", "aspect-ratio", "request-id"):
        parser.add_argument("--" + name)
    parser.add_argument("--revision", type=int)


def apply_resolution(manifest, result):
    drama = dict(drama_block(manifest))
    previous = section(drama, "model_gate")
    if drama.get("sop_version") == "3.0" and previous:
        changed = any(previous.get(k) != result["resolved"].get(k) for k in FIELDS
                      if result["evidence"].get(k) != "default")
        if changed or result["conflicts"]:
            drama.pop("model_gate", None)
            for key in ("post", "delivery"):
                if drama.get(key):
                    drama[key]["stale"] = True
    return {**manifest, "drama": {**drama, "choice_resolution": result}}


def resolve_project(args):
    if not args.project:
        return resolve(args, {})
    if not args.project.is_dir():
        raise ProjectError("PROJECT_MISSING", str(args.project))
    path = manifest_path(args.project)
    with file_lock(path):
        manifest = load_manifest(args.project) if path.exists() else {
            "version": "1.0", "project_id": args.project.name, "shots": [], "takes": [], "edit_list": [],
            "drama": {"sop_version": "3.0"}}
        result = resolve(args, manifest)
        if not result["text_only"]:
            write_json_atomic(path, apply_resolution(manifest, result))
        return result


def cli(args):
    try:
        result = resolve_project(args)
    except ProjectError as exc:
        current = exc.current if isinstance(exc, StaleMenu) else {}
        print(json.dumps({**current, "ok": False, "conflicts": [str(exc)]}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(result["conflicts"]))
