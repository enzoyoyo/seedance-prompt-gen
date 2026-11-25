"""OpenTimelineIO JSON interchange for one contiguous video track at a fixed frame rate."""
import re
from fractions import Fraction

from drama_project import ProjectError, read_json, write_json_atomic


def rational(frames, rate):
    return {"OTIO_SCHEMA": "RationalTime.1", "value": frames, "rate": float(rate)}


def write(path, rows, rate):
    clips = []
    for row in rows:
        data = {k: row[k] for k in ("take_id", "source_hash", "source_in", "source_out", "timeline_in",
                                     "timeline_out", "transform", "audio_route")}
        data.update({k: row[k] for k in ("dialogue_stem", "dialogue_stem_hash") if k in row})
        reference = {"OTIO_SCHEMA": "ExternalReference.1", "name": "", "metadata": {},
                     "target_url": row["source"], "available_range": None}
        clips.append({"OTIO_SCHEMA": "Clip.2", "name": row["spec_id"] or "end card", "metadata": data,
                      "effects": [], "markers": [], "media_references": {"DEFAULT_MEDIA": reference},
                      "active_media_reference_key": "DEFAULT_MEDIA", "source_range": {
                          "OTIO_SCHEMA": "TimeRange.1", "start_time": rational(data["source_in"], rate),
                          "duration": rational(data["source_out"] - data["source_in"], rate)}})
    track = {"OTIO_SCHEMA": "Track.1", "name": "Cut", "kind": "Video", "metadata": {}, "effects": [],
             "markers": [], "source_range": None, "children": clips}
    stack = {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "metadata": {}, "effects": [], "markers": [],
             "source_range": None, "children": [track]}
    write_json_atomic(path, {"OTIO_SCHEMA": "Timeline.1", "name": path.stem, "metadata": {"rate": str(rate)},
                             "global_start_time": rational(0, rate), "tracks": stack})


def read(path, takes):
    data = read_json(path)
    try:
        tracks = data["tracks"]["children"]
        if len(tracks) != 1 or tracks[0]["kind"] != "Video":
            raise ValueError("expected one video track")
        clips = tracks[0]["children"]
        rate = Fraction(data["metadata"]["rate"])
        end_card = None
        if clips and clips[-1]["metadata"]["take_id"] is None:
            tail = clips[-1]
            meta = tail["metadata"]
            start, stop = meta["timeline_in"], meta["timeline_out"]
            if meta["source_in"] != 0 or meta["source_out"] != stop - start or stop <= start:
                raise ValueError("invalid end card")
            if tail["source_range"]["duration"] != rational(stop - start, rate):
                raise ValueError("end card duration changed")
            start_card_frame = start
            end_card = float((stop - start) / rate)
            clips = clips[:-1]
        if rate <= 0 or len(clips) != len(takes):
            raise ValueError("rate or take count mismatch")
        canvas = data["metadata"].get("scale_to")
        sizes = {clip["metadata"]["transform"]["size"] for clip in clips}
        if len(sizes) > 1 and not canvas:
            raise ValueError("inconsistent canvas sizes without scale_to")
        if canvas and (not isinstance(canvas, str) or not re.fullmatch(r"[1-9]\d*x[1-9]\d*", canvas)):
            raise ValueError("invalid scale_to canvas")
        edits, clock = {}, 0
        for clip, take in zip(clips, takes):
            meta = clip["metadata"]
            ref = clip["media_references"][clip["active_media_reference_key"]]
            if (meta["take_id"] != take["take_id"] or meta["source_hash"] != take["file_sha256"]
                    or ref["target_url"] != take["file"]):
                raise ValueError("approved source changed")
            start, stop = meta["source_in"], meta["source_out"]
            if not all(type(v) is int for v in (start, stop)) or not 0 <= start < stop:
                raise ValueError("invalid source range")
            expected = (rational(start, rate), rational(stop - start, rate))
            span = clip["source_range"]
            if expected != (span["start_time"], span["duration"]):
                raise ValueError("source range mismatch")
            if (meta["timeline_in"], meta["timeline_out"]) != (clock, clock + stop - start):
                raise ValueError("noncontiguous edit")
            if meta["audio_route"] not in {"keep_native", "native_no_dialogue", "mute", "replace_dialogue"}:
                raise ValueError("unsupported audio route")
            if canvas:
                meta = {**meta, "transform": {**meta["transform"], "size": canvas}}
            edits[take["take_id"]] = meta
            clock += stop - start
        if end_card and clock != start_card_frame:
            raise ValueError("end card overlaps the edit")
        return rate, edits, end_card
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise ProjectError("INVALID_CUTLIST", str(exc)) from exc
