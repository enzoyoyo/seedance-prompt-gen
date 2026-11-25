"""Shared ffprobe stream selection, subtitle timing and master audio measurements."""
from __future__ import annotations

import contextlib
import json
import math
import re
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path
from fractions import Fraction

from drama_project import ProjectError
from intake_choices import normalize_creative

ROUTES = ("keep_native", "mute", "replace_dialogue", "native_no_dialogue")


def probe(path):
    run = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
                          str(path.resolve())], capture_output=True, text=True)
    if run.returncode:
        raise ProjectError("UNREADABLE_MEDIA", path.name)
    data = json.loads(run.stdout)
    videos = [s for s in data["streams"] if s["codec_type"] == "video"]
    covers = [s for s in videos if s.get("disposition", {}).get("attached_pic")]
    videos = [s for s in videos if s not in covers]
    primary = next((s for s in videos if s.get("codec_name") != "mjpeg"), next(iter(videos), {}))
    extra = [s["index"] for s in [*videos, *covers] if s != primary and s["codec_name"] == "mjpeg"]
    audio = [s for s in data["streams"] if s["codec_type"] == "audio"]
    duration = next((float(v) for v in (primary.get("duration"), data.get("format", {}).get("duration"))
                     if v not in (None, "", "N/A")), 0.0)
    streams = [{k: s.get(k) for k in ("index", "codec_name", "codec_type", "width", "height", "avg_frame_rate")}
               for s in data["streams"]]
    return {"width": primary.get("width"), "height": primary.get("height"), "sar": primary.get("sample_aspect_ratio"),
            "fps": primary.get("avg_frame_rate"), "duration": duration, "streams": streams, "primary_index": primary.get("index"),
            "video_streams": [s["index"] for s in videos], "audio_streams": [s["index"] for s in audio],
            "attached_pictures": [s["index"] for s in covers], "extra_mjpeg_streams": extra}


def seconds(stamp):
    h, m, s = stamp.strip().replace(",", ".").split(":")
    return Decimal(h) * 3600 + Decimal(m) * 60 + Decimal(s)


def subtitles(path):
    text = path.read_text(encoding="utf-8-sig")
    cues = []
    if path.suffix.lower() == ".ass":
        fields = "layer start end style name marginl marginr marginv effect text".split()
        for line in text.splitlines():
            if line.lower().startswith("format:") and "start" in line.lower():
                fields = [s.strip().lower() for s in line.split(":", 1)[1].split(",")]
            if line.lower().startswith("dialogue:"):
                row = dict(zip(fields, line.split(":", 1)[1].split(",", len(fields) - 1)))
                try:
                    text = row["text"]
                    layer = row["layer"].strip()
                    start, end = seconds(row["start"]), seconds(row["end"])
                    if not (start.is_finite() and end.is_finite()):
                        raise ValueError("non-finite subtitle time")
                except (KeyError, ValueError, InvalidOperation) as exc:
                    raise ProjectError("SUBTITLE_INVALID", path.name) from exc
                pos = re.search(r"\\pos\(([^)]+)\)", text)
                region = ("pos", re.sub(r"\s+", "", pos[1])) if pos else ("layer", layer)
                cues.append((start, end, re.sub(r"\{[^}]*\}", "", text), region))
    elif path.suffix.lower() == ".srt":
        for block in re.split(r"\n\s*\n", text.strip()):
            lines = block.splitlines()
            i = next((i for i, s in enumerate(lines) if "-->" in s), None)
            if i is None:
                raise ProjectError("SUBTITLE_INVALID", path.name)
            try:
                a, b = lines[i].split("-->", 1)
                start, end = seconds(a), seconds(b.strip().split()[0])
                if not (start.is_finite() and end.is_finite()):
                    raise ValueError("non-finite subtitle time")
            except (IndexError, ValueError, InvalidOperation) as exc:
                raise ProjectError("SUBTITLE_INVALID", path.name) from exc
            cues.append((start, end, "".join(lines[i + 1:]), ("layer", "0")))
    if not cues or any(a < 0 or b <= a for a, b, _, _ in cues):
        raise ProjectError("SUBTITLE_INVALID", path.name)
    cues.sort(key=lambda row: row[0])
    overlaps, long_lines, previous = [], [], {}
    for index, (start, end, content, region) in enumerate(cues, 1):
        prior = previous.get(region)
        if prior and prior[1] > start - Decimal("0.08"):
            overlaps.append({"cue": prior[0], "overlap_s": float(prior[1] - start)})
        if prior is None or end >= prior[1]:
            previous[region] = (index, end)
        if len(re.findall(r"[\u3400-\u9fff]", content)) > 24:
            long_lines.append(index)
    return {"subtitle_overlaps": overlaps, "long_lines": long_lines, "cue_count": len(cues)}


def audio_scan(path):
    """Stream 50 ms windows. Require a stationary harmonic peak over ten consecutive windows."""
    try:
        import numpy as np
    except ImportError as exc:
        raise ProjectError("AUDIO_ANALYSIS_DEPENDENCY_MISSING", "numpy") from exc
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path.resolve()), "-map", "0:a:0",
           "-ac", "1", "-ar", "16000", "-f", "f32le", "-"]
    n = 800
    window = np.hanning(n)
    last_peak, run, longest, voiced, active = 0, 0, 0, 0, 0
    with subprocess.Popen(cmd, stdout=subprocess.PIPE) as proc:
        while len(block := proc.stdout.read(n * 4)) == n * 4:
            x = np.frombuffer(block, dtype="<f4")
            if np.mean(x * x) < 1e-6:
                run = 0
                continue
            active += 1
            power = abs(np.fft.rfft((x - x.mean()) * window)) ** 2
            peak = int(np.argmax(power[2:]) + 2)
            total = max(float(power.sum()), 1e-15)
            harmonic = sum(power[max(1, k - 1):k + 2].sum() for k in range(peak, len(power), peak))
            tonal = peak >= 3 and power[peak - 1:peak + 2].sum() / total > .50 and harmonic / total > .80
            run = (run + 1 if abs(peak - last_peak) <= 1 else 1) if tonal else 0
            longest = max(longest, run)
            last_peak = peak
            voiced += int(not tonal and power[5:180].sum() / total > .65)
        proc.stdout.close()
        if proc.wait():
            raise ProjectError("AUDIO_DECODE_FAILED", path.name)
    return {"stationary_tone_s": longest / 20, "speech_band_s": voiced / 20, "active_s": active / 20}


def loudness(path):
    run = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(path.resolve()),
                          "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
    summary = run.stderr.rsplit("Summary:", 1)[-1]
    integrated = re.search(r"I:\s*([-\d.]+)\s*LUFS", summary)
    peak = re.search(r"Peak:\s*([-\d.inf]+)\s*dBFS", summary)
    if run.returncode or not integrated or not peak:
        raise ProjectError("LOUDNESS_MEASUREMENT_INCOMPLETE")
    return {"integrated_lufs": float(integrated[1]), "true_peak_dbfs": peak[1]}


def edit_pacing(info, errors, warnings, cutlist, mode, locks):
    if not (cutlist or locks):
        return
    tolerance = .5 / max(1, float(Fraction(info["fps"] or "24")))
    target = locks.get("hard_duration_s")
    if target is not None:
        if not isinstance(target, (int, float)) or not math.isfinite(target) or target <= 0:
            raise ProjectError("INVALID_HARD_DURATION")
        if abs(info["duration"] - target) > tolerance:
            errors.append("HARD_DURATION_MISMATCH")
    if not cutlist:
        if locks.get("locked_one_take"):
            errors.append("ONE_TAKE_UNVERIFIED")
        return
    data = json.loads(cutlist.read_text())
    try:
        if isinstance(data, dict) and "tracks" in data:
            tracks = [t for t in data["tracks"]["children"] if t["kind"] == "Video"]
            if len(tracks) != 1:
                raise ValueError("expected one video track")
            spans = [clip["source_range"]["duration"] for clip in tracks[0]["children"]]
            durations = [float(span["value"]) / float(span["rate"]) for span in spans]
        else:
            rows = data if isinstance(data, list) else data["clips"]
            durations = [float(row["duration"]) for row in rows]
        if not durations or any(not math.isfinite(d) or d <= 0 for d in durations):
            raise ValueError("invalid clip duration")
    except (TypeError, ValueError, KeyError, ZeroDivisionError) as exc:
        raise ProjectError("INVALID_CUTLIST", str(exc)) from exc
    if abs(sum(durations) - info["duration"]) > tolerance + .0005 * len(durations):
        errors.append("CUTLIST_DURATION_MISMATCH")
    if locks.get("locked_one_take") and len(durations) != 1:
        errors.append("ONE_TAKE_LOCK_BROKEN")
    asl = sum(durations) / len(durations)
    info.update(shot_count=len(durations), asl_s=asl)
    bounds = locks.get("target_asl_range", {"cinema": (5, 10), "short_drama": (2.5, 5)}.get(mode))
    if bounds is not None:
        if (not isinstance(bounds, (list, tuple)) or len(bounds) != 2
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in bounds)
                or not 0 < bounds[0] <= bounds[1]):
            raise ProjectError("INVALID_ASL_RANGE")
        if not bounds[0] <= asl <= bounds[1]:
            warnings.append("ASL_PACING_REVIEW")
        if mode == "short_drama" and max(durations) > bounds[1]:
            warnings.append("LONG_HOLD_REVIEW")


def inspect(path, *, delivery_mode="video_clips", creative_mode=None, claimed_resolution=None,
            subtitle=None, audio_route=None, upscaled_from=None, voice_source=None,
            raw_clip=None, dialogue_stem=None, cutlist=None, locks=None):
    creative_mode = normalize_creative(creative_mode)
    if delivery_mode == "prompt_only":
        raise ProjectError("MEDIA_QC_NOT_APPLICABLE_TO_PROMPTS")
    if delivery_mode == "images_only":
        from PIL import Image
        with Image.open(path) as image:
            w, h = image.size
            image.verify()
        return {"ok": True, "review_status": "needs_review", "errors": [], "warnings": [],
                "columns": {"technical": "pass", "visual": "needs_review", "audio": "not_applicable", "brief": "needs_review"},
                "measured": {"width": w, "height": h}, "delivery_mode": delivery_mode, "creative_mode": creative_mode}
    info = probe(path)
    errors, warnings = [], []
    if not info["width"]:
        errors.append("VIDEO_STREAM_MISSING")
    if info["extra_mjpeg_streams"]:
        errors.append("EXTRA_MJPEG_STREAM")
    source = probe(raw_clip) if raw_clip else info
    source_short_edge = min(source["width"] or 0, source["height"] or 0)
    output_short_edge = min(info["width"] or 0, info["height"] or 0)
    short_edge = min(source_short_edge, output_short_edge)
    if claimed_resolution and claimed_resolution.startswith("native_"):
        claim = re.fullmatch(r"native_(\d+)p", claimed_resolution)
        if not claim or short_edge < int(claim[1]) or upscaled_from:
            errors.append("NATIVE_RESOLUTION_MISMATCH")
        if not raw_clip:
            errors.append("NATIVE_CLAIM_UNVERIFIED")
    elif claimed_resolution == "1080p" and short_edge < 1080 and not upscaled_from:
        errors.append("NATIVE_RESOLUTION_MISMATCH")
    try:
        fps = Fraction(info["fps"] or "0")
    except (ValueError, ZeroDivisionError):
        fps = 0
    if fps < Fraction(24000, 1001):
        errors.append("FRAME_RATE_BELOW_24")
    if fps > 0:
        edit_pacing(info, errors, warnings, cutlist, creative_mode, locks or {})
    if subtitle:
        info.update(subtitles(subtitle))
        if info["subtitle_overlaps"]:
            errors.append("SUBTITLE_CUE_OVERLAP")
        if info["long_lines"]:
            errors.append("SUBTITLE_LINE_TOO_LONG")
    has_audio = bool(info["audio_streams"])
    if has_audio:
        scan = audio_scan(path)
        info["audio_measurements"] = scan
        if scan["stationary_tone_s"] >= .5:
            errors.append("SYNTH_BUZZER_OR_TONE_DETECTED")
        if delivery_mode == "full_film":
            try:
                measurement = loudness(path)
                info["loudness"] = measurement
                if audio_route != "mute" and not -16 <= measurement["integrated_lufs"] <= -12:
                    errors.append("AUDIO_LOUDNESS_OUT_OF_RANGE")
                if float(measurement["true_peak_dbfs"]) > -1:
                    errors.append("AUDIO_TRUE_PEAK_TOO_HIGH")
            except ProjectError as exc:
                errors.append(exc.code)
        if audio_route == "mute" and scan["active_s"]:
            errors.append("AUDIO_ROUTE_MISMATCH")
        if audio_route == "native_no_dialogue" and scan["speech_band_s"] >= .5:
            warnings.append("RESIDUAL_NATIVE_SPEECH_REVIEW")
        if audio_route in {"replace_dialogue", "native_no_dialogue"} and raw_clip and probe(raw_clip)["audio_streams"]:
            if same_audio(path, raw_clip) and scan["active_s"] and audio_route == "replace_dialogue":
                errors.append("RESIDUAL_NATIVE_AUDIO")
            elif scan["speech_band_s"] >= .5:
                retained = retained_audio_seconds(path, raw_clip)
                info["aligned_native_audio_s"] = retained
                if retained >= .5:
                    errors.append("RESIDUAL_NATIVE_SPEECH_ENERGY")
    elif audio_route in {"replace_dialogue", "keep_native"}:
        errors.append("AUDIO_STREAM_MISSING")
    if audio_route == "replace_dialogue" and not (raw_clip and dialogue_stem):
        warnings.append("AUDIO_ROUTING_EVIDENCE_INCOMPLETE")
    for key, file in (("raw_clip", raw_clip), ("dialogue_stem", dialogue_stem)):
        if file:
            info[key] = audio_scan(file) if probe(file)["audio_streams"] else {"active_s": 0}
    if dialogue_stem and audio_route == "replace_dialogue" and info["dialogue_stem"]["active_s"] == 0:
        errors.append("DIALOGUE_STEM_SILENT")
    if delivery_mode in {"video_clips", "full_film"} and re.search(r"edge[-_ ]?tts|espeak", str(voice_source), re.I):
        errors.append("DIALOGUE_VOICE_PROVENANCE_REJECTED")
    audio_failure = any(e.startswith(("AUDIO_", "DIALOGUE_", "RESIDUAL_", "SYNTH_")) for e in errors)
    columns = {"technical": "fail" if errors else ("needs_review" if warnings else "pass"), "visual": "needs_review",
               "audio": "fail" if audio_failure else ("needs_review" if has_audio else "not_applicable"),
               "brief": "needs_review"}
    return {"ok": not errors, "review_status": "fail" if errors else "needs_review", "errors": errors, "warnings": warnings, "measured": info, "columns": columns,
            "delivery_mode": delivery_mode, "creative_mode": creative_mode}


def retained_audio_seconds(master, raw):
    """Conservative aligned-window correlation. Decorrelation requires human review."""
    import numpy as np
    block_size = 1600
    with contextlib.ExitStack() as stack:
        readers = []
        for path in (master, raw):
            proc = stack.enter_context(subprocess.Popen(
                ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path.resolve()), "-map", "0:a:0", "-ac", "1",
                 "-af", "highpass=f=120,lowpass=f=3500", "-ar", "16000", "-f", "f32le", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL))
            stack.callback(proc.kill)
            readers.append(proc.stdout)
        streak = longest = 0
        while True:
            chunks = [r.read(block_size * 4) for r in readers]
            if min(map(len, chunks)) < block_size * 4:
                break
            x, y = (np.frombuffer(chunk, dtype="<f4") for chunk in chunks)
            xx, yy = float(x @ x), float(y @ y)
            corr = float(x @ y) / max((xx * yy) ** .5, 1e-12)
            streak = streak + 1 if min(xx, yy) / block_size > 1e-5 and corr >= .80 else 0
            longest = max(streak, longest)
        return longest / 10


def same_audio(first, second):
    def checksum(path):
        return subprocess.check_output(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path.resolve()),
                                        "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-f", "hash", "-"])
    return bool(probe(second)["audio_streams"]) and checksum(first) == checksum(second)


def cli(args):
    meta = {}
    if args.metadata:
        meta = json.loads(args.metadata.read_text())
        if not isinstance(meta, dict):
            raise ProjectError("INVALID_MEDIA_METADATA")
        for key in ("voice_source", "audio_route", "claimed_resolution", "upscaled_from", "creative_mode"):
            if getattr(args, key) is None:
                setattr(args, key, meta.get(key))
        if args.voice_source is None:
            args.voice_source = meta.get("dialogue")
        for key in ("raw_clip", "dialogue_stem", "subtitle", "cutlist"):
            if getattr(args, key) is None and meta.get(key):
                setattr(args, key, args.metadata.parent / meta[key])
        if args.audio_route is not None and args.audio_route not in ROUTES:
            raise ProjectError("INVALID_AUDIO_ROUTE")
    keys = ("delivery_mode", "creative_mode", "claimed_resolution", "subtitle", "audio_route",
            "upscaled_from", "voice_source", "raw_clip", "dialogue_stem", "cutlist")
    locks = {k: meta[k] for k in ("locked_one_take", "hard_duration_s", "target_asl_range") if k in meta}
    result = inspect(args.input, locks=locks, **{k: getattr(args, k) for k in keys})
    print(json.dumps(result, indent=2))
    return int(not result["ok"])
