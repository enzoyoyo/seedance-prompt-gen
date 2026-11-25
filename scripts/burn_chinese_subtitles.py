#!/usr/bin/env python3
"""Burn subtitles into a video with PIL/OpenCV, and/or write them as SRT. One entry for both.

Use when FFmpeg lacks the `subtitles`/`ass` filters or when deterministic subtitle styling is needed.
Cues come from one of two places:
  --subtitles FILE   a JSON list: [{"start": 0, "end": 7, "text": "字幕文本"}], or with
                     "lines": ["first language", "second language"] instead of "text";
  --timeline FILE    the timeline written by assemble_cut.py: cues are then timed from word
                     timestamps of each source clip (--asr-dir cache, else the ASR command) using
                     the project's translation table, or the shot spec lines when there is none.
Font, size and the languages shown are parameters; sizes may be given as a share of the frame.
"""
import argparse, json, os, subprocess, time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def wrap_text(text, font, max_width, max_lines=3):
    lines, cur = [], ""
    for ch in text:
        test = cur + ch
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines[:max_lines]


def active_cue(items, t):
    for item in items:
        if float(item["start"]) <= t < float(item["end"]):
            return item
    return None


def draw_boxed(draw, rows, width, height, bottom):
    """rows: [(text, font, font_size)], drawn as one centred box whose bottom edge sits `bottom`
    pixels above the frame's lower edge; the block is measured, so every line stays in frame."""
    size = max(row[2] for row in rows)
    pad_x, pad_y = int(size * 0.6), int(size * 0.38)
    boxes = [draw.textbbox((0, 0), text, font=font, stroke_width=2) for text, font, _ in rows]
    heights = [box[3] - box[1] + int(row[2] * 0.25) for box, row in zip(boxes, rows)]
    box_w = min(width - 80, max((b[2] - b[0] for b in boxes), default=0) + pad_x * 2)
    box_h = sum(heights) + pad_y * 2 - 10
    x, y = (width - box_w) // 2, max(0, height - bottom - box_h)
    draw.rounded_rectangle([x, y, x + box_w, y + box_h], radius=22, fill=(0, 0, 0, 165))
    yy = y + pad_y - 4
    for (text, font, _), box, line_h in zip(rows, boxes, heights):
        tx = (width - (box[2] - box[0])) // 2
        draw.text((tx, yy), text, font=font, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 230))
        yy += line_h


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="input mp4")
    ap.add_argument("--subtitles", help="JSON subtitle list: start/end/text (or lines)")
    ap.add_argument("--output", help="output mp4 (video only unless --keep-audio)")
    ap.add_argument("--font", default="/System/Library/Fonts/STHeiti Light.ttc")
    ap.add_argument("--font-size", type=int, default=58)
    ap.add_argument("--max-width", type=int, default=900)
    ap.add_argument("--bottom-margin", type=int, default=270, help="pixels from the frame bottom to the subtitle box")
    ap.add_argument("--font-size-ratio", type=float, help="font size as a share of frame height; overrides --font-size")
    ap.add_argument("--max-width-ratio", type=float, help="text width as a share of frame width; overrides --max-width")
    ap.add_argument("--bottom-margin-ratio", type=float, help="share of frame height; overrides --bottom-margin")
    ap.add_argument("--secondary-font", help="font for the lines after the first; default: --font")
    ap.add_argument("--secondary-size-ratio", type=float, help="size of those lines as a share of frame height")
    ap.add_argument("--show", help="which cue lines to show, e.g. 0 or 0,1; default: all")
    ap.add_argument("--srt", help="also write the cues as SRT here")
    ap.add_argument("--keep-audio", action="store_true", help="copy the input's audio into the output")
    ap.add_argument("--timeline", help="timeline JSON from assemble_cut.py; builds word-timed cues")
    ap.add_argument("--project", help="project directory (spec, translations and clip paths), with --timeline")
    ap.add_argument("--asr-dir", help="cache of word-timestamp transcripts, <clip stem>.json")
    ap.add_argument("--asr-bin", default="whisper", help="ASR command used when a transcript is not cached")
    ap.add_argument("--asr-model", default=os.environ.get("ASR_MODEL"),
                    help="ASR model when a transcript is not cached; default $ASR_MODEL")
    ap.add_argument("--asr-arg", action="append", default=[], help="extra ASR argument (repeatable)")
    ap.add_argument("--spoken-column", type=int, default=1, help="which column of a translation pair is spoken")
    ap.add_argument("--lead-s", type=float, default=0.0, help="show each cue this long before its first word")
    ap.add_argument("--tail-s", type=float, default=0.0, help="keep each cue this long after its last word")
    ap.add_argument("--cues-out", help="write the built cues JSON here")
    ap.add_argument("--shot-cues", help="JSON map of spec_id -> [{start, end, text|lines}] manual clip-relative cues")
    ap.add_argument("--allow-unaligned", action="store_true", help="drop cues whose words were not heard")
    return ap


def timed_cues(args):
    """Cues from the cut timeline and word timestamps; refuses when a line was never heard."""
    from drama_project import ProjectError, drama_block, read_json, resolve_in_project
    from subtitle_cues import build_cues, load_words, parse_shot_cues, shot_texts
    from validate_shot_spec import load_project_spec

    if not args.project:
        raise SystemExit("--timeline needs --project and --asr-dir")
    project = Path(args.project).expanduser()
    try:
        spec, _, manifest = load_project_spec(project)
        table = resolve_in_project(project, drama_block(manifest).get("translations"))
        texts = shot_texts(spec, read_json(table) if table and table.is_file() else None, args.spoken_column)
        timeline = read_json(Path(args.timeline))
        manual = parse_shot_cues(read_json(Path(args.shot_cues).expanduser())) if args.shot_cues else {}
        needs_asr = any((texts.get(row.get("spec_id")) or []) and row.get("spec_id") not in manual
                        for row in (timeline if isinstance(timeline, list) else []))
        if needs_asr and not args.asr_dir:
            raise SystemExit("--timeline needs --project and --asr-dir")
        cues, unaligned = build_cues(
            timeline, texts,
            lambda row: load_words(project / row["source"], Path(args.asr_dir), args.asr_bin, args.asr_arg,
                                   args.asr_model),
            args.lead_s, args.tail_s, manual)
    except ProjectError as exc:
        raise SystemExit(str(exc)) from exc
    if unaligned and not args.allow_unaligned:
        raise SystemExit("\n".join(unaligned))
    return cues


def load_cues(args):
    if args.timeline:
        cues = timed_cues(args)
    elif args.subtitles:
        cues = json.loads(Path(args.subtitles).read_text(encoding="utf-8"))
    else:
        raise SystemExit("give --subtitles or --timeline")
    if args.cues_out:
        Path(args.cues_out).write_text(json.dumps(cues, ensure_ascii=False, indent=2), encoding="utf-8")
    return cues


def style(args, width, height):
    """Pixel sizes and fonts for this frame size; ratios win over the pixel flags."""
    size = round(height * args.font_size_ratio) if args.font_size_ratio else args.font_size
    second = round(height * args.secondary_size_ratio) if args.secondary_size_ratio else size
    return {
        "fonts": [(ImageFont.truetype(args.font, size), size),
                  (ImageFont.truetype(args.secondary_font or args.font, second), second)],
        "max_width": round(width * args.max_width_ratio) if args.max_width_ratio else args.max_width,
        "bottom": round(height * args.bottom_margin_ratio) if args.bottom_margin_ratio else args.bottom_margin,
    }


def cue_rows(cue, look, show):
    from subtitle_cues import cue_lines
    rows = []
    for index, text in enumerate(cue_lines(cue, show)):
        font, size = look["fonts"][min(index, 1)]
        rows.extend((line, font, size) for line in wrap_text(text, font, look["max_width"]))
    return rows


def burn_frame(frame, rows, look, width, height):
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw_boxed(ImageDraw.Draw(overlay), rows, width, height, look["bottom"])
    return cv2.cvtColor(np.array(Image.alpha_composite(img, overlay).convert("RGB")), cv2.COLOR_RGB2BGR)


def encoder_command(args, width, height, fps):
    audio = ["-i", args.input, "-map", "0:v", "-map", "1:a?", "-c:a", "copy"] if args.keep_audio else ["-an"]
    return ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(fps),
            "-i", "-", *audio, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", args.output]


def burn(args, items, show):
    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {args.input}")
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    look = style(args, width, height)
    proc = subprocess.Popen(encoder_command(args, width, height, fps), stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    frame_i, start = 0, time.time()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            cue = active_cue(items, frame_i / fps)
            rows = cue_rows(cue, look, show) if cue else []
            proc.stdin.write((burn_frame(frame, rows, look, width, height) if rows else frame).tobytes())
            frame_i += 1
    finally:
        cap.release()
        if proc.stdin:
            proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "ignore")
        proc.stderr.close()
        if proc.wait() != 0:
            raise SystemExit(err[-4000:])
    print(f"burned {frame_i} frames in {time.time()-start:.1f}s -> {args.output}")


def check_subtitle_lexicon(project_arg, items, show):
    if not project_arg:
        return
    from check_release_intent import lexicon_violations
    from drama_project import drama_block, load_manifest, manifest_path, section
    from subtitle_cues import cue_lines

    project = Path(project_arg).expanduser()
    if not manifest_path(project).is_file():
        return
    lexicon = section(drama_block(load_manifest(project)), "release_intent").get("lexicon")
    if not isinstance(lexicon, list):
        return
    violations = []
    for cue in items:
        for line in cue_lines(cue, show):
            violations.extend(lexicon_violations(lexicon, line, "subtitles"))
    if violations:
        raise SystemExit("\n".join(violations))


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.output and not args.srt:
        raise SystemExit("give --output and/or --srt")
    from subtitle_cues import srt_text

    items = load_cues(args)
    show = [int(part) for part in args.show.split(",")] if args.show else None
    check_subtitle_lexicon(args.project, items, show)
    if args.srt:
        Path(args.srt).write_text(srt_text(items, show), encoding="utf-8")
        print(f"wrote {len(items)} cues -> {args.srt}")
    if args.output:
        burn(args, items, show)


if __name__ == "__main__":
    main()
