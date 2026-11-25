#!/usr/bin/env python3
"""List execution adapters detected on this host for the '### 执行选择' gate.

The script is host-agnostic and evidence-only: it reports credential NAMES with a
present/missing state, whether an adapter skill directory or CLI exists, and a
status string. Extended discovery can inspect the model catalog on a local
OpenAI-compatible proxy loopback. Credential values are never included in the output.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from intake_choices import MODES

ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=")

DEFAULT_SKILLS_ROOTS = (
    "~/.hermes/skills",
    "~/.claude/skills",
    "~/.codex/skills",
    "~/.agents/skills",
    "~/.cursor/skills",
    "~/.gemini/skills",
)

DEFAULT_ENV_FILES = (
    "~/.config/seedance-prompt-gen/.env",
)

MAX_SKILL_DEPTH = 3

REGISTRY: List[Dict[str, Any]] = [
    {
        "name": "hermes-image-generate",
        "kinds": ["image"],
        "host_tool": True,
        "env_all": [],
        "env_any": [],
        "cli": [],
        "skill_dir": None,
        "note": "宿主原生 image_generate",
    },
    {
        "name": "lovart-api",
        "kinds": ["image", "video"],
        "env_all": ["LOVART_ACCESS_KEY", "LOVART_SECRET_KEY"],
        "skill_dir": "lovart-api",
    },
    {
        "name": "atlas-cloud",
        "kinds": ["image", "video"],
        "env_any": ["ATLASCLOUD_API_KEY", "ATLAS_API_KEY"],
        "skill_dir": "atlas-cloud",
    },
    {
        "name": "higgsfield-generate",
        "kinds": ["image", "video"],
        "cli": ["higgsfield"],
        "login_session": True,
        "skill_dir": "higgsfield-generate",
        "note": "登录态需 `higgsfield account status` 核对",
    },
    {
        "name": "xyq-skill",
        "kinds": ["image", "video"],
        "env_all": ["XYQ_ACCESS_KEY"],
        "skill_dir": "xyq-skill",
    },
    {
        "name": "xyq-short-drama-skill",
        "kinds": ["video"],
        "env_all": ["XYQ_ACCESS_KEY"],
        "skill_dir": "xyq-short-drama-skill",
    },
    {
        "name": "elevenlabs",
        "kinds": ["audio"],
        "env_any": ["ELEVENLABS_API_KEY", "ELEVENLABS_API_KEYS"],
        "skill_dir": None,
    },
    {
        "name": "agy",
        "kinds": ["analysis"],
        "cli": ["agy"],
        "skill_dir": None,
        "note": "多模态 CLI 抽帧与视频分析（可选）",
    },
]


EXTENDED_REGISTRY = [
    {
        "name": "google-flow-web",
        "kinds": ["image", "video"],
        "env_any": ["GEMINI_API_KEY"],
        "login_session": True,
        "note": "Browser MCP/CDP bridge or Gemini API: Nano Banana 2.1, Veo 3.1, Omni 1.2",
    },
    {
        "name": "grok-imagine",
        "kinds": ["image", "video"],
        "cli": ["grok"],
        "env_any": ["XAI_API_KEY", "GROK_API_KEY"],
        "note": "xAI API, Grok Web bridge or local OpenAI-compatible proxy",
    },
    {"name": "kling", "kinds": ["image", "video"], "skill_dir": "kling", "env_any": ["KLING_ACCESS_KEY"]},
    {"name": "seedance-ark", "kinds": ["image", "video"], "env_any": ["ARK_API_KEY"]},
    {"name": "ffmpeg", "kinds": ["post"], "cli": ["ffmpeg", "ffprobe"]},
]
MODE_KINDS = dict(zip(MODES, (set(), {"image"}, {"image", "video"}, {"image", "video", "audio", "post"})))


def browser_bridge_configured() -> bool:
    """Detect whether any common MCP browser automation server is registered locally without reading secrets."""
    home = Path.home()
    for name in (".claude.json", ".claude/settings.json", ".gemini/settings.json", ".cursor/mcp.json"):
        try:
            config = json.loads((home / name).read_text())
            if isinstance(config, dict):
                projects = config.get("projects", {})
                scopes = [config, *(projects.values() if isinstance(projects, dict) else ())]
                for scope in scopes:
                    servers = scope.get("mcpServers") if isinstance(scope, dict) else None
                    if isinstance(servers, dict) and any(
                        token in key.lower() for key in servers for token in ("browser", "playwright", "chrome", "cdp")
                    ):
                        return True
        except (OSError, ValueError):
            continue
    return False


def local_proxy_loopback():
    """Probe an optional local OpenAI-compatible catalog on loopback; redirect responses never leave the host."""
    raw_port = os.environ.get("OPENAI_COMPAT_PROXY_PORT", "8080")
    try:
        port = int(raw_port)
    except ValueError:
        port = 8080
    if not (1 <= port <= 65535):
        port = 8080
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=.4)
    try:
        conn.request("GET", "/v1/models")
        response = conn.getresponse()
        if response.status != 200:
            return {"reachable": True, "enumerates_models": None, "http_status": response.status}
        models = json.loads(response.read(1024 * 1024)).get("data")
        enumerated = isinstance(models, list) and all(isinstance(m, dict) and isinstance(m.get("id"), str) for m in models)
        return {"reachable": True, "enumerates_models": enumerated, "http_status": response.status}
    except (ConnectionError, TimeoutError, OSError, http.client.HTTPException):
        return {"reachable": False, "enumerates_models": None}
    except (ValueError, AttributeError):
        return {"reachable": True, "enumerates_models": False}
    finally:
        conn.close()


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


def build_rows(env_file_names: set, skill_dir_names: set, extended: bool = False, probe_network: bool = False) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, entry in enumerate(REGISTRY + (EXTENDED_REGISTRY if extended else []), start=1):
        env_all = list(entry.get("env_all", []))
        env_any = list(entry.get("env_any", []))
        credentials = [
            credential_state(name, env_file_names) for name in env_all + env_any
        ]
        by_name = {item["name"]: item for item in credentials}

        skill_dir_name = entry.get("skill_dir")
        skill_dir = None
        if skill_dir_name:
            skill_dir = {
                "name": skill_dir_name,
                "found": skill_dir_name in skill_dir_names,
            }

        cli = []
        for name in entry.get("cli", []):
            cli.append({"name": name, "found": shutil.which(name) is not None})
        if entry.get("cli_path"):
            cli_path = os.path.expanduser(entry["cli_path"])
            cli.append(
                {
                    "name": os.path.basename(cli_path),
                    "found": os.path.isfile(cli_path) and os.access(cli_path, os.X_OK),
                    "path": cli_path,
                }
            )

        rows.append(
            {
                "index": index,
                "name": entry["name"],
                "kinds": list(entry["kinds"]),
                "credentials": credentials,
                "skill_dir": skill_dir,
                "cli": cli,
                "status": resolve_status(entry, by_name, skill_dir, cli),
                "note": entry.get("note", ""),
            }
        )
        if not extended:
            continue
        row = rows[-1]
        installed = bool(skill_dir and skill_dir["found"]) or any(item["found"] for item in cli)
        row.update(installed=installed if skill_dir or cli else None, logged_in=None,
                   enumerates_models=None, operation_supported=None, quoted=False)
        if entry["name"] in {"google-flow-web", "grok-imagine"}:
            row["browser_bridge_configured"] = browser_bridge_configured()
            row["installed"] = installed or row["browser_bridge_configured"]
        if entry["name"] == "google-flow-web" and row["installed"]:
            row["status"] = "Bridge detected; verify browser session"
        if entry["name"] == "ffmpeg":
            row["installed"] = row["operation_supported"] = all(item["found"] for item in cli)
        if entry["name"] == "grok-imagine":
            local = local_proxy_loopback() if probe_network else {"reachable": None, "enumerates_models": None}
            row["enumerates_models"] = local["enumerates_models"]
            row["installed"] = row["installed"] or local["reachable"] is True
            row["routes"] = {"xai_api": by_name["XAI_API_KEY"]["state"],
                             "grok_web_bridge": row["browser_bridge_configured"],
                             "openai_compat_loopback": local["reachable"], "openai_compat_catalog": local,
                             "grok_auth_file_present": (Path.home() / ".grok/auth.json").is_file()}
    return rows


def resolve_status(
    entry: Dict[str, Any],
    by_name: Dict[str, Dict[str, Optional[str]]],
    skill_dir: Optional[Dict[str, Any]],
    cli: List[Dict[str, Any]],
) -> str:
    if entry.get("host_tool"):
        return "由宿主判断"

    any_cli_found = any(item["found"] for item in cli)

    secret_file = entry.get("secret_file")
    if secret_file:
        if not any_cli_found:
            return "缺 CLI"
        if not os.path.isfile(os.path.expanduser(secret_file)):
            return "缺本地 keyring"
        return "本地 keyring 已配置（提交前仍需核验能力/报价/授权）"

    if "analysis" in entry["kinds"]:
        return "可用" if any_cli_found else "缺 CLI"

    if skill_dir is not None and not skill_dir["found"] and not any_cli_found:
        return "缺 adapter"

    env_all = list(entry.get("env_all", []))
    env_any = list(entry.get("env_any", []))
    if env_all and not all(by_name[name]["state"] == "present" for name in env_all):
        return "缺凭证"
    if env_any and not any(by_name[name]["state"] == "present" for name in env_any):
        return "缺凭证"

    if cli and not any_cli_found:
        return "缺 CLI"

    if entry.get("login_session"):
        return "需核对登录态"

    return "可直接用（待 preflight）"


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


def format_tools(row: Dict[str, Any], host_tool: bool) -> str:
    if host_tool:
        return "host tool"
    parts = []
    skill_dir = row["skill_dir"]
    if skill_dir is not None:
        parts.append("skill: {}".format("found" if skill_dir["found"] else "not found"))
    for item in row["cli"]:
        parts.append("cli: {}".format("found" if item["found"] else "not found"))
    return ", ".join(parts) if parts else "—"


def render_markdown(rows: List[Dict[str, Any]]) -> str:
    host_tool_names = {
        entry["name"] for entry in REGISTRY if entry.get("host_tool")
    }
    lines = [
        "### 执行选择",
        "",
        "| # | adapter | 能做 | 凭证 | 工具 | 状态 |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {} | {} | {} | {} | {} | {} |".format(
                row["index"],
                row["name"],
                "/".join(row["kinds"]),
                format_credentials(row["credentials"]),
                format_tools(row, row["name"] in host_tool_names),
                row["status"],
            )
        )
    lines.append("")
    lines.append(
        "回复「用 N」或点名 adapter 后开始；没有回复就停在文本交付。凭证只报名字，不回显值。"
    )
    return "\n".join(lines)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "List execution adapters detected on this host; credential names only."
        )
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print a JSON array instead of the Markdown table",
    )
    parser.add_argument(
        "--skills-root",
        action="append",
        default=None,
        metavar="PATH",
        help="directory to search for adapter skill dirs (repeatable)",
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
    parser.add_argument("--delivery-mode", choices=MODES)
    parser.add_argument("--probe-network", action="store_true", help="query the local model catalog")
    parser.add_argument("--kind", choices=("all", "image", "video", "audio", "post"))
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
    rows = build_rows(env_file_names, skill_dir_names, extended=bool(args.delivery_mode or args.kind),
                      probe_network=args.probe_network)
    if args.delivery_mode:
        rows = [row for row in rows if MODE_KINDS[args.delivery_mode].intersection(row["kinds"])]
    if args.kind and args.kind != "all":
        rows = [row for row in rows if args.kind in row["kinds"]]
    if args.delivery_mode == "prompt_only":
        message = "No live provider required. Compile for a target dialect only when explicitly requested."
        print(json.dumps({"required": False, "providers": [], "note": message}) if args.json else message)
        return 0

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
