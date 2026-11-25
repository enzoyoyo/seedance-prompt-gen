#!/usr/bin/env python3
"""Per-shot acceptance, check 2 of 4: put the identity references and frames of a clip side by side.

The sheet does not judge anything. It only makes the comparison possible in one look: reference
images on the first row, evenly spaced frames of the clip (first to last) on the second. The
file it writes is the evidence for the `identity` check in ledger_submit.py accept.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
from PIL import Image, ImageDraw

from drama_ledger import find_take
from drama_project import ProjectError, resolve_in_project, sha256_file, write_json_atomic
from validate_shot_spec import load_project_spec, resolve_ref, shot_rows

QC_DIR = "qc"
LABEL_HEIGHT = 18
BACKGROUND = (20, 20, 20)
LABEL_COLOUR = (235, 235, 235)


def frame_positions(total: int, count: int) -> list[int]:
    """Evenly spaced frame indexes from the first to the last frame."""
    if total <= 0:
        return []
    if count <= 1 or total == 1:
        return [0]
    return sorted({round(step * (total - 1) / (count - 1)) for step in range(count)})


def read_frames(clip: Path, count: int) -> list[tuple[str, Image.Image]]:
    capture = cv2.VideoCapture(str(clip))
    try:
        if not capture.isOpened():
            raise ProjectError("INPUT_ERROR", f"cannot open video: {clip.name}")
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        frames = []
        for index in frame_positions(total, count):
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if ok:
                frames.append((f"frame {index + 1}/{total}", Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))))
    finally:
        capture.release()
    if not frames:
        raise ProjectError("INPUT_ERROR", f"no readable frames: {clip.name}")
    return frames


def read_refs(paths: list[Path]) -> list[tuple[str, Image.Image]]:
    refs = []
    for path in paths:
        if not path.is_file():
            raise ProjectError("REF_FILE_MISSING", str(path))
        with Image.open(path) as image:
            refs.append((f"ref {path.name}", image.convert("RGB")))
    return refs


def fit_height(image: Image.Image, height: int) -> Image.Image:
    width = max(1, round(image.width * height / image.height))
    return image.resize((width, height))


def compose_row(cells: list[tuple[str, Image.Image]], height: int, gap: int) -> Image.Image:
    scaled = [(label, fit_height(image, height)) for label, image in cells]
    width = sum(image.width for _, image in scaled) + gap * (len(scaled) + 1)
    row = Image.new("RGB", (width, height + LABEL_HEIGHT + gap), BACKGROUND)
    draw = ImageDraw.Draw(row)
    left = gap
    for label, image in scaled:
        draw.text((left, 2), label, fill=LABEL_COLOUR)
        row.paste(image, (left, LABEL_HEIGHT))
        left += image.width + gap
    return row


def compose_sheet(refs: list[tuple[str, Image.Image]], frames: list[tuple[str, Image.Image]],
                  height: int, gap: int = 8) -> Image.Image:
    rows = [compose_row(cells, height, gap) for cells in (refs, frames) if cells]
    sheet = Image.new("RGB", (max(row.width for row in rows), sum(row.height for row in rows)), BACKGROUND)
    top = 0
    for row in rows:
        sheet.paste(row, (0, top))
        top += row.height
    return sheet


def project_inputs(project: Path, take_id: str) -> tuple[Path, list[Path]]:
    """Clip of a ledger take and the reference files its spec shot declares."""
    spec, spec_dir, manifest = load_project_spec(project)
    take = find_take(manifest, take_id)
    clip = resolve_in_project(project, take.get("file"))
    if clip is None or not clip.is_file():
        raise ProjectError("CLIP_FILE_MISSING", f"{take_id}:{take.get('file')}")
    shot = next((row for row in shot_rows(spec) if row.get("id") == take.get("spec_id")), None)
    if shot is None:
        raise ProjectError("UNKNOWN_SHOT", str(take.get("spec_id")))
    refs = []
    for name in shot.get("refs", []):
        path = resolve_ref(spec, spec_dir, name)
        if path is None:
            raise ProjectError("REF_FILE_MISSING", name)
        refs.append(path)
    return clip, refs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, epilog="Exit codes: 0 sheet written; 1 refused; 3 input error.")
    parser.add_argument("--project", type=Path, help="project directory (with --take)")
    parser.add_argument("--take", help="ledger take id; clip and references come from the ledger and spec")
    parser.add_argument("--clip", type=Path, help="clip file, when working outside a project")
    parser.add_argument("--ref", action="append", default=[], type=Path, help="reference image (repeatable), with --clip")
    parser.add_argument("--frames", type=int, default=3, help="how many evenly spaced frames to show")
    parser.add_argument("--cell-height", type=int, default=360, help="pixel height of every cell")
    parser.add_argument("--output", type=Path, help="default: <project>/qc/<clip stem>.identity.jpg")
    args = parser.parse_args(argv)
    try:
        if args.project and args.take:
            project = args.project.expanduser()
            clip, refs = project_inputs(project, args.take)
            output = args.output or project / QC_DIR / f"{clip.stem}.identity.jpg"
        elif args.clip and args.output:
            clip, refs, output = args.clip.expanduser(), [path.expanduser() for path in args.ref], args.output
        else:
            parser.error("give --project with --take, or --clip with --output")
        if args.frames < 1 or args.cell_height < 1:
            raise ProjectError("INPUT_ERROR", "--frames and --cell-height must be positive")
        sheet = compose_sheet(read_refs(refs), read_frames(clip, args.frames), args.cell_height)
        output.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(output, quality=90)
        meta = {"tool": "make_identity_sheet", "take_id": args.take, "clip_sha256": sha256_file(clip),
                "sheet_sha256": sha256_file(output), "references": len(refs)}
        write_json_atomic(output.with_name(output.name + ".json"), meta)
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 3 if exc.code == "INPUT_ERROR" else 1
    print(json.dumps({"ok": True, "sheet": str(output), "references": len(refs)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
