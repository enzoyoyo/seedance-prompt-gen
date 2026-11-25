#!/usr/bin/env python3
"""Check or install thin `/seedance-prompt-gen` slash-command wrappers and host skill symlinks.

Claude Code, Hermes, and Grok expose skills natively as slash commands and need no wrapper file.
For Codex, OpenCode, Gemini CLI, Qwen Code, Antigravity, and Cursor, the thin wrapper instructs the host
to load the shared `seedance-prompt-gen` skill and forwards user arguments verbatim without copying `SKILL.md`.
Default mode is a read-only dry check; `--apply` creates missing entries and never overwrites `different` or
`dead_symlink` items.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

NAME = "seedance-prompt-gen"
SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL = SKILL_DIR / "SKILL.md"
DESCRIPTION = "AI 短剧与叙事视频开放创作、分镜提示词与成片制作（共享 seedance-prompt-gen 技能）"


def body(arguments: str | None) -> str:
    """Render shared thin slash-command prompt body referencing the canonical SKILL.md."""
    tail = (
        f"\n\n用户请求：\n{arguments}\n"
        if arguments
        else "\n\n用户请求是本条消息里斜杠命令之后的全部内容。\n"
    )
    return (
        f"使用 `{NAME}` 技能完成下面的请求。先用当前客户端的技能机制（如 `skill` 工具加载 ID `{NAME}`）加载 `{NAME}`；"
        f"客户端没有技能工具或尚未发现该技能时，读取 `{SKILL}`，并以它所在目录解析 `references/`、`templates/` 与 `scripts/`。"
        "遵守其中的门禁、授权与验收规则；访问被权限规则拒绝时遵守拒绝。"
        + tail
    )


def toml(arguments: str | None) -> str:
    """Render TOML command wrapper for hosts such as Gemini CLI and Qwen Code."""
    text = body(arguments)
    if '"""' in text:
        raise ValueError("wrapper text cannot contain triple quotes")
    return f'description = "{DESCRIPTION}"\nprompt = """\n{text}"""\n'


def markdown(arguments: str | None, front: bool = True) -> str:
    """Render Markdown command/workflow wrapper with optional YAML frontmatter."""
    head = f"---\ndescription: {DESCRIPTION}\n---\n\n" if front else f"# /{NAME}\n\n"
    return head + body(arguments)


def targets(home: Path):
    """Command/prompt wrapper targets for hosts that support per-host slash command files."""
    return [
        ("codex", home / ".codex/prompts" / f"{NAME}.md", lambda: markdown("$ARGUMENTS"), "$ARGUMENTS"),
        ("opencode", home / ".config/opencode/commands" / f"{NAME}.md", lambda: markdown("$ARGUMENTS"), "$ARGUMENTS"),
        ("gemini-cli", home / ".gemini/commands" / f"{NAME}.toml", lambda: toml("{{args}}"), "{{args}}"),
        ("qwen-code", home / ".qwen/commands" / f"{NAME}.toml", lambda: toml("{{args}}"), "{{args}}"),
        ("antigravity", home / ".gemini/antigravity/global_workflows" / f"{NAME}.md", lambda: markdown(None), None),
        ("cursor", home / ".cursor/commands" / f"{NAME}.md", lambda: markdown(None, front=False), None),
    ]


def skill_targets(home: Path):
    """Skill directory symlink targets across active local agents without duplicating ~/.hermes/skills/media."""
    hermes_media = home / ".hermes/skills/media" / NAME
    hermes_path = (
        hermes_media
        if (hermes_media.is_symlink() or hermes_media.exists() or hermes_media.resolve() == SKILL_DIR.resolve())
        else home / ".hermes/skills" / NAME
    )
    return [
        ("codex", home / ".codex/skills" / NAME, home / ".codex"),
        ("claude-code", home / ".claude/skills" / NAME, home / ".claude"),
        ("cursor", home / ".cursor/skills" / NAME, home / ".cursor"),
        ("hermes", hermes_path, home / ".hermes"),
        ("gemini-cli", home / ".gemini/skills" / NAME, home / ".gemini"),
        ("antigravity", home / ".gemini/antigravity/skills" / NAME, home / ".gemini/antigravity"),
        ("antigravity-config", home / ".gemini/config/skills" / NAME, home / ".gemini/config/skills"),
        ("antigravity-cli", home / ".gemini/antigravity-cli/skills" / NAME, home / ".gemini/antigravity-cli/skills"),
        ("opencode", home / ".config/opencode/skills" / NAME, home / ".config/opencode"),
        ("opencode-legacy", home / ".opencode/skills" / NAME, home / ".opencode/skills"),
        ("agents", home / ".agents/skills" / NAME, home / ".agents"),
        ("amp+agents", home / ".config/agents/skills" / NAME, home / ".config/agents"),
        ("grok", home / ".grok/skills" / NAME, home / ".grok"),
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def host_present(path: Path, home: Path) -> bool:
    """Only install for hosts whose config root already exists; never create a new agent's home."""
    rel = path.relative_to(home).parts
    if rel[:2] == (".gemini", "antigravity"):
        return (home / ".gemini" / "antigravity").is_dir()
    return (home / rel[0]).is_dir() if rel[0] != ".config" else (home / rel[0] / rel[1]).is_dir()


def _has_invalid_skill_reference(text: str) -> bool:
    expected = SKILL.resolve()
    for match in re.findall(r"(/[^\s`'\"<>]+/SKILL\.md)", text):
        p = Path(match)
        if not p.is_file() or p.resolve() != expected:
            return True
    return False


def _atomic_symlink(link_path: Path, target_dir: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_link = link_path.parent / f".tmp-{link_path.name}-{os.getpid()}"
    if tmp_link.is_symlink() or tmp_link.exists():
        tmp_link.unlink()
    tmp_link.symlink_to(target_dir)
    os.replace(tmp_link, link_path)


def check_skills(home: Path, apply: bool):
    """Verify or create host skill symlinks pointing to SKILL_DIR."""
    rows, conflicts = [], 0
    src_skill = SKILL.resolve()
    src_sha = _sha256(src_skill) if src_skill.is_file() else None
    src_root = SKILL_DIR.resolve()
    for host, path, presence_dir in skill_targets(home):
        if not presence_dir.is_dir():
            rows.append({"host": host, "kind": "skill", "path": str(path), "status": "host_not_installed"})
            continue
        try:
            st = path.lstat()
            exists_entry = True
        except FileNotFoundError:
            st = None
            exists_entry = False

        if exists_entry and st is not None:
            if stat.S_ISLNK(st.st_mode):
                if not path.exists():
                    status = "dead_symlink"
                elif path.resolve() == src_root:
                    status = "linked"
                else:
                    peer = path / "SKILL.md"
                    has_bundle = (path / "scripts/drama_next.py").is_file() and (
                        path / "references/drama-gates.md"
                    ).is_file()
                    status = (
                        "copied_identical"
                        if (peer.is_file() and has_bundle and src_sha and _sha256(peer) == src_sha)
                        else "different"
                    )
            elif path.is_dir():
                if path.resolve() == src_root:
                    status = "canonical"
                else:
                    peer = path / "SKILL.md"
                    has_bundle = (path / "scripts/drama_next.py").is_file() and (
                        path / "references/drama-gates.md"
                    ).is_file()
                    status = (
                        "copied_identical"
                        if (peer.is_file() and has_bundle and src_sha and _sha256(peer) == src_sha)
                        else "different"
                    )
            else:
                status = "different"
        elif apply:
            _atomic_symlink(path, src_root)
            status = "created"
        else:
            status = "missing"
        conflicts += int(status in ("different", "dead_symlink"))
        rows.append(
            {
                "host": host,
                "kind": "skill",
                "path": str(path),
                "status": status,
                "target_sha256": src_sha,
            }
        )
    return rows, conflicts


def check(home: Path, apply: bool):
    """Verify or create per-host thin slash-command wrappers without overwriting conflicting files."""
    rows, conflicts = [], 0
    for host, path, render, placeholder in targets(home):
        if not host_present(path, home):
            rows.append({"host": host, "kind": "command", "path": str(path), "status": "host_not_installed"})
            continue
        wanted = render()
        if path.is_symlink() and not path.exists():
            status = "dead_symlink"
        elif path.is_file():
            text = path.read_text(encoding="utf-8")
            if text == wanted:
                status = "already"
            elif (
                NAME in text
                and (placeholder is None or placeholder in text)
                and not _has_invalid_skill_reference(text)
            ):
                status = "present_custom"
            else:
                status = "different"
        elif apply:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as handle:
                handle.write(wanted)
            status = "created"
        else:
            status = "missing"
        conflicts += int(status in ("different", "dead_symlink"))
        rows.append({"host": host, "kind": "command", "path": str(path), "status": status})
    return rows, conflicts


def check_all(home: Path, apply: bool):
    """Check both command wrappers and native skill directory symlinks across all supported hosts."""
    cmd_rows, cmd_conflicts = check(home, apply)
    skill_rows, skill_conflicts = check_skills(home, apply)
    return cmd_rows + skill_rows, cmd_conflicts + skill_conflicts


def main(argv=None) -> int:
    """CLI entrypoint for checking or applying multi-host slash wrappers and skill symlinks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="check without writing (default)")
    parser.add_argument("--apply", action="store_true", help="write missing wrappers and skill symlinks (never overwrites)")
    parser.add_argument("--home", default=str(Path.home()), help=argparse.SUPPRESS)
    parser.add_argument("--commands-only", action="store_true", help="check or apply command wrappers only")
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        print(json.dumps({"error": "--apply and --dry-run cannot be used together"}, ensure_ascii=False), file=sys.stderr)
        return 2
    checker = check if args.commands_only else check_all
    rows, conflicts = checker(Path(args.home), args.apply)
    print(
        json.dumps(
            {
                "skill": str(SKILL),
                "skill_dir": str(SKILL_DIR),
                "apply": args.apply,
                "conflicts": conflicts,
                "results": rows,
                "note": "Claude Code, Hermes, Amp (~/.agents or ~/.config/agents/skills), and Grok discover skills natively; 'different' and 'dead_symlink' entries are never overwritten.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
