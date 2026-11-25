#!/usr/bin/env python3
"""Mistake-book lifecycle and the Tier-1 zero-cost regression run.

  validate   schema, non-empty directives, unique ids, off-domain/secret firewall, no conflicting
             ACTIVE rules, and every ACTIVE entry backed by an executable detector and regression case.
  add        locked transactional write behind four governance gates: off-domain check, full ACTIVE
             conflict check (even on same entry_id / rule_id), category merge with canonical case
             fingerprint dedup (duplicate case increments hit_count without bloating cases), semantic
             dedup, active-readiness gate (entries without detector or cases become CANDIDATE), and
             in-memory Tier-1 regression before saving.
  hit        count a recurrence (or, with --false-positive, a rule that hurt a valid creative choice).
  deprecate  retire a rule that stopped recurring or hurt creativity; it leaves L1 & Post-Gen injection.
  tier1-run  run every ACTIVE entry's regression cases through the Pre-Gen engine.

Local and deterministic; zero video API calls. Reads/writes run under an exclusive file lock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from drama_project import file_lock, write_json_atomic
from harness_rules import L1_RULES, active_rules_of, evaluate, valid_custom_detector

DEFAULT_BOOK = Path(__file__).resolve().parent.parent / "references" / "mistake-book.jsonl"
USER_BLOCKLIST_PATH = Path.home() / ".config" / "seedance-prompt-gen" / "private-blocklist.txt"
STATUSES = ("ACTIVE", "DEPRECATED", "CANDIDATE")
ENTRY_KEYS = ("entry_id", "rule_id", "status", "trigger_tags", "if_condition", "root_cause", "remediation_rule",
              "post_gen_focus", "hit_count", "false_positive_count", "created_at", "updated_at", "regression_cases")
TEXT_ENTRY_KEYS = ("entry_id", "rule_id", "if_condition", "root_cause", "remediation_rule", "post_gen_focus")
CASE_KEYS = ("case_id", "title", "synthetic_input_prompt_or_spec", "expected_pre_gen_verdict",
             "expected_triggered_l1_rules", "expected_blocking_errors", "remediation_rule")
OFF_DOMAIN_PATTERNS = (
    re.compile(r"SQL注入|反向Shell|数据库建表迁移|Kubernetes集群编排"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b|\bAKIA[0-9A-Z]{16}\b|BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY"),
    re.compile(r"SYNTHETIC_PRIVATE_[A-Z0-9_]+"),
)
OPPOSED = (
    ("禁烧字幕", "直出字幕"),
    ("禁止烧录字幕", "直出字幕"),
    ("no baked-in subtitles", "burn subtitles in"),
    ("禁止直出", "允许直出"),
    ("严禁直出", "允许直出"),
    ("不得直出", "可以直出"),
    ("不让模型直出", "允许直出"),
    ("不让模型直出", "直出可读"),
    ("clean_plate_post_replace", "render the ui text"),
    ("仅环境底噪", "加入背景音乐"),
    ("只要干净人声与环境声", "加入背景音乐"),
    ("至多 1 名说话者", "多人同时开口"),
)
HARDCODE_RE = re.compile(r"(?:全局|一律|所有镜头|所有短剧|always|every shot)[^。；;\n]{0,12}"
                         r"(?:9:16|16:9|\d+(?:\.\d+)?\s*(?:s|秒|fps|p\b))", re.IGNORECASE)
POS_DIRECTIVE_RE = re.compile(
    r"(?:必须|应当|务必|强制|一律|允许|可以|开启|保留)(?![不禁止严禁无])|"
    r"\b(?:must|always|allow(?:ed)?|require[ds]?)\b(?!\s+(?:not|never|no)\b)",
    re.IGNORECASE,
)
NEG_DIRECTIVE_RE = re.compile(
    r"严禁|禁止|不得|不准|不可|切勿|杜绝|不让|不要|取消|关闭|"
    r"\b(?:never|forbid\w*|prohibit\w*|must\s+not|do\s+not|cannot)\b",
    re.IGNORECASE,
)
POLARITY_STRIP_RE = re.compile(
    r"严禁|禁止|不得|不准|不可|切勿|杜绝|不让|不要|取消|关闭|必须|应当|务必|强制|一律|允许|可以|开启|保留|"
    r"\b(?:must\s+not|do\s+not|cannot|never|forbid\w*|prohibit\w*|must|always|allow(?:ed)?|require[ds]?)\b",
    re.IGNORECASE,
)
DUP_THRESHOLD, MERGE_TAGS, MERGE_CAUSE = 0.6, 0.5, 0.3


class BookError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        clean = detail
        if clean.startswith(f"{code}:"):
            clean = clean[len(code) + 1:]
        super().__init__(f"{code}:{clean}" if clean else code)
        self.code = code


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BookError("BOOK_JSON_INVALID", f"line {number}: {exc.msg}") from exc
        if not isinstance(item, dict):
            raise BookError("BOOK_JSON_INVALID", f"line {number}: entry must be an object")
        rows.append(item)
    return rows


def save(path: Path, rows: list[dict[str, Any]]) -> None:
    import tempfile
    handle, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.chmod(temp, 0o644)
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    except BaseException:
        if os.path.exists(temp):
            os.unlink(temp)
        raise


def external_blocklist(extra_file: Path | None = None) -> list[str]:
    terms: list[str] = []
    env_val = os.environ.get("SEEDANCE_PRIVATE_BLOCKLIST", "")
    if env_val.strip():
        terms += [part.strip() for part in env_val.split(",") if part.strip()]
    for path in ([USER_BLOCKLIST_PATH] + ([extra_file] if extra_file else [])):
        if path and path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                cleaned = line.split("#", 1)[0].strip()
                if cleaned:
                    terms.append(cleaned)
    return terms


def privacy_errors(row: dict[str, Any], extra_terms: list[str] | None = None) -> list[str]:
    text = json.dumps(row, ensure_ascii=False)
    lowered = text.lower()
    rid = row.get("entry_id", "new")
    for pattern in OFF_DOMAIN_PATTERNS:
        if pattern.search(text):
            return [f"PRIVATE_DOMAIN_WORD:{rid}:REDACTED"]
    for term in extra_terms or []:
        if term.lower() in lowered:
            return [f"PRIVATE_DOMAIN_WORD:{rid}:REDACTED"]
    return []


def grams(text: str, size: int = 3) -> set[str]:
    flat = re.sub(r"[\s\W_]+", "", text.lower())
    if not flat:
        return set()
    if len(flat) < size:
        return {flat}
    return {flat[i:i + size] for i in range(len(flat) - size + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def entry_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(key) or "") for key in ("if_condition", "root_cause", "remediation_rule"))


def case_fingerprint(case: dict[str, Any]) -> str:
    body = case.get("synthetic_input_prompt_or_spec")
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def has_executable_detector(row: dict[str, Any]) -> bool:
    return row.get("rule_id") in L1_RULES or valid_custom_detector(row.get("detector"))


def schema_errors(row: dict[str, Any]) -> list[str]:
    rid = row.get("entry_id", "?")
    errors = [f"ENTRY_FIELD_MISSING:{rid}:{key}" for key in ENTRY_KEYS if key not in row]
    errors += [f"ENTRY_FIELD_EMPTY:{rid}:{key}" for key in TEXT_ENTRY_KEYS if key in row and not nonempty(row.get(key))]
    if row.get("status") not in STATUSES:
        errors.append(f"ENTRY_STATUS_INVALID:{rid}")
    if not isinstance(row.get("trigger_tags"), list) or not row.get("trigger_tags") or any(not nonempty(t) for t in row.get("trigger_tags") or []):
        errors.append(f"ENTRY_TRIGGER_TAGS_EMPTY:{rid}")
    cases = row.get("regression_cases")
    if not isinstance(cases, list):
        errors.append(f"ENTRY_CASES_NOT_LIST:{rid}")
        cases = []
    for case in cases:
        if not isinstance(case, dict):
            errors.append(f"CASE_NOT_OBJECT:{rid}")
            continue
        cid = case.get("case_id", "?")
        errors += [f"CASE_FIELD_MISSING:{rid}:{cid}:{key}" for key in CASE_KEYS if key not in case]
        if case.get("expected_pre_gen_verdict") not in ("PASS", "FAIL"):
            errors.append(f"CASE_VERDICT_INVALID:{cid}")
        if not isinstance(case.get("synthetic_input_prompt_or_spec"), dict) or not case.get("synthetic_input_prompt_or_spec"):
            errors.append(f"CASE_INPUT_EMPTY:{cid}")
    if "detector" in row and row["detector"] is not None and not valid_custom_detector(row["detector"]):
        errors.append(f"ENTRY_DETECTOR_INVALID:{rid}")
    if row.get("status") == "ACTIVE":
        if not cases:
            errors.append(f"ACTIVE_WITHOUT_REGRESSION_CASE:{rid}")
        if not has_executable_detector(row):
            errors.append(f"ACTIVE_WITHOUT_ENGINE_DETECTOR:{rid}:{row.get('rule_id')}")
    return errors


def _directive_polarity_conflict(rule_a: str, rule_b: str) -> str | None:
    """Detect general semantic opposition ('必须X' vs '严禁X' / 'must X' vs 'forbid X') on the same target."""
    clauses_a = [c.strip() for c in re.split(r"[。；;！!\n]+", rule_a) if c.strip()]
    clauses_b = [c.strip() for c in re.split(r"[。；;！!\n]+", rule_b) if c.strip()]
    for ca in clauses_a:
        neg_a = bool(NEG_DIRECTIVE_RE.search(ca))
        pos_a = not neg_a and bool(POS_DIRECTIVE_RE.search(ca))
        if not (pos_a or neg_a):
            continue
        stem_a = re.sub(r"[\s\W_]+", "", POLARITY_STRIP_RE.sub("", ca).lower())
        if len(stem_a) < 2:
            continue
        for cb in clauses_b:
            neg_b = bool(NEG_DIRECTIVE_RE.search(cb))
            pos_b = not neg_b and bool(POS_DIRECTIVE_RE.search(cb))
            if not ((pos_a and neg_b) or (neg_a and pos_b)):
                continue
            stem_b = re.sub(r"[\s\W_]+", "", POLARITY_STRIP_RE.sub("", cb).lower())
            if len(stem_b) < 2:
                continue
            if stem_a == stem_b or stem_a in stem_b or stem_b in stem_a or jaccard(grams(stem_a, 2), grams(stem_b, 2)) >= 0.45:
                return f"polarity_opposed:{stem_a[:16]}"
    return None


def conflict_errors(row: dict[str, Any], others: list[dict[str, Any]], skip_self: bool = False) -> list[str]:
    """Opposite directives in one trigger domain, or a fixed creative default dressed up as a rule."""
    text = entry_text(row).lower()
    rid = row.get("entry_id") or "new"
    errors = [f"{rid}:hardcoded_creative_default"] if HARDCODE_RE.search(text) else []
    tags = set(row.get("trigger_tags") or [])
    rem_a = str(row.get("remediation_rule") or "")
    for other in others:
        if other.get("status") != "ACTIVE":
            continue
        if skip_self and other is row:
            continue
        same_domain = bool(tags & set(other.get("trigger_tags") or [])) or other.get("rule_id") == row.get("rule_id") or other.get("entry_id") == row.get("entry_id")
        if not same_domain:
            continue
        theirs = entry_text(other).lower()
        hit_pair = False
        for a, b in OPPOSED:
            if (a.lower() in text and b.lower() in theirs) or (b.lower() in text and a.lower() in theirs):
                errors.append(f"{rid}<>{other['entry_id']}:{a}|{b}")
                hit_pair = True
        if not hit_pair:
            pol = _directive_polarity_conflict(rem_a, str(other.get("remediation_rule") or ""))
            if pol:
                errors.append(f"{rid}<>{other['entry_id']}:{pol}")
    return errors


def validate_rows(rows: list[dict[str, Any]], extra_terms: list[str] | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    seen_entries: set[str] = set()
    seen_cases: set[str] = set()
    seen_fingerprints: set[str] = set()
    for row in rows:
        errors += schema_errors(row) + privacy_errors(row, extra_terms)
        errors += [f"RULE_CONFLICT_DETECTED:{c}" for c in conflict_errors(row, rows, skip_self=True)]
        if row.get("entry_id") in seen_entries:
            errors.append(f"DUPLICATE_ENTRY_ID:{row.get('entry_id')}")
        seen_entries.add(str(row.get("entry_id")))
        for case in row.get("regression_cases") or []:
            if not isinstance(case, dict):
                continue
            cid = case.get("case_id")
            if cid in seen_cases:
                errors.append(f"DUPLICATE_CASE_ID:{cid}")
            seen_cases.add(str(cid))
            if isinstance(case.get("synthetic_input_prompt_or_spec"), dict):
                fp = case_fingerprint(case)
                if fp in seen_fingerprints:
                    errors.append(f"DUPLICATE_CASE_CONTENT:{cid}")
                seen_fingerprints.add(fp)
    active = [row.get("rule_id") for row in rows if row.get("status") == "ACTIVE"]
    errors += [f"DUPLICATE_ACTIVE_RULE:{rule}" for rule in sorted({r for r in active if active.count(r) > 1})]
    return list(dict.fromkeys(errors)), warnings


def merge_target(new: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if row.get("status") != "ACTIVE":
            continue
        same_id = nonempty(new.get("entry_id")) and row.get("entry_id") == new.get("entry_id")
        same_rule = nonempty(new.get("rule_id")) and row.get("rule_id") == new.get("rule_id")
        tags = jaccard(set(new.get("trigger_tags") or []), set(row.get("trigger_tags") or []))
        cause = jaccard(grams(str(new.get("root_cause") or "")), grams(str(row.get("root_cause") or "")))
        if same_id or same_rule or (tags >= MERGE_TAGS and cause >= MERGE_CAUSE):
            return row
    return None


def next_entry_id(rows: list[dict[str, Any]]) -> str:
    numbers = [int(m.group(1)) for row in rows if (m := re.fullmatch(r"MB-(\d+)", str(row.get("entry_id"))))]
    return f"MB-{max(numbers, default=0) + 1:03d}"


def add_entry(rows: list[dict[str, Any]], new: dict[str, Any],
              extra_terms: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (candidate_rows, outcome) behind privacy, conflict, dedup/merge, and active-readiness gates."""
    if not isinstance(new, dict):
        raise BookError("ENTRY_SCHEMA_INVALID", "input must be a JSON object")
    privacy = privacy_errors(new, extra_terms)
    if privacy:
        raise BookError("PRIVATE_DOMAIN_WORD", privacy[0].split(":", 1)[1])
    for key in ("rule_id", "if_condition", "root_cause", "remediation_rule", "post_gen_focus"):
        if not nonempty(new.get(key)):
            raise BookError("ENTRY_SCHEMA_INVALID", f"ENTRY_FIELD_EMPTY:{new.get('entry_id', 'new')}:{key}")
    if not isinstance(new.get("trigger_tags"), list) or not new.get("trigger_tags") or any(not nonempty(t) for t in new["trigger_tags"]):
        raise BookError("ENTRY_SCHEMA_INVALID", "ENTRY_TRIGGER_TAGS_EMPTY")
    conflicts = conflict_errors(new, rows, skip_self=False)
    if conflicts:
        raise BookError("RULE_CONFLICT_DETECTED", ";".join(conflicts))
    stamp = now_iso()
    known_ids = {case.get("case_id") for row in rows for case in row.get("regression_cases") or [] if isinstance(case, dict)}
    known_fps = {case_fingerprint(case) for row in rows for case in row.get("regression_cases") or []
                 if isinstance(case, dict) and isinstance(case.get("synthetic_input_prompt_or_spec"), dict)}
    incoming_cases = list(new.get("regression_cases") or [])
    for case in incoming_cases:
        if not isinstance(case, dict) or any(k not in case for k in CASE_KEYS) or case.get("expected_pre_gen_verdict") not in ("PASS", "FAIL"):
            raise BookError("ENTRY_SCHEMA_INVALID", f"invalid regression case: {case.get('case_id', '?') if isinstance(case, dict) else '?'}")

    target = merge_target(new, rows)
    if target is not None:
        fresh: list[dict[str, Any]] = []
        seen_batch_fps: set[str] = set()
        for case in incoming_cases:
            fp = case_fingerprint(case)
            if case.get("case_id") not in known_ids and fp not in known_fps and fp not in seen_batch_fps:
                fresh.append(case)
                seen_batch_fps.add(fp)
        merged = {
            **target,
            "hit_count": int(target.get("hit_count") or 0) + 1,
            "updated_at": stamp,
            "trigger_tags": sorted(set(target.get("trigger_tags") or []) | set(new.get("trigger_tags") or [])),
            "regression_cases": [*(target.get("regression_cases") or []), *fresh],
        }
        updated_rows = [merged if row is target else row for row in rows]
        action = "merged" if fresh else "hit_incremented"
        return updated_rows, {"action": action, "entry_id": target["entry_id"],
                              "hit_count": merged["hit_count"], "cases_added": [c["case_id"] for c in fresh]}

    for row in rows:
        if jaccard(grams(entry_text(new)), grams(entry_text(row))) >= DUP_THRESHOLD:
            raise BookError("DUPLICATE_ENTRY", f"already covered by {row['entry_id']}")

    fresh_new = [c for c in incoming_cases if c.get("case_id") not in known_ids and case_fingerprint(c) not in known_fps]
    if incoming_cases and not fresh_new:
        raise BookError("DUPLICATE_CASE_CONTENT", "regression case already exists in mistake book")

    ready = has_executable_detector(new) and bool(fresh_new)
    status = "ACTIVE" if ready else "CANDIDATE"
    entry: dict[str, Any] = {key: new.get(key) for key in ENTRY_KEYS}
    if "detector" in new and new["detector"] is not None:
        entry["detector"] = new["detector"]
    entry.update(
        entry_id=new.get("entry_id") or next_entry_id(rows),
        title=new.get("title", ""),
        status=status,
        hit_count=int(new.get("hit_count") or 1),
        false_positive_count=int(new.get("false_positive_count") or 0),
        created_at=stamp,
        updated_at=stamp,
        regression_cases=fresh_new,
    )
    errors = schema_errors(entry)
    if errors:
        raise BookError("ENTRY_SCHEMA_INVALID", ";".join(errors))
    action = "added" if status == "ACTIVE" else "staged_candidate"
    return [*rows, entry], {"action": action, "entry_id": entry["entry_id"], "status": status}


def run_case(case: dict[str, Any], active: set[str], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    report = evaluate(case, active, book_rows=rows)
    wanted = {rule for rule in case["expected_triggered_l1_rules"] if rule in active}
    dropped = {code for code, rule in report["error_rules"].items() if rule not in active and rule != "L0"}
    expected_errors = set(case["expected_blocking_errors"]) - dropped
    got_errors = set(report["blocking_errors"])
    problems = []
    if report["verdict"] != case["expected_pre_gen_verdict"]:
        problems.append(f"verdict {report['verdict']}!={case['expected_pre_gen_verdict']}")
    if set(report["triggered_l1_rules"]) != wanted:
        problems.append(f"triggered {sorted(report['triggered_l1_rules'])}!={sorted(wanted)}")
    missing = expected_errors - got_errors
    if missing:
        problems.append(f"missing errors {sorted(missing)}")
    if case["expected_pre_gen_verdict"] == "PASS" and got_errors:
        problems.append(f"false positive {sorted(got_errors)}")
    return {"case_id": case["case_id"], "ok": not problems, "verdict": report["verdict"],
            "triggered": report["triggered_l1_rules"], "problems": problems}


def tier1(rows: list[dict[str, Any]]) -> dict[str, Any]:
    active = active_rules_of(rows)
    results = [run_case(case, active, rows) for row in rows if row.get("status") == "ACTIVE"
               for case in row.get("regression_cases") or []]
    fail_cases = [r for r in results if r["verdict"] == "FAIL"]
    return {"tool": "mistake_book.tier1", "total": len(results), "passed": sum(r["ok"] for r in results),
            "blocked_negatives": sum(1 for r in fail_cases if r["ok"]),
            "negatives": sum(1 for row in rows if row.get("status") == "ACTIVE" for c in row.get("regression_cases") or []
                             if c.get("expected_pre_gen_verdict") == "FAIL"),
            "results": results, "ok": all(r["ok"] for r in results) and bool(results)}


def update_entry(path: Path, entry_id: str, change: Any) -> dict[str, Any]:
    with file_lock(path):
        rows = load(path)
        target = next((row for row in rows if row.get("entry_id") == entry_id), None)
        if target is None:
            raise BookError("ENTRY_UNKNOWN", entry_id)
        updated = {**change(target), "updated_at": now_iso()}
        save(path, [updated if row is target else row for row in rows])
    return updated


def cmd_validate(args: argparse.Namespace) -> int:
    terms = external_blocklist(args.blocklist_file)
    errors, warnings = validate_rows(load(args.book), terms)
    print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def cmd_add(args: argparse.Namespace) -> int:
    terms = external_blocklist(args.blocklist_file)
    incoming = json.loads(args.input.read_text(encoding="utf-8"))
    with file_lock(args.book):
        current = load(args.book)
        candidate_rows, outcome = add_entry(current, incoming, terms)
        val_errors, _ = validate_rows(candidate_rows, terms)
        if val_errors:
            raise BookError("ENTRY_SCHEMA_INVALID", ";".join(val_errors))
        active_set = active_rules_of(candidate_rows)
        preview = [run_case(case, active_set, candidate_rows)
                   for row in candidate_rows if row.get("entry_id") == outcome["entry_id"]
                   for case in row.get("regression_cases") or []]
        bad_preview = [p for p in preview if not p["ok"]]
        if bad_preview:
            detail = "; ".join(f"{p['case_id']}: {', '.join(p['problems'])}" for p in bad_preview)
            raise BookError("REGRESSION_CASE_FAILED", detail)
        full_reg = tier1(candidate_rows)
        if any(r.get("status") == "ACTIVE" for r in candidate_rows) and not full_reg["ok"]:
            failed_ids = [r["case_id"] for r in full_reg["results"] if not r["ok"]]
            raise BookError("REGRESSION_CASE_FAILED", ",".join(failed_ids))
        save(args.book, candidate_rows)
    print(json.dumps({"ok": True, **outcome, "regression_preview": preview}, ensure_ascii=False, indent=2))
    return 0


def cmd_hit(args: argparse.Namespace) -> int:
    key = "false_positive_count" if args.false_positive else "hit_count"
    row = update_entry(args.book, args.id, lambda r: {**r, key: int(r.get(key) or 0) + 1})
    print(json.dumps({"ok": True, "entry_id": args.id, key: row[key]}, ensure_ascii=False, indent=2))
    return 0


def cmd_deprecate(args: argparse.Namespace) -> int:
    if not nonempty(args.reason):
        raise BookError("DEPRECATE_REASON_REQUIRED", args.id)
    row = update_entry(args.book, args.id, lambda r: {**r, "status": "DEPRECATED", "deprecated_reason": args.reason,
                                                      "deprecated_at": now_iso()})
    print(json.dumps({"ok": True, "entry_id": args.id, "status": row["status"], "rule_id": row.get("rule_id")},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_tier1(args: argparse.Namespace) -> int:
    report = tier1(load(args.book))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for row in report["results"]:
            mark = "PASS" if row["ok"] else "FAIL"
            print(f"{mark} {row['case_id']} verdict={row['verdict']} l1={','.join(row['triggered']) or '-'}"
                  + (f" :: {'; '.join(row['problems'])}" if row["problems"] else ""))
        print(f"TIER1 {report['passed']}/{report['total']} cases ok; negatives blocked "
              f"{report['blocked_negatives']}/{report['negatives']}")
    return 0 if report["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="Exit codes: 0 ok; 1 refused or regression failed; 3 file or JSON error.")
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name: str, handler: Any, text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=text)
        sub.add_argument("--book", type=Path, default=DEFAULT_BOOK)
        sub.add_argument("--blocklist-file", type=Path, default=None)
        sub.set_defaults(handler=handler)
        return sub

    add("validate", cmd_validate, "check the whole book")
    add("add", cmd_add, "add one entry behind dedup/merge/conflict/regression gates").add_argument(
        "--input", required=True, type=Path)
    hit = add("hit", cmd_hit, "count a recurrence or a false positive")
    hit.add_argument("--id", required=True)
    hit.add_argument("--false-positive", action="store_true")
    deprecate = add("deprecate", cmd_deprecate, "retire a rule (leaves L1 & Post-Gen injection, history kept)")
    deprecate.add_argument("--id", required=True)
    deprecate.add_argument("--reason", required=True)
    add("tier1-run", cmd_tier1, "Tier-1 zero-cost regression of all ACTIVE cases").add_argument(
        "--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except BookError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 3 if exc.code == "BOOK_JSON_INVALID" else 1
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [f"INPUT_ERROR:{exc}"]}, ensure_ascii=False, indent=2))
        return 3


if __name__ == "__main__":
    sys.exit(main())
