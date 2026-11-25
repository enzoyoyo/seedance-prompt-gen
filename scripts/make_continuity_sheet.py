#!/usr/bin/env python3
"""Per-shot acceptance, check 4 of 4: side-by-side continuity sheet bound to the take's clip digest.

Places the previous active shot's tail frame (when settled on disk, else this shot's previs/scene
anchor if any) next to the first, middle and last frames of this take's clip, and writes a `.json`
sidecar binding `clip_sha256` (and `prev_clip_sha256` when present) for `ledger_submit.py accept`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image

from drama_ledger import approved_take, find_take, takes_for
from drama_project import ProjectError, nonempty, resolve_in_project, sha256_file, write_json_atomic
from make_identity_sheet import QC_DIR, compose_row, read_frames
from validate_shot_spec import active_shots, load_project_spec, resolve_ref, root_id, shot_rows


def previous_shot_id(rows: list[dict[str, Any]], shot_id: str) -> str | None:
    active = [root_id(rows, row["id"]) for row in active_shots(rows)]
    if shot_id not in active:
        return None
    idx = active.index(shot_id)
    return active[idx - 1] if idx > 0 else None


def settled_prev_take(manifest: dict[str, Any], prev_id: str | None, tier: str) -> dict[str, Any] | None:
    if prev_id is None:
        return None
    approved = approved_take(manifest, prev_id, tier)
    if approved is not None:
        return approved
    candidates = [t for t in takes_for(manifest, prev_id, tier) if t.get("job_state") == "succeeded" and t.get("file")]
    return candidates[-1] if candidates else None


def tail_cell(project: Path, prev_take: dict[str, Any] | None) -> tuple[list[tuple[str, Image.Image]], str | None]:
    if prev_take is None:
        return [], None
    clip = resolve_in_project(project, prev_take.get("file"))
    if clip is None or not clip.is_file():
        return [], None
    frames = read_frames(clip, 2)
    _, tail = frames[-1]
    return [(f"prev {prev_take['shot_id']} tail", tail)], sha256_file(clip)


def anchor_cell(project: Path, spec: dict[str, Any], spec_dir: Path, shot: dict[str, Any]) -> list[tuple[str, Image.Image]]:
    previs_rel = shot.get("previs_ref")
    path = resolve_in_project(project, previs_rel) if nonempty(previs_rel) else None
    if path is None and shot.get("refs"):
        path = resolve_ref(spec, spec_dir, shot["refs"][0])
    if path is None or not path.is_file():
        return []
    with Image.open(path) as img:
        return [(f"anchor {path.name}", img.convert("RGB"))]


def build_project_sheet(project: Path, take_id: str, cell_height: int,
                        out_override: Path | None) -> tuple[Path, dict[str, Any]]:
    spec, spec_dir, manifest = load_project_spec(project)
    take = find_take(manifest, take_id)
    clip = resolve_in_project(project, take.get("file"))
    if clip is None or not clip.is_file():
        raise ProjectError("CLIP_FILE_MISSING", f"{take_id}:{take.get('file')}")
    rows = shot_rows(spec)
    shot = next((row for row in rows if row.get("id") == take.get("spec_id")), None)
    if shot is None:
        raise ProjectError("UNKNOWN_SHOT", str(take.get("spec_id")))
    prev_id = previous_shot_id(rows, take["shot_id"])
    prev_take = settled_prev_take(manifest, prev_id, take["tier"])
    left_cells, prev_sha = tail_cell(project, prev_take)
    if not left_cells:
        left_cells = anchor_cell(project, spec, spec_dir, shot)
    clip_cells = [(f"this {label}", img) for label, img in read_frames(clip, 3)]
    sheet = compose_row([*left_cells, *clip_cells], cell_height, gap=8)
    output = out_override or project / QC_DIR / f"{clip.stem}.continuity.jpg"
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=90)
    meta = {
        "tool": "make_continuity_sheet", "take_id": take_id, "clip_sha256": sha256_file(clip),
        "prev_shot_id": prev_id, "prev_take_id": prev_take["take_id"] if prev_take else None,
        "prev_clip_sha256": prev_sha, "sheet_sha256": sha256_file(output),
    }
    write_json_atomic(output.with_name(output.name + ".json"), meta)
    return output, meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, epilog="Exit codes: 0 sheet written; 1 refused; 3 input error.")
    parser.add_argument("--project", required=True, type=Path, help="project directory")
    parser.add_argument("--take", required=True, help="ledger take id")
    parser.add_argument("--cell-height", type=int, default=360, help="pixel height of every frame cell")
    parser.add_argument("--output", type=Path, help="default: <project>/qc/<clip stem>.continuity.jpg")
    args = parser.parse_args(argv)
    try:
        if args.cell_height < 1:
            raise ProjectError("INPUT_ERROR", "--cell-height must be positive")
        output, meta = build_project_sheet(args.project.expanduser(), args.take, args.cell_height, args.output)
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 3 if exc.code == "INPUT_ERROR" else 1
    print(json.dumps({"ok": True, "sheet": str(output), "prev_take": meta["prev_take_id"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
