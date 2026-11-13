"""Operations on finished meshes for remixes (STL/3MF): repair, scale, cut, booleans.

Booleans are done by manifold3d: it is reliable on triangle meshes, where OCCT stumbles.
Tool bodies are easiest to build in build123d (exact cylinders, slots, fasteners from cadlib.fasteners)
and pass here as they are: they are turned into meshes automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import manifold3d
import numpy as np
import trimesh

from .meshio import load_mesh


@dataclass
class RepairResult:
    mesh: trimesh.Trimesh
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.notes)


# --- loading and repair -----------------------------------------------------


def repair(mesh: trimesh.Trimesh) -> RepairResult:
    """Usual repair of a downloaded mesh. Changes topology, never the shape; everything done is listed in notes."""
    mesh = mesh.copy()
    notes: list[str] = []

    faces_before, verts_before = len(mesh.faces), len(mesh.vertices)
    mesh.merge_vertices()
    if len(mesh.vertices) < verts_before:
        notes.append(f"merged duplicate vertices: {verts_before - len(mesh.vertices)}")

    keep = mesh.nondegenerate_faces() & mesh.unique_faces()
    if not keep.all():
        mesh.update_faces(keep)
        mesh.remove_unreferenced_vertices()
        notes.append(f"removed degenerate and duplicate triangles: {faces_before - len(mesh.faces)}")

    if not mesh.is_winding_consistent:
        trimesh.repair.fix_winding(mesh)
        notes.append("made triangle winding consistent")
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
        notes.append("closed holes" if mesh.is_watertight else "could not close the holes: the mesh stays open")
    if mesh.volume < 0:
        mesh.invert()
        notes.append("the mesh was inside out: normals flipped")
    return RepairResult(mesh, notes)


def load_source(path: Path, fix: bool = True) -> RepairResult:
    """A remix's original: read, and repaired with fix=True. The file itself is never changed."""
    mesh = load_mesh(path)
    return repair(mesh) if fix else RepairResult(mesh)


# --- conversion between trimesh, build123d and manifold ---------------------


def to_mesh(obj) -> trimesh.Trimesh:
    if isinstance(obj, trimesh.Trimesh):
        return obj
    from build123d import Shape

    if isinstance(obj, Shape):
        from .export import shape_to_mesh

        return shape_to_mesh(obj)
    raise TypeError(f"expected a trimesh mesh or a build123d solid, got {type(obj).__name__}")


def to_manifold(obj) -> manifold3d.Manifold:
    mesh = to_mesh(obj)
    m = manifold3d.Manifold(manifold3d.Mesh(
        vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
        tri_verts=np.asarray(mesh.faces, dtype=np.uint32),
    ))
    if m.status() != manifold3d.Error.NoError:
        raise ValueError(
            f"the mesh is unfit for booleans ({m.status().name}): "
            "it is open or not manifold. Run mesh.repair() first, then cad.py check."
        )
    return m


def from_manifold(m: manifold3d.Manifold) -> trimesh.Trimesh:
    out = m.to_mesh()
    if len(out.tri_verts) == 0:
        raise ValueError(
            "nothing is left after the operation: the tool covered the whole part "
            "or missed it (for intersect). Check the tool's position and size."
        )
    return trimesh.Trimesh(vertices=np.asarray(out.vert_properties[:, :3], dtype=float), faces=np.asarray(out.tri_verts), process=True)


# --- operations -------------------------------------------------------------


def subtract(mesh: trimesh.Trimesh, *tools) -> trimesh.Trimesh:
    """Subtract one or more bodies (holes, slots, pockets)."""
    result = to_manifold(mesh)
    for tool in tools:
        result = result - to_manifold(tool)
    return from_manifold(result)


def add(mesh: trimesh.Trimesh, *tools) -> trimesh.Trimesh:
    """Add bodies (bosses, ribs, pads), merging them into one."""
    result = to_manifold(mesh)
    for tool in tools:
        result = result + to_manifold(tool)
    return from_manifold(result)


def intersect(mesh: trimesh.Trimesh, tool) -> trimesh.Trimesh:
    return from_manifold(to_manifold(mesh) ^ to_manifold(tool))


def cut(mesh: trimesh.Trimesh, normal=(0, 0, 1), origin=(0, 0, 0)) -> trimesh.Trimesh:
    """Cut by a plane: the part on the normal's side stays. The cut face is closed automatically."""
    n = np.asarray(normal, dtype=float)
    n /= np.linalg.norm(n)
    offset = float(np.dot(n, np.asarray(origin, dtype=float)))
    return from_manifold(to_manifold(mesh).trim_by_plane(tuple(n), offset))


def split_by_plane(mesh: trimesh.Trimesh, normal=(0, 0, 1), origin=(0, 0, 0)) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """Both halves: (on the normal's side, on the other). For example, to split a large model to fit the bed."""
    keep = cut(mesh, normal, origin)
    other = cut(mesh, -np.asarray(normal, dtype=float), origin)
    return keep, other


def scale(mesh: trimesh.Trimesh, factors, about: str = "min") -> trimesh.Trimesh:
    """Scale per axis: a number or (sx, sy, sz). about='min' keeps the model's corner in place (it stays on the bed), 'center' the centre."""
    f = np.broadcast_to(np.asarray(factors, dtype=float), (3,))
    if np.any(f <= 0):
        raise ValueError(f"scale must be > 0, got {tuple(f)}")
    pivot = mesh.bounds[0] if about == "min" else mesh.bounds.mean(axis=0)
    out = mesh.copy()
    out.vertices = (out.vertices - pivot) * f + pivot
    return out


def scale_to(mesh: trimesh.Trimesh, size, about: str = "min") -> trimesh.Trimesh:
    """Scale to the given size (mm); None for an axis keeps it. For example scale_to(m, (None, None, 50))."""
    factors = [1.0 if s is None else s / e for s, e in zip(size, mesh.extents)]
    return scale(mesh, factors, about)


def translate(mesh: trimesh.Trimesh, offset) -> trimesh.Trimesh:
    out = mesh.copy()
    out.apply_translation(offset)
    return out


def rotate(mesh: trimesh.Trimesh, degrees, about: str = "center") -> trimesh.Trimesh:
    """Turn by (rx, ry, rz) degrees about the X, then Y, then Z axes.

    about='center' turns about the centre of the bounds, 'min' about the lowest corner. After turning the
    model may go below the bed: usually drop_to_bed follows. To lay it on its side: rotate(m, (90, 0, 0)).
    """
    rx, ry, rz = (float(a) for a in np.broadcast_to(np.asarray(degrees, dtype=float), (3,)))
    pivot = mesh.bounds[0] if about == "min" else mesh.bounds.mean(axis=0)
    turn = trimesh.transformations.euler_matrix(*np.radians([rx, ry, rz]), axes="sxyz")
    out = mesh.copy()
    out.apply_transform(
        trimesh.transformations.translation_matrix(pivot) @ turn @ trimesh.transformations.translation_matrix(-pivot)
    )
    return out


def mirror(mesh: trimesh.Trimesh, axis: str = "x") -> trimesh.Trimesh:
    """Mirror copy along an axis ('x', 'y' or 'z') about the centre of the bounds: a left part from a right one.

    Normals stay outward: trimesh flips the triangle winding on a reflection.
    """
    if axis not in ("x", "y", "z"):
        raise ValueError(f"axis {axis!r}: expected 'x', 'y' or 'z'")
    i = "xyz".index(axis)
    center = mesh.bounds.mean(axis=0)
    flip = np.eye(4)
    flip[i, i] = -1.0
    flip[i, 3] = 2 * center[i]
    out = mesh.copy()
    out.apply_transform(flip)
    return out


def drop_to_bed(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Lower the model's bottom to Z=0."""
    return translate(mesh, (0, 0, -mesh.bounds[0][2]))
