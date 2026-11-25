#!/usr/bin/env python3
"""Scene geometry for the zero-cost whitemodel board: plan checks, clay body proxies, camera maths.

Library only. World axes: x to the right of the floorplan, z down the floorplan, y up; metres.
`facing_deg` 0 faces -z (up the floorplan), 90 faces +x. `fov_deg` is the vertical field of view.
"""
from __future__ import annotations

import math
from typing import Any

from drama_project import ProjectError, nonempty

Vec = tuple[float, float, float]
POSES = ("standing", "seated", "leaning", "kneeling", "lying")
POSE_ALIASES = {"stand": "standing", "sit": "seated", "sitting": "seated", "lean": "leaning",
                "kneel": "kneeling", "lie": "lying", "lying_down": "lying"}
VIEWS = ("front", "three_quarter", "profile", "back")
DEFAULT_HEIGHT_M = 1.72
MIN_ACTOR_GAP_M = 0.35
NEAR_M = 0.12
LEAN_DEG = 22.0
TONE = {"actor": 206, "head": 214, "face": 96, "nose": 96, "seat": 104, "prop": 128, "floor": 74, "wall": 58}


def finite_num(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def parse_ratio(text: object) -> tuple[float, float]:
    if not isinstance(text, str) or ":" not in text:
        raise ProjectError("INVALID_BLOCKING_PLAN", f"aspect_ratio:{text}")
    left, _, right = text.partition(":")
    try:
        w, h = float(left), float(right)
    except ValueError as exc:
        raise ProjectError("INVALID_BLOCKING_PLAN", f"aspect_ratio:{text}") from exc
    if w <= 0 or h <= 0 or not (math.isfinite(w) and math.isfinite(h)):
        raise ProjectError("INVALID_BLOCKING_PLAN", f"aspect_ratio:{text}")
    return w, h


def pose_of(actor: dict[str, Any]) -> str | None:
    raw = str(actor.get("pose", "standing")).strip().lower()
    pose = POSE_ALIASES.get(raw, raw)
    return pose if pose in POSES else None


def check_one_actor(row: object, idx: int, seen: set[str], half: tuple[float, float]) -> list[str]:
    aid = row.get("id") if isinstance(row, dict) else None
    if not nonempty(aid) or aid in seen:
        return [f"ACTOR_ID_INVALID_OR_DUPLICATE:{aid or idx}"]
    seen.add(aid)
    if not all(finite_num(row.get(k)) for k in ("x", "z", "facing_deg")):
        return [f"ACTOR_COORDS_INVALID:{aid}"]
    errors = [f"ACTOR_OUTSIDE_ROOM:{aid}"] if abs(row["x"]) > half[0] or abs(row["z"]) > half[1] else []
    if pose_of(row) is None:
        errors.append(f"ACTOR_POSE_UNKNOWN:{aid}:{row.get('pose')}")
    if "height_m" in row and not (finite_num(row["height_m"]) and 0.5 <= row["height_m"] <= 2.5):
        errors.append(f"ACTOR_HEIGHT_INVALID:{aid}")
    if "extra" in row and not isinstance(row["extra"], bool):
        errors.append(f"ACTOR_EXTRA_INVALID:{aid}")
    return errors


def check_actors(actors: object, width_m: float, depth_m: float, expected: object) -> list[str]:
    if not isinstance(actors, list):
        return ["ACTORS_NOT_A_LIST"]
    errors: list[str] = []
    if expected is not None:
        if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
            errors.append("EXPECTED_ACTOR_COUNT_INVALID")
        elif len(actors) != expected:
            errors.append(f"ACTOR_COUNT_MISMATCH:{len(actors)}!={expected}")
    seen: set[str] = set()
    placed: list[tuple[str, float, float]] = []
    for idx, row in enumerate(actors):
        row_errors = check_one_actor(row, idx, seen, (width_m / 2.0, depth_m / 2.0))
        errors += row_errors
        if any(e.startswith(("ACTOR_ID_", "ACTOR_COORDS_")) for e in row_errors):
            continue
        x, z = float(row["x"]), float(row["z"])
        errors += [f"ACTORS_OVERLAPPING:{oid}:{row['id']}" for oid, ox, oz in placed
                   if math.hypot(x - ox, z - oz) < MIN_ACTOR_GAP_M]
        placed.append((row["id"], x, z))
    return errors


def check_one_prop(prop: object, idx: int) -> list[str]:
    if not isinstance(prop, dict) or not nonempty(prop.get("id")):
        return [f"PROP_INVALID:{idx}"]
    valid_box = all(finite_num(prop.get(k)) for k in ("x", "z", "w", "d", "h"))
    valid_y = "y" not in prop or (finite_num(prop["y"]) and float(prop["y"]) >= 0)
    return [] if valid_box and valid_y else [f"PROP_COORDS_INVALID:{prop['id']}"]


def check_props_and_cameras(props: object, cameras: object) -> list[str]:
    if not isinstance(props, list):
        return ["PROPS_NOT_A_LIST"]
    if not isinstance(cameras, list) or not cameras:
        return ["CAMERAS_EMPTY"]
    errors = [err for idx, prop in enumerate(props) for err in check_one_prop(prop, idx)]
    seen: set[str] = set()
    for idx, cam in enumerate(cameras):
        cid = cam.get("id") if isinstance(cam, dict) else None
        if not nonempty(cid) or cid in seen:
            errors.append(f"CAMERA_ID_INVALID_OR_DUPLICATE:{cid or idx}")
            continue
        seen.add(cid)
        if not all(finite_num(cam.get(k)) for k in ("x", "z", "look_at_x", "look_at_z")):
            errors.append(f"CAMERA_COORDS_INVALID:{cid}")
        elif math.hypot(float(cam["x"]) - float(cam["look_at_x"]), float(cam["z"]) - float(cam["look_at_z"])) < 0.1:
            errors.append(f"CAMERA_ZERO_LOOK_VECTOR:{cid}")
    return errors


def axis_warnings(plan: dict[str, Any]) -> list[str]:
    pair = plan.get("axis_pair")
    if not isinstance(pair, list) or len(pair) != 2 or plan.get("allow_axis_cross") is True:
        return []
    by_id = {row["id"]: row for row in plan.get("actors", []) if isinstance(row, dict) and "id" in row}
    if pair[0] not in by_id or pair[1] not in by_id:
        return [f"AXIS_PAIR_UNKNOWN_ACTOR:{pair}"]
    a, b = by_id[pair[0]], by_id[pair[1]]
    dx, dz = float(b["x"]) - float(a["x"]), float(b["z"]) - float(a["z"])
    sides: list[tuple[str, int]] = []
    for cam in plan.get("cameras", []):
        cross = dx * (float(cam["z"]) - float(a["z"])) - dz * (float(cam["x"]) - float(a["x"]))
        if abs(cross) > 1e-3:
            sides.append((cam["id"], 1 if cross > 0 else -1))
    if len({sign for _, sign in sides}) > 1:
        crossed = ",".join(f"{cid}({'+' if s > 0 else '-'})" for cid, s in sides)
        return [f"AXIS_180_CROSSED:{crossed}"]
    return []


def validate_plan(plan: object) -> tuple[list[str], list[str]]:
    """Spatial invariant errors and axis warnings for one blocking option."""
    if not isinstance(plan, dict) or not nonempty(plan.get("scene_id")):
        return ["SCENE_ID_MISSING"], []
    room = plan.get("room")
    if not isinstance(room, dict) or not all(finite_num(room.get(k)) and room[k] > 0 for k in ("width_m", "depth_m")):
        return ["ROOM_DIMENSIONS_INVALID"], []
    try:
        parse_ratio(plan.get("aspect_ratio", "16:9"))
    except ProjectError as exc:
        return [str(exc)], []
    errors = check_actors(plan.get("actors", []), float(room["width_m"]), float(room["depth_m"]),
                          plan.get("expected_actor_count"))
    errors += check_props_and_cameras(plan.get("props", []), plan.get("cameras"))
    errors += [] if errors else actors_inside_props(plan)
    return errors, ([] if errors else axis_warnings(plan))


def actors_inside_props(plan: dict[str, Any]) -> list[str]:
    """An actor's feet may not stand inside a solid prop's footprint (seats are drawn by the pose)."""
    errors = []
    for actor in plan.get("actors", []):
        for prop in plan.get("props", []):
            if prop.get("walkable") is True or float(prop.get("y", 0.0)) >= actor_height(actor):
                continue
            inside_x = abs(float(actor["x"]) - float(prop["x"])) < float(prop["w"]) / 2 - 0.05
            inside_z = abs(float(actor["z"]) - float(prop["z"])) < float(prop["d"]) / 2 - 0.05
            if inside_x and inside_z:
                errors.append(f"ACTOR_INSIDE_PROP:{actor['id']}:{prop['id']}")
    return errors


def upright_parts(h: float, base: float, pitch: float = 0.0) -> list[tuple[str, Vec, Vec, float]]:
    """Torso, arms and head standing on a hip at height `base`, tilted forward by `pitch` degrees."""
    rad = math.radians(pitch)

    def at(up: float, side: float = 0.0) -> Vec:
        return (side, base + up * math.cos(rad), up * math.sin(rad))

    head = at(0.41 * h)
    return [("actor", at(0.165 * h), (0.26 * h, 0.33 * h, 0.15 * h), pitch),
            ("actor", at(0.16 * h, -0.165 * h), (0.065 * h, 0.32 * h, 0.08 * h), pitch),
            ("actor", at(0.16 * h, 0.165 * h), (0.065 * h, 0.32 * h, 0.08 * h), pitch),
            ("head", head, (0.12 * h, 0.14 * h, 0.14 * h), pitch),
            ("nose", (0.0, head[1] - 0.01 * h, head[2] + 0.08 * h), (0.045 * h, 0.04 * h, 0.06 * h), pitch)]


def leg_pair(center: Vec, size: Vec, h: float) -> list[tuple[str, Vec, Vec, float]]:
    return [("actor", (side * 0.065 * h, center[1], center[2]), size, 0.0) for side in (-1, 1)]


def body_parts(pose: str, h: float) -> list[tuple[str, Vec, Vec, float]]:
    """Clay boxes (kind, local centre, size w/h/d, pitch) in actor space; +z is where the actor faces."""
    if pose == "seated":
        s = 0.26 * h
        return [("seat", (0.0, s / 2, -0.02 * h), (0.30 * h, s, 0.26 * h), 0.0),
                *leg_pair((0, s + 0.055 * h, 0.12 * h), (0.10 * h, 0.11 * h, 0.25 * h), h),
                *leg_pair((0, s / 2, 0.22 * h), (0.09 * h, s, 0.10 * h), h),
                *upright_parts(h, s + 0.03 * h)]
    if pose == "kneeling":
        return [*leg_pair((0, 0.05 * h, -0.12 * h), (0.10 * h, 0.10 * h, 0.25 * h), h),
                *leg_pair((0, 0.225 * h, 0.0), (0.10 * h, 0.25 * h, 0.11 * h), h),
                *upright_parts(h, 0.35 * h)]
    if pose == "lying":
        return [*leg_pair((0, 0.055 * h, -0.24 * h), (0.10 * h, 0.11 * h, 0.47 * h), h),
                ("actor", (0.0, 0.075 * h, 0.165 * h), (0.26 * h, 0.15 * h, 0.33 * h), 0.0),
                ("actor", (-0.165 * h, 0.04 * h, 0.165 * h), (0.065 * h, 0.08 * h, 0.32 * h), 0.0),
                ("actor", (0.165 * h, 0.04 * h, 0.165 * h), (0.065 * h, 0.08 * h, 0.32 * h), 0.0),
                ("head", (0.0, 0.07 * h, 0.40 * h), (0.12 * h, 0.14 * h, 0.14 * h), 0.0),
                ("nose", (0.0, 0.165 * h, 0.40 * h), (0.045 * h, 0.06 * h, 0.04 * h), 0.0)]
    pitch = LEAN_DEG if pose == "leaning" else 0.0
    return [*leg_pair((0, 0.235 * h, 0.0), (0.10 * h, 0.47 * h, 0.11 * h), h), *upright_parts(h, 0.47 * h, pitch)]


def to_world(actor: dict[str, Any], local: Vec) -> Vec:
    rad = math.radians(float(actor["facing_deg"]))
    lx, ly, lz = local
    return (float(actor["x"]) + lx * math.cos(rad) + lz * math.sin(rad), ly,
            float(actor["z"]) + lx * math.sin(rad) - lz * math.cos(rad))


def box_faces(center: Vec, size: Vec, pitch: float, place: Any) -> list[list[Vec]]:
    """Six quads of a box, pitched about its own x axis, then placed into the world by `place`."""
    w, h, d = (v / 2 for v in size)
    rad = math.radians(pitch)
    corners = []
    for sx, sy, sz in ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                       (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)):
        y, z = sy * h, sz * d
        corners.append(place((center[0] + sx * w, center[1] + y * math.cos(rad) - z * math.sin(rad),
                              center[2] + y * math.sin(rad) + z * math.cos(rad))))
    quads = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5))
    return [[corners[i] for i in quad] for quad in quads]


def actor_height(actor: dict[str, Any]) -> float:
    return float(actor.get("height_m", DEFAULT_HEIGHT_M))


def prop_faces(prop: dict[str, Any]) -> list[tuple[str, list[Vec]]]:
    base_y = float(prop.get("y", 0.0))
    center = (float(prop["x"]), base_y + float(prop["h"]) / 2, float(prop["z"]))
    size = (float(prop["w"]), float(prop["h"]), float(prop["d"]))
    return [("prop", quad) for quad in box_faces((0.0, 0.0, 0.0), size, 0.0,
                                                 lambda p: (p[0] + center[0], p[1] + center[1], p[2] + center[2]))]


def head_and_face(actor: dict[str, Any]) -> tuple[Vec, Vec]:
    """World head centre and the direction the face points."""
    parts = body_parts(pose_of(actor) or "standing", actor_height(actor))
    head = next(center for kind, center, _, _ in parts if kind == "head")
    origin, nose = to_world(actor, (0.0, 0.0, 0.0)), to_world(actor, (0.0, 0.0, 1.0))
    if pose_of(actor) == "lying":
        return to_world(actor, head), (0.0, 1.0, 0.0)
    tilt = -math.sin(math.radians(LEAN_DEG)) if pose_of(actor) == "leaning" else 0.0
    face = (nose[0] - origin[0], tilt, nose[2] - origin[2])
    return to_world(actor, head), normalize(face)


def normalize(v: Vec) -> Vec:
    length = max(1e-9, math.sqrt(sum(c * c for c in v)))
    return (v[0] / length, v[1] / length, v[2] / length)


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def camera_frame(cam: dict[str, Any]) -> dict[str, Any]:
    pos = (float(cam["x"]), float(cam.get("y", 1.6)), float(cam["z"]))
    target = (float(cam["look_at_x"]), float(cam.get("look_at_y", 1.2)), float(cam["look_at_z"]))
    fwd = normalize((target[0] - pos[0], target[1] - pos[1], target[2] - pos[2]))
    right = normalize((-fwd[2], 0.0, fwd[0]))
    up = (right[1] * fwd[2] - right[2] * fwd[1], right[2] * fwd[0] - right[0] * fwd[2],
          right[0] * fwd[1] - right[1] * fwd[0])
    fov = math.radians(max(18.0, min(95.0, float(cam.get("fov_deg", 50.0)))))
    return {"pos": pos, "fwd": fwd, "right": right, "up": up, "focal": 1.0 / math.tan(fov / 2.0), "fov": fov}


def to_cam(frame: dict[str, Any], p: Vec) -> Vec:
    d = (p[0] - frame["pos"][0], p[1] - frame["pos"][1], p[2] - frame["pos"][2])
    return (dot(d, frame["right"]), dot(d, frame["up"]), dot(d, frame["fwd"]))


def clip_near(poly: list[Vec]) -> list[Vec]:
    """Sutherland-Hodgman against the near plane z = NEAR_M in camera space."""
    out: list[Vec] = []
    for i, cur in enumerate(poly):
        prev = poly[i - 1]
        cur_in, prev_in = cur[2] >= NEAR_M, prev[2] >= NEAR_M
        if cur_in != prev_in:
            t = (NEAR_M - prev[2]) / (cur[2] - prev[2])
            out.append(tuple(prev[k] + (cur[k] - prev[k]) * t for k in range(3)))
        if cur_in:
            out.append(cur)
    return out


def ndc(frame: dict[str, Any], pc: Vec, aspect: float) -> tuple[float, float]:
    """Normalised device coordinates in [-1, 1] across the frame for a camera-space point."""
    return pc[0] / pc[2] * frame["focal"] / aspect, pc[1] / pc[2] * frame["focal"]


def horizontal_half_fov(frame: dict[str, Any], aspect: float) -> float:
    return math.atan(math.tan(frame["fov"] / 2.0) * aspect)


def view_of(actor: dict[str, Any], frame: dict[str, Any]) -> str:
    head, face = head_and_face(actor)
    to_camera = normalize((frame["pos"][0] - head[0], frame["pos"][1] - head[1], frame["pos"][2] - head[2]))
    angle = math.degrees(math.acos(max(-1.0, min(1.0, dot(face, to_camera)))))
    return VIEWS[0] if angle <= 35 else VIEWS[1] if angle <= 70 else VIEWS[2] if angle <= 115 else VIEWS[3]


def ray_hits_prop(start: Vec, end: Vec, prop: dict[str, Any]) -> bool:
    """Slab test on segment start -> end (t in (0.02, 0.98)) against one solid prop box."""
    if prop.get("walkable") is True:
        return False
    px, py, pz = float(prop["x"]), float(prop.get("y", 0.0)), float(prop["z"])
    hw, hh, hd = float(prop["w"]) / 2.0, float(prop["h"]), float(prop["d"]) / 2.0
    bounds = ((px - hw, px + hw), (py, py + hh), (pz - hd, pz + hd))
    t0, t1 = 0.02, 0.98
    for idx, (lo, hi) in enumerate(bounds):
        delta = end[idx] - start[idx]
        if abs(delta) < 1e-9:
            if start[idx] < lo or start[idx] > hi:
                return False
            continue
        a, b = (lo - start[idx]) / delta, (hi - start[idx]) / delta
        t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
        if t0 > t1:
            return False
    return True


def occluded_by_props(start: Vec, end: Vec, props: list[dict[str, Any]], ignore_id: str | None = None) -> bool:
    return any(ray_hits_prop(start, end, prop) for prop in props if prop.get("id") != ignore_id)


def in_frame(actor: dict[str, Any], frame: dict[str, Any], aspect: float,
             props: list[dict[str, Any]] | None = None) -> bool:
    """True when the centre of an unoccluded body part projects inside the frame."""
    parts = body_parts(pose_of(actor) or "standing", actor_height(actor))
    probes = [to_world(actor, center) for kind, center, _, _ in parts if kind in ("actor", "head")]
    blockers = props or []
    for point in probes:
        pc = to_cam(frame, point)
        if pc[2] > NEAR_M:
            nx, ny = ndc(frame, pc, aspect)
            if abs(nx) <= 1.0 and abs(ny) <= 1.0 and not occluded_by_props(frame["pos"], point, blockers):
                return True
    return False


def camera_coverage(plan: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """For each camera, the actors it frames and which side of them it sees."""
    rw, rh = parse_ratio(plan.get("aspect_ratio", "16:9"))
    props = plan.get("props", [])
    out: dict[str, list[dict[str, str]]] = {}
    for cam in plan["cameras"]:
        frame = camera_frame(cam)
        out[cam["id"]] = [{"actor": a["id"], "view": view_of(a, frame)}
                          for a in plan.get("actors", []) if in_frame(a, frame, rw / rh, props)]
    return out


def required_views(coverage: dict[str, list[dict[str, str]]]) -> dict[str, list[str]]:
    needed: dict[str, set[str]] = {}
    for rows in coverage.values():
        for row in rows:
            needed.setdefault(row["actor"], set()).add(row["view"])
    return {aid: [v for v in VIEWS if v in views] for aid, views in sorted(needed.items())}
