#!/usr/bin/env python3
"""Dependency check for the post tools: says exactly what is missing, what to do, and fails.

Nothing is installed or downloaded here. Each post step names the tools it needs; a missing one
is an error with the step it blocks and the next action, never a silent fallback. Stem
separation runs in its own interpreter (--demucs-python, default $DEMUCS_PY), because it usually
lives in a separate virtual environment; the other Python modules are checked in --python.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

from check_spoken_lines import cached_asr_models

STEPS = {
    "assemble": ("ffmpeg", "ffprobe"),
    "subtitles": ("ffmpeg", "whisper", "python:cv2", "python:PIL"),
    "remix": ("ffmpeg", "python:demucs"),
}
HINTS = {
    "ffmpeg": "install ffmpeg (it provides ffprobe) and put it on PATH",
    "ffprobe": "install ffmpeg (it provides ffprobe) and put it on PATH",
    "whisper": "put the whisper command on PATH, or pass --asr-bin <path> to the subtitle and line checks",
    "python:cv2": "use an interpreter with opencv-python: pass it as --python here and run the subtitle tool with it",
    "python:PIL": "use an interpreter with Pillow: pass it as --python here and run the subtitle tool with it",
    "python:demucs": ("point DEMUCS_PY (or --demucs-python) at a Python that can `import demucs`; "
                      "ask the user before creating or installing one"),
}
# Modules that live in the stem-separation interpreter rather than in --python.
DEMUCS_MODULES = frozenset({"python:demucs"})
EXIT_OK, EXIT_MISSING = 0, 4


def available(name: str, python: str, demucs_python: str) -> bool:
    """A command on PATH, or `python:<module>` importable by --python (demucs: by its own interpreter)."""
    _, _, module = name.partition(":")
    if not module:
        return shutil.which(name) is not None
    interpreter = demucs_python if name in DEMUCS_MODULES else python
    probe = f"import importlib.util, sys; sys.exit(0 if importlib.util.find_spec({module!r}) else 1)"
    try:
        return subprocess.run([interpreter, "-c", probe], check=False, capture_output=True).returncode == 0
    except OSError:
        return False


def missing_for(steps: list[str], python: str, demucs_python: str | None = None) -> dict[str, list[str]]:
    demucs = demucs_python or python
    return {step: gaps for step in steps
            if (gaps := [name for name in STEPS[step] if not available(name, python, demucs)])}


def report(steps: list[str], python: str, demucs_python: str) -> dict[str, object]:
    gaps = missing_for(steps, python, demucs_python)
    names = sorted({name for names in gaps.values() for name in names})
    result: dict[str, object] = {"ok": not gaps, "missing": gaps, "next": {name: HINTS.get(name, "see scripts/check_post_deps.py") for name in names},
                                 "python": python, "demucs_python": demucs_python}
    if "subtitles" in steps:
        result["asr_models_on_disk"] = cached_asr_models()
        result["asr_note"] = "pass one of asr_models_on_disk as --asr-model; any other model is a download"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, epilog="Exit codes: 0 all present; 4 something is missing.")
    parser.add_argument("--project", help="accepted for symmetry with the other tools; not read")
    parser.add_argument("--step", action="append", choices=sorted(STEPS), help="check only these steps (repeatable)")
    parser.add_argument("--python", default=sys.executable, help="interpreter that should have cv2 and PIL")
    parser.add_argument("--demucs-python", default=os.environ.get("DEMUCS_PY") or sys.executable,
                        help="interpreter that should have demucs; default: $DEMUCS_PY or this one")
    args = parser.parse_args(argv)
    result = report(args.step or sorted(STEPS), args.python, args.demucs_python)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_OK if result["ok"] else EXIT_MISSING


if __name__ == "__main__":
    sys.exit(main())
