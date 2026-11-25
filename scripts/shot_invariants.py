#!/usr/bin/env python3
"""Per-shot invariants for R1 (actors vs headcount), R4 (screen/UI cue) and prop-state continuity.

Library only. Keyword and number patterns only trigger an explicit declaration (`crowd_count` or
`screen_ui`); they never prescribe prompt wording or sentence structure.
"""
from __future__ import annotations

import re
from typing import Any

from drama_project import nonempty

PROPS_KEYS = frozenset({"in", "out"})
BEAT_SCENE_RE = re.compile(r"^(?P<scene>[A-Za-z][A-Za-z0-9_]*)-B\d+[A-Za-z0-9_]*$")
SHOT_SCENE_RE = re.compile(r"^(?P<scene>S\d+)[_-]")

EN_NUMBERS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "dozen": 12, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "hundred": 100, "thousand": 1000,
}
ZH_NUMBERS = {"两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
              "十": 10, "百": 100, "千": 1000}

EN_HEADCOUNT_RE = re.compile(
    r"\b(?P<num>two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|dozen|twenty|thirty|forty|fifty|"
    r"hundred|thousand|[2-9]|[1-9]\d+)\b"
    r"(?![\s-]*(?:year|minute|second|hour|day|week|month|shot|quarter|percent|time|mm|cm|m|km|fps|p|k)\b)"
    r"(?:\s+(?!(?:is|are|was|were|and|or|in|on|at|with|of|to|from|for|by|as|who|that|image)\b)[a-z][a-z-]*){0,2}"
    r"\s+(?P<noun>board\s+members|people|persons|men|women|members|guards|officers|police|policemen|"
    r"executives|directors|engineers|analysts|reporters|journalists|protesters|gamers|crowds?|bystanders|"
    r"onlookers|strangers|figures|silhouettes|assistants|soldiers|workers|employees|guests|visitors|actors)\b",
    re.IGNORECASE,
)

ZH_HEADCOUNT_RE = re.compile(
    r"(?<!第)(?P<num>[两二三四五六七八九十百千]+|[2-9]|[1-9]\d+)\s*(?:名|个|位|群)"
    r"(?:[\u4e00-\u9fff]{0,4}?)"
    r"(?P<noun>人头|路人|警察|保安|董事|高管|记者|群众|人群|员工|工程师|分析师|保镖|观众|身影|男人|女人|男子|女子|群演|人)"
)

NEGATED_UI_RE = re.compile(
    r"\bno\s+(?:on-screen\s+text|text\s+overlays?|subtitles|captions|overlaid\s+ui(?:\s+watermarks?)?|"
    r"ui\s+watermarks?)\b|无字幕|不加字幕|无屏幕字",
    re.IGNORECASE,
)

EN_SCREEN_CUE_RE = re.compile(
    r"(?<!on-)(?<!off-)(?<!wide)(?<!sun)(?<!wind)(?<!smoke\s)\b(?:"
    r"screens?|flatscreens?|touchscreens?|popups?|pop-ups?|modals?|dialog\s+box(?:es)?|taskbars?|hud|ui|"
    r"(?:app|user|web|digital)\s+interfaces?|smartphones?|cellphones?|iphones?|mobile\s+phones?|"
    r"(?:pc|wall|led|desk|computer|wide|studio)\s+monitors?|monitors|"
    r"(?:digital\s+|diagnostics?\s+|display\s+)?tablets?|led\s+tickers?|marquees?"
    r")\b",
    re.IGNORECASE,
)

ZH_SCREEN_CUE_RE = re.compile(
    r"(?:屏幕|大屏|巨幕|显示器|弹窗|界面|手机|平板电脑|故障平板|电脑屏|直播屏|监控屏|任务栏|报错框|状态栏|K线屏|LED屏)"
)


def valid_nonneg_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def parse_zh_num(token: str) -> int:
    if token.isdigit():
        return int(token)
    if len(token) == 1:
        return ZH_NUMBERS.get(token, 0)
    total = 0
    cur = 0
    for ch in token:
        val = ZH_NUMBERS.get(ch, 0)
        if val >= 10:
            total += max(1, cur) * val
            cur = 0
        else:
            cur = val
    return total + cur


def detected_headcounts(prompt: str) -> list[int]:
    counts = [EN_NUMBERS.get(m.group("num").lower()) or int(m.group("num"))
              for m in EN_HEADCOUNT_RE.finditer(prompt)]
    counts += [parse_zh_num(m.group("num")) for m in ZH_HEADCOUNT_RE.finditer(prompt)]
    return [n for n in counts if n >= 2]


def check_actors_and_headcount(shot: dict[str, Any], generated: bool) -> list[str]:
    sid = shot["id"]
    errors: list[str] = []
    has_valid_actors = False
    if "actors" in shot:
        actors = shot["actors"]
        if (not isinstance(actors, list) or any(not nonempty(a) for a in actors)
                or len(set(actors)) != len(actors)):
            errors.append(f"INVALID_ACTORS:{sid}")
        else:
            has_valid_actors = True
    if "crowd_count" in shot and not valid_nonneg_int(shot["crowd_count"]):
        errors.append(f"INVALID_CROWD_COUNT:{sid}")
    count = shot.get("actor_count")
    if has_valid_actors and valid_nonneg_int(count) and len(shot["actors"]) != count:
        errors.append(f"SHOT_ACTOR_COUNT_MISMATCH:{sid}:{len(shot['actors'])}!={count}")
    if generated and valid_nonneg_int(count):
        crowd = shot["crowd_count"] if valid_nonneg_int(shot.get("crowd_count")) else 0
        allowed = int(count) + int(crowd)
        over = [n for n in detected_headcounts(str(shot.get("prompt", ""))) if n > allowed]
        if over:
            errors.append(f"PROMPT_HEADCOUNT_EXCEEDS_ACTORS:{sid}:{max(over)}>{allowed}")
    return errors


def mentions_screen_or_ui(shot: dict[str, Any]) -> bool:
    line = shot.get("line", "")
    line_text = " ".join(line) if isinstance(line, list) else str(line)
    cleaned = NEGATED_UI_RE.sub(" ", f"{line_text}\n{shot.get('prompt', '')}")
    return bool(EN_SCREEN_CUE_RE.search(cleaned) or ZH_SCREEN_CUE_RE.search(cleaned))


def _valid_prop_map(value: object) -> bool:
    return (isinstance(value, dict)
            and all(nonempty(k) and nonempty(v) for k, v in value.items()))


def check_props_state(shot: dict[str, Any]) -> list[str]:
    sid = shot["id"]
    errors: list[str] = []
    if "props_state" in shot:
        props = shot["props_state"]
        if (not isinstance(props, dict) or not set(props) <= PROPS_KEYS
                or any(not _valid_prop_map(props[k]) for k in props)):
            errors.append(f"INVALID_PROPS_STATE:{sid}")
    if "continuity_break" in shot and not isinstance(shot["continuity_break"], bool):
        errors.append(f"INVALID_CONTINUITY_BREAK:{sid}")
    return errors


def shot_scene_key(shot: dict[str, Any]) -> str | None:
    if nonempty(shot.get("scene")):
        return str(shot["scene"]).strip()
    beats = shot.get("beats")
    first_beat = beats[0] if isinstance(beats, list) and beats and nonempty(beats[0]) else shot.get("beat")
    if nonempty(first_beat):
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", str(first_beat)):
            match = BEAT_SCENE_RE.match(token)
            if match:
                return match.group("scene")
    sid = shot.get("id")
    if nonempty(sid):
        match = SHOT_SCENE_RE.match(str(sid))
        if match:
            return match.group("scene")
    return None


def check_props_continuity(active_rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for prev, curr in zip(active_rows, active_rows[1:]):
        if curr.get("continuity_break") is True:
            continue
        prev_scene, curr_scene = shot_scene_key(prev), shot_scene_key(curr)
        if not prev_scene or prev_scene != curr_scene:
            continue
        prev_props, curr_props = prev.get("props_state"), curr.get("props_state")
        prev_out = prev_props.get("out") if isinstance(prev_props, dict) else None
        curr_in = curr_props.get("in") if isinstance(curr_props, dict) else None
        if not (_valid_prop_map(prev_out) and _valid_prop_map(curr_in)):
            continue
        for key in sorted(set(prev_out) & set(curr_in)):
            if prev_out[key] != curr_in[key]:
                errors.append(f"PROP_CONTINUITY_MISMATCH:{prev['id']}->{curr['id']}:"
                              f"{key}:{prev_out[key]}!={curr_in[key]}")
    return errors

