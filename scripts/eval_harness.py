#!/usr/bin/env python3
"""SPEC v2.0 eval harness: Pre-Gen text eval, dual-track sampling, Clean-Room blind review, escalation.

  pre-gen      deterministic text eval of one shot, NBP object, or regression case.
  sample       contact sheet (2 fps uniform + first + last + action-peak frame, every cell stamped
               `#NN t=S.SSs [TAG]`); `--mode dual` adds a low-rate 360p review stream, HD key frames,
               cut-boundary frames (`--prev-clip`), and side-by-side anchor board (`--anchor`).
  post-gen     Clean-Room blind review: real media decoding & metadata stripping, isolated working
               directory (`cwd=bundle`) and sanitized environment, schema-enforced stateless `agy`
               judge, atomic rubric with frame-evidence & modality checks, local deterministic
               engineering verification, and automatic project repair/invalidation state transitions.
  escalate     human-decision pack once a circuit breaker trips: bound problem frames (or explicit
               no-frame provider failure proof), root causes, variables tried, split/rewrite advice.
  asset-round  atomic pre-generation reservation (`--reserve`) and settlement (`--settle` / `--result`)
               for character/scene asset self-repair rounds (at most 2 reruns).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from drama_project import ProjectError, nonempty
from harness_rules import (
    L1_RULES, ROUTE_ACTIONS, ROUTE_ORDER, active_rules_from, active_rules_of, custom_rules_of,
    evaluate, finite_positive, load_book, rubric_for,
)

EXIT_PASS, EXIT_FAIL, EXIT_INPUT, EXIT_SKIPPED = 0, 1, 3, 4
DEFAULT_BOOK = Path(__file__).resolve().parent.parent / "references" / "mistake-book.jsonl"
AGY_MODEL = os.environ.get("AGY_MODEL", "gemini-2.5-pro")
LOCAL_RERUN_CAP = 2
VIDEO_EXTS = frozenset({".mp4", ".mov", ".webm", ".mkv", ".m4v"})
IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
MEDIA_SUFFIXES = VIDEO_EXTS | IMAGE_EXTS
SAFE_ENV_KEYS = ("HOME", "PATH", "LANG", "LC_ALL", "TMPDIR", "USER", "LOGNAME", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")


# --------------------------------------------------------------------------- parameter validation


def validate_sampling_params(sample_fps: float, cell_height: int) -> None:
    if not finite_positive(sample_fps) or sample_fps > 60.0:
        raise ValueError(f"INVALID_SAMPLE_FPS:{sample_fps}: must be a finite number in (0, 60]")
    if isinstance(cell_height, bool) or not isinstance(cell_height, int) or not (32 <= cell_height <= 2160):
        raise ValueError(f"INVALID_CELL_HEIGHT:{cell_height}: must be an integer in [32, 2160]")


def validate_timeout(timeout: float) -> None:
    if not finite_positive(timeout):
        raise ValueError(f"INVALID_TIMEOUT:{timeout}: must be a finite positive number")


# --------------------------------------------------------------------------- project access


def project_shot_case(project: Path, shot_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """(case payload, extra context, manifest) for one spec shot of a short-drama project."""
    from change_impact import pending_gate2_errors, stale_shot_ids
    from drama_project import drama_block, section
    from model_gate import gate_required, model_gate_errors
    from previs_coverage import locked_views
    from validate_shot_spec import active_shots, compose_prompt, load_project_spec, root_id, shot_rows

    spec, spec_dir, manifest = load_project_spec(project)
    all_rows = shot_rows(spec)
    rows = active_shots(all_rows)
    index = next((i for i, row in enumerate(rows) if row.get("id") == shot_id), None)
    target_row = rows[index] if index is not None else next((r for r in all_rows if r.get("id") == shot_id), None)
    if target_row is None:
        raise ValueError(f"UNKNOWN_SHOT:{shot_id}")
    drama = drama_block(manifest)
    root = root_id(all_rows, shot_id)
    raw_missing = not nonempty(target_row.get("prompt"))
    shot = {
        **target_row,
        "shot_id": shot_id,
        "duration_s": target_row.get("duration"),
        "prompt": compose_prompt(spec, spec_dir, target_row),
        **({"_raw_prompt_missing": True} if raw_missing else {}),
    }
    if root in stale_shot_ids(drama):
        shot["stale_upstream"] = True
    if pending_gate2_errors(drama):
        shot["pending_gate2"] = True
    prev = {**rows[index - 1], "shot_id": rows[index - 1]["id"]} if index is not None and index > 0 else None
    intent = section(drama, "release_intent")
    chars = section(section(drama, "identity_assets"), "characters")
    actor_views = {name.lower(): sorted(locked_views(r)) for name, r in chars.items() if isinstance(r, dict)}
    payload = {"synthetic_input_prompt_or_spec": {"curr_shot": shot, "prev_shot": prev, "release_intent": intent}}
    extra = {
        "model_gate_errors": model_gate_errors(drama) if gate_required(drama) else [],
        "project_actor_views": actor_views, "creative_mode": drama.get("creative_mode"),
    }
    return payload, extra, manifest


def cmd_pre_gen(args: argparse.Namespace) -> int:
    book_rows = load_book(args.book) if args.book and args.book.is_file() else []
    active = active_rules_of(book_rows) if book_rows else None
    if args.input:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        extra: dict[str, Any] = {}
        if args.project:
            from drama_project import drama_block, load_manifest
            from model_gate import gate_required, model_gate_errors
            drama = drama_block(load_manifest(args.project))
            extra = {"model_gate_errors": model_gate_errors(drama) if gate_required(drama) else []}
    elif args.project and args.shot:
        payload, extra, _ = project_shot_case(args.project, args.shot)
    else:
        raise ValueError("give --input, or --project with --shot")
    report = evaluate(payload, active, extra, book_rows)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return EXIT_PASS if report["verdict"] == "PASS" else EXIT_FAIL


# --------------------------------------------------------------------------- sampling


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clip_has_audio_stream(clip: Path) -> bool:
    if shutil.which("ffprobe") is None:
        return False
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
         "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True, check=False,
    )
    return done.returncode == 0 and bool(done.stdout.strip())


def scan_motion(clip: Path) -> tuple[float, int, int | None]:
    import cv2
    import numpy

    capture = cv2.VideoCapture(str(clip))
    if not capture.isOpened():
        raise ValueError(f"CLIP_UNREADABLE:{clip.name}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0) or 24.0
    if not finite_positive(fps):
        fps = 24.0
    count, previous, peak, best = 0, None, None, -1.0
    while True:
        ok, frame = capture.read()
        if not ok or frame is None:
            break
        small = cv2.cvtColor(cv2.resize(frame, (64, 64)), cv2.COLOR_BGR2GRAY).astype(numpy.float32)
        if previous is not None:
            score = float(numpy.mean(numpy.abs(small - previous)))
            if score > best:
                best, peak = score, count
        previous, count = small, count + 1
    capture.release()
    if count == 0:
        raise ValueError(f"CLIP_HAS_NO_FRAMES:{clip.name}")
    return fps, count, peak


def pick_frames(fps: float, count: int, peak: int | None, sample_fps: float) -> list[dict[str, Any]]:
    validate_sampling_params(sample_fps, 240)
    step = max(1.0, fps / sample_fps)
    tags: dict[int, list[str]] = {}
    for k in range(int(math.ceil(count / step))):
        tags.setdefault(min(count - 1, int(round(k * step))), [])
    tags.setdefault(0, []).append("FIRST")
    tags.setdefault(count - 1, []).append("LAST")
    if peak is not None:
        tags.setdefault(peak, []).append("PEAK")
    return [{"n": n, "index": index, "t": round(index / fps, 3), "tags": tags[index]}
            for n, index in enumerate(sorted(tags), start=1)]


def grab_frames(clip: Path, indices: set[int]) -> dict[int, Any]:
    import cv2

    capture = cv2.VideoCapture(str(clip))
    frames, index = {}, 0
    while indices - set(frames):
        ok, frame = capture.read()
        if not ok or frame is None:
            break
        if index in indices:
            frames[index] = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        index += 1
    capture.release()
    return frames


def frame_label(row: dict[str, Any]) -> str:
    tags = "".join(f" [{tag}]" for tag in row["tags"])
    return f"#{row['n']:02d} t={row['t']:.2f}s{tags}"


def compose_contact(images: list[tuple[str, Any]], out: Path, cell_height: int) -> None:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default()
    tiles = []
    for label, array in images:
        image = Image.fromarray(array)
        width = max(1, int(image.width * cell_height / max(1, image.height)))
        tiles.append((label, image.resize((width, cell_height))))
    columns = min(6, max(1, len(tiles)))
    cell_w = max(tile.width for _, tile in tiles)
    strip = 18
    rows = math.ceil(len(tiles) / columns)
    sheet = Image.new("RGB", (columns * cell_w, rows * (cell_height + strip)), (16, 16, 16))
    draw = ImageDraw.Draw(sheet)
    for position, (label, tile) in enumerate(tiles):
        x, y = (position % columns) * cell_w, (position // columns) * (cell_height + strip)
        draw.text((x + 4, y + 3), label, fill=(255, 230, 80), font=font)
        sheet.paste(tile, (x, y + strip))
    sheet.save(out, quality=90)


def write_sidecar(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ffmpeg_lowrate(clip: Path, out: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise FileNotFoundError("POST_DEPENDENCY_MISSING:ffmpeg")
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", str(clip),
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "veryfast", "-b:v", "400k",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k", str(out),
    ], check=True)


def last_frame(clip: Path) -> Any:
    _, count, _ = scan_motion(clip)
    return grab_frames(clip, {count - 1})[count - 1]


def save_png(array: Any, path: Path) -> Path:
    from PIL import Image

    Image.fromarray(array).save(path)
    return path


def anchor_board(anchors: list[Path], frames: list[tuple[str, Any]], out: Path, cell_height: int) -> None:
    import numpy
    from PIL import Image

    tiles = []
    for idx, p in enumerate(anchors, start=1):
        with Image.open(p) as im:
            tiles.append((f"anchor #{idx:02d}", numpy.asarray(im.convert("RGB"))))
    compose_contact([*tiles, *frames], out, cell_height)


def sample_clip(clip: Path, out_dir: Path, mode: str = "contact", sample_fps: float = 2.0,
                prev_clip: Path | None = None, anchors: list[Path] | None = None,
                cell_height: int = 240, stem_prefix: str = "") -> dict[str, Any]:
    """Contact sheet (+ dual-track extras); returns the sidecar payload with every written path."""
    validate_sampling_params(sample_fps, cell_height)
    out_dir.mkdir(parents=True, exist_ok=True)
    fps, count, peak = scan_motion(clip)
    rows = pick_frames(fps, count, peak, sample_fps)
    frames = grab_frames(clip, {row["index"] for row in rows})
    rows = [row for row in rows if row["index"] in frames]
    stem = f"{stem_prefix}{clip.stem}"
    sheet = out_dir / f"{stem}.contact.jpg"
    compose_contact([(frame_label(row), frames[row["index"]]) for row in rows], sheet, cell_height)
    has_aud = clip_has_audio_stream(clip)
    payload: dict[str, Any] = {
        "tool": "eval_harness.sample", "mode": mode, "clip": clip.name, "clip_sha256": sha256_of(clip),
        "fps": round(fps, 3), "frame_count": count, "duration_s": round(count / fps, 3), "sample_fps": sample_fps,
        "has_audio": has_aud, "frames": rows, "contact_sheet": str(sheet), "sheet_sha256": sha256_of(sheet),
        "media": [str(sheet)],
    }
    if mode == "dual":
        keyed = {tag: row for row in rows for tag in row["tags"]}
        lowrate = out_dir / f"{stem}.lowrate.mp4"
        ffmpeg_lowrate(clip, lowrate)
        keys = {tag.lower(): str(save_png(frames[row["index"]], out_dir / f"{stem}.{tag.lower()}.png"))
                for tag, row in keyed.items()}
        if prev_clip is not None and prev_clip.is_file():
            keys["cut_before"] = str(save_png(last_frame(prev_clip), out_dir / f"{stem}.cut_before.png"))
            keys["cut_after"] = keys.get("first", "")
        media_list = [str(lowrate), *[p for p in keys.values() if p]]
        payload.update(lowrate=str(lowrate), key_frames=keys, media=list(dict.fromkeys(media_list)))
    if anchors:
        board = out_dir / f"{stem}.anchor_board.jpg"
        picked = [(frame_label(row), frames[row["index"]]) for row in rows if row["tags"]]
        anchor_board(anchors, picked, board, cell_height)
        payload["anchor_board"] = str(board)
        payload["media"] = list(dict.fromkeys([*payload["media"], str(board)]))
    write_sidecar(sheet.with_name(sheet.name + ".json"), {k: v for k, v in payload.items() if k != "media"})
    return payload


def cmd_sample(args: argparse.Namespace) -> int:
    payload = sample_clip(args.clip, args.output_dir, args.mode, args.sample_fps, args.prev_clip, args.anchor,
                          args.cell_height)
    print(json.dumps({"ok": True, **{k: v for k, v in payload.items() if k != "frames"},
                      "frames": [frame_label(row) for row in payload["frames"]]}, ensure_ascii=False, indent=2))
    return EXIT_PASS


# --------------------------------------------------------------------------- clean room


class CleanRoomError(ValueError):
    code = "CLEAN_ROOM_CONTAMINATION_ERROR"


BUNDLE_TOP = frozenset({"media", "anchors", "brief.json", "rubric.json"})
BRIEF_KEYS = frozenset({"task", "expected_action", "media", "anchors", "track", "media_bindings"})
RUBRIC_KEYS = frozenset({"id", "question", "pass_example", "fail_example", "repair_route",
                         "requires_audio", "requires_motion", "needs_anchor", "parent_rule"})
TAINTED_NAME_RE = re.compile(r"shots?\b|resume-manifest|script\.lock|prompt|nbp|reasoning|transcript|history|"
                             r"cleanroom|lines\.json|qc[_-]?notes?", re.IGNORECASE)
PROMPT_MARKER_RE = re.compile(
    r"image\s*\d+\s+is\b|@[a-z]+_[a-z0-9_]+_v\d+|nbp_version|\bnegative\s*[:=]|"
    r"图片\s*\d+\s*是|参考图\s*\d+|首帧参考|尾帧参考|提示词|"
    r"\b(?:verdict|reasoning|approved|rejected|passed|failed|retake|prior\s+review|"
    r"previously\s+(?:approved|passed|reviewed)|clean[- ]?room)\b|chain[- ]of[- ]thought|"
    r"此前.*?(?:通过|合格|审查|盲审)|上一[轮版次]|已经通过|审查通过|盲审通过|"
    r"判为?\s*(?:通过|合格|失败)|废片|重拍",
    re.IGNORECASE,
)
ASCII_SHINGLE = 20
CJK_SHINGLE = 8
CJK_CHARS_RE = re.compile(r"[\u4e00-\u9fff]+")
SENTENCE_BREAK_RE = re.compile(r"[。！？]|[.!?](?=\s+\S)")
EVIDENCE_LOCATOR_RE = re.compile(
    r"#\d+|\bt=\d+(?:\.\d+)?s?\b|\b\d+(?:\.\d+)?\s*s\b|\b\d{1,2}:\d{2}\b|"
    r"\bframe\s*\d+\b|第\s*\d+\s*[帧格]|0\d\.(?:png|jpg|jpeg|webp|mp4)",
    re.IGNORECASE,
)


def ascii_shingles(text: str) -> set[str]:
    flat = re.sub(r"\s+", " ", text.lower()).strip()
    if len(flat) < ASCII_SHINGLE:
        return set()
    return {flat[i:i + ASCII_SHINGLE] for i in range(len(flat) - ASCII_SHINGLE + 1)}


def cjk_shingles(text: str) -> set[str]:
    cjk = "".join(CJK_CHARS_RE.findall(text))
    if len(cjk) < CJK_SHINGLE:
        return set()
    return {cjk[i:i + CJK_SHINGLE] for i in range(len(cjk) - CJK_SHINGLE + 1)}


def has_text_leak(candidate: str, forbidden_texts: list[str]) -> bool:
    cand_a, cand_c = ascii_shingles(candidate), cjk_shingles(candidate)
    for text in forbidden_texts:
        if not text:
            continue
        if (cand_a and (cand_a & ascii_shingles(text))) or (cand_c and (cand_c & cjk_shingles(text))):
            return True
    return False


def sanitize_image_to(src: Path, dst: Path) -> str:
    """Decode image pixels and re-save a fresh metadata-free RGB file; refuses non-image payloads."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(src) as im:
            im.load()
            rgb = im.convert("RGB")
            clean = Image.frombytes("RGB", rgb.size, rgb.tobytes())
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise CleanRoomError(f"UNDECODABLE_IMAGE:{src.name}") from exc
    if dst.suffix.lower() in {".jpg", ".jpeg"}:
        clean.save(dst, format="JPEG", quality=92)
    else:
        clean.save(dst, format="PNG")
    return sha256_of(dst)


def sanitize_video_to(src: Path, dst: Path) -> str:
    """Verify video decodability and strip container metadata tags before entering Clean-Room."""
    try:
        scan_motion(src)
    except Exception as exc:
        raise CleanRoomError(f"UNDECODABLE_VIDEO:{src.name}") from exc
    if shutil.which("ffmpeg") is not None:
        done = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-map_metadata", "-1", "-map_chapters", "-1",
             "-c", "copy", str(dst)],
            capture_output=True, text=True, check=False,
        )
        if done.returncode != 0 or not dst.is_file():
            ffmpeg_lowrate(src, dst)
    else:
        shutil.copyfile(src, dst)
    return sha256_of(dst)


def copy_sanitized_media(src: Path, dst_dir: Path, number: int) -> Path:
    suffix = src.suffix.lower()
    if suffix not in MEDIA_SUFFIXES:
        raise CleanRoomError(f"{src.name} is not plain review media")
    out_ext = ".jpg" if suffix in {".jpg", ".jpeg"} else (".png" if suffix in IMAGE_EXTS else ".mp4")
    dst = dst_dir / f"{number:02d}{out_ext}"
    if suffix in IMAGE_EXTS:
        sanitize_image_to(src, dst)
    else:
        sanitize_video_to(src, dst)
    return dst


def assert_clean_room_isolated(bundle: Path, forbidden_texts: list[str] | None = None,
                               project: Path | None = None) -> None:
    """Raise CleanRoomError unless the folder holds only decoded media, anchors, brief and rubric outside project."""
    if project is not None:
        proj_res, bun_res = project.resolve(), bundle.resolve()
        if bun_res == proj_res or proj_res in bun_res.parents:
            raise CleanRoomError("clean_room bundle must reside outside the project directory")
    names = {item.name for item in bundle.iterdir()}
    if not names <= BUNDLE_TOP:
        raise CleanRoomError(f"unexpected entries: {', '.join(sorted(names - BUNDLE_TOP))}")
    for folder in ("media", "anchors"):
        for item in (bundle / folder).iterdir() if (bundle / folder).is_dir() else []:
            if item.suffix.lower() not in MEDIA_SUFFIXES or TAINTED_NAME_RE.search(item.name):
                raise CleanRoomError(f"{folder}/{item.name} is not plain review media")
    brief = json.loads((bundle / "brief.json").read_text(encoding="utf-8"))
    rubric = json.loads((bundle / "rubric.json").read_text(encoding="utf-8"))
    if not set(brief) <= BRIEF_KEYS or any(not set(item) <= RUBRIC_KEYS for item in rubric):
        raise CleanRoomError("brief/rubric carry fields outside the four-part payload")
    action = str(brief.get("expected_action") or "")
    if not action.strip() or "\n" in action or len(action) > 200 or SENTENCE_BREAK_RE.search(action.rstrip(".。!！?？ ")):
        raise CleanRoomError("expected action must be one sentence of at most 200 characters")
    if PROMPT_MARKER_RE.search(action):
        raise CleanRoomError("expected action contains generation-prompt or prior-verdict markers")
    payload_text = json.dumps([brief, rubric], ensure_ascii=False)
    if has_text_leak(payload_text, forbidden_texts or []):
        raise CleanRoomError("payload contains text copied from the generation prompt, script or prior QC")


def build_clean_room_bundle(root: Path, media: list[Path], anchors: list[Path], expected_action: str,
                            rubric: list[dict[str, Any]], track: str,
                            forbidden_texts: list[str] | None = None,
                            media_bindings: list[dict[str, Any]] | None = None,
                            project: Path | None = None) -> Path:
    bundle = root / "clean_room"
    for folder, files in (("media", media), ("anchors", anchors)):
        (bundle / folder).mkdir(parents=True, exist_ok=True)
        for number, path in enumerate(files, start=1):
            copy_sanitized_media(path, bundle / folder, number)
    public_rubric = [{k: v for k, v in item.items() if k in ("id", "question", "pass_example", "fail_example", "repair_route")}
                     for item in rubric]
    brief: dict[str, Any] = {
        "task": "clean_room_blind_review",
        "expected_action": expected_action.strip(),
        "track": track,
        "media": sorted(p.name for p in (bundle / "media").iterdir()),
        "anchors": sorted(p.name for p in (bundle / "anchors").iterdir()),
    }
    if media_bindings:
        brief["media_bindings"] = [
            {"source_index": b["index"], "clean_files": b.get("clean_files", [])}
            for b in media_bindings
        ]
    write_sidecar(bundle / "brief.json", brief)
    write_sidecar(bundle / "rubric.json", public_rubric)
    assert_clean_room_isolated(bundle, forbidden_texts, project=project)
    return bundle


def judge_schema(rubric: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [item["id"] for item in rubric]
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "minItems": len(ids),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": ids},
                        "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
                        "evidence": {"type": "string", "minLength": 4},
                    },
                    "required": ["id", "verdict", "evidence"],
                },
            },
        },
        "required": ["items"],
    }


def judge_instruction(rubric: list[dict[str, Any]]) -> str:
    ids = ", ".join(item["id"] for item in rubric)
    return (
        "你是 Clean-Room 独立视觉盲审员，与生成环节完全隔离。本任务严禁读取任何外部记忆文件（如 BOOTSTRAP.md、AGENTS.md）"
        "或调用任何 MCP 工具，严禁猜测生成提示词或历史结论。只允许用 read_file 查看当前工作目录下的："
        "brief.json（一句话预期动作）、rubric.json（原子级是非题，每题附 PASS 正例与 FAIL 反例）、"
        "media/（待审视频、低码率审片流或带时间戳序列拼图）、anchors/（角色/场景/白模基准锚点图）。"
        f"必须逐一回答全部题号（{ids}），每题只判 PASS 或 FAIL，触碰任一红线即判 FAIL，"
        "且必须在 evidence 中写出具体帧号或时间戳（如 `#03 t=1.00s ...` 或 `01.png #01 t=0.00s ...`）。"
        '立即只输出一个 JSON 对象：{"items":[{"id":"L0-01","verdict":"PASS","evidence":"#01 t=0.00s ..."}]}'
    )


def extract_verdict(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            outer = json.loads(stripped)
            if isinstance(outer, dict):
                if outer.get("status") not in (None, "SUCCESS"):
                    return None
                if isinstance(outer.get("structured_output"), dict) and isinstance(outer["structured_output"].get("items"), list):
                    return outer["structured_output"]
                if isinstance(outer.get("items"), list):
                    return outer
                if isinstance(outer.get("response"), str):
                    text = outer["response"]
        except json.JSONDecodeError:
            pass
    decoder = json.JSONDecoder()
    found = None
    for start in [m.start() for m in re.finditer(r"\{", text)]:
        try:
            value, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            found = value
    return found


def sanitized_judge_env(bundle: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
    env["PWD"] = str(bundle)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_judge(bundle: Path, instruction: str, rubric: list[dict[str, Any]],
              judge_cmd: str | None, timeout: float) -> tuple[str, str | None, dict[str, Any]]:
    """Run judge in isolated `cwd=bundle` with sanitized env; non-zero exit never produces PASS."""
    validate_timeout(timeout)
    meta: dict[str, Any] = {"judge_cwd": str(bundle), "judge_cwd_isolated": True}
    if judge_cmd:
        inst_file = bundle.parent / "instruction.txt"
        inst_file.write_text(instruction, encoding="utf-8")
        argv = [part.replace("{bundle}", str(bundle)).replace("{instruction_file}", str(inst_file))
                .replace("{instruction}", instruction) for part in shlex.split(judge_cmd)]
        piped = None if any(tag in judge_cmd for tag in ("{instruction}", "{instruction_file}")) else instruction
        name = "judge-cmd"
    else:
        if shutil.which("agy") is None:
            raise FileNotFoundError("agy")
        schema_file = bundle.parent / "verdict_schema.json"
        schema_file.write_text(json.dumps(judge_schema(rubric), ensure_ascii=False), encoding="utf-8")
        argv = [
            "agy", "-p", instruction, "--model", AGY_MODEL, "--effort", "high",
            "--disable-slash-commands", "--output-format", "json",
            "--json-schema", str(schema_file), "--add-dir", str(bundle),
        ]
        piped, name = None, f"agy:{AGY_MODEL}"
    if shutil.which(argv[0]) is None:
        raise FileNotFoundError(argv[0])
    done = subprocess.run(
        argv, input=piped, cwd=str(bundle), env=sanitized_judge_env(bundle),
        capture_output=True, text=True, timeout=timeout, check=False,
    )
    meta["returncode"] = done.returncode
    if done.returncode != 0:
        return f"{name}:exit_{done.returncode}", None, meta
    raw = done.stdout or ""
    try:
        outer = json.loads(raw.strip())
        if isinstance(outer, dict) and outer.get("conversation_id"):
            meta["judge_session_id"] = outer["conversation_id"]
    except json.JSONDecodeError:
        pass
    return name, raw, meta


def grade(rubric: list[dict[str, Any]], verdict: dict[str, Any] | None, *,
          has_anchors: bool = True, media_has_audio: bool = True,
          track: str = "dual", media_count: int = 1) -> dict[str, Any]:
    by_id: dict[str, list[dict[str, Any]]] = {}
    for entry in (verdict or {}).get("items", []):
        if isinstance(entry, dict) and entry.get("id") is not None:
            by_id.setdefault(str(entry["id"]), []).append(entry)

    items, missing = [], []
    for item in rubric:
        rid = item["id"]
        answers = by_id.get(rid, [])
        observable = True
        unobs_reason = ""
        if item.get("needs_anchor") and not has_anchors:
            observable, unobs_reason = False, "NO_ANCHOR_PROVIDED"
        elif item.get("requires_audio") and not media_has_audio:
            observable, unobs_reason = False, "NO_AUDIO_IN_REVIEW_TRACK"
        elif item.get("requires_motion") and track == "images" and media_count < 2:
            observable, unobs_reason = False, "SINGLE_STATIC_IMAGE_NO_MOTION"

        fail_hit = next((a for a in answers if str(a.get("verdict", "")).upper() == "FAIL"), None)
        if fail_hit is not None:
            ev = str(fail_hit.get("evidence") or "").strip() or "FAIL reported by judge"
            items.append({"id": rid, "question": item["question"], "verdict": "FAIL",
                          "evidence": ev, "repair_route": item["repair_route"]})
            continue

        if not observable:
            missing.append(f"{rid}:{unobs_reason}")
            items.append({"id": rid, "question": item["question"], "verdict": None,
                          "evidence": unobs_reason, "repair_route": item["repair_route"]})
            continue
        if len(answers) == 0:
            missing.append(rid)
            items.append({"id": rid, "question": item["question"], "verdict": None,
                          "evidence": None, "repair_route": item["repair_route"]})
            continue
        if len(answers) > 1:
            missing.append(f"{rid}:DUPLICATE_ITEM_ID")
            items.append({"id": rid, "question": item["question"], "verdict": None,
                          "evidence": "duplicate item IDs in judge output", "repair_route": item["repair_route"]})
            continue

        ans = answers[0]
        val = str(ans.get("verdict", "")).upper()
        ev = str(ans.get("evidence") or "").strip()
        if val != "PASS":
            missing.append(rid)
            items.append({"id": rid, "question": item["question"], "verdict": None,
                          "evidence": ev or None, "repair_route": item["repair_route"]})
        elif not ev or not EVIDENCE_LOCATOR_RE.search(ev):
            missing.append(f"{rid}:MISSING_FRAME_EVIDENCE")
            items.append({"id": rid, "question": item["question"], "verdict": None,
                          "evidence": ev or None, "repair_route": item["repair_route"]})
        else:
            items.append({"id": rid, "question": item["question"], "verdict": "PASS",
                          "evidence": ev, "repair_route": item["repair_route"]})

    failed = [item for item in items if item["verdict"] == "FAIL"]
    routes = [route for route in ROUTE_ORDER if any(item["repair_route"] == route for item in failed)]
    overall = "FAIL" if failed else ("ANALYSIS_INCOMPLETE" if missing else "PASS")
    return {
        "verdict": overall,
        "items": items,
        "failed": [item["id"] for item in failed],
        "unanswered": missing,
        "repair_route": routes,
        "repair_actions": [ROUTE_ACTIONS[route] for route in routes],
    }


def engineering_post_checks(project: Path, manifest: dict[str, Any], spec: dict[str, Any],
                            spec_dir: Path, take: dict[str, Any], clip: Path,
                            l1: list[str]) -> list[dict[str, Any]]:
    """Deterministic local checks for manifest hashes, model identity, AV sync and resolution continuity."""
    from change_impact import take_matches_current_refs
    from drama_setup import stream_duration
    from drama_project import take_rows

    failures: list[dict[str, Any]] = []
    if take.get("stale") is True or not take_matches_current_refs(spec, spec_dir, take):
        failures.append({"id": "ENG-L1-08", "verdict": "FAIL",
                         "evidence": f"{take['take_id']} is STALE or ref_sha256s do not match current locked refs",
                         "repair_route": "cross_stage_rollback_stale"})
    rep_model = take.get("reported_model")
    req_model = take.get("exact_model_id")
    if nonempty(rep_model) and nonempty(req_model) and str(rep_model).strip() != str(req_model).strip():
        failures.append({"id": "ENG-L1-09", "verdict": "FAIL",
                         "evidence": f"reported_model {rep_model} != exact_model_id {req_model}",
                         "repair_route": "cross_stage_rollback_stale"})
    if shutil.which("ffprobe") is not None and clip.suffix.lower() in VIDEO_EXTS:
        meta = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate,duration",
             "-print_format", "json", str(clip)],
            capture_output=True, text=True, check=False,
        )
        streams = (json.loads(meta.stdout).get("streams") or []) if meta.returncode == 0 and meta.stdout else []
        v_dur, a_dur = stream_duration(streams, "video"), stream_duration(streams, "audio")
        if "L1-07" in l1 and v_dur is not None and a_dur is not None and abs(v_dur - a_dur) > 0.25:
            failures.append({"id": "ENG-L1-07-AVSYNC", "verdict": "FAIL",
                             "evidence": f"video={v_dur:.3f}s audio={a_dur:.3f}s (>0.25s)",
                             "repair_route": "post_clean_plate_fix"})
        if "L1-11" in l1:
            v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            if v_stream:
                cur_wh = (v_stream.get("width"), v_stream.get("height"))
                for other in take_rows(manifest):
                    if other.get("take_id") != take.get("take_id") and other.get("status") == "approved" and other.get("tier") == take.get("tier"):
                        op = (project / str(other.get("file") or "")).resolve()
                        if op.is_file():
                            om = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                                 "stream=width,height", "-print_format", "json", str(op)],
                                                capture_output=True, text=True, check=False)
                            ost = (json.loads(om.stdout).get("streams") or [None])[0] if om.returncode == 0 and om.stdout else None
                            if ost and (ost.get("width"), ost.get("height")) != cur_wh:
                                failures.append({"id": "ENG-L1-11-RES", "verdict": "FAIL",
                                                 "evidence": f"resolution {cur_wh} != {other['take_id']} {(ost.get('width'), ost.get('height'))}",
                                                 "repair_route": "boost_identity_anchor"})
                                break
    return failures


def resolve_take_inputs(args: argparse.Namespace, book_rows: list[dict[str, Any]],
                        active_set: set[str] | None) -> tuple[list[Path], list[Path], str, list[str], list[str], Path, Path | None, str | None, dict[str, Any]]:
    from change_impact import verify_and_collect_take_anchors
    from drama_ledger import approved_take, find_take
    from drama_project import drama_block, load_manifest, resolve_in_project, section, take_rows
    from lock_script import locked_script_text, read_lock
    from make_continuity_sheet import previous_shot_id
    from validate_shot_spec import compose_prompt, load_project_spec, shot_rows

    manifest = load_manifest(args.project)
    take = find_take(manifest, args.take)
    clip = resolve_in_project(args.project, take.get("file"))
    if clip is None or not clip.is_file():
        raise ValueError(f"CLIP_FILE_MISSING:{args.take}")
    spec, spec_dir, _ = load_project_spec(args.project)
    rows = shot_rows(spec)
    shot = next(row for row in rows if row.get("id") == take.get("spec_id"))

    drama = drama_block(manifest)
    anchors, anchor_errs = verify_and_collect_take_anchors(args.project, drama, spec, spec_dir, shot)
    if anchor_errs:
        raise CleanRoomError(f"LOCKED_ANCHOR_INVALID:{anchor_errs[0]}")
    for extra_a in args.anchor or []:
        if extra_a.is_file() and all(x.resolve() != extra_a.resolve() for x in anchors):
            anchors.append(extra_a)

    prev_clip = args.prev_clip
    if prev_clip is None:
        prev_sid = previous_shot_id(rows, take["shot_id"])
        prev_app = approved_take(manifest, prev_sid, take["tier"]) if prev_sid else None
        if prev_app and nonempty(prev_app.get("file")):
            pc = resolve_in_project(args.project, prev_app.get("file"))
            if pc and pc.is_file():
                prev_clip = pc

    action = args.expected_action or shot.get("expected_action")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("EXPECTED_ACTION_REQUIRED: pass --expected-action <one sentence> or add expected_action")

    payload, extra, _ = project_shot_case(args.project, shot["id"])
    auto_l1 = evaluate(payload, active_set, extra, book_rows)["triggered_l1_rules"]
    if args.l1:
        given_l1 = list(dict.fromkeys(args.l1))
        dropped = [r for r in auto_l1 if r not in given_l1]
        if dropped:
            raise ValueError(f"PROJECT_L1_CANNOT_DROP_TRIGGERED:{','.join(dropped)}")
        l1 = [r for r in given_l1 if active_set is None or r in active_set]
    else:
        l1 = auto_l1

    forbidden = [
        str(shot.get("prompt") or ""),
        compose_prompt(spec, spec_dir, shot),
        json.dumps({k: v for k, v in shot.items() if k != "expected_action"}, ensure_ascii=False),
        *(str(t.get("reject_reason") or "") for t in take_rows(manifest) if t.get("reject_reason")),
        *(str(t.get("failure_reason") or "") for t in take_rows(manifest) if t.get("failure_reason")),
    ]
    if read_lock(args.project) is not None:
        forbidden.append(locked_script_text(args.project))

    gen_model = str(take.get("exact_model_id") or section(drama, "model_gate").get("video_model") or "")
    ctx_bundle = {"manifest": manifest, "spec": spec, "spec_dir": spec_dir, "take": take, "shot": shot}
    return [clip], anchors, action, l1, forbidden, args.project / "qc", prev_clip, gen_model, ctx_bundle


def prepare_media(clips: list[Path], track: str, work: Path, prev_clip: Path | None,
                  anchors: list[Path] | None = None) -> tuple[list[Path], str, list[dict[str, Any]], bool]:
    videos = [c for c in clips if c.suffix.lower() in VIDEO_EXTS]
    if not videos:
        bindings = []
        for idx, c in enumerate(clips, start=1):
            bindings.append({"index": idx, "source_name": c.name, "source_sha256": sha256_of(c),
                             "derived_media": [str(c)], "derived_sha256s": [sha256_of(c)]})
        return clips, "images", bindings, False

    media: list[Path] = []
    bindings = []
    any_audio = False
    clean_counter = 1
    for idx, clip in enumerate(clips, start=1):
        sha = sha256_of(clip)
        if clip not in videos:
            media.append(clip)
            bindings.append({"index": idx, "source_name": clip.name, "source_sha256": sha,
                             "derived_media": [str(clip)], "derived_sha256s": [sha],
                             "clean_files": [f"{clean_counter:02d}{clip.suffix.lower()}"]})
            clean_counter += 1
            continue
        sub_work = work / f"clip_{idx:02d}_{sha[:8]}"
        payload = sample_clip(
            clip, sub_work, "dual" if track == "dual" else "contact",
            prev_clip=prev_clip if idx == 1 else None,
            anchors=anchors, stem_prefix=f"c{idx:02d}_",
        )
        derived = [Path(p) for p in payload["media"]]
        clean_names = []
        for d in derived:
            ext = ".jpg" if d.suffix.lower() in {".jpg", ".jpeg"} else (".png" if d.suffix.lower() in IMAGE_EXTS else ".mp4")
            clean_names.append(f"{clean_counter:02d}{ext}")
            clean_counter += 1
        media.extend(derived)
        if track == "dual" and payload.get("has_audio"):
            any_audio = True
        bindings.append({
            "index": idx,
            "source_name": clip.name,
            "source_sha256": sha,
            "contact_sheet_sha256": payload["sheet_sha256"],
            "derived_media": [str(d) for d in derived],
            "derived_sha256s": [sha256_of(d) for d in derived],
            "clean_files": clean_names,
        })
    return media, track, bindings, any_audio


def persist_project_qc_frames(project: Path, clip: Path, report: dict[str, Any]) -> list[str]:
    """Save contact sheet and any FAIL-cited problem frame PNGs into `<project>/qc/` for escalation packs."""
    if clip.suffix.lower() not in VIDEO_EXTS:
        return []
    qc = project / "qc"
    qc.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    payload = sample_clip(clip, qc, "contact")
    saved.append(str(Path(payload["contact_sheet"]).resolve().relative_to(project.resolve())))
    if report.get("verdict") == "FAIL":
        fps = float(payload.get("fps") or 24.0)
        count = int(payload.get("frame_count") or 1)
        wanted_indices: dict[str, int] = {}
        for item in report.get("items") or []:
            if item.get("verdict") != "FAIL":
                continue
            ev = str(item.get("evidence") or "")
            t_match = re.search(r"t=(\d+(?:\.\d+)?)s?", ev)
            f_match = re.search(r"#(\d+)", ev)
            if t_match:
                idx = min(count - 1, max(0, int(round(float(t_match.group(1)) * fps))))
            elif f_match:
                num = int(f_match.group(1))
                row_hit = next((r for r in payload["frames"] if r["n"] == num), None)
                idx = row_hit["index"] if row_hit else min(count - 1, max(0, num))
            else:
                idx = count // 2
            wanted_indices[item["id"]] = idx
        if wanted_indices:
            raw_frames = grab_frames(clip, set(wanted_indices.values()))
            for rid, fidx in wanted_indices.items():
                if fidx in raw_frames:
                    out_png = save_png(raw_frames[fidx], qc / f"{clip.stem}.problem_{rid}.png")
                    write_sidecar(out_png.with_name(out_png.name + ".json"), {
                        "tool": "eval_harness.problem_frame", "clip_sha256": payload["clip_sha256"],
                        "rule_id": rid, "frame_index": fidx, "png_sha256": sha256_of(out_png),
                    })
                    saved.append(str(out_png.resolve().relative_to(project.resolve())))
    return saved


def apply_post_gen_loop(project: Path, take_id: str, report: dict[str, Any]) -> dict[str, Any]:
    """Automatically transition project state on Post-Gen FAIL: reject take, queue repair or cross-stage STALE, or trip breaker."""
    import drama_ledger as ledger
    from change_impact import apply_invalidation, invalidation_scope
    from check_budget_gate import circuit_breaker_errors
    from drama_project import drama_block, now_iso, section, update_manifest
    from model_gate import delivery_mode
    from previs_coverage import scene_of_beat, script_beats
    from validate_shot_spec import load_project_spec, root_id, shot_beats, shot_rows

    spec, _, _ = load_project_spec(project)
    rows = shot_rows(spec)
    outcome: dict[str, Any] = {}

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        take = ledger.find_take(manifest, take_id)
        shot = next((r for r in rows if r.get("id") == take.get("spec_id")), {"id": take["shot_id"]})
        root_sid = root_id(rows, shot["id"])
        tier = str(take.get("tier") or "draft")
        failed_str = ",".join(report.get("failed") or [])
        routes = list(report.get("repair_route") or ["slow_or_split_shot"])
        primary = routes[0]
        reason = f"Clean-Room Post-Gen FAIL [{failed_str}] -> {primary}"

        updated = manifest
        if take.get("job_state") == "succeeded" and take.get("status") == "candidate":
            updated = ledger.judge_take(updated, take_id, "rejected", {}, reason, now_iso())

        var_map = {
            "slow_or_split_shot": "prompt",
            "boost_identity_anchor": "refs",
            "post_clean_plate_fix": "post_clean_plate",
            "cross_stage_rollback_stale": "upstream_asset_or_previs",
        }
        single_var = var_map.get(primary, "prompt")

        # Cross-stage rollback automatically invalidates the faulty Step 2/3/4 source & opens incremental Gate #2
        inv_applied = None
        if "cross_stage_rollback_stale" in routes:
            drama_cur = drama_block(updated)
            beats = script_beats(project) or []
            sc_candidates = [sc for b in shot_beats(shot, beats) if (sc := scene_of_beat(b))]
            previs_scenes = section(section(drama_cur, "previs"), "scenes")
            chars = section(section(drama_cur, "identity_assets"), "characters")
            scenes_locked = section(section(drama_cur, "identity_assets"), "scenes")
            stage, target = None, None
            if sc_candidates and sc_candidates[0] in previs_scenes and any(x in failed_str for x in ("L0-01", "L1-01", "L1-03b", "L1-10", "L1-12")):
                stage, target = "previs", sc_candidates[0]
            elif (shot.get("actors") or []) and shot["actors"][0] in chars:
                stage, target = "character", shot["actors"][0]
            elif sc_candidates and sc_candidates[0] in previs_scenes:
                stage, target = "previs", sc_candidates[0]
            elif scenes_locked:
                stage, target = "scene", next(iter(scenes_locked))
            if stage and target:
                scope = invalidation_scope(project, updated, stage, target)
                updated = apply_invalidation(updated, stage, target, reason, scope)
                inv_applied = {"stage": stage, "target": target, "stale_shots": scope["shots"],
                               "stale_previs_scenes": scope["previs_scenes"]}

        drama = drama_block(updated)
        mode = delivery_mode(drama)
        breaker_errs = circuit_breaker_errors(updated, spec, shot, tier)
        status = ("CROSS_STAGE_INVALIDATED" if inv_applied
                  else ("ESCALATED_CIRCUIT_BREAKER" if breaker_errs
                        else ("AWAITING_CLIP_RETURN" if mode == "prompt_only" else "NEEDS_SINGLE_VAR_RETAKE")))
        queue = dict(section(drama, "repair_queue"))
        queue[root_sid] = {
            "shot_id": root_sid,
            "spec_id": shot["id"],
            "tier": tier,
            "failed_take": take_id,
            "failed_items": report.get("failed", []),
            "repair_route": primary,
            "all_routes": routes,
            "single_variable": single_var,
            "status": status,
            "invalidation": inv_applied,
            "breaker_errors": breaker_errs,
            "recorded_at": now_iso(),
        }
        outcome.update(queue[root_sid])
        return {**updated, "drama": {**drama, "repair_queue": queue}}

    update_manifest(project, mutate)

    # Persist retake helper or circuit-breaker escalation pack on disk
    qc = project / "qc"
    qc.mkdir(parents=True, exist_ok=True)
    root_sid = outcome["shot_id"]
    tier = outcome["tier"]
    if outcome.get("breaker_errors"):
        pack = escalation_pack(project, root_sid, tier)
        md_path = qc / f"escalation_{root_sid}_{tier}.md"
        json_path = qc / f"escalation_{root_sid}_{tier}.json"
        md_path.write_text(pack_markdown(pack), encoding="utf-8")
        json_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
        outcome["escalation_pack_file"] = str(md_path.resolve().relative_to(project.resolve()))
    if outcome["status"] in ("NEEDS_SINGLE_VAR_RETAKE", "AWAITING_CLIP_RETURN"):
        plan_path = qc / f"{root_sid}_{tier}.retake_plan.json"
        plan_doc = {
            "supersedes": outcome["spec_id"],
            "changed_variables": [outcome["single_variable"]],
            "repair_route": outcome["repair_route"],
            "failed_items": outcome["failed_items"],
            "guidance": ROUTE_ACTIONS.get(outcome["repair_route"], ""),
        }
        write_sidecar(plan_path, plan_doc)
        outcome["retake_plan_file"] = str(plan_path.resolve().relative_to(project.resolve()))
    return outcome


def cmd_post_gen(args: argparse.Namespace) -> int:
    validate_timeout(args.timeout)
    book_rows = load_book(args.book) if args.book and args.book.is_file() else []
    active_set = active_rules_of(book_rows) if book_rows else None
    custom_map = custom_rules_of(book_rows)
    known_l1 = set(L1_RULES) | set(custom_map)

    proj_ctx: dict[str, Any] | None = None
    gen_model = ""
    if args.project and args.take:
        clips, anchors, action, l1, forbidden, out_dir, prev_clip, gen_model, proj_ctx = resolve_take_inputs(
            args, book_rows, active_set
        )
        chosen_track = args.track or ("dual" if shutil.which("ffmpeg") and clips[0].suffix.lower() in VIDEO_EXTS else "contact")
    elif args.clip and args.expected_action:
        clips = list(args.clip)
        for c in clips:
            if not c.is_file():
                raise ValueError(f"CLIP_FILE_MISSING:{c}")
        anchors = [a for a in (args.anchor or []) if a.is_file()]
        if len(anchors) != len(args.anchor or []):
            raise ValueError("ANCHOR_FILE_MISSING")
        action = args.expected_action
        l1 = list(dict.fromkeys(args.l1 or []))
        forbidden = []
        prev_clip = args.prev_clip
        out_dir = args.output.parent if args.output else clips[0].parent
        chosen_track = args.track or ("dual" if ("L1-07" in l1 and shutil.which("ffmpeg") and any(c.suffix.lower() in VIDEO_EXTS for c in clips)) else "contact")
    else:
        raise ValueError("give --project with --take, or --clip with --expected-action")

    unknown = [rule for rule in l1 if rule not in known_l1]
    if unknown:
        raise ValueError(f"UNKNOWN_L1_RULE:{','.join(unknown)}")
    if not anchors and not args.allow_no_anchor:
        raise CleanRoomError("ANCHOR_REQUIRED: provide at least one --anchor image (or pass --allow-no-anchor for anchorless clips)")

    rubric = rubric_for(l1, active_set, book_rows)
    judge_meta: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="cleanroom-") as scratch:
        work = Path(scratch)
        media, actual_track, bindings, any_audio = prepare_media(clips, chosen_track, work / "samples", prev_clip, anchors)
        bundle = build_clean_room_bundle(
            work, media, anchors, action, rubric, actual_track, forbidden,
            media_bindings=bindings, project=args.project,
        )
        instruction = judge_instruction(rubric)
        assert_instruction_clean(instruction, forbidden)
        is_mock = bool(args.mock_verdict)
        if is_mock:
            judge, raw = "mock", load_mock(args.mock_verdict)
            judge_meta = {"mock": True, "judge_cwd_isolated": False}
        else:
            try:
                judge, raw, judge_meta = run_judge(bundle, instruction, rubric, args.judge_cmd, args.timeout)
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                judge, raw, judge_meta = f"unavailable:{exc}", None, {"judge_cwd_isolated": True, "error": str(exc)}

    verified_isolated = bool(not is_mock and raw is not None and judge_meta.get("judge_cwd_isolated") is True)
    recognized_judge = bool(
        not is_mock and raw is not None and judge.startswith("agy:") and nonempty(judge_meta.get("judge_session_id"))
    )
    report: dict[str, Any] = {
        "tool": "eval_harness.post_gen",
        "judge": judge,
        "recognized_multimodal_judge": recognized_judge,
        "generator_model": gen_model or None,
        "heterogeneous_from_generator": bool(gen_model and judge and gen_model.casefold() not in judge.casefold()),
        "track": actual_track,
        "mock": is_mock,
        "clean_room_verified": verified_isolated,
        "judge_meta": judge_meta,
        "expected_action": action,
        "l1_rules": [r for r in l1 if active_set is None or r in active_set],
        "media": [p.name for p in clips],
        "clip_sha256": [sha256_of(p) for p in clips],
        "anchor_sha256s": [sha256_of(a) for a in anchors],
        "media_bindings": bindings,
    }
    if raw is None:
        report.update(verdict="ANALYSIS_SKIPPED", items=[], failed=[], unanswered=[r["id"] for r in rubric],
                      repair_route=[], repair_actions=[],
                      note=f"visual judge did not complete ({judge}): ANALYSIS_SKIPPED, never PASS")
    else:
        graded = grade(
            rubric, extract_verdict(raw),
            has_anchors=bool(anchors), media_has_audio=bool(any_audio),
            track=actual_track, media_count=len(media),
        )
        report.update(graded)

    if proj_ctx is not None:
        eng_fails = engineering_post_checks(
            args.project, proj_ctx["manifest"], proj_ctx["spec"], proj_ctx["spec_dir"],
            proj_ctx["take"], clips[0], report["l1_rules"],
        )
        if eng_fails:
            report["items"] = [*(report.get("items") or []), *eng_fails]
            report["failed"] = list(dict.fromkeys([*(report.get("failed") or []), *(f["id"] for f in eng_fails)]))
            merged_routes = [r for r in ROUTE_ORDER if r in set(report.get("repair_route") or []) | {f["repair_route"] for f in eng_fails}]
            report["repair_route"] = merged_routes
            report["repair_actions"] = [ROUTE_ACTIONS[r] for r in merged_routes]
            report["verdict"] = "FAIL"
        saved_qc = persist_project_qc_frames(args.project, clips[0], report)
        report["qc_frames"] = saved_qc

    target = args.output or out_dir / f"{clips[0].stem}.cleanroom.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    write_sidecar(target, report)

    if proj_ctx is not None and report["verdict"] == "FAIL" and not args.no_apply_loop:
        loop_state = apply_post_gen_loop(args.project, args.take, report)
        report["loop_transition"] = loop_state
        write_sidecar(target, report)

    print(json.dumps({**report, "report": str(target)}, ensure_ascii=False, indent=2))
    return {"PASS": EXIT_PASS, "FAIL": EXIT_FAIL}.get(report["verdict"], EXIT_SKIPPED)


def assert_instruction_clean(instruction: str, forbidden: list[str]) -> None:
    if has_text_leak(instruction, forbidden):
        raise CleanRoomError("judge instruction contains generation text")


def load_mock(value: str) -> str:
    if value.lstrip().startswith("{"):
        return value
    return Path(value).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- escalation and asset rounds


def evidence_for(project: Path, take: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], list[str], str]:
    """Return (bound problem frame paths, bound cleanroom reports, fail causes from reports, frame status)."""
    from drama_project import resolve_in_project

    clip_rel = take.get("file")
    clip_sha = take.get("file_sha256")
    clip_path = resolve_in_project(project, clip_rel) if nonempty(clip_rel) else None
    if clip_path is None or not clip_path.is_file():
        return [], [], [], "NO_FRAMES_PRODUCED_BY_PROVIDER"

    qc = project / "qc"
    qc.mkdir(parents=True, exist_ok=True)
    stem = clip_path.stem
    reports: list[dict[str, Any]] = []
    report_causes: list[str] = []
    raw_report_objs: list[dict[str, Any]] = []
    for path in sorted(qc.glob(f"{stem}*.cleanroom.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("clip_sha256") == [clip_sha]:
            raw_report_objs.append(data)
            reports.append({
                "report": str(path.resolve().relative_to(project.resolve())),
                "verdict": data.get("verdict"),
                "failed": data.get("failed", []),
                "repair_route": data.get("repair_route", []),
            })
            for item in data.get("items") or []:
                if isinstance(item, dict) and item.get("verdict") == "FAIL":
                    report_causes.append(f"{item.get('id')}: {item.get('evidence') or 'FAIL'}")

    bound_frames: list[str] = []
    for img in sorted(qc.glob(f"{stem}*")):
        if img.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        sidecar = img.with_name(img.name + ".json")
        if sidecar.is_file():
            try:
                smeta = json.loads(sidecar.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                smeta = {}
            if smeta.get("clip_sha256") == clip_sha:
                bound_frames.append(str(img.resolve().relative_to(project.resolve())))

    if not bound_frames and clip_path.suffix.lower() in VIDEO_EXTS:
        last_rep = raw_report_objs[-1] if raw_report_objs else {"verdict": "FAIL", "items": []}
        bound_frames = persist_project_qc_frames(project, clip_path, last_rep)

    status = "BOUND_PROBLEM_FRAMES" if bound_frames else "MEDIA_PRESENT_NO_EXTRACTED_FRAMES"
    return sorted(set(bound_frames)), reports, report_causes, status


def escalation_pack(project: Path, shot: str | None, tier: str) -> dict[str, Any]:
    from check_budget_gate import counted_attempt, rerender_status
    from drama_project import take_rows
    from validate_shot_spec import load_project_spec

    spec, _, manifest = load_project_spec(project)
    status = rerender_status(manifest, spec, tier)
    shots = [shot] if shot else sorted(sid for sid, n in status["attempts"].items() if n > 0)
    packs = []
    for sid in shots:
        takes = [t for t in take_rows(manifest) if t.get("shot_id") == sid]
        frames, reports, causes, tried, routes, provider_proofs = [], [], [], [], [], []
        frame_statuses: list[str] = []
        for take in takes:
            if not counted_attempt(take):
                continue
            take_frames, take_reports, rep_causes, f_status = evidence_for(project, take)
            frame_statuses.append(f_status)
            frames.extend(take_frames)
            reports.extend(take_reports)
            causes.extend(rep_causes)
            for reason_val in (take.get("reject_reason"), take.get("failure_reason")):
                if nonempty(reason_val):
                    causes.append(f"{take['take_id']}: {reason_val}")
            if f_status == "NO_FRAMES_PRODUCED_BY_PROVIDER":
                provider_proofs.append({
                    "take_id": take["take_id"],
                    "tier": take.get("tier"),
                    "job_state": take.get("job_state"),
                    "job_ids": take.get("job_ids") or {},
                    "failure_reason": take.get("failure_reason") or take.get("unknown_reason") or "no media returned",
                    "settled_at": take.get("settled_at") or take.get("submitted_at"),
                })
            tried.append(f"{take['take_id']} ({take.get('tier')}): {', '.join(take.get('changed_variables') or []) or 'first attempt'}")
            routes.extend(r for rep in take_reports for r in rep["repair_route"])
        dedup_frames = list(dict.fromkeys(frames))
        dedup_causes = list(dict.fromkeys(causes))
        routes = [r for r in ROUTE_ORDER if r in routes] or ["slow_or_split_shot", "boost_identity_anchor"]
        overall_frame_status = ("BOUND_PROBLEM_FRAMES" if dedup_frames
                                else ("NO_FRAMES_PRODUCED_BY_PROVIDER" if "NO_FRAMES_PRODUCED_BY_PROVIDER" in frame_statuses
                                      else "NO_TAKES_RECORDED"))
        packs.append({
            "shot_id": sid,
            "attempts_at_tier": status["attempts"].get(sid, 0),
            "problem_frames_status": overall_frame_status,
            "problem_frames": dedup_frames,
            "provider_terminal_proofs": provider_proofs,
            "clean_room_reports": reports,
            "root_causes": dedup_causes or ["Provider 尚未返回可审画面或尚未执行 post-gen"],
            "tried_variables": tried,
            "suggestions": [ROUTE_ACTIONS[r] for r in routes],
        })
    return {
        "tool": "eval_harness.escalate",
        "tier": tier,
        "circuit_breaker": {k: v for k, v in status.items() if k != "attempts"},
        "decision_needed": "已触及预算熔断：停止自动重试，请用户在「拆镜 / 改词 / 跨阶回退 / 接受现状」中裁决",
        "shots": packs,
    }


def pack_markdown(pack: dict[str, Any]) -> str:
    breaker = pack["circuit_breaker"]
    lines = [
        "# 预算熔断人工裁决包", "",
        f"- 当前档位：`{pack['tier']}`",
        f"- 整片跨档累计重渲染：{breaker['used']}/{breaker['cap']}（活跃生成总镜头 {breaker['total_shots']}）", "",
        pack["decision_needed"], "",
    ]
    for shot in pack["shots"]:
        lines.append(f"## {shot['shot_id']}（当前档已尝试 {shot['attempts_at_tier']} 次 · 状态 `{shot['problem_frames_status']}`）")
        lines.append("")
        lines.append("问题帧：")
        if shot["problem_frames"]:
            lines.extend(f"- `{frame}`" for frame in shot["problem_frames"])
        elif shot["problem_frames_status"] == "NO_FRAMES_PRODUCED_BY_PROVIDER":
            lines.append("- `[NO_FRAMES_PRODUCED_BY_PROVIDER]` 供应商在产出视频帧前即终态失败，详见下方终态回执：")
            for pf in shot["provider_terminal_proofs"]:
                lines.append(f"  - `{pf['take_id']}` job_ids={json.dumps(pf['job_ids'], ensure_ascii=False)} reason={pf['failure_reason']}")
        else:
            lines.append("- （暂无已落盘媒体）")
        lines += ["", "失败根因：", *[f"- {cause}" for cause in shot["root_causes"]],
                  "", "已试方案：", *[f"- {item}" for item in shot["tried_variables"]],
                  "", "拆镜 / 改词建议：", *[f"- {item}" for item in shot["suggestions"]], ""]
    return "\n".join(lines)


def cmd_escalate(args: argparse.Namespace) -> int:
    pack = escalation_pack(args.project, args.shot, args.tier)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        text = pack_markdown(pack) if args.output.suffix == ".md" else json.dumps(pack, ensure_ascii=False, indent=2)
        args.output.write_text(text, encoding="utf-8")
    print(json.dumps({**pack, "output": str(args.output) if args.output else None}, ensure_ascii=False, indent=2))
    return EXIT_PASS


def persist_asset_escalation_pack(project: Path, asset: str) -> str:
    """Persist a bound human-decision pack under `<project>/qc/` when an asset hits the local 2-rerun cap."""
    from drama_project import drama_block, load_manifest, now_iso, section, sha256_file

    manifest = load_manifest(project)
    drama = drama_block(manifest)
    rounds = [r for r in (section(drama, "asset_loops").get(asset) or []) if isinstance(r, dict)]
    qc = project / "qc"
    qc.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", asset)

    # Locate any candidate or locked image files matching this asset stem
    stem = asset.split(".")[0]
    evidence_files: list[dict[str, str]] = []
    for folder_name in ("refs", "00_previs", "qc"):
        folder = project / folder_name
        if folder.is_dir():
            for p in sorted(folder.glob(f"*{stem}*")):
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                    rel = str(p.resolve().relative_to(project.resolve()))
                    evidence_files.append({"path": rel, "sha256": sha256_file(p)})

    causes = [f"round #{i}: {r.get('note') or r.get('result')}" for i, r in enumerate(rounds, start=1)]
    pack = {
        "tool": "eval_harness.asset_escalate",
        "generated_at": now_iso(),
        "asset": asset,
        "local_cap": LOCAL_RERUN_CAP,
        "attempts": len(rounds),
        "reruns": max(0, len(rounds) - 1),
        "evidence_files": evidence_files,
        "frame_status": "BOUND_ASSET_CANDIDATES" if evidence_files else "NO_ASSET_FILES_ON_DISK",
        "root_causes": causes or ["3 attempts exhausted without user-acceptable asset"],
        "tried": [{"round": i, "result": r.get("result"), "note": r.get("note") or ""} for i, r in enumerate(rounds, start=1)],
        "suggestions": [
            ROUTE_ACTIONS["boost_identity_anchor"],
            "停止自动重试该资产，将现有候选图与失败点交由用户裁决（调整人物设定描述、换基底参考图或切换生图模型）。",
        ],
    }
    md_lines = [
        "# 资产预算熔断人工裁决包（SPEC v2.0）",
        "",
        f"- 资产标识：`{asset}`｜已尝试 `{len(rounds)}` 次（重跑 `{max(0, len(rounds) - 1)}/{LOCAL_RERUN_CAP}` 轮已达上限）",
        f"- 证据文件：{', '.join(e['path'] for e in evidence_files) or pack['frame_status']}",
        "- 失败根因：" + ("；".join(pack["root_causes"])),
        "- 已试轮次：" + ("；".join(f"#{t['round']}({t['result']}: {t['note'] or 'no note'})" for t in pack["tried"])),
        "- 裁决建议：" + (" / ".join(pack["suggestions"])),
    ]
    md_path = qc / f"escalation_asset_{safe}.md"
    json_path = qc / f"escalation_asset_{safe}.json"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    write_sidecar(json_path, pack)
    return str(md_path.resolve().relative_to(project.resolve()))


def cmd_asset_round(args: argparse.Namespace) -> int:
    from drama_project import drama_block, now_iso, section, update_manifest

    if not args.reserve and not args.settle and not args.result:
        raise ValueError("give --reserve, --settle pass|fail, or --result pass|fail")
    result: dict[str, Any] = {}

    def mutate(manifest: dict[str, Any]) -> dict[str, Any]:
        drama = drama_block(manifest)
        loops = dict(section(drama, "asset_loops"))
        rounds = [dict(r) for r in (loops.get(args.asset) or []) if isinstance(r, dict)]
        stamp = now_iso()

        if args.settle:
            open_idx = next((i for i in range(len(rounds) - 1, -1, -1) if rounds[i].get("result") == "reserved"), None)
            if open_idx is None:
                if len(rounds) > LOCAL_RERUN_CAP:
                    raise ProjectError("CIRCUIT_BREAKER_LOCAL_LIMIT",
                                       f"asset:{args.asset}:reruns={LOCAL_RERUN_CAP}_max={LOCAL_RERUN_CAP}")
                rounds.append({"result": args.settle, "note": args.note or "", "recorded_at": stamp})
            else:
                rounds[open_idx] = {**rounds[open_idx], "result": args.settle, "note": args.note or rounds[open_idx].get("note", ""),
                                    "settled_at": stamp}
            final_res = args.settle
        elif args.reserve:
            if any(r.get("result") == "reserved" for r in rounds):
                raise ProjectError("ASSET_ROUND_ALREADY_IN_FLIGHT", args.asset)
            if len(rounds) > LOCAL_RERUN_CAP:
                raise ProjectError("CIRCUIT_BREAKER_LOCAL_LIMIT",
                                   f"asset:{args.asset}:reruns={LOCAL_RERUN_CAP}_max={LOCAL_RERUN_CAP}")
            rounds.append({"result": "reserved", "note": args.note or "", "reserved_at": stamp})
            final_res = "reserved"
        else:
            if len(rounds) > LOCAL_RERUN_CAP:
                raise ProjectError("CIRCUIT_BREAKER_LOCAL_LIMIT",
                                   f"asset:{args.asset}:reruns={LOCAL_RERUN_CAP}_max={LOCAL_RERUN_CAP}")
            rounds.append({"result": args.result, "note": args.note or "", "recorded_at": stamp})
            final_res = args.result

        result.update(
            asset=args.asset,
            state=final_res,
            attempts=len(rounds),
            reruns=max(0, len(rounds) - 1),
            may_retry=(final_res == "fail" and len(rounds) <= LOCAL_RERUN_CAP),
        )
        return {**manifest, "drama": {**drama, "asset_loops": {**loops, args.asset: rounds}}}

    try:
        update_manifest(args.project, mutate)
    except ProjectError as exc:
        extra_out: dict[str, Any] = {}
        if exc.code == "CIRCUIT_BREAKER_LOCAL_LIMIT":
            extra_out["escalation_pack_file"] = persist_asset_escalation_pack(args.project, args.asset)
        print(json.dumps({"ok": False, "errors": [str(exc)], **extra_out,
                          "next": "Stop retrying this asset; put the candidates and failure notes to the user."},
                         ensure_ascii=False, indent=2))
        return EXIT_FAIL
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return EXIT_PASS


# --------------------------------------------------------------------------- CLI


def cmd_redo(args):
    from drama_project import drama_block, section, take_rows, update_manifest
    if args.take_id is not None and (not re.fullmatch(r"[\w@.#-]{1,160}", args.take_id) or args.take_id in {".", ".."}):
        raise ProjectError("INVALID_TAKE_ID")
    def mutate(manifest):
        rows = take_rows(manifest)
        parent = next((t for t in rows if t.get("take_id") == args.parent_take_id), None)
        if not parent:
            raise ProjectError("PARENT_TAKE_MISSING", args.parent_take_id)
        if parent.get("job_state") in {"preparing", "submitted", "unknown"}:
            raise ProjectError("RECOVER_PARENT_BEFORE_REDO", args.parent_take_id)
        if len(args.changed_factor) != 1:
            raise ProjectError("RETAKE_CHANGED_VARIABLES_NOT_ONE")
        factor = args.changed_factor[0].strip()
        if not factor:
            raise ProjectError("CHANGED_FACTOR_REQUIRED")
        if args.take_id is None:
            from drama_ledger import next_take_id
            args.take_id = next_take_id(manifest, parent.get("spec_id") or parent["shot_id"], parent["tier"])
        record = {"take_id": args.take_id, "parent_take_id": args.parent_take_id, "changed_factor": factor,
                  "change_value": args.change,
                  "shot_id": parent.get("shot_id"), "tier": parent.get("tier"), "status": "planned"}
        drama = drama_block(manifest)
        plans = section(drama, "redo_plans")
        before = plans.get(args.take_id) or next((t for t in rows if t.get("take_id") == args.take_id), None)
        if before:
            if all(before.get(k) == v for k, v in record.items() if k != "status"):
                return manifest
            raise ProjectError("TAKE_ID_CONFLICT", args.take_id)
        taken_ids = {t.get("take_id") for t in rows}
        if any(p["shot_id"] == record["shot_id"] and p["tier"] == record["tier"] and tid not in taken_ids
               for tid, p in plans.items()):
            raise ProjectError("REDO_ALREADY_PLANNED")
        parent.update(stale=True, stale_reason=f"Redo: {factor}")
        downstream = []
        for key in ("cuts", "act_cuts"):
            for name, cut in section(drama, key).items():
                if args.parent_take_id in cut.get("takes", []):
                    cut["stale"] = True
                    downstream.append(f"{key}/{name}")
        for key in ("post", "delivery"):
            if drama.get(key):
                drama[key]["stale"] = True
                downstream.append(key)
        record["downstream_stale"] = downstream
        return {**manifest, "drama": {**drama, "redo_plans": {**plans, args.take_id: record}}, "takes": rows}
    result = update_manifest(args.project, mutate)
    print(json.dumps(result["drama"]["redo_plans"][args.take_id]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="Exit codes: 0 PASS/done; 1 FAIL or refused; 3 input error; "
                                            "4 ANALYSIS_SKIPPED/INCOMPLETE or missing dependency.")
    commands = parser.add_subparsers(dest="command", required=True)
    redo = commands.add_parser("redo", help="record a single-variable retake and invalidate dependent edits")
    redo.add_argument("--project", required=True, type=Path)
    redo.add_argument("--parent-take-id", "--take", required=True)
    redo.add_argument("--take-id")
    redo.add_argument("--change")
    redo.add_argument("--changed-factor", "--factor", required=True, action="append")
    redo.add_argument("--json", action="store_true")
    redo.set_defaults(handler=cmd_redo)
    import media_inspection
    from intake_choices import CREATIVE, MODES
    qc = commands.add_parser("media-qc", help="inspect real streams, cues, audio and review coverage")
    qc.add_argument("--input", required=True, type=Path)
    qc.add_argument("--metadata", type=Path, help="audio routing, source media, subtitle and voice provenance")
    qc.add_argument("--delivery-mode", choices=MODES, default="video_clips")
    qc.add_argument("--creative-mode", choices=(*CREATIVE, "film"))
    qc.add_argument("--audio-route", choices=media_inspection.ROUTES)
    for name in ("subtitle", "raw-clip", "dialogue-stem", "cutlist"):
        qc.add_argument("--" + name, type=Path)
    for name in ("claimed-resolution", "upscaled-from", "voice-source"):
        qc.add_argument("--" + name)
    qc.add_argument("--json", action="store_true")
    qc.set_defaults(handler=media_inspection.cli)
    pre = commands.add_parser("pre-gen", help="text eval of one shot, NBP prompt, or regression case")
    pre.add_argument("--input", type=Path)
    pre.add_argument("--project", type=Path)
    pre.add_argument("--shot")
    pre.add_argument("--book", type=Path, default=DEFAULT_BOOK, help="mistake book (DEPRECATED/CANDIDATE rules unmount)")
    pre.set_defaults(handler=cmd_pre_gen)

    sample = commands.add_parser("sample", help="contact sheet / dual-track sampling of one clip")
    sample.add_argument("--clip", required=True, type=Path)
    sample.add_argument("--output-dir", required=True, type=Path)
    sample.add_argument("--mode", choices=("contact", "dual"), default="contact")
    sample.add_argument("--sample-fps", type=float, default=2.0)
    sample.add_argument("--prev-clip", type=Path)
    sample.add_argument("--anchor", action="append", type=Path, default=[])
    sample.add_argument("--cell-height", type=int, default=240)
    sample.set_defaults(handler=cmd_sample)

    post = commands.add_parser("post-gen", help="Clean-Room blind review of a take or a returned clip/screenshot")
    post.add_argument("--project", type=Path)
    post.add_argument("--take")
    post.add_argument("--clip", action="append", type=Path)
    post.add_argument("--expected-action")
    post.add_argument("--anchor", action="append", type=Path, default=[])
    post.add_argument("--allow-no-anchor", action="store_true", help="explicitly allow anchorless clips")
    post.add_argument("--l1", action="append", default=[])
    post.add_argument("--book", type=Path, default=DEFAULT_BOOK)
    post.add_argument("--track", choices=("dual", "contact"), default=None)
    post.add_argument("--prev-clip", type=Path)
    post.add_argument("--judge-cmd", help="judge CLI template; {bundle} {instruction} {instruction_file}")
    post.add_argument("--mock-verdict", help="JSON verdict text or file (tests / offline replay; never accepted in prod)")
    post.add_argument("--no-apply-loop", action="store_true", help="do not mutate project manifest on FAIL")
    post.add_argument("--timeout", type=float, default=300.0)
    post.add_argument("--output", type=Path)
    post.set_defaults(handler=cmd_post_gen)

    esc = commands.add_parser("escalate", help="human-decision pack after a circuit breaker")
    esc.add_argument("--project", required=True, type=Path)
    esc.add_argument("--shot")
    esc.add_argument("--tier", default="draft")
    esc.add_argument("--output", type=Path)
    esc.set_defaults(handler=cmd_escalate)

    asset = commands.add_parser("asset-round", help="reserve or settle one self-repair round of a character/scene asset")
    asset.add_argument("--project", required=True, type=Path)
    asset.add_argument("--asset", required=True)
    asset.add_argument("--reserve", action="store_true", help="atomically reserve an asset attempt before generating")
    asset.add_argument("--settle", choices=("pass", "fail"), help="settle a reserved asset attempt")
    asset.add_argument("--result", choices=("pass", "fail"), help="single-step record of an asset attempt")
    asset.add_argument("--note")
    asset.set_defaults(handler=cmd_asset_round)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except CleanRoomError as exc:
        print(json.dumps({"ok": False, "errors": [f"{CleanRoomError.code}:{exc}"]}, ensure_ascii=False, indent=2))
        return EXIT_FAIL
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return EXIT_SKIPPED
    except ProjectError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return EXIT_INPUT if exc.code == "INPUT_ERROR" else EXIT_FAIL
    except (ValueError, OSError, StopIteration, subprocess.CalledProcessError) as exc:
        print(json.dumps({"ok": False, "errors": [f"INPUT_ERROR:{exc}"]}, ensure_ascii=False, indent=2))
        return EXIT_INPUT


if __name__ == "__main__":
    sys.exit(main())
