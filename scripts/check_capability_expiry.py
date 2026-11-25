#!/usr/bin/env python3
"""Fail when a dated capability receipt is expired and unmarked."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPIRES_RE = re.compile(r"expires_at\s*=\s*(\d{4}-\d{2}-\d{2})")
MARK = "【已过期 → TODO_VERIFY_LIVE】"
ADVISORY_HEADING = "## 写作宿主观察"
STOP_REMINDING_MARKER = "不再提醒"


def parse_day(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def is_advisory_reminder(heading: str, line: str) -> bool:
    return heading == ADVISORY_HEADING and STOP_REMINDING_MARKER in line


def has_active_writing_host_note(today: date, root: Path = ROOT) -> bool:
    path = root / "references" / "model-adaptation.md"
    if not path.is_file():
        return False
    heading = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            heading = line.strip()
        if heading != ADVISORY_HEADING or MARK in line:
            continue
        if any(parse_day(match.group(1)) >= today for match in EXPIRES_RE.finditer(line)):
            return True
    return False


def scan_markdown(path: Path, today: date, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    heading = ""
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("## "):
            heading = line.strip()
        if is_advisory_reminder(heading, line):
            continue
        for match in EXPIRES_RE.finditer(line):
            expires = parse_day(match.group(1))
            if expires < today and MARK not in line:
                errors.append(f"{path.relative_to(root)}:{index}: expired {expires.isoformat()} unmarked")
    return errors


def scan_ledger(path: Path, today: date, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return errors
    for index, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        row = json.loads(raw)
        temporal = row.get("temporal") or {}
        until = temporal.get("effective_until")
        if not until:
            continue
        expires = parse_day(until[:10])
        notes = " ".join(row.get("notes") or [])
        marked = MARK in notes or MARK in raw
        if expires < today and not marked:
            errors.append(f"{path.relative_to(root)}:{index}: expired {expires.isoformat()} unmarked")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--include-matrix", action="store_true")
    args = parser.parse_args()
    today = parse_day(args.today)
    root = args.root
    errors = scan_markdown(root / "references" / "model-adaptation.md", today, root)
    errors.extend(scan_ledger(root / "references" / "platform-evidence-ledger.jsonl", today, root))
    if args.include_matrix:
        matrix = root / "references/model-capability-matrix.json"
        try:
            expires = parse_day(json.loads(matrix.read_text())["expires_at"])
            if expires < today:
                errors.append(f"{matrix.name}: expired {expires}")
        except (OSError, TypeError, ValueError, KeyError) as exc:
            errors.append(f"{matrix.name}: invalid receipt: {exc}")
    if errors:
        print("CAPABILITY_EXPIRED")
        for item in errors:
            print(item)
        return 1
    print("CAPABILITY_EXPIRY_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
