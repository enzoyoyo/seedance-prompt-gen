#!/usr/bin/env python3
"""List live-research tools detected on this host for the '### 搜源工具' gate.

Companion to ``list_execution_providers.py`` and deliberately built the same way:
stdlib only, never touches the network, never runs a probed CLI, and reports
credential NAMES with a present/missing state instead of any value.

``any_available`` is true only when at least one row reaches the usable status
(``可用``). The host-native retrieval row never counts toward it: the host, not
this script, decides whether its own search tool exists, and it also spends the
current model's budget, so brainstorm mode keeps it as a fallback. When
``any_available`` is false the caller marks the whole research block
``RESEARCH_SKIPPED`` and falls back to the default intake path.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=")

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SKILLS_ROOTS = (
    "~/.hermes/skills",
    "~/.claude/skills",
    "~/.codex/skills",
    "~/.agents/skills",
    "~/.cursor/skills",
    "~/.gemini/skills",
)

DEFAULT_ENV_FILES = ("~/.config/seedance-prompt-gen/.env",)

MAX_SKILL_DEPTH = 3

STATUS_AVAILABLE = "可用"
STATUS_HOST = "由宿主判断；耗当前模型额度，脑暴模式排后"

REGISTRY: List[Dict[str, Any]] = [
    {
        "name": "grok",
        "kinds": ["search", "fetch"],
        "cli": ["grok"],
        "note": "单次调用 `grok -p`；登录态与 web 工具由 Grok CLI 自身配置决定",
    },
    {
        "name": "hermes",
        "kinds": ["search", "fetch"],
        "cli": ["hermes"],
        "note": "单次调用 `hermes chat --oneshot`；默认模型与 web backend 由 Hermes 配置决定",
    },
    {
        "name": "agent-reach",
        "kinds": ["platform_samples"],
        "cli": ["agent-reach"],
        "note": "各平台状态跑 `agent-reach doctor --json`",
    },
    {
        "name": "opencli",
        "kinds": ["platform_samples"],
        "cli": ["opencli"],
        "note": "按平台 adapter 取样本；不替代原始 URL 核验",
    },
    {
        "name": "yt-dlp",
        "kinds": ["sample_download"],
        "cli": ["yt-dlp"],
        "note": "只下可合法公开获取的样本，存临时目录",
    },
    {
        "name": "ffmpeg",
        "kinds": ["keyframes"],
        "cli": ["ffmpeg"],
        "note": "抽 0–2 s、钩子、转折、结尾关键帧",
    },
    {
        "name": "agy",
        "kinds": ["frame_analysis"],
        "cli": ["agy"],
        "note": "多模态 CLI 逐帧读取样片关键帧（可选）",
    },
    {
        "name": "doubao_search",
        "kinds": ["search"],
        "cli": ["doubao-search"],
        "env_all": ["VOLC_DOUBAO_SEARCH_API_KEY"],
        "note": "可选豆包检索 CLI；缺工具或凭证时自动跳过",
    },
    {
        "name": "host-web-search",
        "kinds": ["search", "fetch"],
        "host_tool": True,
        "note": "宿主原生检索；只作补位",
    },
    {
        "name": "exa-search",
        "kinds": ["search"],
        "skill_dir": "exa-search",
        "env_all": ["EXA_API_KEY"],
        "note": "skill 目录 + 凭证都在才可用",
    },
]


def read_env_file_names(path: str) -> List[str]:
    """Return the KEY NAMES declared in a dotenv-style file; values are dropped."""
    names: List[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                match = ENV_LINE_RE.match(line)
                del line
                if match:
                    names.append(match.group(1))
    except OSError:
        return []
    return names


def collect_env_file_names(paths: List[str]) -> set:
    names: set = set()
    for raw in paths:
        expanded = os.path.expanduser(raw)
        if os.path.isfile(expanded):
            names.update(read_env_file_names(expanded))
    return names


def collect_skill_dir_names(roots: List[str]) -> set:
    found: set = set()
    for raw in roots:
        root = os.path.expanduser(raw)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, _filenames in os.walk(root, followlinks=True):
            rel = os.path.relpath(dirpath, root)
            depth = 0 if rel == os.curdir else len(rel.split(os.sep))
            if depth >= MAX_SKILL_DEPTH:
                dirnames[:] = []
                continue
            for name in dirnames:
                found.add(name)
    return found


def credential_state(name: str, env_file_names: set) -> Dict[str, Optional[str]]:
    if os.environ.get(name):
        return {"name": name, "state": "present", "source": "env"}
    if name in env_file_names:
        return {"name": name, "state": "present", "source": "env-file"}
    return {"name": name, "state": "missing", "source": None}


def resolve_status(
    entry: Dict[str, Any],
    by_name: Dict[str, Dict[str, Optional[str]]],
    detected: Dict[str, Any],
) -> str:
    if entry.get("host_tool"):
        return STATUS_HOST

    cli = detected["cli"]
    if cli and not any(item["found"] for item in cli):
        return "缺 CLI"

    skill_dir = detected["skill_dir"]
    if skill_dir is not None and not skill_dir["found"]:
        return "缺 skill"

    probe_file = detected["file"]
    if probe_file is not None and not probe_file["found"]:
        return "缺脚本"

    env_all = list(entry.get("env_all", []))
    if env_all and not all(by_name[name]["state"] == "present" for name in env_all):
        return "缺凭证"

    return STATUS_AVAILABLE


def build_rows(env_file_names: set, skill_dir_names: set) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, entry in enumerate(REGISTRY, start=1):
        credentials = [
            credential_state(name, env_file_names)
            for name in entry.get("env_all", [])
        ]
        by_name = {item["name"]: item for item in credentials}

        skill_dir_name = entry.get("skill_dir")
        skill_dir = (
            {"name": skill_dir_name, "found": skill_dir_name in skill_dir_names}
            if skill_dir_name
            else None
        )

        file_path = entry.get("file")
        probe_file = (
            {"path": file_path, "found": (ROOT / file_path).is_file()}
            if file_path
            else None
        )

        detected = {
            "cli": [
                {"name": name, "found": shutil.which(name) is not None}
                for name in entry.get("cli", [])
            ],
            "skill_dir": skill_dir,
            "file": probe_file,
            "host_tool": bool(entry.get("host_tool")),
        }

        rows.append(
            {
                "index": index,
                "name": entry["name"],
                "kinds": list(entry["kinds"]),
                "credentials": credentials,
                "detected": detected,
                "status": resolve_status(entry, by_name, detected),
                "note": entry.get("note", ""),
            }
        )
    return rows


def format_credentials(credentials: List[Dict[str, Optional[str]]]) -> str:
    if not credentials:
        return "—"
    parts = []
    for item in credentials:
        if item["state"] == "present":
            parts.append("{} present ({})".format(item["name"], item["source"]))
        else:
            parts.append("{} missing".format(item["name"]))
    return ", ".join(parts)


def format_detected(detected: Dict[str, Any]) -> str:
    if detected["host_tool"]:
        return "host tool"
    parts = []
    for item in detected["cli"]:
        parts.append(
            "cli {}: {}".format(item["name"], "found" if item["found"] else "not found")
        )
    skill_dir = detected["skill_dir"]
    if skill_dir is not None:
        parts.append(
            "skill: {}".format("found" if skill_dir["found"] else "not found")
        )
    probe_file = detected["file"]
    if probe_file is not None:
        parts.append(
            "file: {}".format("found" if probe_file["found"] else "not found")
        )
    return ", ".join(parts) if parts else "—"


def render_markdown(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "### 搜源工具",
        "",
        "| # | 工具 | 能做 | 凭证 | 检测 | 状态 |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {} | {} | {} | {} | {} | {} |".format(
                row["index"],
                row["name"],
                "/".join(row["kinds"]),
                format_credentials(row["credentials"]),
                format_detected(row["detected"]),
                row["status"],
            )
        )
    lines.append("")
    lines.append("全部不可用时标 RESEARCH_SKIPPED；凭证只报名字，不回显值。")
    return "\n".join(lines)


def build_payload(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "gate": "搜源工具",
        "tools": rows,
        "any_available": any(row["status"] == STATUS_AVAILABLE for row in rows),
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "List live-research tools detected on this host; credential names only."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print a JSON object instead of the Markdown table",
    )
    parser.add_argument(
        "--skills-root",
        action="append",
        default=None,
        metavar="PATH",
        help="directory to search for research skill dirs (repeatable)",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=None,
        metavar="PATH",
        help="dotenv-style file whose KEY NAMES count as present (repeatable)",
    )
    parser.add_argument(
        "--no-env-file",
        action="store_true",
        help="do not scan any env file",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    roots = args.skills_root if args.skills_root else list(DEFAULT_SKILLS_ROOTS)

    if args.no_env_file:
        env_files: List[str] = []
    elif args.env_file:
        env_files = list(args.env_file)
    else:
        env_files = list(DEFAULT_ENV_FILES)

    env_file_names = collect_env_file_names(env_files)
    skill_dir_names = collect_skill_dir_names(roots)
    rows = build_rows(env_file_names, skill_dir_names)

    if args.json:
        print(json.dumps(build_payload(rows), ensure_ascii=False, indent=2))
    else:
        print(render_markdown(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
