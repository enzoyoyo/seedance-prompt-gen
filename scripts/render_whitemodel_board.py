#!/usr/bin/env python3
"""Render zero-cost clay whitemodel & blocking boards into 00_previs/ for the user to choose from.

The plan (templates/whitemodel-blocking-plan.json) gives the room, props, exact actors with pose and
facing, and cameras; optional `options` overlay the base plan with alternative blockings (A/B/...),
each checked on its own (room bounds, actor overlap, exact headcount, 180-degree axis). For every
option it writes into the --output folder:
  <stem>[_<option>].png           annotated board: floorplan + every camera view (pages _p2... if needed)
  <stem>[_<option>]_<camera>.png  clean grey frame per camera, no annotation (previs_ref / first-frame use)
  <stem>[_<option>].blocking.json sidecar: digests, what each camera frames and from which side, and
                                  the derived required_views per actor for the identity gate; actors
                                  marked `"extra": true` (background figures) are listed under `extras`
                                  and need no locked character
  <stem>_compare.png              side-by-side comparison sheet when there are two or more options
Offline and zero-cost (`planning_only`). `--check` validates and prints JSON without writing files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from drama_project import ProjectError, nonempty, read_json, sha256_file, write_json_atomic
from whitemodel_draw import (
    AMBER, BG, BLUE, MUTED, PANEL, RED, TEXT, VIEW_TEXT, Floorplan, Fonts, annotate_view, render_view, text_box,
)
from whitemodel_scene import camera_coverage, parse_ratio, pose_of, required_views, validate_plan

BOARD_W = 2400
FLOOR_W = 1000
GAP = 40
HEADER_H = 170
LEGEND_H = 230
VIEWS_PER_PAGE = 4
VIEW_BLOCK_MAX_H = 1500
CELL_EXTRA_H = 130
LINE_H = 32
CLEAN_LONG_EDGE = 1280
FONT_WARNING = "CJK_FONT_MISSING: labels fall back to ASCII ids"
LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
OPTION_KEYS = ("actors", "cameras", "props", "room", "axis_pair", "allow_axis_cross", "expected_actor_count",
               "note", "title")


def expand_options(plan: object) -> list[tuple[str | None, dict[str, Any]]]:
    """(label, merged plan) per option; a plan without `options` is one unlabeled option."""
    if not isinstance(plan, dict):
        raise ProjectError("INVALID_BLOCKING_PLAN", "plan must be a JSON object")
    base = {k: v for k, v in plan.items() if k != "options"}
    options = plan.get("options")
    if options is None:
        return [(None, base)]
    if not isinstance(options, list) or not options:
        raise ProjectError("INVALID_BLOCKING_PLAN", "options must be a non-empty list")
    out: list[tuple[str | None, dict[str, Any]]] = []
    for idx, opt in enumerate(options):
        label = opt.get("label") if isinstance(opt, dict) else None
        if not isinstance(label, str) or not LABEL_RE.fullmatch(label) or label in {o[0] for o in out}:
            raise ProjectError("INVALID_BLOCKING_PLAN", f"option {idx} needs a unique file-safe label")
        unknown = sorted(set(opt) - set(OPTION_KEYS) - {"label"})
        if unknown:
            raise ProjectError("INVALID_BLOCKING_PLAN", f"option {label}: unknown keys {unknown}")
        out.append((label, {**base, **{k: v for k, v in opt.items() if k != "label"}}))
    return out


def check_options(options: list[tuple[str | None, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Each option validated on its own: {option, errors, warnings}."""
    return [dict(zip(("option", "errors", "warnings"), (label, *validate_plan(plan)))) for label, plan in options]


def flatten(checks: list[dict[str, Any]], key: str) -> list[str]:
    """All errors or warnings, prefixed with `<option>:` when there is more than one option."""
    multi = len(checks) > 1
    return [f"{row['option']}:{item}" if multi else item for row in checks for item in row[key]]


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "cam"


def view_grid(n: int, ratio: tuple[float, float], area_w: int, max_h: int,
              extra: int = CELL_EXTRA_H) -> tuple[int, int, int]:
    """Columns and view size (w, h) that give the largest views while the block fits `max_h`."""
    best, fallback = None, None
    for cols in range(1, max(1, n) + 1):
        rows = math.ceil(n / cols)
        vw = (area_w - (cols - 1) * GAP) // cols
        vh = int(vw * ratio[1] / ratio[0])
        total = rows * (vh + extra)
        candidate = (vw * vh, cols, vw, vh, total)
        if total <= max_h and (best is None or candidate[0] > best[0]):
            best = candidate
        if fallback is None or total < fallback[4]:
            fallback = candidate
    chosen = best or fallback
    return chosen[1], chosen[2], chosen[3]


def caption(fonts: Fonts, plan: dict[str, Any], seen: list[dict[str, str]]) -> str:
    names = {a["id"]: fonts.name(a) for a in plan.get("actors", [])}
    if not seen:
        return fonts.t("拍到：无人（空镜）", "Frames: nobody (empty)")
    parts = [f"{names[row['actor']]}({fonts.t(*VIEW_TEXT[row['view']])})" for row in seen]
    return fonts.t("拍到：", "Frames: ") + "、".join(parts) if fonts.cjk else "Frames: " + ", ".join(parts)


def draw_cell(board: Image.Image, plan: dict[str, Any], cam: dict[str, Any], box: tuple[int, int, int, int],
              fonts: Fonts, seen: list[dict[str, str]]) -> None:
    x, y, vw, vh = box
    draw = ImageDraw.Draw(board)
    title_font = fonts.get(30)
    title = fit(draw, fonts.name(cam), title_font, vw)
    draw.text((x, y), title, font=title_font, fill=BLUE)
    view = render_view(plan, cam, (vw, vh), annotated=True)
    annotate_view(view, plan, cam, fonts, seen)
    board.paste(view, (x, y + 44))
    draw.rectangle((x - 2, y + 42, x + vw + 1, y + 44 + vh + 1), outline=BLUE, width=3)
    font = fonts.get(24)
    meta = f"{fonts.t('视场', 'fov')} {int(float(cam.get('fov_deg', 50)))}° · " \
           f"{fonts.t('机高', 'height')} {float(cam.get('y', 1.6)):.2f}m"
    lines = wrap(draw, caption(fonts, plan, seen), font, vw)
    for idx, line in enumerate(lines):
        draw.text((x, y + 54 + vh + idx * LINE_H), line, font=font, fill=TEXT)
    draw.text((x, y + 56 + vh + len(lines) * LINE_H), fit(draw, meta, font, vw), font=font, fill=MUTED)


def wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, width: int) -> list[str]:
    """Break `text` into lines no wider than `width`; nothing is dropped."""
    lines, cur = [], ""
    for ch in text:
        if cur and draw.textlength(cur + ch, font=font) > width:
            lines.append(cur)
            cur = ch.lstrip()
        else:
            cur += ch
    return lines + [cur] if cur else lines


def cell_extra(draw: ImageDraw.ImageDraw, texts: list[str], font: Any, width: int) -> int:
    lines = max(len(wrap(draw, text, font, width)) for text in texts)
    return CELL_EXTRA_H + max(0, lines - 1) * LINE_H


def fit(draw: ImageDraw.ImageDraw, text: str, font: Any, width: int) -> str:
    """Shorten `text` with an ellipsis until it fits `width` pixels."""
    if draw.textlength(text, font=font) <= width:
        return text
    while len(text) > 1 and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def legend(draw: ImageDraw.ImageDraw, x: int, y: int, fonts: Fonts) -> None:
    font = fonts.get(24)
    rows = [
        ((190, 190, 190), fonts.t("灰色人形 = 演员（圆头／躯干／腿分开；头上深色椭圆 = 脸，看得到脸就是朝向镜头）",
                                  "Grey figure = actor (round head/torso/legs; dark oval on head = face)")),
        (AMBER, fonts.t("橙色扇形／地面箭头 = 脸朝哪边", "Amber wedge / floor arrow = where the face points")),
        (AMBER, fonts.t("橙色虚线 = 180° 轴线：机位都放在同一侧，左右关系才不乱",
                        "Amber dashes = 180° axis: keep all cameras on one side")),
        (BLUE, fonts.t("蓝色 = 机位与取景范围；右侧每格 = 该机位实际拍到的画面",
                       "Blue = camera and its field of view; each right panel = what it sees")),
        (MUTED, fonts.t("网格 1 格 = 1 米；机位图下方写出拍到谁、拍到哪一面",
                        "Grid = 1 m; under each view: who is framed and which side")),
    ]
    for idx, (color, text) in enumerate(rows):
        yy = y + idx * 42
        draw.rectangle((x, yy + 6, x + 26, yy + 30), fill=color)
        draw.text((x + 40, yy), text, font=font, fill=TEXT)


def header(draw: ImageDraw.ImageDraw, plan: dict[str, Any], label: str | None, page: tuple[int, int],
           fonts: Fonts, warnings: list[str]) -> None:
    opt = f" · {fonts.t('方案', 'option')} {label}" if label else ""
    pages = f" · {fonts.t('第', 'page ')}{page[0]}/{page[1]}{fonts.t('页', '')}" if page[1] > 1 else ""
    draw.text((GAP, 22), f"{fonts.t('白模站位板', 'WHITEMODEL BLOCKING')} · {fonts.t('场景', 'scene')} "
              f"{plan['scene_id']}{opt}{pages}", font=fonts.get(44), fill=TEXT)
    sub = " — ".join(str(plan[k]) for k in ("title", "note") if nonempty(plan.get(k)))
    facts = fonts.t(f"画幅 {plan.get('aspect_ratio', '16:9')} · 在场 {len(plan.get('actors', []))} 人 · "
                    f"机位 {len(plan['cameras'])} 个 · 仅预演，零成本",
                    f"ratio {plan.get('aspect_ratio', '16:9')} · {len(plan.get('actors', []))} actors · "
                    f"{len(plan['cameras'])} cameras · planning only, zero cost")
    line = f"{sub} · {facts}" if sub and (fonts.cjk or sub.isascii()) else facts
    width = BOARD_W - 2 * GAP
    draw.text((GAP, 84), fit(draw, line, fonts.get(28), width), font=fonts.get(28), fill=MUTED)
    if warnings:
        text = fonts.t("警告：", "WARNING: ") + "; ".join(warnings)
        draw.text((GAP, 126), fit(draw, text, fonts.get(26), width), font=fonts.get(26), fill=RED)


def compose_page(plan: dict[str, Any], label: str | None, cams: list[dict[str, Any]], page: tuple[int, int],
                 fonts: Fonts, coverage: dict[str, list[dict[str, str]]], warnings: list[str]) -> Image.Image:
    ratio = parse_ratio(plan.get("aspect_ratio", "16:9"))
    area_w = BOARD_W - FLOOR_W - 3 * GAP
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    texts = [caption(fonts, plan, coverage[cam["id"]]) for cam in cams]
    _, vw, _ = view_grid(len(cams), ratio, area_w, VIEW_BLOCK_MAX_H)
    extra = cell_extra(probe, texts, fonts.get(24), vw)
    cols, vw, vh = view_grid(len(cams), ratio, area_w, VIEW_BLOCK_MAX_H, extra)
    extra = max(extra, cell_extra(probe, texts, fonts.get(24), vw))
    views_h = math.ceil(len(cams) / cols) * (vh + extra)
    floor_h = max(600, min(Floorplan.natural_height(plan, FLOOR_W), max(820, views_h - LEGEND_H)))
    board = Image.new("RGB", (BOARD_W, HEADER_H + max(floor_h + LEGEND_H, views_h) + GAP), BG)
    draw = ImageDraw.Draw(board)
    header(draw, plan, label, page, fonts, warnings)
    board.paste(Floorplan(plan, (FLOOR_W, floor_h)).render(fonts), (GAP, HEADER_H))
    draw.text((GAP + 16, HEADER_H + 12), fonts.t("俯视站位图", "TOP-DOWN FLOORPLAN"), font=fonts.get(30), fill=AMBER)
    legend(draw, GAP, HEADER_H + floor_h + 24, fonts)
    x0 = FLOOR_W + 2 * GAP
    for idx, cam in enumerate(cams):
        r, c = divmod(idx, cols)
        draw_cell(board, plan, cam, (x0 + c * (vw + GAP), HEADER_H + r * (vh + extra), vw, vh), fonts,
                  coverage[cam["id"]])
    return board


def clean_size(ratio: tuple[float, float]) -> tuple[int, int]:
    if ratio[0] >= ratio[1]:
        return CLEAN_LONG_EDGE, max(2, round(CLEAN_LONG_EDGE * ratio[1] / ratio[0]))
    return max(2, round(CLEAN_LONG_EDGE * ratio[0] / ratio[1])), CLEAN_LONG_EDGE


def plan_digest(plan: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def render_option(plan: dict[str, Any], label: str | None, stem: Path, fonts: Fonts,
                  warnings: list[str]) -> dict[str, Any]:
    coverage = camera_coverage(plan)
    cams = plan["cameras"]
    chunks = [cams[i:i + VIEWS_PER_PAGE] for i in range(0, len(cams), VIEWS_PER_PAGE)]
    pages = []
    for number, chunk in enumerate(chunks, start=1):
        path = stem.with_name(stem.name + (f"_p{number}" if number > 1 else "") + ".png")
        compose_page(plan, label, chunk, (number, len(chunks)), fonts, coverage, warnings).save(path)
        pages.append({"file": path.name, "sha256": sha256_file(path)})
    frames = {}
    for cam in cams:
        path = stem.with_name(f"{stem.name}_{safe(cam['id'])}.png")
        render_view(plan, cam, clean_size(parse_ratio(plan.get("aspect_ratio", "16:9"))), annotated=False).save(path)
        frames[cam["id"]] = {"file": path.name, "sha256": sha256_file(path)}
    meta = {
        "ok": True, "scope": "planning_only", "provider_submission": "not_performed", "renderer": "whitemodel_board",
        "scene_id": plan["scene_id"], "option": label, "note": plan.get("note", ""),
        "aspect_ratio": plan.get("aspect_ratio", "16:9"),
        "expected_actor_count": plan.get("expected_actor_count", len(plan.get("actors", []))),
        "actor_count": len(plan.get("actors", [])), "actors": [row["id"] for row in plan.get("actors", [])],
        "extras": [row["id"] for row in plan.get("actors", []) if row.get("extra") is True],
        "poses": {row["id"]: pose_of(row) for row in plan.get("actors", [])},
        "cameras": [row["id"] for row in cams], "coverage": coverage, "required_views": required_views(coverage),
        "warnings": warnings, "board": pages[0]["file"], "board_sha256": pages[0]["sha256"], "pages": pages,
        "frames": frames, "plan_sha256": plan_digest(plan),
    }
    write_json_atomic(stem.with_name(stem.name + ".blocking.json"), meta)
    return meta


def compose_compare(rendered: list[tuple[str, dict[str, Any]]], fonts: Fonts, out: Path) -> None:
    """One sheet with every option side by side: label, floorplan, and each camera's view."""
    col_w = max(900, (BOARD_W - GAP) // len(rendered) - GAP)
    width = max(1920, len(rendered) * (col_w + GAP) + GAP)
    columns = [compare_column(label, plan, fonts, col_w) for label, plan in rendered]
    sheet = Image.new("RGB", (width, 120 + max(c.size[1] for c in columns) + GAP), BG)
    draw = ImageDraw.Draw(sheet)
    scene = rendered[0][1]["scene_id"]
    draw.text((GAP, 30), fonts.t(f"场景 {scene} · 站位方案对比（请选一个）", f"Scene {scene} · blocking options (pick one)"),
              font=fonts.get(48), fill=TEXT)
    for idx, column in enumerate(columns):
        sheet.paste(column, (GAP + idx * (col_w + GAP), 120))
    sheet.save(out)


def compare_column(label: str, plan: dict[str, Any], fonts: Fonts, col_w: int) -> Image.Image:
    ratio = parse_ratio(plan.get("aspect_ratio", "16:9"))
    cams = plan["cameras"]
    cols, vw, vh = view_grid(len(cams), ratio, col_w - 2 * 16, 1100)
    rows = math.ceil(len(cams) / cols)
    floor_h = int(col_w * 0.8)
    column = Image.new("RGB", (col_w, 110 + floor_h + rows * (vh + 60) + 20), PANEL)
    draw = ImageDraw.Draw(column)
    draw.text((16, 12), f"{fonts.t('方案', 'Option')} {label}", font=fonts.get(52), fill=AMBER)
    note = str(plan.get("note", ""))
    if note and (fonts.cjk or note.isascii()):
        draw.text((16, 74), fit(draw, note, fonts.get(26), col_w - 32), font=fonts.get(26), fill=TEXT)
    column.paste(Floorplan(plan, (col_w, floor_h)).render(fonts), (0, 110))
    coverage = camera_coverage(plan)
    for idx, cam in enumerate(cams):
        r, c = divmod(idx, cols)
        x, y = 16 + c * (vw + GAP), 110 + floor_h + r * (vh + 60) + 10
        view = render_view(plan, cam, (vw, vh), annotated=True)
        annotate_view(view, plan, cam, fonts, coverage[cam["id"]])
        column.paste(view, (x, y + 40))
        text_box(draw, (x, y + 4), fonts.name(cam), fonts.get(24), BLUE, None)
    return column


def render_all(raw: dict[str, Any], out: Path) -> dict[str, Any]:
    options = expand_options(raw)
    checks = check_options(options)
    if flatten(checks, "errors"):
        raise ProjectError("BLOCKING_INVALID", "; ".join(flatten(checks, "errors")))
    out.parent.mkdir(parents=True, exist_ok=True)
    fonts = Fonts()
    font_warn = [] if fonts.cjk else [FONT_WARNING]
    results = []
    for (label, plan), check in zip(options, checks):
        stem = out.with_suffix("") if label is None else out.with_name(f"{out.stem}_{label}")
        results.append(render_option(plan, label, stem, fonts, check["warnings"] + font_warn))
    compare = None
    if len(options) > 1:
        compare = out.with_name(f"{out.stem}_compare.png")
        compose_compare([(label, plan) for label, plan in options], fonts, compare)
    return {"options": results, "compare": compare.name if compare else None,
            "warnings": flatten(checks, "warnings") + font_warn}


def check_summary(raw: object) -> tuple[int, dict[str, Any]]:
    options = expand_options(raw)
    checks = check_options(options)
    errors, warnings = flatten(checks, "errors"), flatten(checks, "warnings")
    if errors:
        return 1, {"ok": False, "errors": errors, "warnings": warnings}
    counts = {len(plan.get("actors", [])) for _, plan in options}
    return 0, {"ok": True, "scope": "planning_only", "scene_id": options[0][1]["scene_id"],
               "actor_count": counts.pop() if len(counts) == 1 else None, "warnings": warnings,
               "options": [{"option": label, "required_views": required_views(camera_coverage(plan))}
                           for label, plan in options]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes: 0 valid/rendered; 1 spatial invariant failed; 3 input error.")
    parser.add_argument("--plan", required=True, type=Path, help="scene blocking JSON (may hold `options`)")
    parser.add_argument("--output", type=Path, help="board PNG path inside <project>/00_previs/, e.g. 00_previs/S1.png")
    parser.add_argument("--check", action="store_true", help="validate only; write no files")
    args = parser.parse_args(argv)
    try:
        raw = read_json(args.plan.expanduser())
        code, summary = check_summary(raw)
        if args.check or code:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return code
        if args.output is None:
            raise ProjectError("INPUT_ERROR", "give --output <00_previs/board.png> or --check")
        out = args.output.expanduser()
        if "00_previs" not in out.parts:
            raise ProjectError("PREVIS_OUTSIDE_00_PREVIS", str(out))
        result = render_all(raw, out)
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 3 if exc.code == "INPUT_ERROR" else 1
    print(json.dumps({"ok": True, "scope": "planning_only", **result, "output_dir": str(out.parent)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
