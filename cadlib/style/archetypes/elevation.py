"""Helpers shared by the planar archetypes: an elevation drawn in (x, z) on Plane.XZ and extruded along Y.

Faces are wound so their normal is +Y and fuse with the members of `cadlib.style.members`. Points
are (x, z) tuples.
"""

from __future__ import annotations

import math

import numpy as np
from build123d import Compound, Edge, Face, Plane, Pos, Solid, Vector, Wire, fillet

from cadlib.style.dialects import Dialect
from cadlib.style.lattice import _point_seg_dist, _segments
from cadlib.style.outline import Point, arch, clip_roof, to_face

ROOF_DEG = 46.0  # roofs are clipped a degree steeper than the 45 degree limit, clear of rounding noise
THIN_EDGE = 0.45  # an edge finish is at most this share of the thinnest member
RIB_WIDTH_WALLS = 2.5  # relief rib width / min_wall
RIB_HEIGHT_LAYERS = 15  # relief rib height / layer


def poly(pts: list[Point], smooth_deg: float = 12.0) -> Face:
    """Planar face of an (x, z) outline, wound so its normal is +Y like the members' faces (they fuse).

    Runs of points that turn by less than smooth_deg per vertex become one spline, so a sampled
    arch is a few smooth edges an edge finish can follow, not dozens of facets.
    """
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    pts = pts if area < 0 else pts[::-1]
    n = len(pts)
    seg = [math.dist(pts[i], pts[(i + 1) % n]) for i in range(n)]
    long = 2.5 * float(np.median(seg))  # a straight run (a jamb) between sampled curves stays a line
    corners = [
        i for i in range(n)
        if _turn_deg(pts[i - 1], pts[i], pts[(i + 1) % n]) > smooth_deg or max(seg[i - 1], seg[i]) > long
    ]
    if len(corners) < 2:
        return to_face(pts)
    edges = []
    for a, b in zip(corners, corners[1:] + corners[:1]):
        run = [pts[k % n] for k in range(a, b + (n if b <= a else 0) + 1)]
        vecs = [Vector(u, 0, v) for u, v in run]
        edges.append(Edge.make_line(*vecs) if len(run) == 2 else Edge.make_spline(vecs))
    return Face(Wire(edges))


def disc(centre: Point, r: float) -> Face:
    # Polygon faces from to_face wind clockwise seen along the plane normal; the disc follows suit.
    return Face(Wire.make_circle(r, Plane(origin=(centre[0], 0, centre[1]), z_dir=(0, 1, 0))))


def fuse(faces: list[Face]) -> Face:
    fused = faces[0]
    for f in faces[1:]:
        fused = fused + f
    return fused


def band(a: Point, b: Point, w: float) -> Face:
    """A straight bar of width w from a to b."""
    du, dv = b[0] - a[0], b[1] - a[1]
    n = math.hypot(du, dv)
    nu, nv = -dv / n * w / 2, du / n * w / 2
    return poly([(a[0] + nu, a[1] + nv), (b[0] + nu, b[1] + nv), (b[0] - nu, b[1] - nv), (a[0] - nu, a[1] - nv)])


def offset_path(path: list[Point], dist: float) -> list[Point]:
    """An open (x, z) path moved sideways by dist (to the left of its travel when positive)."""
    a = np.array(path)
    d = np.gradient(a, axis=0)
    d /= np.linalg.norm(d, axis=1)[:, None]
    return [(float(x - dist * dz), float(z + dist * dx)) for (x, z), (dx, dz) in zip(a, d)]


def turn(pts: list[Point], up: Point) -> list[Point]:
    """Turn points whose apex is +v so that it points along `up`."""
    ang = math.atan2(up[1], up[0]) - math.pi / 2
    c, s = math.cos(ang), math.sin(ang)
    return [(c * u - s * v, s * u + c * v) for u, v in pts]


def shift(pts: list[Point], at: Point) -> list[Point]:
    return [(u + at[0], v + at[1]) for u, v in pts]


def round_corners(face: Face, dialect: Dialect, concave: float, convex: float, radius=None) -> Face:
    """Rounded dialects round the elevation's corners in 2D, which seldom fails the way a 3D fillet does.

    Concave corners (where members meet) take `concave`, convex ones `convex`; a corner that cannot
    take its radius tries half of it, then a quarter, then stays sharp. The vertical edges then are
    tangent seams and the 3D finish only rounds the top and bed outlines. `radius(pos, convex)`, when
    given, sets each corner's radius instead. Chamfer dialects are returned unchanged.
    """
    if dialect.edge != "fillet":
        return face
    holes = face.inner_wires()
    if len(holes) > 1:
        # OCCT's 2D fillet keeps only one hole of a face, so a face with several holes is rounded
        # as its outline and each hole on its own (a hole's convex corner is a concave one of the part).
        def flipped(pos, is_convex: bool) -> float:
            return radius(pos, not is_convex) if radius is not None else (concave if is_convex else convex)

        result = round_corners(Face(face.outer_wire()), dialect, concave, convex, radius)
        for wire in holes:
            hole = Face(wire)
            result = result - round_corners(hole, dialect, concave, convex, flipped)
        faces = result.faces()
        return faces[0] if len(faces) == 1 else face
    for pos in [Vector(v) for v in face.vertices()]:
        found = _corner_at(face, pos)
        if found is None:
            continue
        vertex, is_convex = found
        r = radius(pos, is_convex) if radius is not None else (convex if is_convex else concave)
        if r <= 0:
            continue
        for size in (r, r / 2, r / 4):
            try:
                faces = fillet(vertex, size).faces()
            except Exception:  # noqa: BLE001  OCCT refuses a radius that does not fit
                continue
            # Accept only a rounding that kept every hole and moved no more than a corner's worth of area.
            if (
                len(faces) == 1
                and faces[0].is_valid
                and len(faces[0].inner_wires()) == len(face.inner_wires())
                and abs(faces[0].area - face.area) < size * size
            ):
                face = faces[0]
                break
    return face


def _corner_at(face: Face, pos: Vector):
    """(vertex, convex?) of the face's vertex at `pos` when its two edges meet at an angle, else None."""
    vertex = next((v for v in face.vertices() if (Vector(v) - pos).length < 1e-6), None)
    if vertex is None:
        return None
    dirs = []
    for e in face.edges():
        if (e @ 0 - pos).length < 1e-6:
            dirs.append(e % 0)
        elif (e @ 1 - pos).length < 1e-6:
            dirs.append(-(e % 1))
    if len(dirs) != 2 or dirs[0].dot(dirs[1]) < -math.cos(math.radians(1.0)):
        return None  # tangent: the edges run on in a straight line
    bisector = (dirs[0] + dirs[1]).normalized()
    return vertex, face.is_inside(pos + bisector * 0.05)


def extrude_y(shape, depth: float, y0: float | None = None):
    """Extrusion of faces in the XZ plane over y0 <= y <= y0 + depth (default: centred on y = 0, no seam there)."""
    y0 = -depth / 2 if y0 is None else y0
    solids = [Solid.extrude(Pos(0, y0, 0) * f, Vector(0, depth, 0)) for f in shape.faces()]
    return solids[0] if len(solids) == 1 else Compound(solids)


def one(shape, what: str = "the part") -> Solid:
    solids = shape.solids()
    if len(solids) != 1:
        raise ValueError(f"{what} fell apart into {len(solids)} bodies")
    return solids[0]


def cap_face(d: float, up: Point, plane: Plane) -> Face:
    """The 45 degree cap that turns a round hole of diameter d into a teardrop pointing to `up`."""
    return to_face(clip_roof(turn(arch("round", d, d / 2, n=32), up), up, ROOF_DEG), plane)


def point_field(region: Face, plane: Plane, point: Point, cell: float):
    """Lattice field(x, y, z) in world coordinates: 1 nearest `point` (x, z), 0 at the far end of the region.

    Distances are measured in the region's plane (`point` and the sample are both projected onto
    it), normalised over the region, so the whole range of cells and bars shows across it.
    """
    org, xd, yd = plane.origin, plane.x_dir, plane.y_dir

    def uv(at: Vector) -> tuple[float, float]:
        return (at - org).dot(xd), (at - org).dot(yd)

    cu, cv = uv(Vector(point[0], 0, point[1]))
    ra, rb = _segments(region, plane)
    # Nearest: to the outline's segments (a straight edge has only its two ends as vertices);
    # farthest: at a vertex. Cell centres stay this far in.
    near = float(_point_seg_dist(np.array([[cu, cv]]), ra, rb).min()) + cell / 2
    far = float(np.hypot(ra[:, 0] - cu, ra[:, 1] - cv).max()) - cell
    far = max(far, near + cell)  # a region hardly bigger than a cell: still a falling field, no sign flip

    def field(x: float, y: float, z: float) -> float:
        u, v = uv(Vector(x, y, z))
        return (far - math.hypot(u - cu, v - cv)) / (far - near)

    return field


def _turn_deg(a: Point, b: Point, c: Point) -> float:
    """How far the path a -> b -> c turns at b, degrees."""
    d1 = (b[0] - a[0], b[1] - a[1])
    d2 = (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*d1), math.hypot(*d2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    cos = (d1[0] * d2[0] + d1[1] * d2[1]) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))
