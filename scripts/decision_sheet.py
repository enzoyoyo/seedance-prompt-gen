#!/usr/bin/env python3
"""Decision sheets for the present -> decide gates: candidate grid, waiver choice, confirmation code.

Library only. The confirmation code is drawn into the sheet's pixels and nowhere else; callers keep
only a random salt and the salted SHA-256 of the code. This is friction against an agent filling
in the user's reply on its own, not cryptographic proof: an agent that deliberately reads the image
can still obtain the code.
"""
from __future__ import annotations

import hashlib
import math
import re
import secrets
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from drama_project import ProjectError
from whitemodel_draw import AMBER, BG, BLUE, MUTED, PANEL, TEXT, Fonts

CODE_LETTERS = "ACDEFHJKMNPRTUVWXY"
CODE_DIGITS = "2345679"
CODE_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{3})[\s\-_·.:：]*([0-9]{3})(?![A-Z0-9])", re.IGNORECASE)
SHEET_W = 2400
GAP = 40
HEADER_H = 300
CELL_TITLE_H = 64
FOOTER_LINE_H = 50
ROWS_PER_PAGE = 2
GATE_TITLES = {"identity": ("角色多角度与场景资产", "character views & scene assets"),
               "previs": ("白模与站位", "whitemodel blocking")}


def new_code() -> str:
    """A short code such as KMP-473 with no look-alike pairs (0/O, 1/I/L, 2/Z, 5/S, 6/G, 8/B, Q)."""
    letters = "".join(secrets.choice(CODE_LETTERS) for _ in range(3))
    return f"{letters}-{''.join(secrets.choice(CODE_DIGITS) for _ in range(3))}"


def new_salt() -> str:
    return secrets.token_hex(16)


def code_digest(salt: str, code: str) -> str:
    return hashlib.sha256(f"{salt}:{normalize_code(code)}".encode("utf-8")).hexdigest()


def normalize_code(code: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", code.upper())


def codes_in(words: str) -> list[str]:
    """Every code-shaped token in a reply (three letters then three digits), normalised."""
    return [(a + b).upper() for a, b in CODE_RE.findall(words)]


def redact_codes(words: str) -> str:
    """The reply with every code-shaped token replaced, so the stored words never hold the code."""
    return CODE_RE.sub("[确认码]", words)


def load_thumb(path: Path, box: tuple[int, int]) -> Image.Image:
    try:
        with Image.open(path) as img:
            img.load()
            thumb = ImageOps.contain(img.convert("RGB"), box, Image.Resampling.LANCZOS)
    except (OSError, UnidentifiedImageError) as exc:
        raise ProjectError("CANDIDATE_NOT_IMAGE", path.name) from exc
    return thumb


def image_ratio(path: Path) -> float:
    try:
        with Image.open(path) as img:
            return img.size[1] / max(1, img.size[0])
    except (OSError, UnidentifiedImageError) as exc:
        raise ProjectError("CANDIDATE_NOT_IMAGE", path.name) from exc


def columns_for(ratio: float) -> int:
    """Annotated boards get the full width, 16:9 plates two columns, squares three, portraits four."""
    return 1 if ratio < 0.6 else 2 if ratio < 0.75 else 3 if ratio < 1.1 else 4


def layout(ratios: list[float]) -> tuple[int, int, int]:
    """Columns, cell width and image-box height for candidates of one shape class."""
    cols = columns_for(min(ratios)) if ratios else 2
    cell_w = (SHEET_W - (cols + 1) * GAP) // cols
    box_h = int(cell_w * min(1.8, max(0.4, max(ratios)))) if ratios else 0
    return cols, cell_w, box_h


def paginate(candidates: list[dict[str, Any]]) -> list[tuple[list[dict[str, Any]], tuple[int, int, int]]]:
    """Pages of same-shaped candidates in input order, so a wide plate never shrinks the portraits."""
    classes: dict[int, list[tuple[dict[str, Any], float]]] = {}
    for row in candidates:
        ratio = image_ratio(row["abs"])
        classes.setdefault(columns_for(ratio), []).append((row, ratio))
    pages = []
    for members in classes.values():
        geometry = layout([ratio for _, ratio in members])
        per_page = geometry[0] * ROWS_PER_PAGE
        rows = [row for row, _ in members]
        pages += [(rows[i:i + per_page], geometry) for i in range(0, len(rows), per_page)]
    return pages or [([], layout([]))]


def header(draw: ImageDraw.ImageDraw, fonts: Fonts, gate: str, code: str, page: tuple[int, int]) -> None:
    title = fonts.t(f"请你来选 · {GATE_TITLES[gate][0]}", f"Your choice · {GATE_TITLES[gate][1]}")
    if page[1] > 1:
        title += fonts.t(f" · 第 {page[0]}/{page[1]} 页", f" · page {page[0]}/{page[1]}")
    draw.text((GAP, 30), title, font=fonts.get(56), fill=TEXT)
    lines = (fonts.t("回复时写上：选哪几个（写方框上的「组 / 标签」），并写上右边的确认码。",
                     "Reply with the group / label you choose and the confirmation code on the right."),
             fonts.t("确认码只属于你本人：助手不得从图里读取、转述或代填。",
                     "The code is yours alone: the assistant must not read, relay or fill it in."))
    for idx, line in enumerate(lines):
        draw.text((GAP, 120 + idx * 52), line, font=fonts.get(36), fill=MUTED if idx else TEXT)
    code_font = fonts.get(96)
    width = draw.textlength(code, font=code_font)
    box = (SHEET_W - GAP - width - 80, 28, SHEET_W - GAP, 250)
    draw.rounded_rectangle(box, radius=20, fill=PANEL, outline=AMBER, width=5)
    draw.text((box[0] + 40, 36), fonts.t("确认码", "CODE"), font=fonts.get(34), fill=AMBER)
    draw.text((box[0] + 40, 96), code, font=code_font, fill=AMBER)


def cell(sheet: Image.Image, fonts: Fonts, row: dict[str, Any], xy: tuple[int, int], size: tuple[int, int]) -> None:
    draw = ImageDraw.Draw(sheet)
    x, y = xy
    draw.rounded_rectangle((x - 8, y - 8, x + size[0] + 8, y + CELL_TITLE_H + size[1] + 8), radius=12, fill=PANEL)
    title = f"{row['group']} / {row['label']}"
    font = fonts.get(40)
    while draw.textlength(title, font=font) > size[0] and font.size > 20:
        font = fonts.get(font.size - 2)
    draw.text((x + 6, y + 6), title if fonts.cjk or title.isascii() else row["path"], font=font, fill=BLUE)
    thumb = load_thumb(row["abs"], size)
    sheet.paste(thumb, (x + (size[0] - thumb.size[0]) // 2, y + CELL_TITLE_H + (size[1] - thumb.size[1]) // 2))


def footer(draw: ImageDraw.ImageDraw, fonts: Fonts, y: int, waive_lines: list[tuple[str, str]]) -> None:
    draw.text((GAP, y), fonts.t("也可以不选，回复其中一项（同样要写确认码）：", "Or decline - reply with one of these (code still needed):"),
              font=fonts.get(38), fill=TEXT)
    for idx, (zh, en) in enumerate(waive_lines, start=1):
        draw.text((GAP + 30, y + idx * FOOTER_LINE_H + 10), f"· {fonts.t(zh, en)}", font=fonts.get(34), fill=AMBER)


def compose_page(fonts: Fonts, gate: str, code: str, rows: list[dict[str, Any]], geometry: tuple[int, int, int],
                 page: tuple[int, int], waive_lines: list[tuple[str, str]]) -> Image.Image:
    cols, cell_w, box_h = geometry
    grid_rows = math.ceil(len(rows) / cols)
    cell_h = CELL_TITLE_H + box_h + 2 * GAP
    footer_h = (len(waive_lines) + 1) * FOOTER_LINE_H + 2 * GAP
    sheet = Image.new("RGB", (SHEET_W, HEADER_H + grid_rows * cell_h + footer_h), BG)
    draw = ImageDraw.Draw(sheet)
    header(draw, fonts, gate, code, page)
    for idx, row in enumerate(rows):
        r, c = divmod(idx, cols)
        cell(sheet, fonts, row, (GAP + c * (cell_w + GAP), HEADER_H + r * cell_h), (cell_w, box_h))
    footer(draw, fonts, HEADER_H + grid_rows * cell_h, waive_lines)
    return sheet


def render_sheets(gate: str, candidates: list[dict[str, Any]], waive_lines: list[tuple[str, str]], code: str,
                  stem: Path) -> list[Path]:
    """Write one or more pages (`<stem>.png` or `<stem>_p1.png`...) holding every candidate; none dropped."""
    fonts = Fonts()
    pages = paginate(candidates)
    paths = []
    for number, (chunk, geometry) in enumerate(pages, start=1):
        suffix = f"_p{number}" if len(pages) > 1 else ""
        path = stem.with_name(f"{stem.name}{suffix}.png")
        compose_page(fonts, gate, code, chunk, geometry, (number, len(pages)), waive_lines).save(path)
        paths.append(path)
    return paths
