"""Calibration coupons: a labelled step series of one fit, printed to find its value.

`make(feature, p, ...)` builds the coupon; `uv run cad.py coupon <feature>` builds and checks it like
any model. Each sample steps one value `c` on the diameter, labelled ".05", ".10" …; the owner tries
the samples with the real part (a rod, a magnet, a bolt) and the value that fits goes into the
`printer.toml` key the coupon names.

A new fit is a new feature function registered in FEATURES: it gets the values and its options and
returns the bodies. Layout, labels and wrapping to the bed are shared.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from build123d import Box, Cylinder, Part, Pos, extrude

from .config import Profile
from .magnets import Magnet, magnet, pocket_depth
from .text import label
from .threads import ISO_COARSE_PITCH, internal_thread_tube

PLATE_T = 3.0          # plate thickness for hole and pin samples (hole depth)
PIN_H = 8.0            # pin height above the plate
LABEL_SIZE = 4.0       # label font height
LABEL_GAP = 2.0        # between a sample and its label
EDGE = 4.0             # plate edge to the nearest sample
GAP = 3.0              # between neighbouring samples (wall between holes)
BODY_GAP = 6.0         # between separate bodies on the bed
KEY_RING_WALL = 3.0    # wall of the press/slide key's ring
KEY_BAR_W = 10.0
TAB_L = 12.0           # thread ring's label tab, beyond the ring
TAB_T = 2.0
DEFAULT_MAGNETS = ("5x4", "6x2", "10x3")   # the owner's range: tall small, Gridfinity's 6x2, the largest
PUSH_LEDGE = 0.5       # a magnet pocket keeps at least this ledge per side around the push-out hole
# Printed internal threads below M6 don't build yet (cadlib.threads cannot fuse the turns at those
# pitches); the thread coupon offers the sizes that do.
THREAD_SIZES = ("M6", "M8", "M10", "M12")


@dataclass(frozen=True)
class Coupon:
    name: str          # output file name, e.g. "coupon-magnet-d6x2"
    body: Part
    bodies: int        # separate bodies on the bed
    key: str           # the printer.toml key the result goes to
    how_to: str        # how to try the samples and read the result


@dataclass(frozen=True)
class Feature:
    defaults: tuple[float, float, float]   # from, to, step on the diameter, mm
    key: str
    build: Callable[..., Coupon]
    options: tuple[str, ...] = ()          # the options this feature takes (d, h, size)


def values(start: float, stop: float, step: float) -> list[float]:
    """start, start + step … stop (inclusive), rounded to 0.001 mm."""
    if step <= 0:
        raise ValueError(f"--step must be above 0, got {step}")
    if stop < start:
        raise ValueError(f"--from {start} is above --to {stop}")
    n = int(math.floor((stop - start) / step + 1e-6)) + 1
    return [round(start + i * step, 3) for i in range(n)]


def label_text(c: float) -> str:
    """0.05 → ".05", 0 → ".00", 0.075 → ".075", 1.25 → "1.25": as precise as the value, at least 2 places."""
    text = f"{c:.3f}"
    if text.endswith("0"):
        text = text[:-1]
    return text[1:] if text.startswith("0") else text


def _relief(p: Profile) -> float:
    return 3 * p.layer_mm


def _labels(cs: list[float], xy: list[tuple[float, float]], z: float, p: Profile) -> list[Part]:
    return [extrude(Pos(x, y, z) * label(label_text(c), LABEL_SIZE), amount=_relief(p)) for c, (x, y) in zip(cs, xy)]


def _grid(n: int, cell_w: float, cell_d: float, p: Profile, extra_d: float = 0.0) -> list[tuple[float, float]]:
    """Cell centres, rows of as many cells as the bed width holds, first row at the top (+Y)."""
    width, depth, _ = p.usable_volume_mm
    per_row = max(1, int((width - 2 * EDGE) // cell_w))
    rows = math.ceil(n / per_row)
    if rows * cell_d + 2 * EDGE + extra_d > depth:
        fit = per_row * int((depth - 2 * EDGE - extra_d) // cell_d)
        raise ValueError(f"{n} samples don't fit on the bed: at most {fit} at this size, narrow the range")
    cols = min(n, per_row)
    return [((i % per_row - (cols - 1) / 2) * cell_w, -(i // per_row) * cell_d) for i in range(n)]


def _plate(xy: list[tuple[float, float]], cell_w: float, cell_d: float, t: float) -> Part:
    xs = [x for x, _ in xy]
    ys = [y for _, y in xy]
    w = max(xs) - min(xs) + cell_w + 2 * EDGE - 2 * GAP
    d = max(ys) - min(ys) + cell_d + 2 * EDGE - 2 * GAP
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    return Pos(cx, cy, t / 2) * Box(w, d, t)


# --- features ------------------------------------------------------------------------------------


def _hole(cs: list[float], p: Profile, d: float = 8.0, **_) -> Coupon:
    widest = d + max(cs)
    cell_w = max(widest, 2 * LABEL_SIZE) + 2 * GAP
    cell_d = widest + LABEL_GAP + LABEL_SIZE + 2 * GAP
    xy = _grid(len(cs), cell_w, cell_d, p)
    hole_y = (cell_d - 2 * GAP) / 2 - widest / 2
    label_y = hole_y - widest / 2 - LABEL_GAP - LABEL_SIZE / 2
    body = _plate(xy, cell_w, cell_d, PLATE_T)
    body -= [Pos(x, y + hole_y, PLATE_T / 2) * Cylinder((d + c) / 2, PLATE_T + 1) for c, (x, y) in zip(cs, xy)]
    body += _labels(cs, [(x, y + label_y) for x, y in xy], PLATE_T, p)
    return Coupon(f"coupon-hole-d{d:g}", body, 1, "hole_clearance_mm",
                  f"Push a metal rod or drill shank of exactly {d:g} mm into each hole. The smallest c "
                  "where it goes in freely with a little play and never sticks goes into hole_clearance_mm.")


def _pin_hole(kind: str):
    def build(cs: list[float], p: Profile, d: float = 8.0, **_) -> Coupon:
        widest = d + max(cs)
        cell_w = max(widest, 2 * LABEL_SIZE) + 2 * GAP
        cell_d = 2 * widest + 2 * LABEL_GAP + LABEL_SIZE + 2 * GAP
        ring_r = d / 2 + KEY_RING_WALL
        key_d = 2 * ring_r + BODY_GAP
        xy = _grid(len(cs), cell_w, cell_d, p, extra_d=key_d)
        top = (cell_d - 2 * GAP) / 2
        hole_y, label_y = top - widest / 2, top - widest - LABEL_GAP - LABEL_SIZE / 2
        pin_y = label_y - LABEL_SIZE / 2 - LABEL_GAP - widest / 2
        plate = _plate(xy, cell_w, cell_d, PLATE_T)
        plate -= [Pos(x, y + hole_y, PLATE_T / 2) * Cylinder((d + c) / 2, PLATE_T + 1) for c, (x, y) in zip(cs, xy)]
        plate += [Pos(x, y + pin_y, PLATE_T + PIN_H / 2) * Cylinder((d - c) / 2, PIN_H) for c, (x, y) in zip(cs, xy)]
        plate += _labels(cs, [(x, y + label_y) for x, y in xy], PLATE_T, p)

        # the key: a ring with an exact d hole and an exact d pin on one bar, below the plate
        bb = plate.bounding_box()
        ky = bb.min.Y - BODY_GAP - ring_r
        x0 = bb.min.X + ring_r
        x1 = max(x0 + 4 * ring_r, x0 + 3 * d)
        key = Pos(x0, ky, PLATE_T / 2) * Cylinder(ring_r, PLATE_T)
        key += Pos((x0 + x1) / 2, ky, PLATE_T / 2) * Box(x1 - x0, KEY_BAR_W, PLATE_T)
        key += Pos(x1, ky, PLATE_T / 2) * Cylinder(ring_r, PLATE_T)
        key -= Pos(x0, ky, PLATE_T / 2) * Cylinder(d / 2, PLATE_T + 1)
        key += Pos(x1, ky, PLATE_T + PIN_H / 2) * Cylinder(d / 2, PIN_H)
        fit = {"press": "goes in with force, holds by itself, no play",
               "slide": "moves freely by hand with almost no play"}[kind]
        return Coupon(f"coupon-{kind}-d{d:g}", plate + key, 2, f"{kind}_fit_mm",
                      f"Push the key's pin into each hole and slide the key's ring onto each pin. The c where "
                      f"the fit {fit} goes into {kind}_fit_mm (holes and pins may differ: report both).")
    return build


def magnet_floor(p: Profile) -> float:
    """Floor under a magnet pocket: a minimum wall, so the push-out hole has something to go through."""
    return p.min_wall_mm


def _magnet_strip(cs: list[float], p: Profile, m: Magnet) -> Part:
    """One strip for one magnet size: its name in the first cell, then a pocket d + c per value."""
    depth = pocket_depth(m, p)
    floor = magnet_floor(p)
    t = floor + depth
    push_d = min(max(2.0, m.d / 3), m.d - 2 * PUSH_LEDGE)   # small magnets keep a ledge to rest on
    widest = m.d + max(cs)
    cell_w = max(widest, 3 * LABEL_SIZE) + 2 * GAP
    cell_d = widest + LABEL_GAP + LABEL_SIZE + 2 * GAP
    xy = _grid(len(cs) + 1, cell_w, cell_d, p)
    name_xy, xy = xy[0], xy[1:]
    hole_y = (cell_d - 2 * GAP) / 2 - widest / 2
    label_y = hole_y - widest / 2 - LABEL_GAP - LABEL_SIZE / 2
    body = _plate([name_xy] + xy, cell_w, cell_d, t)
    body -= [Pos(x, y + hole_y, floor + depth / 2 + 0.5) * Cylinder((m.d + c) / 2, depth + 1) for c, (x, y) in zip(cs, xy)]
    if push_d >= 2 * p.nozzle_mm:   # below about two lines wide it would print closed anyway
        body -= [Pos(x, y + hole_y, t / 2) * Cylinder(push_d / 2, t + 1) for x, y in xy]
    body += _labels(cs, [(x, y + label_y) for x, y in xy], t, p)
    body += extrude(Pos(name_xy[0], name_xy[1] + hole_y, t) * label(m.name, LABEL_SIZE), amount=_relief(p))
    return body


def _magnet(cs: list[float], p: Profile, d: float | None = None, h: float | None = None,
            size: str | None = None, **_) -> Coupon:
    if (d is None) != (h is None):
        raise ValueError("magnet coupon: --d and --h go together (a measured magnet), or use --size 6x2")
    if d is not None and size is not None:
        raise ValueError("magnet coupon: --size or --d/--h, not both")
    if d is not None:
        mags, name = [Magnet(d, h)], f"coupon-magnet-d{d:g}x{h:g}"
    else:
        mags = [magnet(s) for s in (size.split(",") if size else DEFAULT_MAGNETS)]
        name = "coupon-magnet-" + "-".join(m.name for m in mags)
    strips, y = [], 0.0
    for m in mags:
        strip = _magnet_strip(cs, p, m)
        bb = strip.bounding_box()
        strips.append(Pos(-bb.center().X, y - bb.max.Y, 0) * strip)
        y -= bb.size.Y + BODY_GAP
    if -y - BODY_GAP > p.usable_volume_mm[1]:
        raise ValueError(f"{len(mags)} magnet sizes don't fit on the bed in one coupon: split them with --size")
    body = strips[0]
    for strip in strips[1:]:
        body += strip
    return Coupon(name, body, len(mags), "magnet_fit_mm",
                  "Press a magnet into each pocket of its strip by hand (the size is written at the start), "
                  "then push it out through the hole underneath. The c where it goes in with a firm push and "
                  "does not fall out when the coupon is turned over goes into magnet_fit_mm. If the sizes "
                  "disagree by more than 0.05, tell me both.")


def _thread(cs: list[float], p: Profile, size: str = "M8", **_) -> Coupon:
    key = size.upper()
    if key not in THREAD_SIZES:
        small = " (printed threads below M6 don't build yet)" if key in ISO_COARSE_PITCH else ""
        raise ValueError(f"thread {size}{small}: the coupon has {', '.join(THREAD_SIZES)}")
    d = float(key[1:])
    pitch = ISO_COARSE_PITCH[key]
    outer = 2 * d
    length = max(6 * pitch, 5.0)
    cell_w = outer + BODY_GAP
    cell_d = outer + TAB_L + BODY_GAP
    xy = _grid(len(cs), cell_w, cell_d, p)
    rings = []
    for c, (x, y) in zip(cs, xy):
        ring = Pos(x, y, 0) * internal_thread_tube(outer, d + c, pitch, length)
        tab_y = y - outer / 2 - TAB_L / 2 + 1
        ring += Pos(x, tab_y, TAB_T / 2) * Box(3 * LABEL_SIZE, TAB_L + 2, TAB_T)
        ring += _labels([c], [(x, tab_y - 0.5)], TAB_T, p)
        rings.append(ring)
    body = rings[0]
    for ring in rings[1:]:
        body += ring
    return Coupon(f"coupon-thread-{key}", body, len(cs), "thread_clearance_mm",
                  f"Screw a real {key} bolt into each ring. The c where it turns by hand all the way with "
                  "little play goes into thread_clearance_mm.")


FEATURES: dict[str, Feature] = {
    "hole": Feature((0.0, 0.5, 0.1), "hole_clearance_mm", _hole, ("d",)),
    "press": Feature((0.0, 0.25, 0.05), "press_fit_mm", _pin_hole("press"), ("d",)),
    "slide": Feature((0.15, 0.5, 0.05), "slide_fit_mm", _pin_hole("slide"), ("d",)),
    "magnet": Feature((0.0, 0.3, 0.05), "magnet_fit_mm", _magnet, ("d", "h", "size")),
    "thread": Feature((0.2, 0.5, 0.05), "thread_clearance_mm", _thread, ("size",)),
}


def make(feature: str, p: Profile, *, start: float | None = None, stop: float | None = None,
         step: float | None = None, **opts) -> Coupon:
    """The coupon for one feature; start/stop/step default to the feature's own range."""
    if feature not in FEATURES:
        raise ValueError(f"no coupon {feature!r}, there are: {', '.join(FEATURES)}")
    f = FEATURES[feature]
    lo, hi, st = f.defaults
    cs = values(lo if start is None else start, hi if stop is None else stop, st if step is None else step)
    opts = {k: v for k, v in opts.items() if v is not None}
    for name, value in opts.items():
        if name not in f.options:
            raise ValueError(f"--{name} is not used by the {feature} coupon (it takes: "
                             f"{', '.join('--' + o for o in f.options) or 'no size options'})")
        if name in ("d", "h") and not value > 0:
            raise ValueError(f"--{name} must be above 0, got {value}")
    return f.build(cs, p, **opts)
