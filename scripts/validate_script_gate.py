#!/usr/bin/env python3
"""Structural checks for script tension-gate / intake / diagnosis markdown."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_ROWS = ("想要", "阻力", "代价", "升级", "转折", "钩子", "结尾", "标题")
PITCH_FIELDS = ("一句话前提", "欲望式", "阻力", "可见代价", "开场钩子", "标题候选")
PITCH_FIELD_RE = (
    r"(?:一句话前提|一句话)",
    r"欲望式",
    r"阻力",
    r"(?:可见代价|代价)",
    r"(?:开场钩子|钩子)",
    r"标题候选\s*\d*",
)
BARE_TOKENS = {
    "✓", "✔", "√", "是", "通过", "OK", "ok", "已通过",
    "无", "N/A", "不适用", "生活本身",
}
FAIL_TOKS = (
    "不通过", "不成立", "✗", "×", "未通过", "❌", "✕", "缺失",
    "无", "弱", "缺", "需", "待", "不足", "空", "潜在", "不够", "薄",
)
PASS_TOKS = ("✓", "成立", "通过", "OK", "强")
QUOTES = "「」“”\"『』"
MARKER_PREFIXES = (
    "剧本张力门", "张力门诊断", "张力门", "标题候选", "接单问题", "脑暴", "剧本正文",
)
HEADING_RE = re.compile(r"^(#{2,3})\s+(\S.*)$")
NUM_RE = re.compile(r"^\s*(?:\d+[\.、\)]|\-|\*)\s*\S")
PITCH_LEAD_RE = re.compile(r"^[#*\->0-9.、)\s]+")
PITCH_NAME_RE = re.compile(
    r"(?:pitch\s*\d+|[（(]?(?:方案|点子|提案)[）)]?\s*[\d一二三四五])",
    re.IGNORECASE,
)
SEL_HEAD_RE = re.compile(r"^(选定|主选|首选|选用|选\s*\d)")
SEL_INLINE_RE = re.compile(r"(主选|选定|选用|首选|[—\-←]+\s*选|选\s*[1１一](?!\d))")
TEST_GROUPS = (
    ("陌生人", "会点", "想点"),
    ("独有", "只属于", "专属", "本集", "这个故事"),
    ("泄", "剧透"),
)


def load_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def heading_blocks(text: str) -> list[tuple[int, str, str]]:
    lines = text.splitlines()
    found: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line.strip())
        if m:
            found.append((i, len(m.group(1)), m.group(2).strip()))
    blocks: list[tuple[int, str, str]] = []
    for idx, (start, level, title) in enumerate(found):
        end = found[idx + 1][0] if idx + 1 < len(found) else len(lines)
        blocks.append((level, title, "\n".join(lines[start:end])))
    return blocks


def normalize_marker(line: str) -> str:
    return line.strip().strip("*#【】：")


def labeled_starts(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for i, line in enumerate(text.splitlines()):
        m = HEADING_RE.match(line.strip())
        if m:
            found.append((i, m.group(2).strip()))
            continue
        key = normalize_marker(line)
        if any(key.startswith(n) for n in MARKER_PREFIXES):
            found.append((i, key))
    return found


def slice_at(text: str, starts: list[tuple[int, str]], idx: int) -> str:
    lines = text.splitlines()
    start = starts[idx][0]
    end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
    return "\n".join(lines[start:end])


def find_section(text: str, needle: str) -> str | None:
    for _level, title, body in heading_blocks(text):
        if title.startswith(needle):
            return body
    return None


def find_section_or_marker(text: str, needle: str) -> str | None:
    found = find_section(text, needle)
    if found is not None:
        return found
    starts = labeled_starts(text)
    for i, (_idx, title) in enumerate(starts):
        if title.startswith(needle):
            return slice_at(text, starts, i)
    return None


def find_gate_section(text: str, prefer_diagnosis: bool = False) -> str | None:
    starts = labeled_starts(text)
    hits = [(i, title) for i, (_idx, title) in enumerate(starts) if "张力门" in title]
    if not hits:
        return None
    if prefer_diagnosis:
        for i, title in hits:
            if "诊断" in title:
                return slice_at(text, starts, i)
    return slice_at(text, starts, hits[0][0])


def split_row(line: str) -> list[str] | None:
    raw = line.strip().replace("｜", "|")
    if "|" not in raw:
        return None
    if re.match(r"^\|?\s*:?-{3,}", raw.replace("|", " ").strip() or raw):
        cells = [c.strip() for c in raw.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells if c):
            return None
    if not raw.lstrip().startswith("|") and raw.count("|") < 2:
        return None
    return [c.strip() for c in raw.strip("|").split("|")]


def parse_table(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        cells = split_row(line)
        if cells:
            rows.append(cells)
    return rows


def norm_cell(cell: str) -> str:
    return cell.replace("*", "").strip()


def match_label(cell: str, label: str) -> bool:
    return label in norm_cell(cell)


def has_quotes(text: str) -> bool:
    return any(ch in text for ch in QUOTES)


def numbered_lines(section: str) -> list[str]:
    out: list[str] = []
    for line in section.splitlines():
        s = line.strip()
        if re.match(r"^\d+[\.、\)]\s*\S", s):
            out.append(s)
    return out


def extract_mechanism(line: str) -> str | None:
    m = re.search(r"机制[:：]\s*", line)
    if m:
        rest = line[m.end():]
        cut = re.split(r"[—\-|\|]", rest, maxsplit=1)[0].strip()
        return cut or None
    pairs = re.findall(r"[（(]([^）)]+)[）)]", line)
    if pairs:
        return pairs[-1].strip() or None
    m = re.search(r"(?:——|—|-)\s*", line)
    if not m:
        return None
    rest = line[m.end():]
    cut = re.split(r"[—\-|\|]", rest, maxsplit=1)[0].strip()
    return cut or None


def first_table_rows(section: str) -> list[list[str]]:
    rows = parse_table(section)
    if not rows:
        return []
    data = rows[1:] if rows and "张力项" in norm_cell(rows[0][0]) else rows
    return [r for r in data if r and not set("".join(r)) <= set("-:| ")]


def check_required_rows(rows: list[list[str]], errors: list[str]) -> dict[str, list[str]]:
    by_label: dict[str, list[str]] = {}
    for row in rows:
        if not row:
            continue
        first = norm_cell(row[0])
        for label in REQUIRED_ROWS:
            if label in first:
                by_label[label] = row
    for label in REQUIRED_ROWS:
        if label not in by_label:
            errors.append(f"MISSING_ROW:{label}")
    return by_label


def title_evidence_exempt(evidence: str) -> bool:
    compact = evidence.strip()
    return "见下" in compact or "候选" in compact or "下方" in compact or len(compact) < 8


def validate_final_gate(text: str, errors: list[str], warnings: list[str]) -> None:
    section = find_gate_section(text, prefer_diagnosis=False)
    if section is None:
        errors.append("MISSING_GATE_SECTION")
        return
    by_label = check_required_rows(first_table_rows(section), errors)
    for label, row in by_label.items():
        evidence = row[2] if len(row) > 2 else (row[-1] if len(row) >= 2 else "")
        compact = evidence.strip()
        if label == "标题" and title_evidence_exempt(evidence):
            continue
        if len(compact) < 8:
            errors.append(f"EMPTY_EVIDENCE:{label}")
        if compact in BARE_TOKENS:
            errors.append(f"BARE_AFFIRMATION:{label}")
        if compact and compact not in BARE_TOKENS and not has_quotes(compact):
            warnings.append(f"UNQUOTED_EVIDENCE:{label}")


def find_title_section(text: str) -> str | None:
    found = find_section_or_marker(text, "标题候选")
    if found is not None:
        return found
    blocks = heading_blocks(text)
    for _level, title, body in blocks:
        if "标题候选" in title or "标题" in title:
            return body
    return None


def tests_block(section: str) -> str:
    lines = section.splitlines()
    start = None
    for i, ln in enumerate(lines):
        stripped = re.sub(r"^[\s*#-]+", "", ln.strip())
        if stripped.startswith("三测"):
            start = i
            break
    if start is None:
        return ""
    chunk = [lines[start]]
    for line in lines[start + 1:]:
        if not line.strip() or HEADING_RE.match(line.strip()):
            break
        chunk.append(line)
    return "\n".join(chunk)


def tests_ok(section: str, nums: list[str]) -> bool:
    if nums and all("三测" in line for line in nums):
        return True
    block = tests_block(section)
    if not block:
        return False
    hits = sum(any(tok in block for tok in group) for group in TEST_GROUPS)
    return hits >= 2


def selection_ok(section: str, nums: list[str]) -> bool:
    for ln in section.splitlines():
        stripped = re.sub(r"[*\->#]", "", ln).strip()
        if SEL_HEAD_RE.match(stripped):
            return True
    return any(SEL_INLINE_RE.search(line) for line in nums)


def validate_final_titles(text: str, errors: list[str]) -> None:
    section = find_title_section(text)
    if section is None:
        errors.append("TITLE_SECTION_MISSING")
        return
    nums = numbered_lines(section)
    if len(nums) < 5:
        errors.append("TITLE_CANDIDATES_LT5")
    if len(nums) > 6:
        errors.append("TITLE_CANDIDATES_GT6")
    mechs = {extract_mechanism(line) for line in nums}
    mechs.discard(None)
    if len(mechs) < 3:
        errors.append("TITLE_MECHANISMS_LT3")
    if not tests_ok(section, nums):
        errors.append("TITLE_TESTS_MISSING")
    if not selection_ok(section, nums):
        errors.append("TITLE_SELECTION_MISSING")


def validate_final(text: str) -> tuple[list[str], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    validate_final_gate(text, errors, warnings)
    validate_final_titles(text, errors)
    return errors, warnings, []


def count_question_lines(section: str) -> int:
    n = 0
    for line in section.splitlines()[1:]:
        if HEADING_RE.match(line.strip()):
            break
        if re.match(r"^-{3,}$", line.strip()):
            continue
        if NUM_RE.match(line):
            n += 1
    return n


def is_pitch_span_start(line: str) -> bool:
    m = HEADING_RE.match(line.strip())
    if m:
        title = m.group(2).strip()
        if title.startswith("脑暴") or "pitch" in title.lower():
            return True
    return normalize_marker(line).startswith("脑暴")


def pitch_span(text: str) -> str | None:
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if is_pitch_span_start(ln)), None)
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        stripped = lines[j].strip()
        if re.match(r"^##\s+\S", stripped):
            end = j
            break
        if stripped.startswith("####"):
            continue
        key = normalize_marker(lines[j])
        if key.startswith(("接单问题", "剧本张力门", "张力门诊断", "剧本正文")):
            end = j
            break
    return "\n".join(lines[start:end])


def is_pitch_block_start(line: str) -> bool:
    s = line.strip()
    if s.startswith("####"):
        return True
    if re.match(r"^\d+[\.、)]\s*\S", s):
        return True
    stripped = PITCH_LEAD_RE.sub("", s)
    if re.match(r"^(?:pitch\s*\d+)", stripped, re.I):
        return True
    return bool(PITCH_NAME_RE.match(stripped))


def pitch_blocks(section: str) -> list[str]:
    lines = section.splitlines()
    starts = [i for i, ln in enumerate(lines) if is_pitch_block_start(ln)]
    blocks: list[str] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end])
        first = next((ln.strip() for ln in lines[start:end] if ln.strip()), "")
        if first.startswith("####") or any(
            pitch_has_field(block, pat) for pat in PITCH_FIELD_RE
        ):
            blocks.append(block)
    return blocks


def pitch_has_field(block: str, pattern: str) -> bool:
    return bool(re.search(rf"{pattern}\s*(?:[（(][^）)]*[）)]\s*)?[:：]", block))


def evidence_filled(section: str) -> int:
    n = 0
    for row in first_table_rows(section):
        evidence = row[2] if len(row) > 2 else (row[-1] if len(row) >= 2 else "")
        compact = evidence.strip()
        if compact and compact not in BARE_TOKENS:
            n += 1
    return n


def has_full_script(text: str) -> bool:
    if find_section_or_marker(text, "剧本正文") is not None:
        return True
    gate = find_gate_section(text, prefer_diagnosis=False)
    return bool(gate) and evidence_filled(gate) >= 5


def has_defaults_section(text: str) -> bool:
    return any(
        level == 3 and title.startswith("默认假设")
        for level, title, _body in heading_blocks(text)
    )


def validate_intake(text: str) -> tuple[list[str], list[str], list[str]]:
    errors: list[str] = []
    q = find_section_or_marker(text, "接单问题")
    if q is None:
        errors.append("QUESTIONS_SECTION_MISSING")
    elif count_question_lines(q) > 2:
        errors.append("QUESTIONS_GT2")
    if not has_defaults_section(text):
        errors.append("DEFAULTS_SECTION_MISSING")
    p = pitch_span(text)
    if p is None:
        errors.append("PITCHES_SECTION_MISSING")
    else:
        blocks = pitch_blocks(p)
        if not (2 <= len(blocks) <= 3):
            errors.append("PITCH_COUNT_OUT_OF_RANGE")
        for i, block in enumerate(blocks, 1):
            for field, pattern in zip(PITCH_FIELDS, PITCH_FIELD_RE):
                if not pitch_has_field(block, pattern):
                    errors.append(f"PITCH_FIELD_MISSING:{i}:{field}")
    if has_full_script(text):
        errors.append("FULL_SCRIPT_IN_INTAKE")
    return errors, [], []


def is_failing_verdict(cell: str) -> bool:
    if any(tok in cell for tok in FAIL_TOKS):
        return True
    if any(tok in cell for tok in PASS_TOKS):
        return False
    return False


def split_options(cell: str) -> list[str]:
    t = cell
    for mark in "①②③④⑤⑥⑦⑧⑨⑩❶❷❸❹❺❻❼❽❾❿":
        t = t.replace(mark, "\n")
    t = t.replace("；", "\n").replace(";", "\n")
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"\d+\)", "\n", t)
    t = re.sub(r"(^|\s)\d+[\.、]", r"\1\n", t)
    t = re.sub(r"[A-Ea-e][\.、\)]\s", "\n", t)
    return [p.strip() for p in t.splitlines() if p.strip()]


def col_index(header: list[str], needle: str, fallback: int) -> int:
    for i, cell in enumerate(header):
        if needle in norm_cell(cell):
            return i
    return fallback


def options_index(header: list[str], fallback: int) -> int:
    for i, cell in enumerate(header):
        if any(k in norm_cell(cell) for k in ("升级", "选项", "问题", "建议")):
            return i
    return max(len(header) - 1, fallback)


def sparse_owner_quote(quote: str) -> bool:
    q = quote.strip()
    if not q:
        return True
    if q in {
        "无", "空", "N/A", "n/a", "没有", "无原文", "/",
        "—", "－", "-", "--", "——", "–",
        "无原句", "原文无", "未提供", "原文未提供", "原文没有",
    }:
        return True
    if re.match(r"^[—–－\-_~～·]+$", q):
        return True
    return q.startswith((
        "无原句", "无对应", "原文无", "未提供", "原文未提供", "原文没有",
    ))


def title_options_deferred(text: str, opts: str) -> bool:
    if "候选" not in opts:
        return False
    section = find_title_section(text)
    return section is not None and len(numbered_lines(section)) >= 2


def validate_diagnosis(text: str) -> tuple[list[str], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    failing: list[str] = []
    section = find_gate_section(text, prefer_diagnosis=True)
    if section is None:
        errors.append("DIAGNOSIS_SECTION_MISSING")
        return errors, warnings, failing
    rows = parse_table(section)
    if not rows:
        errors.append("DIAGNOSIS_SECTION_MISSING")
        return errors, warnings, failing
    header, data = rows[0], rows[1:]
    i_verdict = col_index(header, "判定", 1)
    i_quote = col_index(header, "原文引用", 2)
    if i_quote == 2 and "原文" not in norm_cell(header[min(2, len(header) - 1)] if header else ""):
        i_quote = col_index(header, "原文", 2)
    i_opt = options_index(header, 3)
    by_label = check_required_rows(data, errors)
    for label, row in by_label.items():
        verdict = row[i_verdict] if len(row) > i_verdict else ""
        quote = row[i_quote] if len(row) > i_quote else ""
        opts = row[i_opt] if len(row) > i_opt else (row[-1] if row else "")
        if not is_failing_verdict(verdict):
            continue
        failing.append(label)
        if not sparse_owner_quote(quote) and not has_quotes(quote):
            errors.append(f"NO_QUOTED_OWNER_TEXT:{label}")
        if len(split_options(opts)) < 2 and not (label == "标题" and title_options_deferred(text, opts)):
            errors.append(f"UPGRADE_OPTIONS_LT2:{label}")
    if not failing:
        warnings.append("ALL_ROWS_PASS")
    if find_section(text, "剧本张力门") is not None or find_section(text, "剧本正文") is not None:
        errors.append("REWRITE_WITHOUT_CONFIRMATION")
    return errors, warnings, failing


def evaluate(text: str, mode: str) -> dict:
    if mode == "final":
        errors, warnings, failing = validate_final(text)
    elif mode == "intake":
        errors, warnings, failing = validate_intake(text)
    elif mode == "diagnosis":
        errors, warnings, failing = validate_diagnosis(text)
    else:
        errors, warnings, failing = [f"UNKNOWN_MODE:{mode}"], [], []
    payload = {
        "ok": not errors,
        "mode": mode,
        "errors": errors,
        "warnings": warnings,
        "structural_only": True,
        "semantics_checked": False,
        "failing_rows": failing,
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate structural script-gate markdown contracts.",
        epilog=(
            "Intake errors include QUESTIONS_GT2, PITCH_COUNT_OUT_OF_RANGE, "
            "and DEFAULTS_SECTION_MISSING."
        ),
    )
    parser.add_argument("--input", required=True, help="Markdown file path, or - for stdin")
    parser.add_argument(
        "--mode",
        default="final",
        choices=("final", "intake", "diagnosis"),
        help="Contract to validate (default: final)",
    )
    args = parser.parse_args(argv)
    payload = evaluate(load_input(args.input), args.mode)
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
