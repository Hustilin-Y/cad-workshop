"""Fastener tools to subtract from a part: holes, countersinks, counterbores, nuts, inserts.

Convention: every tool stands with its top at Z=0 and goes down (−Z): that's the side the screw
enters from. Put it on a surface like this: `body -= Pos(x, y, z_surface) * clearance_hole("M4", 5, p)`.
For a side face turn the tool: `Pos(...) * Rot(0, 90, 0) * ...` (the entry faces −X).

Tolerances come from the printer profile (printer.toml), not from code.
"""

from __future__ import annotations

from dataclasses import dataclass

from build123d import Cone, Cylinder, Part, Pos, RegularPolygon, Box, extrude

from .config import Profile

EPS = 0.01  # tools stick out of the surface this much so the boolean leaves no skin


@dataclass(frozen=True)
class Metric:
    d: float              # nominal thread diameter
    clear_fine: float     # clearance hole, fine series — ISO 273 (fine)
    head_d: float         # socket head cap screw head — ISO 4762 (dk max)
    head_h: float         # head height — ISO 4762 (k max)
    cbore_d: float        # counterbore for ISO 4762 — DIN 974-1 (series 1)
    csk_d: float          # countersink for a 90° countersunk head — ISO 15065 (= theoretical dk max, ISO 7046-1)
    nut_s: float          # nut across flats — ISO 4032 (s)
    nut_m: float          # nut height — ISO 4032 (m max)
    insert_d: float       # heat-set insert hole — D3 from the CNC Kitchen and ruthex tables (for a printed hole)
    insert_l: float       # heat-set insert length (typical)


# Reference sizes, mm. Sources: ISO 273:1979, ISO 4762:2004, DIN 974-1:2008,
# ISO 7046-1:2011 and ISO 15065:2005, ISO 4032:2012. The countersink follows the head's theoretical
# dk (6.3 for M3): the actual head is smaller (5.5) because of its cylindrical land, and a
# countersink sized to it would be shallow, leaving the head 0.4–0.5 mm proud. Inserts differ by
# maker: measure yours with a caliper and pass hole_d/length explicitly if they differ.
METRIC: dict[str, Metric] = {
    "M2":   Metric(2.0, 2.2, 3.8, 2.0, 4.3, 4.4, 4.0, 1.6, 3.2, 4.0),
    "M2.5": Metric(2.5, 2.7, 4.5, 2.5, 5.0, 5.5, 5.0, 2.0, 4.0, 5.7),
    "M3":   Metric(3.0, 3.2, 5.5, 3.0, 6.0, 6.3, 5.5, 2.4, 4.0, 5.7),
    "M4":   Metric(4.0, 4.3, 7.0, 4.0, 8.0, 9.4, 7.0, 3.2, 5.6, 8.1),
    "M5":   Metric(5.0, 5.3, 8.5, 5.0, 10.0, 10.4, 8.0, 4.7, 6.4, 9.5),
}


def metric(size: str) -> Metric:
    key = size.upper()
    if key not in METRIC:
        raise ValueError(f"fastener {size} isn't described, there are: {', '.join(METRIC)}")
    return METRIC[key]


def _down_cylinder(d: float, depth: float) -> Part:
    """A cylinder from Z=+EPS down to Z=−depth."""
    return Pos(0, 0, (EPS - depth) / 2) * Cylinder(d / 2, depth + EPS)


def clearance_hole(size: str, depth: float, p: Profile) -> Part:
    """Through or blind hole for a screw: ISO 273 fine + the printer's clearance."""
    m = metric(size)
    return _down_cylinder(m.clear_fine + p.hole_clearance_mm, depth)


def counterbore_hole(size: str, depth: float, p: Profile, head_depth: float | None = None) -> Part:
    """Hole with a counterbore for an ISO 4762 socket head (the head sits flush)."""
    m = metric(size)
    head_depth = m.head_h + p.layer_mm if head_depth is None else head_depth
    hole = clearance_hole(size, depth, p)
    return hole + _down_cylinder(m.cbore_d + p.hole_clearance_mm, head_depth)


def countersunk_hole(size: str, depth: float, p: Profile) -> Part:
    """Hole for a 90° countersunk screw: a cone from the head diameter down to the hole."""
    m = metric(size)
    return _countersink(m.clear_fine + p.hole_clearance_mm, m.csk_d + p.hole_clearance_mm, depth)


# Countersunk wood/plug screws with a 90° head: d → head diameter dk.
# Source: DIN 7997 (countersunk wood screws), dk ≈ 2·d. Heads of different brands differ by
# ±0.5 mm: measure if you can and pass head_d explicitly.
WOOD_SCREW_HEAD: dict[float, float] = {3.0: 6.0, 3.5: 7.0, 4.0: 8.0, 4.5: 9.0, 5.0: 10.0, 6.0: 12.0}
WOOD_SCREW_CLEARANCE = 0.4  # added to the thread diameter, like ISO 273 fine, so the thread passes freely and doesn't tear the plastic


def wood_screw_countersunk_hole(d: float, depth: float, p: Profile, head_d: float | None = None) -> Part:
    """Through hole for a countersunk wood screw of diameter d (mm): the thread passes freely, the head sits flush."""
    if head_d is None:
        if d not in WOOD_SCREW_HEAD:
            raise ValueError(f"wood screw {d} mm isn't described, there are: {', '.join(f'{k:g}' for k in WOOD_SCREW_HEAD)}; or pass head_d")
        head_d = WOOD_SCREW_HEAD[d]
    return _countersink(d + WOOD_SCREW_CLEARANCE + p.hole_clearance_mm, head_d + p.hole_clearance_mm, depth)


def _countersink(hole_d: float, head_d: float, depth: float) -> Part:
    cone_h = (head_d - hole_d) / 2  # 90°: the height equals the difference of the radii
    cone = Pos(0, 0, -cone_h / 2 + EPS / 2) * Cone(hole_d / 2, head_d / 2 + EPS, cone_h + EPS)
    return _down_cylinder(hole_d, depth) + cone


def chamfer_ring(d: float, size: float = 0.6) -> Part:
    """Chamfer on the edge of a hole of diameter d: 45°, `size` wide (eases entry, removes the lip)."""
    return Pos(0, 0, -size / 2 + EPS / 2) * Cone(d / 2, d / 2 + size + EPS, size + EPS)


def nut_pocket(size: str, p: Profile, depth: float | None = None, slot: float = 0.0) -> Part:
    """Hexagonal pocket for an ISO 4032 nut (flats along X).

    slot > 0 extends the pocket sideways along +X by that length: a slot to slide the nut in from the side.
    """
    m = metric(size)
    s = m.nut_s + p.slide_fit_mm                       # across flats with clearance
    depth = m.nut_m + p.layer_mm if depth is None else depth
    # RegularPolygon takes the circumscribed circle, s = 2·R·cos30°. Vertices at 0° and 180°, so the flats run along X.
    hexagon = RegularPolygon(s / (3 ** 0.5), 6)
    pocket = Pos(0, 0, -depth) * extrude(hexagon, amount=depth + EPS)
    if slot > 0:
        pocket += Pos(slot / 2, 0, (EPS - depth) / 2) * Box(slot, s, depth + EPS)
    return pocket


def insert_hole(size: str, p: Profile, hole_d: float | None = None, length: float | None = None, extra: float = 1.0) -> Part:
    """Hole for a heat-set insert: the maker's diameter, depth = insert length + `extra` for displaced plastic.

    No printer clearance is added: the makers' D3 is meant for a printed hole, and the insert has to
    melt into the wall rather than slide in. p is kept for a uniform signature.
    """
    m = metric(size)
    d = m.insert_d if hole_d is None else hole_d
    length = m.insert_l if length is None else length
    return _down_cylinder(d, length + extra) + chamfer_ring(d, 0.4)
