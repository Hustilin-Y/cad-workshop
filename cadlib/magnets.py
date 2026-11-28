"""Disc magnets (sintered NdFeB): nominal sizes and the pocket they press into.

There is no standard for disc magnet sizes: sellers stock metric diameter × height sizes, and the
owner uses common ones up to 10 × 3. Their dimensional tolerance is typically ±0.1 mm on diameter
and height (KJ Magnetics lists ±0.004 in for its N42 discs). So a pocket is drawn from the nominal
size: the diameter gets `p.magnet_fit_mm` (found with `cad.py coupon magnet`), the depth covers the
+0.1 so an oversize magnet still sits flush, rounded up to a whole layer.

A pocket tool stands with its top at Z = 0 and goes down into −Z, as the `cadlib.fasteners` tools:
`body -= Pos(x, y, z_top) * pocket(magnet("6x2"), p)`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from build123d import Cylinder, Part, Pos

from .config import Profile

EPS = 0.01            # the tool sticks out of the surface this much so the boolean leaves no skin
TOLERANCE_MM = 0.1    # typical ± on diameter and height of sintered NdFeB discs

# Sizes the metric sellers commonly stock, d × h in mm, up to the owner's largest (10 × 3).
CATALOGUE = ("2x1", "3x1", "3x2", "4x2", "5x1", "5x2", "5x3", "5x4", "6x2", "6x3",
             "8x2", "8x3", "10x2", "10x3")

_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[x×хX]\s*(\d+(?:\.\d+)?)\s*$")  # x, ×, Cyrillic х


@dataclass(frozen=True)
class Magnet:
    d: float   # nominal diameter
    h: float   # nominal height

    @property
    def name(self) -> str:
        return f"{self.d:g}x{self.h:g}"


def magnet(size: str) -> Magnet:
    """'6x2' → Magnet(6, 2). Any positive DxH is accepted; CATALOGUE lists the usual ones."""
    m = _SIZE_RE.match(size)
    if not m or float(m.group(1)) <= 0 or float(m.group(2)) <= 0:
        raise ValueError(f"magnet size {size!r}: expected DxH in mm, e.g. 6x2 (usual: {', '.join(CATALOGUE)})")
    return Magnet(float(m.group(1)), float(m.group(2)))


def pocket_depth(m: Magnet, p: Profile) -> float:
    """Nominal height plus the tolerance, rounded up to a whole layer."""
    return math.ceil((m.h + TOLERANCE_MM) / p.layer_mm - 1e-9) * p.layer_mm


def pocket(m: Magnet, p: Profile, depth: float | None = None) -> Part:
    """A pocket for a press-fit magnet, to subtract; top at Z = 0, Ø = nominal d + p.magnet_fit_mm."""
    depth = pocket_depth(m, p) if depth is None else depth
    return Pos(0, 0, (EPS - depth) / 2) * Cylinder((m.d + p.magnet_fit_mm) / 2, depth + EPS)
