#!/usr/bin/env python3
"""Raster drawing for the whitemodel board: clay camera views, the annotated floorplan, fonts.

Library only. Clay geometry stays greyscale so a video model cannot read it as wardrobe; colour
is used only for annotations (facing, axis, cameras) on the annotated board, never in clean frames.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from whitemodel_scene import (
    NEAR_M, TONE, Vec, actor_height, body_parts, box_faces, camera_frame, clip_near, dot, head_and_face,
    horizontal_half_fov, in_frame, normalize, occluded_by_props, parse_ratio, pose_of, prop_faces, to_cam, to_world,
)

SS = 2
BG = (24, 26, 30)
PANEL = (38, 41, 46)
TEXT = (238, 240, 244)
MUTED = (165, 170, 178)
AMBER = (245, 180, 60)
BLUE = (90, 180, 250)
RED = (245, 105, 90)
LIGHT = normalize((0.35, 0.9, -0.45))
CJK_FONTS = (
    "/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "C:/Windows/Fonts/msyh.ttc",
)
VIEW_TEXT = {"front": ("正面", "front"), "three_quarter": ("3/4侧", "3/4"), "profile": ("侧面", "profile"),
             "back": ("背面", "back")}
POSE_TEXT = {"standing": ("站", "stand"), "seated": ("坐", "seated"), "leaning": ("前倾", "lean"),
             "kneeling": ("跪", "kneel"), "lying": ("躺", "lying")}


class Fonts:
    """CJK font when one exists on this machine; otherwise Pillow's default and ASCII-only labels."""

    def __init__(self) -> None:
        self.path = next((p for p in CJK_FONTS if Path(p).is_file()), None)
        self.cjk = self.path is not None
        self.cache: dict[int, Any] = {}

    def get(self, size: int) -> Any:
        if size not in self.cache:
            self.cache[size] = (ImageFont.truetype(self.path, size) if self.path
                                else ImageFont.load_default(size=size))
        return self.cache[size]

    def t(self, zh: str, en: str) -> str:
        return zh if self.cjk else en

    def name(self, row: dict[str, Any]) -> str:
        label = str(row.get("label") or row["id"])
        return label if self.cjk or label.isascii() else str(row["id"])


def outward(quad: list[Vec], center: Vec) -> list[Vec]:
    n = face_normal(quad)
    mid = tuple(sum(p[k] for p in quad) / len(quad) for k in range(3))
    return quad if dot(n, (mid[0] - center[0], mid[1] - center[1], mid[2] - center[2])) >= 0 else quad[::-1]


def face_normal(quad: list[Vec]) -> Vec:
    a, b, c = quad[0], quad[1], quad[2]
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    return normalize((u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]))


def solid_items(plan: dict[str, Any]) -> list[tuple[Vec, str, Any]]:
    """Every clay solid as (world centre, "box" | "head", payload) for painter's-order drawing.

    Boxes carry [(tone kind, outward quad)]; heads carry (radius_xy, face direction) and are drawn as
    shaded ovals with a darker face patch so facing reads from any camera.
    """
    items: list[tuple[Vec, str, Any]] = []
    for prop in plan.get("props", []):
        py = float(prop.get("y", 0.0)) + float(prop["h"]) / 2
        items.append(((float(prop["x"]), py, float(prop["z"])), "box", prop_faces(prop)))
    for actor in plan.get("actors", []):
        h = actor_height(actor)
        _, face_dir = head_and_face(actor)
        for kind, center, size, pitch in body_parts(pose_of(actor) or "standing", h):
            world = to_world(actor, center)
            if kind == "head":
                items.append((world, "head", ((size[0] * 0.55, size[1] * 0.55), face_dir)))
                continue
            if kind == "nose":
                continue
            quads = [outward(q, world) for q in box_faces(center, size, pitch, lambda p, a=actor: to_world(a, p))]
            items.append((world, "box", [(kind, q) for q in quads]))
    return items


def depth_shade(z: float) -> float:
    """Near geometry is darker so an over-the-shoulder foreground reads as a silhouette."""
    return 0.45 + 0.55 * min(1.0, max(0.0, (z - 0.3) / 2.2))


def room_quads(plan: dict[str, Any]) -> list[tuple[str, list[Vec]]]:
    room = plan["room"]
    w, d, h = float(room["width_m"]), float(room["depth_m"]), float(room.get("height_m", 3.0))
    center = (0.0, h / 2, 0.0)
    quads = box_faces((0.0, 0.0, 0.0), (w, h, d), 0.0, lambda p: (p[0], p[1] + h / 2, p[2]))
    inward = [outward(q, center)[::-1] for q in quads]
    return [("floor" if all(abs(p[1]) < 1e-6 for p in q) else "wall", q)
            for q in inward if not all(abs(p[1] - h) < 1e-6 for p in q)]


class ViewRaster:
    """One camera's clay render at a target pixel size, supersampled then reduced."""

    def __init__(self, cam: dict[str, Any], size: tuple[int, int]) -> None:
        self.frame = camera_frame(cam)
        self.size = size
        self.big = (size[0] * SS, size[1] * SS)
        self.image = Image.new("RGB", self.big, (35, 35, 35))
        self.draw = ImageDraw.Draw(self.image)

    def project(self, pc: Vec) -> tuple[float, float]:
        half = self.big[1] / 2.0
        return (self.big[0] / 2.0 + pc[0] / pc[2] * self.frame["focal"] * half,
                half - pc[1] / pc[2] * self.frame["focal"] * half)

    def fill(self, quad: list[Vec], tone: int, cull: bool = True, color: tuple[int, int, int] | None = None,
             fade: bool = False) -> None:
        n = face_normal(quad)
        pos = self.frame["pos"]
        if cull and dot(n, (pos[0] - quad[0][0], pos[1] - quad[0][1], pos[2] - quad[0][2])) <= 0:
            return
        clipped = clip_near([to_cam(self.frame, p) for p in quad])
        if len(clipped) < 3:
            return
        shade = depth_shade(sum(p[2] for p in clipped) / len(clipped)) if fade else 1.0
        lit = int(tone * shade * (0.58 + 0.42 * max(0.0, dot(n, LIGHT))))
        rgb = color or (lit, lit, lit)
        edge = tuple(int(c * 0.6) for c in rgb)
        self.draw.polygon([self.project(p) for p in clipped], fill=rgb, outline=edge, width=SS)

    def oval(self, center: Vec, radius: tuple[float, float], tone: int) -> None:
        pc = to_cam(self.frame, center)
        if pc[2] <= NEAR_M + radius[1]:
            return
        cx, cy = self.project(pc)
        k = self.frame["focal"] * self.big[1] / 2.0 / pc[2]
        rx, ry = radius[0] * k, radius[1] * k
        rgb = (tone,) * 3
        self.draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=rgb, outline=tuple(int(c * 0.6) for c in rgb),
                          width=SS)

    def head(self, center: Vec, radius: tuple[float, float], face_dir: Vec) -> None:
        """Shaded oval head; a darker patch shifted toward the face shows where it points."""
        shade = depth_shade(to_cam(self.frame, center)[2])
        self.oval(center, radius, int(TONE["head"] * shade * 0.85))
        pos = self.frame["pos"]
        if dot(face_dir, normalize((pos[0] - center[0], pos[1] - center[1], pos[2] - center[2]))) < -0.15:
            return
        shift = radius[0] * 0.45
        patch = (center[0] + face_dir[0] * shift, center[1] + face_dir[1] * shift - radius[1] * 0.12,
                 center[2] + face_dir[2] * shift)
        self.oval(patch, (radius[0] * 0.52, radius[1] * 0.68), int(TONE["head"] * shade * 0.55))

    def segment(self, a: Vec, b: Vec, rgb: tuple[int, int, int], width: int) -> None:
        pa, pb = to_cam(self.frame, a), to_cam(self.frame, b)
        if pa[2] < NEAR_M and pb[2] < NEAR_M:
            return
        if pa[2] < NEAR_M or pb[2] < NEAR_M:
            t = (NEAR_M - pa[2]) / (pb[2] - pa[2])
            cut = tuple(pa[k] + (pb[k] - pa[k]) * t for k in range(3))
            pa, pb = (cut, pb) if pa[2] < NEAR_M else (pa, cut)
        self.draw.line([self.project(pa), self.project(pb)], fill=rgb, width=width * SS)


def floor_grid(view: ViewRaster, plan: dict[str, Any]) -> None:
    room = plan["room"]
    hw, hd = float(room["width_m"]) / 2, float(room["depth_m"]) / 2
    rgb = (100, 100, 100)
    for k in range(-int(hw), int(hw) + 1):
        view.segment((float(k), 0.002, -hd), (float(k), 0.002, hd), rgb, 1)
    for k in range(-int(hd), int(hd) + 1):
        view.segment((-hw, 0.002, float(k)), (hw, 0.002, float(k)), rgb, 1)


def facing_arrow(actor: dict[str, Any]) -> list[Vec]:
    return [to_world(actor, (0.0, 0.006, 0.85)), to_world(actor, (0.2, 0.006, 0.38)),
            to_world(actor, (-0.2, 0.006, 0.38))]


def render_view(plan: dict[str, Any], cam: dict[str, Any], size: tuple[int, int], annotated: bool) -> Image.Image:
    """Clay render of what `cam` sees, already clipped to its own frame (no annotation text)."""
    view = ViewRaster(cam, size)
    for kind, quad in room_quads(plan):
        view.fill(quad, TONE[kind])
    floor_grid(view, plan)
    if annotated:
        for actor in plan.get("actors", []):
            view.fill(outward(facing_arrow(actor), (0.0, -1.0, 0.0)), 0, cull=False, color=AMBER)
    pos = view.frame["pos"]
    for center, shape, payload in sorted(solid_items(plan), key=lambda b: -math.dist(pos, b[0])):
        if shape == "head":
            view.head(center, *payload)
            continue
        for kind, quad in payload:
            view.fill(quad, TONE[kind], fade=True)
    return view.image.resize(size, Image.Resampling.LANCZOS)


def text_box(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font: Any,
             fill: tuple[int, int, int], bg: tuple[int, ...] | None = (16, 18, 22)) -> tuple[float, ...]:
    box = draw.textbbox(xy, text, font=font)
    pad = max(3, font.size // 6)
    rect = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
    if bg is not None:
        draw.rounded_rectangle(rect, radius=pad, fill=bg)
    draw.text(xy, text, font=font, fill=fill)
    return rect


def overlaps(rect: tuple[float, ...], taken: list[tuple[float, ...]]) -> bool:
    return any(rect[0] < t[2] and rect[2] > t[0] and rect[1] < t[3] and rect[3] > t[1] for t in taken)


def label_ring(w: float, h: float, gap: float) -> list[tuple[float, float]]:
    return [(gap, -h / 2), (-gap - w, -h / 2), (-w / 2, -gap - h), (-w / 2, gap),
            (gap, gap), (-gap - w, -gap - h), (gap, -gap - h), (-gap - w, gap)]


def place_label(draw: ImageDraw.ImageDraw, anchor: tuple[float, float], text: str, font: Any,
                fill: tuple[int, int, int], taken: list[tuple[float, ...]], bounds: tuple[int, int]) -> None:
    """Put a label near `anchor`, trying sides in turn so labels do not cover each other."""
    w = draw.textlength(text, font=font)
    h = font.size
    pad = max(8, font.size // 3)
    offsets = [offset for ring in (0.6, 1.8, 3.2, 4.8) for offset in label_ring(w, h, h * ring)]
    best = None
    for dx, dy in offsets:
        x = min(max(pad, anchor[0] + dx), max(pad, bounds[0] - w - pad))
        y = min(max(pad, anchor[1] + dy), max(pad, bounds[1] - h - pad))
        rect = (x - 4, y - 4, x + w + 4, y + h + 8)
        best = best or (x, y, rect)
        if not overlaps(rect, taken):
            best = (x, y, rect)
            break
    taken.append(text_box(draw, best[:2], text, font, fill))


def annotate_view(image: Image.Image, plan: dict[str, Any], cam: dict[str, Any], fonts: Fonts,
                  coverage: list[dict[str, str]]) -> None:
    """Name and seen side of each framed actor, plus visible focal props, placed inside the view."""
    draw = ImageDraw.Draw(image)
    frame = camera_frame(cam)
    w, h = image.size
    props = plan.get("props", [])
    font = fonts.get(max(18, min(30, w // 16)))
    prop_font = fonts.get(max(15, min(22, w // 22)))
    views = {row["actor"]: row["view"] for row in coverage}
    taken: list[tuple[float, ...]] = []
    for actor in plan.get("actors", []):
        if actor["id"] not in views or not in_frame(actor, frame, w / h, props):
            continue
        head, _ = head_and_face(actor)
        pc = to_cam(frame, (head[0], head[1] + 0.22, head[2]))
        if pc[2] <= 0.2:
            continue
        px = w / 2 + pc[0] / pc[2] * frame["focal"] * h / 2
        py = h / 2 - pc[1] / pc[2] * frame["focal"] * h / 2
        label = f"{fonts.name(actor)} · {fonts.t(*VIEW_TEXT[views[actor['id']]])}"
        place_label(draw, (min(max(px, 8), w - 8), min(max(py, 8), h - 8)), label, font, TEXT, taken, (w, h))
    for prop in props:
        point = (float(prop["x"]), float(prop.get("y", 0.0)) + float(prop["h"]) * 0.75, float(prop["z"]))
        pc = to_cam(frame, point)
        if pc[2] <= 0.4 or occluded_by_props(frame["pos"], point, props, ignore_id=prop.get("id")):
            continue
        px = w / 2 + pc[0] / pc[2] * frame["focal"] * h / 2
        py = h / 2 - pc[1] / pc[2] * frame["focal"] * h / 2
        if 12 <= px <= w - 12 and 12 <= py <= h - 12:
            place_label(draw, (px, py), fonts.name(prop), prop_font, MUTED, taken, (w, h))


FLOOR_MARGIN = 70


def floor_extent(plan: dict[str, Any]) -> tuple[float, float]:
    room = plan["room"]
    ex = max([float(room["width_m"]) / 2] + [abs(float(c["x"])) + 0.4 for c in plan["cameras"]])
    ez = max([float(room["depth_m"]) / 2] + [abs(float(c["z"])) + 0.4 for c in plan["cameras"]])
    return ex, ez


class Floorplan:
    """Top-down plan: metric grid, props, facing sectors, 180-degree axis, camera frustums."""

    def __init__(self, plan: dict[str, Any], size: tuple[int, int]) -> None:
        self.plan, self.size = plan, size
        room = plan["room"]
        self.hw, self.hd = float(room["width_m"]) / 2, float(room["depth_m"]) / 2
        ex, ez = floor_extent(plan)
        self.scale = min((size[0] - 2 * FLOOR_MARGIN) / (2 * ex), (size[1] - 2 * FLOOR_MARGIN) / (2 * ez))
        self.cx, self.cy = size[0] / 2.0, size[1] / 2.0

    @staticmethod
    def natural_height(plan: dict[str, Any], width: int) -> int:
        """Panel height that fits the room and cameras at full `width` without empty bands."""
        ex, ez = floor_extent(plan)
        return int(2 * ez * (width - 2 * FLOOR_MARGIN) / (2 * ex) + 2 * FLOOR_MARGIN)

    def px(self, x: float, z: float, k: int = 1) -> tuple[float, float]:
        return ((self.cx + x * self.scale) * k, (self.cy + z * self.scale) * k)

    def render(self, fonts: Fonts) -> Image.Image:
        big = (self.size[0] * SS, self.size[1] * SS)
        base = Image.new("RGBA", big, PANEL + (255,))
        layer = Image.new("RGBA", big, (0, 0, 0, 0))
        self.room_and_props(ImageDraw.Draw(base))
        self.frustums_and_sectors(ImageDraw.Draw(layer))
        mask = Image.new("L", big, 0)
        ImageDraw.Draw(mask).rectangle((*self.px(-self.hw, -self.hd, SS), *self.px(self.hw, self.hd, SS)), fill=255)
        base = Image.alpha_composite(base, Image.composite(layer, Image.new("RGBA", big, (0, 0, 0, 0)), mask))
        draw = ImageDraw.Draw(base)
        self.axis(draw)
        self.actors(draw)
        self.cameras(draw)
        image = base.convert("RGB").resize(self.size, Image.Resampling.LANCZOS)
        self.labels(ImageDraw.Draw(image), fonts)
        return image

    def room_and_props(self, draw: ImageDraw.ImageDraw) -> None:
        draw.rectangle((*self.px(-self.hw, -self.hd, SS), *self.px(self.hw, self.hd, SS)), fill=(TONE["floor"],) * 3)
        for k in range(-int(self.hw), int(self.hw) + 1):
            draw.line((*self.px(k, -self.hd, SS), *self.px(k, self.hd, SS)), fill=(96, 100, 106), width=SS)
        for k in range(-int(self.hd), int(self.hd) + 1):
            draw.line((*self.px(-self.hw, k, SS), *self.px(self.hw, k, SS)), fill=(96, 100, 106), width=SS)
        draw.rectangle((*self.px(-self.hw, -self.hd, SS), *self.px(self.hw, self.hd, SS)),
                       outline=(200, 204, 210), width=3 * SS)
        for prop in self.plan.get("props", []):
            x, z, w, d = (float(prop[k]) for k in ("x", "z", "w", "d"))
            draw.rectangle((*self.px(x - w / 2, z - d / 2, SS), *self.px(x + w / 2, z + d / 2, SS)),
                           fill=(TONE["prop"],) * 3, outline=(210, 212, 216), width=SS)

    def frustums_and_sectors(self, draw: ImageDraw.ImageDraw) -> None:
        rw, rh = parse_ratio(self.plan.get("aspect_ratio", "16:9"))
        alpha = max(14, 34 * 3 // max(3, len(self.plan["cameras"])))
        reach = max(2.5, *(math.dist((float(c["x"]), float(c["z"])), (float(a["x"]), float(a["z"]))) + 1.0
                          for c in self.plan["cameras"] for a in self.plan.get("actors", [])), 0.0)
        for cam in self.plan["cameras"]:
            frame = camera_frame(cam)
            yaw, half = math.atan2(frame["fwd"][2], frame["fwd"][0]), horizontal_half_fov(frame, rw / rh)
            ox, oz = float(cam["x"]), float(cam["z"])
            pts = [self.px(ox, oz, SS)] + [self.px(ox + reach * math.cos(yaw + s * half),
                                                   oz + reach * math.sin(yaw + s * half), SS) for s in (-1, 1)]
            draw.polygon(pts, fill=BLUE + (alpha,), outline=BLUE + (170,), width=2 * SS)
        radius = 0.9 * self.scale * SS
        for actor in self.plan.get("actors", []):
            ax, ay = self.px(float(actor["x"]), float(actor["z"]), SS)
            mid = float(actor["facing_deg"]) - 90.0
            draw.pieslice((ax - radius, ay - radius, ax + radius, ay + radius), mid - 30, mid + 30,
                          fill=AMBER + (90,), outline=AMBER + (220,), width=SS)

    def axis(self, draw: ImageDraw.ImageDraw) -> None:
        ends = self.axis_ends()
        if ends is None:
            return
        (x0, z0), (x1, z1) = ends
        length = math.hypot(x1 - x0, z1 - z0)
        steps = int(length / 0.3)
        for i in range(steps):
            t0, t1 = i * 0.3 / length, min(1.0, (i * 0.3 + 0.18) / length)
            draw.line((*self.px(x0 + (x1 - x0) * t0, z0 + (z1 - z0) * t0, SS),
                       *self.px(x0 + (x1 - x0) * t1, z0 + (z1 - z0) * t1, SS)), fill=AMBER, width=3 * SS)

    def axis_ends(self) -> tuple[tuple[float, float], tuple[float, float]] | None:
        pair = self.plan.get("axis_pair")
        by_id = {a["id"]: a for a in self.plan.get("actors", [])}
        if not isinstance(pair, list) or len(pair) != 2 or not all(p in by_id for p in pair):
            return None
        ax, az = float(by_id[pair[0]]["x"]), float(by_id[pair[0]]["z"])
        dx, dz = float(by_id[pair[1]]["x"]) - ax, float(by_id[pair[1]]["z"]) - az
        if math.hypot(dx, dz) < 1e-6:
            return None
        ts = [t for lim, o, d in ((self.hw, ax, dx), (-self.hw, ax, dx), (self.hd, az, dz), (-self.hd, az, dz))
              if abs(d) > 1e-9 for t in [(lim - o) / d]]
        inside = [t for t in ts if abs(ax + dx * t) <= self.hw + 1e-6 and abs(az + dz * t) <= self.hd + 1e-6]
        return (ax + dx * min(inside), az + dz * min(inside)), (ax + dx * max(inside), az + dz * max(inside))

    def actors(self, draw: ImageDraw.ImageDraw) -> None:
        for actor in self.plan.get("actors", []):
            h = actor_height(actor)
            parts = sorted(body_parts(pose_of(actor) or "standing", h), key=lambda p: p[1][1] + p[2][1] / 2)
            for kind, center, size, pitch in parts:
                corners = [p for quad in box_faces(center, size, pitch, lambda q: to_world(actor, q)) for p in quad]
                hull = convex_hull([(p[0], p[2]) for p in corners])
                top = max(p[1] for p in corners)
                tone = TONE[kind] if kind not in ("actor", "head") else int(150 + 70 * min(1.0, top / h))
                draw.polygon([self.px(x, z, SS) for x, z in hull], fill=(tone,) * 3, outline=(20, 20, 22), width=SS)

    def cameras(self, draw: ImageDraw.ImageDraw) -> None:
        size = max(0.22, 26 / self.scale)
        for cam in self.plan["cameras"]:
            frame = camera_frame(cam)
            f = normalize((frame["fwd"][0], 0.0, frame["fwd"][2]))
            r = (-f[2], 0.0, f[0])
            ox, oz = float(cam["x"]), float(cam["z"])

            def at(a: float, b: float) -> tuple[float, float]:
                return self.px(ox + f[0] * a + r[0] * b, oz + f[2] * a + r[2] * b, SS)

            body = [at(-size, -size * 0.6), at(-size, size * 0.6), at(size * 0.3, size * 0.6), at(size * 0.3, -size * 0.6)]
            lens = [at(size * 0.3, -size * 0.25), at(size * 0.3, size * 0.25), at(size * 0.9, size * 0.55),
                    at(size * 0.9, -size * 0.55)]
            draw.polygon(body, fill=BLUE, outline=TEXT, width=SS)
            draw.polygon(lens, fill=BLUE, outline=TEXT, width=SS)

    def labels(self, draw: ImageDraw.ImageDraw, fonts: Fonts) -> None:
        small, mid = fonts.get(20), fonts.get(26)
        tick = max(1, math.ceil(max(2 * self.hw, 2 * self.hd) / 10))
        for k in range(0, int(2 * self.hw) + 1, tick):
            x, y = self.px(-self.hw + k, -self.hd)
            draw.text((x - 6, y - 26), f"{k}m", font=small, fill=MUTED)
        for k in range(tick, int(2 * self.hd) + 1, tick):
            x, y = self.px(-self.hw, -self.hd + k)
            draw.text((x - 44, y - 10), f"{k}m", font=small, fill=MUTED)
        taken = [self.icon_rect(float(a["x"]), float(a["z"]), 0.3) for a in self.plan.get("actors", [])]
        taken += [self.icon_rect(float(c["x"]), float(c["z"]), 0.25) for c in self.plan["cameras"]]
        for prop in self.plan.get("props", []):
            place_label(draw, self.px(float(prop["x"]), float(prop["z"])), fonts.name(prop), small, MUTED, taken, self.size)
        for actor in self.plan.get("actors", []):
            text = f"{fonts.name(actor)}（{fonts.t(*POSE_TEXT[pose_of(actor) or 'standing'])}）" if fonts.cjk \
                else f"{fonts.name(actor)} ({POSE_TEXT[pose_of(actor) or 'standing'][1]})"
            place_label(draw, self.px(float(actor["x"]), float(actor["z"])), text, mid, TEXT, taken, self.size)
        for cam in self.plan["cameras"]:
            place_label(draw, self.px(float(cam["x"]), float(cam["z"])), fonts.name(cam), mid, BLUE, taken, self.size)
        ends = self.axis_ends()
        if ends is not None:
            place_label(draw, self.px(*ends[1]), fonts.t("180° 轴线", "180° axis"), small, AMBER, taken, self.size)

    def icon_rect(self, x: float, z: float, metres: float) -> tuple[float, ...]:
        (x0, y0), (x1, y1) = self.px(x - metres, z - metres), self.px(x + metres, z + metres)
        return (x0, y0, x1, y1)


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def half(seq: list[tuple[float, float]]) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for p in seq:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (p[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(p)
        return out[:-1]

    return half(pts) + half(pts[::-1])
