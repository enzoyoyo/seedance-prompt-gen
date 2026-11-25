"""Inventory existing project media without inferring acceptance from filenames."""
import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from drama_project import (MANIFEST_NAME, VIDEO_SUFFIXES, ProjectError, file_lock, load_manifest,
                           read_json, resolve_in_project, sha256_file, write_json_atomic)
from media_inspection import probe, subtitles
import drama_ledger as ledger

IMAGES = {".jpeg", ".jpg", ".png", ".webp"}
FOLDERS = {"clips", "clips_v2", "01_takes", "images", "output", "02_final"}
MEDIA = VIDEO_SUFFIXES | IMAGES


def files(project):
    for folder, dirs, names in os.walk(project):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in {"node_modules", "__pycache__", "venv"})
        for name in sorted(names):
            path = Path(folder, name)
            if not path.is_symlink() and path.is_file():
                yield path


def media_files(project):
    return [path for path in files(project) if path.suffix.lower() in MEDIA
            and (path.parent == project or FOLDERS.intersection(path.relative_to(project).parts[:-1]))]


def records(value):
    if isinstance(value, list):
        for row in value:
            yield from records(row)
    if isinstance(value, dict):
        for field in ("file_sha256s", "output_sha256s"):
            mapping = value.get(field, {})
            if isinstance(mapping, dict):
                for path, sha in mapping.items():
                    if isinstance(path, str) and Path(path).suffix.lower() in MEDIA:
                        yield path, {"file": path, "file_sha256": sha}
        name = value.get("file") or value.get("path")
        if isinstance(name, str) and Path(name).suffix.lower() in MEDIA:
            yield name, value
        for k, row in value.items():
            if k != "inventory":
                yield from records(row)


def untracked(project, manifest):
    known = {str(p.relative_to(project.resolve())) for name, _ in records(manifest)
             if (p := resolve_in_project(project, name))}
    known.update(row["file"] for row in manifest.get("inventory", []) if isinstance(row, dict) and "file" in row)
    return any(str(p.relative_to(project)) not in known for p in media_files(project))


def inventory(project, manifest):
    by_path = defaultdict(list)
    disk = set(media_files(project))
    support = []
    for path in files(project):
        rel = str(path.relative_to(project))
        try:
            if path.suffix.lower() in {".srt", ".ass"}:
                support.append({"file": rel, **subtitles(path)})
            elif path.suffix.lower() in {".md", ".txt", ".py", ".sh", ".fountain"}:
                support.append({"file": rel, "kind": "script"})
            elif path.suffix == ".json" and ("manifest" in path.name or "ledger" in path.name):
                if path.name != MANIFEST_NAME:
                    for name, row in records(read_json(path)):
                        by_path[name].append(row)
                support.append({"file": rel, "kind": "manifest"})
        except (ProjectError, ValueError, OSError, ArithmeticError, KeyError, IndexError) as exc:
            support.append({"file": rel, "error": str(exc)})
    for name, row in records(manifest):
        by_path[name].append(row)
    result = {kind: [] for kind in ("matched", "orphan", "ambiguous", "missing")}
    for name in by_path:
        path = resolve_in_project(project, name)
        if path and path.is_file():
            disk.add(path)
        else:
            result["missing"].append({"file": name})
    saved = []
    for path in sorted(disk):
        rel, digest = str(path.relative_to(project)), sha256_file(path)
        rows = by_path.get(rel, [])
        ids = {r.get("shot_id") for r in rows if r.get("shot_id")}
        hashes = {r.get("file_sha256") or r.get("sha256") for r in rows} - {None}
        kind = "ambiguous" if len(ids) > 1 or hashes - {digest} else ("matched" if rows else "orphan")
        item = {"file": rel, "file_sha256": digest, "classification": kind,
                "origin": next((r.get("source_origin", r["origin"]) for r in rows if r.get("origin")), "unknown_origin")}
        try:
            item.update(probe(path))
        except ProjectError as exc:
            item["error"] = str(exc)
        result[kind].append(item)
        saved.append(item)
    return {**result, "support_files": support, "inventory": saved}


def reconcile_cli(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true")
    group.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tier", choices=("draft", "lowres", "final"), default="draft",
                        help="review tier for an explicitly chosen existing take")
    parser.add_argument("--choose", action="append", default=[], metavar="SHOT=FILE",
                        help="on apply, associate a discovered clip with a shot for pending review")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    project = args.project.resolve()
    path = project / MANIFEST_NAME
    def scan():
        manifest = load_manifest(project) if path.exists() else {"version": "1.0", "project_id": project.name,
                                                                 "takes": [], "shots": [], "drama": {"sop_version": "3.0"}}
        report = inventory(project, manifest)
        if args.choose and not args.apply:
            raise ProjectError("CHOOSE_REQUIRES_APPLY")
        if args.apply:
            for choice in args.choose:
                shot, sep, name = choice.partition("=")
                item = next((r for r in report["inventory"] if r["file"] == name), None)
                if not sep or not shot.strip() or not item or not item.get("video_streams") or Path(name).suffix.lower() not in VIDEO_SUFFIXES:
                    raise ProjectError("INVALID_TAKE_SELECTION", choice)
                same = [t for t in manifest.get("takes", []) if t.get("file") == name]
                if same and not all(t.get("shot_id") == shot and t.get("file_sha256") == item["file_sha256"] for t in same):
                    raise ProjectError("TAKE_SELECTION_CONFLICT", name)
                if not same:
                    take = ledger.new_take(ledger.next_take_id(manifest, shot, args.tier), shot, shot, args.tier,
                                           file=name, file_sha256=item["file_sha256"], origin="reused",
                                           source_origin="unknown_origin", job_state="succeeded", duration_s=item["duration"])
                    manifest = ledger.add_take(manifest, take)
            write_json_atomic(path, {**manifest, "inventory": report["inventory"]})
        return report
    try:
        if not project.is_dir():
            raise ProjectError("PROJECT_MISSING")
        if args.apply:
            with file_lock(path):
                report = scan()
        else:
            report = scan()
    except (OSError, ValueError, ProjectError, ArithmeticError, KeyError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}))
        return 3
    print(json.dumps({"ok": True, "applied": args.apply, **report}, ensure_ascii=False, indent=2))
    return 0
