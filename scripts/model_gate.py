#!/usr/bin/env python3
"""Explicit model gate (Human Gate #1, STOP & WAIT) for SPEC v2.0 projects.

  render  print the four required choices with this host's detected adapters (names and
          present/missing states only, never a credential value): Markdown numbered menu,
          the host `ask_question` JSON, or both. With `--project`, records a fresh gate
          presentation nonce in `resume-manifest.json`. The assistant shows it and ends its turn.
  check   validate `drama.model_gate` in a project's resume-manifest.json.

The four required choices: (1) image model, (2) video model, (3) audio plan (BGM model /
voice & SFX model / no audio for this project), (4) global spec and delivery mode (aspect
ratio, total duration & pacing, style tone, prompt-only vs tool render). Nothing is chosen by
default: the user picks every item and `drama_setup.py model-gate` records their own words.
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
from pathlib import Path
from typing import Any

import intake_choices
import list_execution_providers as providers
from drama_project import ProjectError, drama_block, load_manifest, manifest_path, now_iso, section, update_manifest

GATE_FIELDS = ("image_model", "video_model", "audio_plan", "aspect_ratio", "pacing", "style_tone", "delivery_mode")
DELIVERY_MODES = ("prompt_only", "tool_render")
NO_AUDIO_WORDS = ("none", "本项目无需生成音频")
AUDIO_PART_RE = re.compile(r"^(?P<kind>bgm|tts_sfx):(?P<model>\S.*)$")
ASPECT_RATIO_RE = re.compile(r"^(?P<w>\d+(?:\.\d+)?):(?P<h>\d+(?:\.\d+)?)$")
DURATION_UNIT_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:s|sec|secs|second|seconds|秒|分|分钟|min|mins|小时|h|集)|"
    r"[一二两三四五六七八九十百]+\s*(?:秒|分钟|分|集)",
    re.IGNORECASE,
)
PLACEHOLDER_RE = re.compile(
    r"(?:^|[\s:;,/|+-])(?:todo|tbd|auto|auto_default|default|assumed_by_agent|agent_default|placeholder|"
    r"default_by_agent|whatever|any|same|unspecified|none_selected)(?:$|[\s:;,/|+-])|"
    r"<[^<>]*>|待定|默认值|按默认|(?<![a-z0-9_])默认(?![a-z0-9_])|随便|任意|同上|不限",
    re.IGNORECASE,
)
TRIVIAL_REPLY_RE = re.compile(
    r"^(?:就这样|好的?|可以|行|确认|同意|继续|没问题|ok|okay|yes|sure|fine|go\s+ahead)[。！!.,，、\s]*$",
    re.IGNORECASE,
)
MODEL_SPLIT_RE = re.compile(r"[,/|;+]")
NONCE_RE = re.compile(r"\bMG-[A-Z0-9]{6}\b", re.IGNORECASE)
STOP_LINE = ("**STOP & WAIT**：以上四项由用户逐项选定后才可开始任何生图／生视频／音频生成；"
             "本轮回复到此结束，不预设默认值，不替用户作答。")


def gate_required(drama: dict[str, Any]) -> bool:
    """SPEC v2.0 projects (and any project that already holds a model gate) must pass the gate."""
    return drama.get("sop_version") in {"2.0", "3.0"} or "model_gate" in drama


def is_placeholder(value: object) -> bool:
    if not isinstance(value, str):
        return True
    stripped = value.strip()
    if not stripped or stripped.casefold() in {"none", "null", "n/a", "na", "unknown", "?"}:
        return True
    return bool(PLACEHOLDER_RE.search(stripped))


def valid_aspect_ratio(value: object) -> bool:
    if not isinstance(value, str):
        return False
    match = ASPECT_RATIO_RE.fullmatch(value.strip())
    if not match:
        return False
    return float(match.group("w")) > 0 and float(match.group("h")) > 0


def valid_pacing(value: object) -> bool:
    if not isinstance(value, str) or is_placeholder(value):
        return False
    text = value.strip()
    if not DURATION_UNIT_RE.search(text):
        return False
    without_duration = DURATION_UNIT_RE.sub(" ", text)
    descriptive = re.sub(r"[\d\s.,:;，。：；、/|+-]+", "", without_duration)
    return len(descriptive) >= 2


def audio_plan_errors(value: object) -> list[str]:
    """`none` / `本项目无需生成音频`, or `bgm:<model>` and/or `tts_sfx:<model>` joined by `+`."""
    if not isinstance(value, str) or not value.strip():
        return ["MODEL_GATE_INCOMPLETE:audio_plan"]
    plan = value.strip()
    if plan in NO_AUDIO_WORDS:
        return []
    parts = [part.strip() for part in plan.split("+")]
    kinds = [AUDIO_PART_RE.match(part) for part in parts]
    if not all(kinds) or len({m["kind"] for m in kinds if m}) != len(parts):
        return [f"MODEL_GATE_AUDIO_PLAN_INVALID:{plan}"]
    if any(is_placeholder(m["model"]) for m in kinds if m):
        return [f"MODEL_GATE_PLACEHOLDER:audio_plan:{plan}"]
    return []


def allowed_models(spec_value: object) -> list[str]:
    if not isinstance(spec_value, str):
        return []
    return [item.strip() for item in MODEL_SPLIT_RE.split(spec_value) if item.strip()]


def field_errors(record: dict[str, Any], name: str) -> list[str]:
    value = record.get(name)
    if name == "audio_plan":
        return audio_plan_errors(value)
    if not isinstance(value, str) or not value.strip():
        return [f"MODEL_GATE_INCOMPLETE:{name}"]
    if name == "delivery_mode":
        return [] if value in DELIVERY_MODES else [f"MODEL_GATE_DELIVERY_MODE_INVALID:{value}"]
    if name == "aspect_ratio":
        return [] if valid_aspect_ratio(value) else [f"MODEL_GATE_ASPECT_RATIO_INVALID:{value}"]
    if name == "pacing":
        return [] if valid_pacing(value) else [f"MODEL_GATE_PACING_INCOMPLETE:{value}"]
    if name in ("image_model", "video_model"):
        tokens = allowed_models(value)
        if not tokens or any(is_placeholder(tok) for tok in tokens):
            return [f"MODEL_GATE_PLACEHOLDER:{name}"]
        return []
    return [f"MODEL_GATE_PLACEHOLDER:{name}"] if is_placeholder(value) else []


PARTIAL_DISCLAIMER_RE = re.compile(
    r"只确认|仅确认|其余未定|其他未定|暂不确认|待确认|only\s+confirm|nothing\s+else",
    re.IGNORECASE,
)
CLAUSE_BOUNDARY_RE = re.compile(
    r"[，;；。！!？?\n]+|"
    r"(?=(?:但是|不过|而不是|而非|除了|但(?=\s*[不没未无免禁排去取拒只仅另改换])))|"
    r"(?=\b(?:but|except|rather\s+than|instead\s+of)\b)",
    re.IGNORECASE,
)
SUBCLAUSE_SEP_RE = re.compile(r"[,、]+")
NEG_PREFIX_RE = re.compile(
    r"不用|不使用|不选|不采纳|不采用|不要|不跑|不生成|不加|不配|不是|禁用|排除|去掉|取消|拒绝|无需|无须|不含|而非|而不是|除了|"
    r"[不没未无免零](?=\s*(?:配乐|配音|音乐|人声|音效|旁白|音频|渲染|输出|用|要|加|选|采纳|单集|冷色|画幅|9:|16:|1:|4:|21:))|"
    r"\b(?:no|not|never|without|exclude\w*|skip\w*|drop\w*|avoid\w*|instead\s+of|rather\s+than)\b",
    re.IGNORECASE,
)
POST_NEG_RE = re.compile(
    r"^\s*(?:[:：—–-]\s*)?"
    r"(?:(?:这个|该|此|这|上述|以上)?\s*(?:风格|基调|影调|色调|节奏|时长|画幅|比例|模型|方案|模式|选项|配置|方式|用途|成片|提示词|生成|部分|环节)\s*)?"
    r"(?:就|则|先|暂|暂时|一律|统统|全都?|都|均|还是|依然|仍|却|可|应|应该|必须)?\s*"
    r"(?:"
    r"[（(]\s*(?:不要用|不用|不使用|不要|不选|禁用|排除|取消|拒绝|not\s+used|rejected|excluded)\s*[）)]|"
    r"(?:不要用|不用|不使用|不采用|不采纳|不启用|不选|不选用|不考虑|不要|不行|不可|不可用|不合适|不适合|"
    r"禁用|排除|去掉|删掉|取消|拒绝|否决|弃用|放弃|作罢|算了|免了|不予(?:采用|采纳|使用|考虑)|"
    r"不是(?:我要的|本片|这次|我们|目标|所选)\S*|并非(?:我要的|本片|这次|目标|所选)\S*|"
    r"(?:is|are|was|were|should\s+be|must\s+be|will\s+be)?\s*"
    r"(?:not\s+(?:used|chosen|selected|approved|adopted|enabled|wanted|allowed|accepted|ok|okay)|"
    r"rejected|excluded|dropped|skipped|forbidden|disabled|omitted|ruled\s+out)|"
    r"(?:do|does|did|should|must|will)\s+not\s+(?:use|choose|select|adopt|enable|include|want))"
    r"(?:\s*(?:(?:这个|该|此|这)\s*(?:风格|基调|影调|色调|节奏|时长|画幅|比例|模型|方案|模式|选项|配置)|它|this(?:\s+\w+)?|it))?"
    r"\s*(?:了|吧|哈|呢|呀|哦|啦|就行|即可)?"
    r"(?:\s*(?:[（(][^）)]*[）)]|(?:因为|由于|because\b|since\b).*))?\s*$|"
    r"(?:改成|改为|换成|换为|换掉|替换为|替换成)\S*"
    r")",
    re.IGNORECASE,
)
WHOLE_NO_AUDIO_RE = re.compile(
    r"本项目无需生成音频|无需生成音频|无需音频|不生成音频|不需要音频|不要音频|无音频|纯静音|"
    r"(?:不配音[、，,\s]*(?:也|且)?不配乐)|(?:不配乐[、，,\s]*(?:也|且)?不配音)|"
    r"\bno\s+audio\b|(?<![a-z0-9_.-])none(?![a-z0-9_.-])",
    re.IGNORECASE,
)
AUDIO_GENERIC_CUE_RE = re.compile(r"音频|声轨|(?<![a-z0-9_.-])audio(?:_plan)?(?![a-z0-9_.-])", re.IGNORECASE)
AUDIO_BGM_CUE_RE = re.compile(r"配乐|背景音乐|音乐|(?<![a-z0-9_.-])(?:bgm|music)(?![a-z0-9_.-])", re.IGNORECASE)
AUDIO_VOICE_CUE_RE = re.compile(
    r"配音|人声|音效|旁白|(?<![a-z0-9_.-])(?:tts(?:_sfx)?|voice(?:over)?|sfx)(?![a-z0-9_.-])",
    re.IGNORECASE,
)
ROLE_CUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("image", re.compile(r"图片|生图|图像|(?<![a-z0-9_.-])image(?:_model)?(?![a-z0-9_.-])", re.IGNORECASE)),
    ("video", re.compile(r"视频|生视频|(?<![a-z0-9_.-])video(?:_model)?(?![a-z0-9_.-])", re.IGNORECASE)),
    ("bgm", AUDIO_BGM_CUE_RE),
    ("tts_sfx", AUDIO_VOICE_CUE_RE),
)
MODEL_SLUG_RE = re.compile(r"(?<![a-z0-9_.-])[a-z][a-z0-9_]*(?:[-./][a-z0-9_]+)+(?![a-z0-9_.-])", re.IGNORECASE)
MODEL_LIST_STEP_RE = re.compile(
    r"^\s*(?:[,、/+]|和|与|及|加|\band\b)\s*[a-z][a-z0-9_]*(?:[-./][a-z0-9_]+)+(?![a-z0-9_.-])",
    re.IGNORECASE,
)
POST_ROLE_CONN_RE = re.compile(
    r"^\s*(?:[:：—–-]|->|=>)?\s*(?:用于|用作|作为|作|当|当成|充当|做|负责|承担|供|给|是|跑|生成|出|for|as|to\s+generate)\s*|"
    r"^\s*[（(]\s*",
    re.IGNORECASE,
)
PREV_POST_ROLE_SPAN_RE = re.compile(
    r"[a-z][a-z0-9_]*(?:[-./][a-z0-9_]+)+\s*"
    r"(?:用于|用作|作为|作|当|当成|充当|做|负责|承担|供|for|as)\s*"
    r"(?:图片|生图|图像|视频|生视频|配乐|背景音乐|音乐|配音|人声|音效|旁白|音频|声轨|image|video|bgm|music|tts_sfx|tts|voiceover|voice|sfx|audio)",
    re.IGNORECASE,
)
RESERVED_SLUGS = frozenset({"tool_render", "prompt_only", "tts_sfx", "ask_question"})


def _norm_compact(text: str) -> str:
    return re.sub(r"[\s.,:;，。：；、/|+-]+", "", text.casefold())


def _phrase_flex_pattern(phrase: str) -> re.Pattern[str]:
    """Match a spec phrase allowing optional whitespace/punctuation between segments so clause negation is preserved."""
    parts = [re.escape(p) for p in re.split(r"[\s.,:;，。：；、/|+-]+", phrase.strip()) if p]
    return re.compile(r"[\s.,:;，。：；、/|+-]*".join(parts), re.IGNORECASE)


def _token_pattern(token: str) -> re.Pattern[str]:
    esc = re.escape(token.strip())
    left = r"(?<![a-z0-9_.-])" if re.match(r"^[a-z0-9_.-]", token.strip(), re.I) else ""
    right = r"(?![a-z0-9_.-])" if re.search(r"[a-z0-9_.-]$", token.strip(), re.I) else ""
    return re.compile(f"{left}{esc}{right}", re.IGNORECASE)


def _has_any_role_cue(text: str) -> bool:
    return any(pat.search(text) for _, pat in ROLE_CUES) or bool(AUDIO_GENERIC_CUE_RE.search(text))


def _is_pre_negated(prefix: str) -> bool:
    return bool(NEG_PREFIX_RE.search(prefix) or re.search(r"[不没未无免]\s*$", prefix))


def _is_post_negated(suffix: str) -> bool:
    return bool(POST_NEG_RE.search(suffix))


def _segment_has_negation(seg: str) -> bool:
    if _is_pre_negated(seg) or _is_post_negated(seg):
        return True
    for m in MODEL_SLUG_RE.finditer(seg):
        if _is_post_negated(seg[m.end():]):
            return True
    return False


def _is_bare_model_item(seg: str) -> bool:
    return bool(MODEL_SLUG_RE.search(seg)) and not _has_any_role_cue(seg) and not _segment_has_negation(seg)


def _split_clauses(words: str) -> list[str]:
    clauses: list[str] = []
    for major in CLAUSE_BOUNDARY_RE.split(words):
        if not major or not major.strip():
            continue
        subs = [s.strip() for s in SUBCLAUSE_SEP_RE.split(major) if s and s.strip()]
        if not subs:
            continue
        merged: list[str] = [subs[0]]
        for seg in subs[1:]:
            prev = merged[-1]
            if not _segment_has_negation(prev) and not _segment_has_negation(seg) and (
                _is_bare_model_item(seg) or _is_bare_model_item(prev)
            ):
                merged[-1] = f"{prev}, {seg}"
            else:
                merged.append(seg)
        clauses.extend(merged)
    return clauses


def _nearest_specific_role(prefix: str) -> str | None:
    best_pos = -1
    best_role: str | None = None
    for role, pat in ROLE_CUES:
        for m in pat.finditer(prefix):
            if m.end() > best_pos:
                best_pos = m.end()
                best_role = role
    return best_role


def _first_specific_role(suffix: str) -> str | None:
    best_pos: int | None = None
    best_role: str | None = None
    for role, pat in ROLE_CUES:
        m = pat.search(suffix)
        if m and (best_pos is None or m.start() < best_pos):
            best_pos = m.start()
            best_role = role
    return best_role


def _advance_past_model_list(suffix: str) -> str:
    rest = suffix
    while True:
        step = MODEL_LIST_STEP_RE.match(rest)
        if not step:
            break
        rest = rest[step.end():]
    return rest


def _local_tail(suffix: str) -> str:
    nxt = MODEL_SLUG_RE.search(suffix)
    return suffix[:nxt.start()] if nxt else suffix


def _role_matches_in_clause(clause: str, m: re.Match[str], expected_role: str) -> bool:
    clean_prefix = PREV_POST_ROLE_SPAN_RE.sub(" ", clause[:m.start()])
    pre_role = _nearest_specific_role(clean_prefix)
    if pre_role is not None and pre_role != expected_role:
        return False

    tail = _local_tail(_advance_past_model_list(clause[m.end():]))
    conn = POST_ROLE_CONN_RE.match(tail)
    if conn:
        post_role = _first_specific_role(tail[conn.end():])
        if post_role is not None and post_role != expected_role:
            return False
    if pre_role is None:
        any_post_role = _first_specific_role(tail)
        if any_post_role is not None and any_post_role != expected_role:
            return False
        if expected_role in ("image", "video") and (
            AUDIO_GENERIC_CUE_RE.search(clean_prefix) or AUDIO_GENERIC_CUE_RE.search(tail)
        ):
            return False
    return True


def _token_affirmed_and_unnegated(clauses: list[str], pat: re.Pattern[str],
                                  expected_role: str | None = None) -> bool:
    affirmed = False
    for clause in clauses:
        for m in pat.finditer(clause):
            prefix = clause[:m.start()]
            suffix = clause[m.end():]
            list_tail = _local_tail(_advance_past_model_list(suffix))
            if _is_pre_negated(prefix) or _is_post_negated(_local_tail(suffix)) or _is_post_negated(list_tail):
                return False
            if expected_role is not None and not _role_matches_in_clause(clause, m, expected_role):
                return False
            affirmed = True
    return affirmed


def _phrase_affirmed_and_unnegated(words: str, phrase: str) -> bool:
    stripped = phrase.strip()
    if not stripped:
        return False
    pat = _phrase_flex_pattern(stripped)
    affirmed = False
    for m in pat.finditer(words):
        clause_prefix = re.split(r"[,，;；。！!？?\n]+", CLAUSE_BOUNDARY_RE.split(words[:m.start()])[-1])[-1]
        clause_suffix = re.split(r"[,，;；。！!？?\n]+", CLAUSE_BOUNDARY_RE.split(words[m.end():])[0])[0]
        if _is_pre_negated(clause_prefix) or _is_post_negated(clause_suffix):
            return False
        affirmed = True
    return affirmed


def _cue_has_affirmative(clauses: list[str], pat: re.Pattern[str]) -> bool:
    for clause in clauses:
        for m in pat.finditer(clause):
            prefix = clause[:m.start()]
            tail = _local_tail(clause[m.end():])
            if not _is_pre_negated(prefix) and not _is_post_negated(tail):
                return True
    return False


def _cue_has_negated(clauses: list[str], pat: re.Pattern[str]) -> bool:
    for clause in clauses:
        for m in pat.finditer(clause):
            prefix = clause[:m.start()]
            tail = _local_tail(clause[m.end():])
            if _is_pre_negated(prefix) or _is_post_negated(tail):
                return True
    return False


def user_words_bound(record: dict[str, Any], words: str, drama: dict[str, Any] | None = None) -> bool:
    """User reply must explicitly confirm EVERY chosen model (with matching role) and spec field without contradiction."""
    if TRIVIAL_REPLY_RE.fullmatch(words) or len(words.strip()) < 6 or PARTIAL_DISCLAIMER_RE.search(words):
        return False
    clauses = _split_clauses(words)

    # 1 & 2: EVERY declared image_model and EVERY declared video_model must appear affirmatively under its proper role
    img_role_pat = ROLE_CUES[0][1]
    vid_role_pat = ROLE_CUES[1][1]
    if (
        not _cue_has_affirmative(clauses, img_role_pat)
        or not _cue_has_affirmative(clauses, vid_role_pat)
        or _cue_has_negated(clauses, img_role_pat)
        or _cue_has_negated(clauses, vid_role_pat)
    ):
        return False
    img_tokens = [t.strip().casefold() for t in allowed_models(record.get("image_model")) if len(t.strip()) >= 2]
    vid_tokens = [t.strip().casefold() for t in allowed_models(record.get("video_model")) if len(t.strip()) >= 2]
    if not img_tokens or not vid_tokens:
        return False
    if not all(_token_affirmed_and_unnegated(clauses, _token_pattern(tok), "image") for tok in img_tokens):
        return False
    if not all(_token_affirmed_and_unnegated(clauses, _token_pattern(tok), "video") for tok in vid_tokens):
        return False

    # 3: Audio plan — whole-project no-audio with zero affirmative BGM/voice cues, OR every audio sub-model affirmed in its role
    audio = str(record.get("audio_plan") or "").strip()
    aud_models: list[str] = []
    aud_kinds: set[str] = set()
    if audio in NO_AUDIO_WORDS:
        if not _cue_has_affirmative(clauses, WHOLE_NO_AUDIO_RE) or _cue_has_negated(clauses, WHOLE_NO_AUDIO_RE):
            return False
        if _cue_has_affirmative(clauses, AUDIO_BGM_CUE_RE) or _cue_has_affirmative(clauses, AUDIO_VOICE_CUE_RE):
            return False
    else:
        if _cue_has_affirmative(clauses, WHOLE_NO_AUDIO_RE):
            return False
        for part in audio.split("+"):
            m = AUDIO_PART_RE.match(part.strip())
            if m and len(m["model"].strip()) >= 2:
                kind = m["kind"]
                tok = m["model"].strip().casefold()
                aud_kinds.add(kind)
                aud_models.append(tok)
                if not _token_affirmed_and_unnegated(clauses, _token_pattern(tok), kind):
                    return False
        if not aud_models:
            return False
        has_generic_audio = _cue_has_affirmative(clauses, AUDIO_GENERIC_CUE_RE) and not _cue_has_negated(
            clauses, AUDIO_GENERIC_CUE_RE
        )
        if "bgm" in aud_kinds:
            if _cue_has_negated(clauses, AUDIO_BGM_CUE_RE):
                return False
            if not _cue_has_affirmative(clauses, AUDIO_BGM_CUE_RE) and not has_generic_audio:
                return False
        if "tts_sfx" in aud_kinds:
            if _cue_has_negated(clauses, AUDIO_VOICE_CUE_RE):
                return False
            if not _cue_has_affirmative(clauses, AUDIO_VOICE_CUE_RE) and not has_generic_audio:
                return False
        if "bgm" not in aud_kinds and _cue_has_affirmative(clauses, AUDIO_BGM_CUE_RE):
            return False
        if "tts_sfx" not in aud_kinds and _cue_has_affirmative(clauses, AUDIO_VOICE_CUE_RE):
            return False

    # Reject if user affirmatively named another model slug that is absent from the locked record!
    declared_slugs = set(img_tokens) | set(vid_tokens) | set(aud_models) | RESERVED_SLUGS
    for clause in clauses:
        for m in MODEL_SLUG_RE.finditer(clause):
            slug = m.group(0).casefold()
            if slug in declared_slugs:
                continue
            prefix = clause[:m.start()]
            suffix = clause[m.end():]
            if not _is_pre_negated(prefix) and not _is_post_negated(_local_tail(suffix)) and not _is_post_negated(
                _local_tail(_advance_past_model_list(suffix))
            ):
                return False

    # 4: Aspect ratio, full pacing (duration + rhythm), style tone, and delivery mode must ALL be affirmed & unnegated
    ratio = str(record.get("aspect_ratio") or "").strip()
    ratio_pat = re.compile(rf"(?<![0-9.]){re.escape(ratio)}(?![0-9.])", re.IGNORECASE)
    if not ratio or not _token_affirmed_and_unnegated(clauses, ratio_pat):
        return False
    any_ratio_pat = re.compile(r"(?<![0-9.])\d+(?:\.\d+)?:\d+(?:\.\d+)?(?![0-9.])")
    for clause in clauses:
        for m in any_ratio_pat.finditer(clause):
            if m.group(0) != ratio:
                prefix = clause[:m.start()]
                tail = _local_tail(clause[m.end():])
                if not _is_pre_negated(prefix) and not _is_post_negated(tail):
                    return False

    pacing = str(record.get("pacing") or "").strip()
    if not _phrase_affirmed_and_unnegated(words, pacing):
        return False

    style = str(record.get("style_tone") or "").strip()
    if not _phrase_affirmed_and_unnegated(words, style):
        return False

    mode = record.get("delivery_mode")
    prompt_pat = re.compile(
        r"(?<![a-z0-9_.-])prompt_only(?![a-z0-9_.-])|"
        r"仅输出结构化提示词|只输出结构化提示词|仅输出提示词|只出提示词|纯提示词|结构化提示词|仅输出",
        re.IGNORECASE,
    )
    render_pat = re.compile(
        r"(?<![a-z0-9_.-])tool_render(?![a-z0-9_.-])|"
        r"直接调用工具渲染成片|调用工具渲染成片|直接调用工具渲染|直接渲染成片|调用工具渲染|渲染成片|直接渲染",
        re.IGNORECASE,
    )
    chosen_pat, opp_pat = (prompt_pat, render_pat) if mode == "prompt_only" else (render_pat, prompt_pat)
    if not _cue_has_affirmative(clauses, chosen_pat) or _cue_has_negated(clauses, chosen_pat):
        return False
    if _cue_has_affirmative(clauses, opp_pat):
        return False
    return True


def model_gate_errors(drama: dict[str, Any]) -> list[str]:
    """Errors of the recorded gate; [] when all four choices are locked with the user's own words."""
    record = drama.get("model_gate")
    if not isinstance(record, dict) or not record:
        return ["MODEL_GATE_MISSING"]
    if drama.get("sop_version") == "3.0":
        required = intake_choices.required_choices(record.get("delivery_mode"))
        errors = [f"MODEL_GATE_INCOMPLETE:{key}" for key in required if not record.get(key)]
        if intake_choices.is_video_only(record.get("image_model")):
            errors.append("VIDEO_ONLY_IMAGE_MODEL")
        if record.get("delivery_mode") not in intake_choices.MODES:
            errors.append("MODEL_GATE_DELIVERY_MODE_INVALID")
        if "creative_mode" in record and intake_choices.normalize_creative(record.get("creative_mode")) not in intake_choices.CREATIVE:
            errors.append("MODEL_GATE_CREATIVE_MODE_INVALID")
        if "aspect_ratio" in record and not valid_aspect_ratio(record.get("aspect_ratio")):
            errors.append("MODEL_GATE_ASPECT_RATIO_INVALID")
        if is_placeholder(record.get("user_words")):
            errors.append("MODEL_GATE_USER_WORDS_INVALID")
        if not record.get("confirmed_at"):
            errors.append("MODEL_GATE_INCOMPLETE:confirmed_at")
        return errors
    errors = [err for name in GATE_FIELDS for err in field_errors(record, name)]
    words = record.get("user_words")
    if not isinstance(words, str) or not words.strip() or is_placeholder(words):
        errors.append("MODEL_GATE_USER_WORDS_INVALID")
    elif not user_words_bound(record, words.strip(), drama):
        errors.append("MODEL_GATE_USER_WORDS_UNBOUND")
    if not isinstance(record.get("confirmed_at"), str) or not record["confirmed_at"].strip():
        errors.append("MODEL_GATE_INCOMPLETE:confirmed_at")
    return errors


def model_gate_execution_errors(
    drama: dict[str, Any],
    resolved_video_model: str | None = None,
    intent_ratio: str | None = None,
) -> list[str]:
    """Cross-check a locked model gate against release_intent.aspect_ratio and the actual adapter model."""
    record = drama.get("model_gate")
    if not isinstance(record, dict) or not record or model_gate_errors(drama):
        return []
    errors: list[str] = []
    locked_ratio = str(record.get("aspect_ratio") or "").strip()
    if locked_ratio and isinstance(intent_ratio, str) and intent_ratio.strip() and locked_ratio != intent_ratio.strip():
        errors.append(f"MODEL_GATE_ASPECT_RATIO_MISMATCH:{locked_ratio}!={intent_ratio.strip()}")
    if isinstance(resolved_video_model, str) and resolved_video_model.strip():
        allowed = {tok.casefold() for tok in allowed_models(record.get("video_model"))}
        if drama.get("sop_version") == "3.0":
            for chosen in tuple(allowed):
                if chosen in intake_choices.VIDEO_MODELS:
                    allowed.update(m.casefold() for m in (intake_choices.VIDEO_MODELS[chosen], *intake_choices.ALTERNATES.get(chosen, ())))
        if resolved_video_model.strip().casefold() not in allowed:
            errors.append(f"MODEL_GATE_VIDEO_MODEL_MISMATCH:{resolved_video_model.strip()}!={record.get('video_model')}")
    return errors


def delivery_mode(drama: dict[str, Any]) -> str | None:
    record = drama.get("model_gate")
    return record.get("delivery_mode") if isinstance(record, dict) else None


def options_for(rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [{"label": row["name"], "value": row["name"], "status": row["status"]}
            for row in rows if kind in row["kinds"]]


def build_questions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    audio = [*({"label": f"BGM：{o['label']}", "value": f"bgm:{o['value']}", "status": o["status"]}
               for o in options_for(rows, "audio")),
             *({"label": f"配音与音效：{o['label']}", "value": f"tts_sfx:{o['value']}", "status": o["status"]}
               for o in options_for(rows, "audio")),
             {"label": "本项目无需生成音频", "value": "none", "status": "—"}]
    return [
        {"id": "image_model", "question": "① 图片生成模型（必选）", "required": True,
         "options": options_for(rows, "image"), "allow_custom": True},
        {"id": "video_model", "question": "② 视频生成模型（必选）", "required": True,
         "options": options_for(rows, "video"), "allow_custom": True},
        {"id": "audio_plan", "question": "③ 音频方案（必选：BGM 模型 / 配音与音效模型 / 本项目无需生成音频，可组合）",
         "required": True, "options": audio, "allow_custom": True},
        {"id": "global_spec", "question": "④ 全局规格与交付模式（必选：画幅比例、总时长与镜头节奏、风格基调、交付模式）",
         "required": True, "allow_custom": True,
         "fields": [
             {"id": "aspect_ratio", "label": "画幅比例（由发布平台推导，未定平台时 16:9 通用母版仅为候选）"},
             {"id": "pacing", "label": "总时长与镜头节奏"},
             {"id": "style_tone", "label": "风格基调"},
             {"id": "delivery_mode", "label": "交付模式",
              "options": [{"label": "仅输出结构化提示词", "value": "prompt_only"},
                          {"label": "直接调用工具渲染成片", "value": "tool_render"}]},
         ]},
    ]


def ask_question_payload(rows: list[dict[str, Any]], nonce: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "ask_question", "gate": "human_gate_1_model_gate", "stop_and_wait": True,
        "no_default": True, "questions": build_questions(rows),
        "record_with": "python3 scripts/drama_setup.py model-gate --project <dir> --image-model ... "
                       "--video-model ... --audio-plan ... --delivery-mode ... --aspect-ratio ... "
                       "--pacing ... --style-tone ... --user-words \"<用户原话>\"",
    }
    if nonce:
        payload["nonce"] = nonce
    return payload


def render_markdown(rows: list[dict[str, Any]], nonce: str | None = None) -> str:
    lines = ["### 模型门禁（Human Gate #1 · STOP & WAIT）", ""]
    for question in build_questions(rows):
        lines.append(f"**{question['question']}**")
        for number, option in enumerate(question.get("options", []), start=1):
            lines.append(f"{number}. {option['label']}（{option['status']}）")
        for field in question.get("fields", []):
            choices = " / ".join(o["label"] for o in field.get("options", []))
            lines.append(f"- {field['label']}" + (f"：{choices}" if choices else "：请填写"))
        lines.append("")
    if nonce:
        lines.append(f"门禁会话标识：`{nonce}`（用户回复中可附带或直接点名所选模型与规格）")
    lines.append("可直接写其他模型名；凭证只报名字与 present/missing，不回显值。")
    lines.append(STOP_LINE)
    return "\n".join(lines)


def detected_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    roots = args.skills_root or list(providers.DEFAULT_SKILLS_ROOTS)
    env_files = [] if args.no_env_file else (args.env_file or list(providers.DEFAULT_ENV_FILES))
    return providers.build_rows(providers.collect_env_file_names(env_files), providers.collect_skill_dir_names(roots))


def record_rendered_nonce(project: Path | None) -> str | None:
    if project is None:
        return None
    target = project.expanduser()
    if not manifest_path(target).is_file():
        return None
    nonce = f"MG-{secrets.token_hex(3).upper()}"

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        drama = drama_block(manifest)
        shown = {**section(drama, "presentations"), "model_gate": {"nonce": nonce, "rendered_at": now_iso()}}
        return {**manifest, "drama": {**drama, "presentations": shown}}
    update_manifest(target, mutate)
    return nonce


def cmd_render(args: argparse.Namespace) -> int:
    if args.project and manifest_path(args.project.expanduser()).is_file():
        project = args.project.expanduser()
        manifest = load_manifest(project)
        drama = drama_block(manifest)
        if drama.get("sop_version") == "3.0":
            resolution = section(drama, "choice_resolution") or intake_choices.initial_menu(manifest)
            if args.format in {"markdown", "both"}:
                if resolution["missing"]:
                    for question in resolution["numbered_menu"]:
                        print(question["field"].replace("_", " "))
                        for option in question["options"]:
                            print(f"{option['number']}. {option['value']}")
                else:
                    print("All required choices are resolved.")
            if args.format in {"ask-question-json", "both"}:
                print(json.dumps(resolution["host_selector_payload"], ensure_ascii=False, indent=2))
            return 0
    rows = detected_rows(args)
    nonce = record_rendered_nonce(args.project)
    if args.format == "ask-question-json":
        print(json.dumps(ask_question_payload(rows, nonce), ensure_ascii=False, indent=2))
    elif args.format == "both":
        print(render_markdown(rows, nonce))
        print("\n```json\n" + json.dumps(ask_question_payload(rows, nonce), ensure_ascii=False, indent=2) + "\n```")
    else:
        print(render_markdown(rows, nonce))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    try:
        manifest = load_manifest(args.project.expanduser())
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 3
    drama = drama_block(manifest)
    intent_ratio = section(drama, "release_intent").get("aspect_ratio")
    errors = model_gate_errors(drama) + model_gate_execution_errors(drama, None, intent_ratio)
    print(json.dumps({"ok": not errors, "required": gate_required(drama), "errors": errors,
                      "next": "" if not errors else "python3 scripts/model_gate.py render, show it, STOP & WAIT"},
                     ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="Exit codes: 0 ok; 1 gate incomplete; 3 file or JSON error.")
    commands = parser.add_subparsers(dest="command", required=True)
    resolver = commands.add_parser("resolve", help="resolve current instructions and project choices")
    intake_choices.add_arguments(resolver)
    resolver.add_argument("--project", type=Path)
    resolver.add_argument("--json", action="store_true")
    resolver.set_defaults(handler=intake_choices.cli)
    render = commands.add_parser("render", help="print the four-choice menu / ask_question JSON")
    render.add_argument("--project", type=Path, help="optional project dir to bind a render nonce")
    render.add_argument("--format", choices=("markdown", "ask-question-json", "both"), default="markdown")
    render.add_argument("--skills-root", action="append", default=None, metavar="PATH")
    render.add_argument("--env-file", action="append", default=None, metavar="PATH")
    render.add_argument("--no-env-file", action="store_true")
    render.set_defaults(handler=cmd_render)
    check = commands.add_parser("check", help="validate drama.model_gate of a project")
    check.add_argument("--project", required=True, type=Path)
    check.set_defaults(handler=cmd_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
