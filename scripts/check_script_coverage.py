#!/usr/bin/env python3
"""Check that shots cover a beat-tagged script: every beat shot, every line verbatim,
right speaker, right beat, right order.

Two inputs are accepted: NBP v2 shot files (--shots), or one shot spec (--spec, see
references/shot-spec.md). With a spec, the lines must be the script's own words; when the film
is spoken in another language, --translations registers source/target pairs and the spec is
checked against that table instead of being trusted."""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from validate_nbp_prompt import parse_dialogue_line
from validate_shot_spec import active_shots, root_id, shot_beats, shot_rows

BEAT_RE = re.compile(r"^(?P<action>△\s*)?\[(?P<id>[A-Za-z][A-Za-z0-9_-]*)\]\s*(?P<rest>.*)$")
# A speaker label is a name, not a clause: sentence punctuation means it is prose with a colon.
SPEAKER_MAX_CHARS = 20
SPEAKER_BREAK_RE = re.compile(r"[，。,.!?！？、；;]")
# Labelled production notes inside a beat are not spoken lines.
NON_SPEAKER_LABELS = {"字幕", "画面", "镜头", "音效", "环境声", "音乐", "bgm", "注", "备注", "场景", "人物", "时间", "地点"}
QUOTE_RE = re.compile(r"[「」『』“”\"'‘’\s]")
# Markdown emphasis around a speaker label or a stressed word is typography, not script text.
EMPHASIS_RE = re.compile(r"\*\*|__")
# Spec lines: several speakers in one shot are written "A: words / B: words".
SEGMENT_SPLIT_RE = re.compile(r"\s+/\s+")
SEGMENT_LABEL_RE = re.compile(r"^\s*[^:：/]{1,20}[:：]\s*")
# A segment that is wholly parenthesised is a note such as "(no dialogue)", not spoken words.
SEGMENT_NOTE_RE = re.compile(r"^\s*[(（][^)）]*[)）]\s*$")


def normalize(words: str) -> str:
    return QUOTE_RE.sub("", unicodedata.normalize("NFKC", words))


def script_line(text: str) -> tuple[str, str] | None:
    """Return (speaker, words) for a dialogue line; action lines start with △, directives with 【."""
    if text.startswith(("△", "【")):
        return None
    parsed = parse_dialogue_line(EMPHASIS_RE.sub("", text))
    if parsed is None:
        return None
    speaker, _, words = parsed
    if (
        len(speaker) > SPEAKER_MAX_CHARS
        or SPEAKER_BREAK_RE.search(speaker)
        or speaker.casefold() in NON_SPEAKER_LABELS
    ):
        return None
    return speaker, words


def parse_script(text: str) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """Beats in order, dialogue lines in order, and format errors.

    Lines before the first [beat-id] after a heading are scene header and are ignored.
    """
    beats: list[str] = []
    lines: list[dict[str, str]] = []
    errors: list[str] = []
    current: str | None = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            current = None
            continue
        match = BEAT_RE.match(stripped)
        if match:
            current = match.group("id")
            if current in beats:
                errors.append(f"DUPLICATE_BEAT_ID:{current}")
            else:
                beats.append(current)
            if match.group("action"):
                continue
            stripped = match.group("rest").strip()
        if current is None or not stripped:
            continue
        parsed = script_line(stripped)
        if parsed:
            speaker, words = parsed
            lines.append({"beat": current, "speaker": speaker, "words": words})
    if not beats:
        errors.append("SCRIPT_NO_BEAT_IDS")
    return beats, lines, errors


def shot_lines(shot: dict[str, Any]) -> list[tuple[str, str] | None]:
    audio = shot.get("audio")
    dialogue = audio.get("dialogue") if isinstance(audio, dict) else None
    if not isinstance(dialogue, list):
        return []
    result: list[tuple[str, str] | None] = []
    for line in dialogue:
        parsed = parse_dialogue_line(line) if isinstance(line, str) else None
        result.append((parsed[0], parsed[2]) if parsed else None)
    return result


def check_coverage(
    script_text: str, shots: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    beats, lines, errors = parse_script(script_text)
    warnings: list[str] = []
    beat_set = set(beats)
    covered_beats: set[str] = set()
    matched: set[int] = set()
    last_index = -1

    for name, shot in shots:
        script_ref = shot.get("script_ref")
        source_beats = script_ref.get("source_beats") if isinstance(script_ref, dict) else None
        if not isinstance(source_beats, list) or not source_beats:
            errors.append(f"SHOT_UNREFERENCED:{name}")
            source_beats = []
        for beat in source_beats:
            if beat in beat_set:
                covered_beats.add(beat)
            else:
                errors.append(f"UNKNOWN_BEAT:{name}:{beat}")

        for position, parsed in enumerate(shot_lines(shot)):
            if parsed is None:
                errors.append(f"UNATTRIBUTED_LINE:{name}:audio.dialogue[{position}]")
                continue
            speaker, words = parsed
            key = normalize(words)
            candidates = [i for i, line in enumerate(lines) if normalize(line["words"]) == key]
            in_beat = [i for i in candidates if lines[i]["beat"] in source_beats]
            if not candidates:
                errors.append(f"EXTRA_LINE:{name}:{speaker}：{words}")
                continue
            if not in_beat:
                expected_beats = ",".join(sorted({lines[i]["beat"] for i in candidates}))
                errors.append(f"LINE_BEAT_MISMATCH:{name}:{words}:{expected_beats}")
                continue
            fresh = [i for i in in_beat if i not in matched]
            if not fresh:
                # Coverage (master + close-up) legitimately repeats a line; the edit keeps one.
                warnings.append(f"DUPLICATE_LINE:{name}:{words}")
                continue
            index = fresh[0]
            expected_speaker = lines[index]["speaker"]
            if speaker.strip().casefold() != expected_speaker.casefold():
                errors.append(f"SPEAKER_MISMATCH:{name}:{words}:{speaker}!={expected_speaker}")
            if index < last_index:
                errors.append(f"ORDER_MISMATCH:{name}:{words}")
            matched.add(index)
            last_index = max(last_index, index)

    for beat in beats:
        if beat not in covered_beats:
            errors.append(f"UNCOVERED_BEAT:{beat}")
    for index, line in enumerate(lines):
        if index not in matched:
            errors.append(f"MISSING_LINE:{line['beat']}:{line['speaker']}：{line['words']}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "beats": len(beats),
            "covered_beats": len(covered_beats),
            "lines": len(lines),
            "matched_lines": len(matched),
            "shots": len(shots),
        },
    }


def fold_words(text: str) -> str:
    """Letters and digits only, case-folded: punctuation, quotes and spacing never count as a change."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold() if ch.isalnum())


def spec_segments(shot: dict[str, Any]) -> list[str]:
    line = shot.get("line")
    if isinstance(line, list):
        return [item for item in line
                if isinstance(item, str) and item.strip() and not SEGMENT_NOTE_RE.match(item)]
    if isinstance(line, str) and line.strip():
        parts = SEGMENT_SPLIT_RE.split(line)
        return [part for part in parts if part.strip() and not SEGMENT_NOTE_RE.match(part)]
    return []


def fit_segment(segment: str, allowed: str) -> str | None:
    """Folded words of a segment if they occur in `allowed`; a leading speaker label is dropped only
    when the whole segment does not fit (a spoken line may itself contain a colon)."""
    for candidate in (fold_words(segment), fold_words(SEGMENT_LABEL_RE.sub("", segment, count=1))):
        if candidate and candidate in allowed:
            return candidate
    return None


def translation_pairs(table: object, rows: list[dict[str, Any]], beats: list[str],
                      errors: list[str]) -> list[dict[str, Any]]:
    """Normalise a pair table: [{beat, source, target}] or {shot_id: [[source, target], ...]}."""
    active = active_shots(rows)
    pairs: list[dict[str, Any]] = []
    if isinstance(table, list):
        for index, row in enumerate(table):
            if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ("beat", "source", "target")):
                errors.append(f"TRANSLATION_ROW_INVALID:{index}")
                continue
            pairs.append({"key": row["beat"], "beats": [row["beat"]], "shot": None,
                          "source": row["source"], "target": row["target"]})
        return pairs
    if not isinstance(table, dict):
        errors.append("TRANSLATION_TABLE_INVALID")
        return pairs
    for key, entries in table.items():
        if key.startswith("_"):
            continue
        root = root_id(rows, key)
        shot = next((row for row in active if root_id(rows, row["id"]) == root), None)
        if shot is None or not isinstance(entries, list):
            errors.append(f"TRANSLATION_UNKNOWN_SHOT:{key}")
            continue
        for entry in entries:
            # [script words, spoken words] or, when the user decided to word a subtitle differently
            # in post, [script words, spoken words, shown subtitle]; the gate checks the first two.
            if not isinstance(entry, list) or len(entry) not in (2, 3) or not all(isinstance(x, str) for x in entry):
                errors.append(f"TRANSLATION_ROW_INVALID:{key}")
                continue
            pairs.append({"key": key, "beats": shot_beats(shot, beats), "shot": shot["id"],
                          "source": entry[0], "target": entry[1]})
    return pairs


def check_beat_coverage(spec: dict[str, Any], active: list[dict[str, Any]], beats: list[str],
                        errors: list[str]) -> dict[str, list[dict[str, Any]]]:
    covering: dict[str, list[dict[str, Any]]] = {beat: [] for beat in beats}
    for shot in active:
        found = shot_beats(shot, beats)
        if not found:
            errors.append(f"SHOT_UNREFERENCED:{shot['id']}")
        for beat in found:
            if beat in covering:
                covering[beat].append(shot)
            else:
                errors.append(f"UNKNOWN_BEAT:{shot['id']}:{beat}")
    post = [beat for beat in spec.get("post_beats", []) if isinstance(beat, str)]
    errors.extend(f"UNKNOWN_BEAT:post_beats:{beat}" for beat in post if beat not in covering)
    errors.extend(f"UNCOVERED_BEAT:{beat}" for beat in beats if not covering[beat] and beat not in post)
    return covering


def check_spec_lines(active: list[dict[str, Any]], beats: list[str], lines: list[dict[str, str]],
                     pairs: list[dict[str, Any]] | None, errors: list[str]) -> int:
    """Every spec line is script text (or a registered translation of it), and no script line is lost."""
    script_by_beat = {beat: [line for line in lines if line["beat"] == beat] for beat in beats}
    spoken: dict[str, list[str]] = {shot["id"]: [] for shot in active}
    shot_ids_by_beat: dict[str, list[str]] = {beat: [] for beat in beats}
    for shot in active:
        own_beats = shot_beats(shot, beats)
        for beat in own_beats:
            shot_ids_by_beat.setdefault(beat, []).append(shot["id"])
        if pairs is None:
            allowed = "".join(fold_words(line["words"]) for beat in own_beats for line in script_by_beat.get(beat, []))
            code = "LINE_NOT_IN_SCRIPT"
        else:
            allowed = "".join(fold_words(pair["target"]) for pair in pairs
                              if pair["shot"] == shot["id"] or (pair["shot"] is None and set(pair["beats"]) & set(own_beats)))
            code = "LINE_NOT_IN_TRANSLATION"
        for segment in spec_segments(shot):
            fitted = fit_segment(segment, allowed)
            if fitted is None:
                errors.append(f"{code}:{shot['id']}:{segment}")
            else:
                spoken[shot["id"]].append(fitted)
    for pair in pairs or []:
        source_pool = "".join(fold_words(line["words"]) for beat in pair["beats"] for line in script_by_beat.get(beat, []))
        if fold_words(pair["source"]) not in source_pool:
            errors.append(f"TRANSLATION_SOURCE_NOT_IN_SCRIPT:{pair['key']}:{pair['source']}")
        shot_ids = [pair["shot"]] if pair["shot"] else [sid for beat in pair["beats"] for sid in shot_ids_by_beat.get(beat, [])]
        if fold_words(pair["target"]) not in "".join(part for sid in shot_ids for part in spoken.get(sid, [])):
            errors.append(f"TRANSLATED_LINE_NOT_IN_SHOT:{pair['key']}:{pair['target']}")
    matched = 0
    for beat in beats:
        if pairs is None:
            pool = "".join(part for sid in shot_ids_by_beat[beat] for part in spoken[sid])
        else:
            pool = "".join(fold_words(pair["source"]) for pair in pairs if beat in pair["beats"])
        for line in script_by_beat[beat]:
            if fold_words(line["words"]) in pool:
                matched += 1
            else:
                errors.append(f"MISSING_LINE:{beat}:{line['speaker']}：{line['words']}")
    return matched


def check_spec_coverage(script_text: str, spec: dict[str, Any], translations: object = None) -> dict[str, Any]:
    """Coverage of a locked script by a shot spec; superseded shots do not count."""
    beats, lines, errors = parse_script(script_text)
    rows = [row for row in shot_rows(spec) if isinstance(row.get("id"), str)]
    active = active_shots(rows)
    covering = check_beat_coverage(spec, active, beats, errors)
    pairs = None if translations is None else translation_pairs(translations, rows, beats, errors)
    matched = check_spec_lines(active, beats, lines, pairs, errors)
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": [],
        "summary": {
            "beats": len(beats),
            "covered_beats": sum(1 for beat in beats if covering[beat] or beat in spec.get("post_beats", [])),
            "lines": len(lines),
            "matched_lines": matched,
            "shots": len(active),
            "translated": pairs is not None,
        },
    }


def load_object(path_arg: str) -> Any:
    path = Path(path_arg).expanduser()
    return path.name, json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Exit codes: 0 covered; 1 coverage or script format errors; 3 file/JSON error.",
    )
    parser.add_argument("--script", required=True, help="beat-tagged script (markdown or text)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--shots", nargs="+", help="NBP v2 shot JSON files in edit order")
    source.add_argument("--spec", help="shot spec JSON (references/shot-spec.md)")
    parser.add_argument("--translations", help="with --spec: source/target line pairs for a translated film")
    args = parser.parse_args()

    try:
        script_text = Path(args.script).expanduser().read_text(encoding="utf-8")
        if args.spec:
            name, spec = load_object(args.spec)
            if not isinstance(spec, dict):
                raise ValueError(f"{name} is not a JSON object")
            translations = load_object(args.translations)[1] if args.translations else None
            report = check_spec_coverage(script_text, spec, translations)
        else:
            shots = []
            for shot_path in args.shots:
                name, shot = load_object(shot_path)
                if not isinstance(shot, dict):
                    raise ValueError(f"{name} is not a JSON object")
                shots.append((name, shot))
            report = check_coverage(script_text, shots)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "errors": [f"INPUT_ERROR:{exc}"]}, ensure_ascii=False, indent=2))
        return 3

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
