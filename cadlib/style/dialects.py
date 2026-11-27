"""Dialects: the choices that make a form read as gothic, gaudi, hitech, parametric or biomech.

biomech is a sci-fi biomechanical look: thin curved strands like tendons and segmented, spine-like relief.

A dialect fixes the opening shape, the lattice cutter, the edge finish and the member proportions.
Archetypes pick from here instead of hard-coding styles. Dimensionless ratios only: sizes come from the profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from build123d import Edge, Face, Solid
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as _EdgeFaceMap

from cadlib.checks import down_vector
from cadlib.config import Profile
from cadlib.finish import bevel, soften
from cadlib.style.outline import ArchKind

_TOL = 1e-4
_SEAM_COS = 0.9998  # faces within ~1 degree of each other along an edge meet tangentially


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
        Dialect("biomech", "oval", "none", "fillet", 0.2, True, 0.5),
    )
}


def get_dialect(name: str) -> Dialect:
    try:
        return DIALECTS[name]
    except KeyError:
        raise ValueError(f"unknown style {name!r}, there are: {', '.join(DIALECTS)}") from None


def edge_size(dialect: Dialect, depth: float, p: Profile) -> float:
    """The dialect's edge for an extrusion `depth` deep: clamp(edge_ratio * depth, layer_mm, depth / 3)."""
    return min(max(dialect.edge_ratio * depth, p.layer_mm), depth / 3)


def _depths(edge: Edge, down: np.ndarray) -> np.ndarray:
    """Positions along `down` of five points sampled along the edge."""
    return np.array([np.dot(tuple(edge @ t), down) for t in (0, 0.25, 0.5, 0.75, 1)])


def _seams(body: Solid) -> set[int]:
    """Hashes of the edges where two faces meet tangentially (a line running into an arc, say).

    Such a seam has no corner to round or chamfer, and OCCT fails on it, taking the whole chain down.
    """
    ancestors = _EdgeFaceMap()
    TopExp.MapShapesAndAncestors_s(body.wrapped, TopAbs_EDGE, TopAbs_FACE, ancestors)
    seams = set()
    for i in range(1, ancestors.Extent() + 1):
        faces = list(ancestors.FindFromIndex(i))
        if len(faces) != 2:
            continue
        edge = Edge(ancestors.FindKey(i))
        mid = edge @ 0.5
        n0, n1 = (Face(f).normal_at(mid) for f in faces)
        if abs(n0.dot(n1)) > _SEAM_COS:
            seams.add(hash(edge))
    return seams


def _classify(body: Solid, down: np.ndarray) -> tuple[list[Edge], list[Edge], list[Edge]]:
    """(bed, vertical, top) edges for a print direction, tangent seams left out.

    bed = lying in the lowest plane along `down`, vertical = parallel to `down`, top = all the rest.
    """
    seams = _seams(body)
    edges = body.edges()
    depths = [_depths(e, down) for e in edges]
    bed_depth = max(d.max() for d in depths)
    bed, vertical, top = [], [], []
    for e, d in zip(edges, depths):
        if hash(e) in seams:
            continue
        if d.min() > bed_depth - _TOL:
            bed.append(e)
        elif abs(d[-1] - d[0]) > e.length - _TOL:
            vertical.append(e)
        else:
            top.append(e)
    return bed, vertical, top


def finish_extrusion(
    body: Solid, dialect: Dialect, depth: float, print_down, p: Profile, max_size: float | None = None
) -> Solid:
    """Finish an extruded body for printing.

    Bed edges get a 45° chamfer, vertical and top edges the dialect's edge. Edge size is
    clamp(edge_ratio * depth, layer_mm, depth / 3), at most `max_size` when given (a caller's
    thinnest member: a rounding wider than half a member cannot be made). `print_down` None means
    -Z (the file's bottom is on the bed). Tangent seams (a line running into an arc) are left alone.
    """
    down = down_vector("-z" if print_down is None else print_down)
    size = edge_size(dialect, depth, p)
    if max_size is not None:
        size = max(min(size, max_size), p.layer_mm)
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
