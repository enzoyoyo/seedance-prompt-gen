#!/usr/bin/env python3
"""Subtitle cues timed from word timestamps. Library for burn_chinese_subtitles.py.

A cue is {"start", "end", "lines": [...]}: one line per language, in the order of the project's
translation pairs. Timing comes from where the spoken words were actually heard in each source
clip, shifted onto the cut by the assembler's timeline; nothing is spaced by guesswork.
"""
from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from check_script_coverage import spec_segments
from check_spoken_lines import asr_model_args, require_asr, run_asr_json, spoken_text, words
from drama_project import ProjectError, read_json
from validate_shot_spec import shot_rows

Word = tuple[str, float, float]


def heard_words(payload: Any) -> list[Word]:
    """Comparable tokens with times, from a transcript JSON carrying segments[].words[]."""
    result: list[Word] = []
    segments = payload.get("segments") if isinstance(payload, dict) else None
    for segment in segments if isinstance(segments, list) else []:
        for row in segment.get("words") or []:
            result.extend((token, float(row["start"]), float(row["end"])) for token in words(str(row.get("word", ""))))
    return result


def load_words(clip: Path, asr_dir: Path, binary: str, extra: list[str], model: str | None = None) -> list[Word]:
    """Word timings for one source clip: the cached transcript, else a fresh ASR run kept in the cache."""
    cached = asr_dir / f"{clip.stem}.json"
    if not cached.is_file():
        require_asr(binary)
    payload = read_json(cached) if cached.is_file() else run_asr_json(
        clip, binary, [*asr_model_args(model, extra), "--word_timestamps", "True", *extra], keep_in=asr_dir)
    found = heard_words(payload)
    if not found and payload.get("segments"):
        raise ProjectError("ASR_WITHOUT_WORD_TIMESTAMPS", cached.name)
    return found


def shot_texts(spec: dict[str, Any], translations: Any, spoken_column: int) -> dict[str, list[dict[str, Any]]]:
    """Per shot: the lines to show and the words that are spoken, from the translation table or the spec."""
    if isinstance(translations, dict):
        return {shot_id: [{"lines": list(pair), "spoken": pair[spoken_column]} for pair in pairs]
                for shot_id, pairs in translations.items() if not shot_id.startswith("_")}
    texts = {}
    for shot in shot_rows(spec):
        segments = [spoken_text(segment) for segment in spec_segments(shot)]
        texts[shot["id"]] = [{"lines": [text], "spoken": text} for text in segments if text.strip()]
    return texts


def align_cues(texts: list[dict[str, Any]], heard: list[Word]) -> list[dict[str, Any] | None]:
    """Each cue's first and last heard word; None when none of its words were heard in order."""
    tokens, owner = [], []
    for index, text in enumerate(texts):
        cue_tokens = words(text["spoken"])
        tokens += cue_tokens
        owner += [index] * len(cue_tokens)
    spans: dict[int, list[int]] = {}
    matcher = difflib.SequenceMatcher(a=tokens, b=[word[0] for word in heard], autojunk=False)
    for block in matcher.get_matching_blocks():
        for step in range(block.size):
            spans.setdefault(owner[block.a + step], []).append(block.b + step)
    return [{"lines": text["lines"], "start": heard[min(spans[index])][1], "end": heard[max(spans[index])][2]}
            if index in spans else None for index, text in enumerate(texts)]


def place(cue: dict[str, Any], row: dict[str, Any], lead: float, tail: float) -> dict[str, Any]:
    """Move a clip-relative cue onto the cut timeline, clamped to the clip's slot."""
    offset, start, length = float(row.get("offset") or 0), float(row["start"]), float(row["duration"])
    begin = min(max(cue["start"] - offset - lead, 0.0), length)
    end = min(max(cue["end"] - offset + tail, begin), length)
    return {"start": round(start + begin, 3), "end": round(start + end, 3), "lines": cue["lines"]}


def parse_shot_cues(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """Validate and normalise manual clip-relative cues: {spec_id: [{start, end, text|lines}]}."""
    if not isinstance(payload, dict):
        raise ProjectError("SHOT_CUES_INVALID", "top-level must be an object")
    out: dict[str, list[dict[str, Any]]] = {}
    for shot_id, rows in payload.items():
        if not isinstance(shot_id, str) or not shot_id.strip() or not isinstance(rows, list):
            raise ProjectError("SHOT_CUES_INVALID", str(shot_id))
        parsed: list[dict[str, Any]] = []
        for idx, item in enumerate(rows):
            start = item.get("start") if isinstance(item, dict) else None
            end = item.get("end") if isinstance(item, dict) else None
            num_ok = (isinstance(start, (int, float)) and not isinstance(start, bool)
                      and isinstance(end, (int, float)) and not isinstance(end, bool)
                      and 0 <= float(start) < float(end))
            lines = cue_lines(item) if isinstance(item, dict) else []
            if not num_ok or not lines:
                raise ProjectError("SHOT_CUES_INVALID", f"{shot_id}:{idx}")
            parsed.append({"start": float(start), "end": float(end), "lines": lines})
        out[shot_id] = parsed
    return out


def build_cues(timeline: list[dict[str, Any]], texts: dict[str, list[dict[str, Any]]],
               words_for: Any, lead: float = 0.0, tail: float = 0.0,
               manual_cues: dict[str, list[dict[str, Any]]] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Cues on the cut timeline and the list of cues whose words were not heard."""
    cues, unaligned = [], []
    for row in timeline:
        shot_id = row.get("spec_id")
        if manual_cues and shot_id in manual_cues:
            cues.extend(place(cue, row, lead, tail) for cue in manual_cues[shot_id])
            continue
        wanted = texts.get(shot_id) or []
        if not wanted:
            continue
        for index, cue in enumerate(align_cues(wanted, words_for(row))):
            if cue is None:
                unaligned.append(f"CUE_NOT_ALIGNED:{shot_id}:{index}")
            else:
                cues.append(place(cue, row, lead, tail))
    return sorted(cues, key=lambda cue: cue["start"]), unaligned


def srt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    return f"{millis // 3600000:02d}:{millis // 60000 % 60:02d}:{millis // 1000 % 60:02d},{millis % 1000:03d}"


def cue_lines(cue: dict[str, Any], show: list[int] | None = None) -> list[str]:
    lines = cue["lines"] if isinstance(cue.get("lines"), list) else [cue.get("text", "")]
    picked = [lines[index] for index in show if index < len(lines)] if show else lines
    return [line for line in picked if isinstance(line, str) and line.strip()]


def srt_text(cues: list[dict[str, Any]], show: list[int] | None = None) -> str:
    blocks = [f"{number}\n{srt_time(float(cue['start']))} --> {srt_time(float(cue['end']))}\n" + "\n".join(cue_lines(cue, show))
              for number, cue in enumerate(cues, start=1)]
    return "\n\n".join(blocks) + "\n"
