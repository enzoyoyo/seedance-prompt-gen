#!/usr/bin/env python3
"""Inspect a JianYing (CapCut) draft JSON for Windows drive paths and missing local fonts.

Read-only and offline: scans `draft_content.json` (or `draft_info.json` inside a draft folder),
including stringified JSON inside `materials.texts[].content`, and reports exact JSON trails for:
  - WINDOWS_DRIVE_PATH  residual Windows drive letters such as `D:` or `C:\\...`
  - MISSING_FONT_PATH   explicit font file paths that do not exist on this machine
  - MISSING_FONT        named fonts with no valid local file path and no matching installed font
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import unicodedata
from pathlib import Path
from typing import Any, BinaryIO, Callable

from drama_project import ProjectError, read_json

WIN_SLASH_RE = re.compile(r"^[A-Za-z]:[\\/]")
WIN_BARE_RE = re.compile(r"^[A-Za-z]:$")
PATH_KEY_RE = re.compile(r"(?:^path$|_path$|_dir$|_file$|_url$)")
FONT_TRAIL_RE = re.compile(r"(?:^|\.)(?:font|fonts\[\d+\])$")
FONT_SUFFIXES = frozenset({".ttf", ".otf", ".ttc", ".dfont"})
BUILTIN_FONT_LABELS = frozenset({"默认", "系统默认", "default", "system"})
SYSTEM_FONT_DIRS = (
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "/System/Library/PrivateFrameworks/FontServices.framework/Resources/Reserved",
    "/System/Library/AssetsV2/PreinstalledAssetsV2/InstallWithOs",
    "/Library/Fonts",
    "~/Library/Fonts",
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "~/.local/share/fonts",
)


def norm_font(name: str) -> str:
    folded = unicodedata.normalize("NFKC", name).casefold().strip()
    return re.sub(r"[\s_\-]+", "", folded)


def find_name_table(handle: BinaryIO, offset: int) -> tuple[int, int] | None:
    handle.seek(offset)
    head = handle.read(12)
    if len(head) < 12:
        return None
    _, num_tables = struct.unpack(">I H", head[:6])
    directory = handle.read(min(num_tables, 128) * 16)
    for idx in range(len(directory) // 16):
        tag, _, off, length = struct.unpack_from(">4s I I I", directory, idx * 16)
        if tag == b"name":
            return off, length
    return None


def decode_name_record(blob: bytes, str_off: int, rec_pos: int) -> str | None:
    pid, _, _, nid, slen, soff = struct.unpack_from(">6H", blob, rec_pos)
    if nid not in {1, 2, 4, 6, 16}:
        return None
    raw = blob[str_off + soff:str_off + soff + slen]
    encoding = "utf-16-be" if pid in {0, 3} else ("mac_roman" if pid == 1 else None)
    if encoding is None:
        return None
    try:
        text = raw.decode(encoding).strip("\x00").strip()
    except UnicodeDecodeError:
        return None
    return norm_font(text) if text else None


def read_sfnt_names(handle: BinaryIO, offset: int) -> set[str]:
    located = find_name_table(handle, offset)
    if located is None:
        return set()
    table_off, table_len = located
    handle.seek(table_off)
    blob = handle.read(min(table_len, 262144))
    if len(blob) < 6:
        return set()
    _, count, str_off = struct.unpack_from(">3H", blob, 0)
    limit = min(count, (len(blob) - 6) // 12, 256)
    names = (decode_name_record(blob, str_off, 6 + idx * 12) for idx in range(limit))
    return {name for name in names if name}


def font_file_names(path: Path) -> set[str]:
    names = {norm_font(path.stem)}
    try:
        with path.open("rb") as handle:
            magic = handle.read(12)
            offsets = [0]
            if len(magic) >= 12 and magic[:4] == b"ttcf":
                _, _, count = struct.unpack(">4s I I", magic)
                count = min(count, 64)
                raw_offs = handle.read(count * 4)
                offsets = list(struct.unpack(f">{len(raw_offs) // 4}I", raw_offs))
            for off in offsets:
                names |= read_sfnt_names(handle, off)
    except (OSError, struct.error):
        return names
    return names


def installed_fonts(extra_dirs: list[Path], include_system: bool = True) -> set[str]:
    roots = [*extra_dirs, *(Path(p).expanduser() for p in SYSTEM_FONT_DIRS if include_system)]
    found: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in FONT_SUFFIXES:
                found |= font_file_names(path)
    return found


def is_win_drive(key: str, value: str) -> bool:
    stripped = value.strip()
    if WIN_SLASH_RE.match(stripped):
        return True
    return bool(PATH_KEY_RE.search(key) and WIN_BARE_RE.match(stripped))


def valid_local_file(raw: object) -> bool:
    if not isinstance(raw, str) or not raw.strip():
        return False
    stripped = raw.strip()
    if WIN_SLASH_RE.match(stripped) or WIN_BARE_RE.match(stripped):
        return False
    return Path(stripped).expanduser().is_file()


def string_issues(node: dict[str, Any], key: str, value: str, trail: str,
                  catalog: Callable[[], set[str]]) -> list[dict[str, str]]:
    loc = f"{trail}.{key}" if trail else key
    if is_win_drive(key, value):
        return [{"code": "WINDOWS_DRIVE_PATH", "location": loc, "value": value}]
    stripped = value.strip()
    if not stripped:
        return []
    in_font = bool(FONT_TRAIL_RE.search(trail))
    if key in {"font_path", "font_url"} or (key == "path" and in_font):
        if not Path(stripped).expanduser().is_file():
            return [{"code": "MISSING_FONT_PATH", "location": loc, "value": value}]
        return []
    path_field = "font_path" if key in {"font_name", "font_title"} else ("path" if key in {"name", "title"} and in_font else None)
    if path_field is None or valid_local_file(node.get(path_field)):
        return []
    if stripped.casefold() in BUILTIN_FONT_LABELS or norm_font(stripped) in catalog():
        return []
    return [{"code": "MISSING_FONT", "location": loc, "value": value}]


def embedded_json(key: str, value: Any) -> Any | None:
    if key != "content" or not isinstance(value, str):
        return None
    trimmed = value.lstrip()
    if not trimmed.startswith(("{", "[")):
        return None
    try:
        return json.loads(trimmed)
    except json.JSONDecodeError:
        return None


def walk_dict_entry(node: dict[str, Any], key: str, value: Any, trail: str,
                    catalog: Callable[[], set[str]]) -> list[dict[str, str]]:
    loc = f"{trail}.{key}" if trail else key
    if isinstance(value, str):
        issues = string_issues(node, key, value, trail, catalog)
        nested = embedded_json(key, value)
        return [*issues, *(walk_draft(nested, f"{loc}(json)", catalog) if nested is not None else [])]
    if isinstance(value, (dict, list)):
        return walk_draft(value, loc, catalog)
    return []


def walk_list_item(item: Any, loc: str, catalog: Callable[[], set[str]]) -> list[dict[str, str]]:
    if isinstance(item, str) and WIN_SLASH_RE.match(item.strip()):
        return [{"code": "WINDOWS_DRIVE_PATH", "location": loc, "value": item}]
    if isinstance(item, (dict, list)):
        return walk_draft(item, loc, catalog)
    return []


def walk_draft(node: Any, trail: str, catalog: Callable[[], set[str]]) -> list[dict[str, str]]:
    if isinstance(node, dict):
        return [row for key, value in node.items()
                for row in walk_dict_entry(node, str(key), value, trail, catalog)]
    if isinstance(node, list):
        return [row for idx, item in enumerate(node)
                for row in walk_list_item(item, f"{trail}[{idx}]", catalog)]
    return []


def resolve_draft_file(target: Path) -> Path:
    if target.is_file():
        return target
    if target.is_dir():
        for name in ("draft_content.json", "draft_info.json"):
            candidate = target / name
            if candidate.is_file():
                return candidate
        raise ProjectError("INPUT_ERROR", f"no draft_content.json or draft_info.json in {target}")
    raise ProjectError("INPUT_ERROR", f"draft path not found: {target}")


def audit_draft(draft_path: Path, font_dirs: list[Path] | None = None,
                include_system: bool = True) -> dict[str, Any]:
    resolved = resolve_draft_file(draft_path)
    payload = read_json(resolved)
    cache: set[str] | None = None

    def catalog() -> set[str]:
        nonlocal cache
        if cache is None:
            cache = installed_fonts(font_dirs or [], include_system=include_system)
        return cache

    issues = walk_draft(payload, "", catalog)
    errors = [f"{row['code']}:{row['location']}:{row['value']}" for row in issues]
    return {"ok": not errors, "draft": str(resolved), "issues": issues, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes: 0 draft clean; 1 drive-letter or missing-font issues; 3 file or JSON error.",
    )
    parser.add_argument("--draft", required=True, type=Path, help="draft_content.json or JianYing draft directory")
    parser.add_argument("--font-dir", action="append", default=[], type=Path, help="extra directory of local fonts")
    parser.add_argument("--no-system-fonts", action="store_true", help="check named fonts only against --font-dir")
    args = parser.parse_args(argv)
    try:
        report = audit_draft(args.draft.expanduser(), [d.expanduser() for d in args.font_dir],
                             include_system=not args.no_system_fonts)
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 3
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
