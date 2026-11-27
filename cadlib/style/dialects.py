"""Dialects: the choices that make a form read as gothic, gaudi, hitech or parametric.

A dialect fixes the opening shape, the lattice cutter, the edge finish and the member proportions.
Archetypes pick from here instead of hard-coding styles. Dimensionless ratios only: sizes come from the profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from build123d import Edge, Solid

from cadlib.checks import down_vector
from cadlib.config import Profile
from cadlib.finish import bevel, soften
from cadlib.style.outline import ArchKind

_TOL = 1e-4


@dataclass(frozen=True)
class Dialect:
    name: str
    opening: ArchKind
    lattice: Literal["none", "hex", "tri"]
    edge: Literal["chamfer", "fillet"]
    edge_ratio: float  # edge size / extrusion depth
    relief_ribs: bool
    taper: float  # tip width / root width


DIALECTS: dict[str, Dialect] = {
    d.name: d
    for d in (
        Dialect("gothic", "pointed", "none", "chamfer", 0.08, True, 0.6),
        Dialect("gaudi", "catenary", "none", "fillet", 0.25, False, 0.45),
        Dialect("hitech", "round", "tri", "fillet", 0.05, False, 1.0),
        Dialect("parametric", "oval", "hex", "fillet", 0.15, False, 0.5),
    )
}


def get_dialect(name: str) -> Dialect:
    try:
        return DIALECTS[name]
    except KeyError:
        raise ValueError(f"unknown style {name!r}, there are: {', '.join(DIALECTS)}") from None


def _depths(edge: Edge, down: np.ndarray) -> np.ndarray:
    """Positions along `down` of five points sampled along the edge."""
    return np.array([np.dot(tuple(edge @ t), down) for t in (0, 0.25, 0.5, 0.75, 1)])


def _classify(body: Solid, down: np.ndarray) -> tuple[list[Edge], list[Edge], list[Edge]]:
    """(bed, vertical, top) edges for a print direction.

    bed = lying in the lowest plane along `down`, vertical = parallel to `down`, top = all the rest.
    """
    edges = body.edges()
    depths = [_depths(e, down) for e in edges]
    bed_depth = max(d.max() for d in depths)
    bed, vertical, top = [], [], []
    for e, d in zip(edges, depths):
        if d.min() > bed_depth - _TOL:
            bed.append(e)
        elif abs(d[-1] - d[0]) > e.length - _TOL:
            vertical.append(e)
        else:
            top.append(e)
    return bed, vertical, top


def finish_extrusion(body: Solid, dialect: Dialect, depth: float, print_down, p: Profile) -> Solid:
    """Finish an extruded body for printing.

    Bed edges get a 45° chamfer, vertical and top edges the dialect's edge. Edge size is
    clamp(edge_ratio * depth, layer_mm, depth / 3). `print_down` None means -Z (the file's bottom is on the bed).
    """
    down = down_vector("-z" if print_down is None else print_down)
    size = min(max(dialect.edge_ratio * depth, p.layer_mm), depth / 3)
    op = bevel if dialect.edge == "chamfer" else soften

    # The dialect edge goes first: its vertical and top edges meet in corners and are done as one chain.
    # The bed edges are then found again on the new body and chamfered.
    _, vertical, top = _classify(body, down)
    if vertical or top:
        body, _ = op(body, vertical + top, size)
    bed, _, _ = _classify(body, down)
    if bed:
        body, _ = bevel(body, bed, max(p.layer_mm * 2, 0.4))
    return body
