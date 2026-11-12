"""Операции над готовыми сетками для ремиксов (STL/3MF): починка, масштаб, разрез, булевы.

Булевы операции делает manifold3d: он надёжен на треугольных сетках, где OCCT спотыкается.
Тела-инструменты удобно строить в build123d (точные цилиндры, пазы, крепёж из cadlib.fasteners)
и передавать сюда как есть — они сами переведутся в сетку.
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


# --- загрузка и починка ------------------------------------------------------


def repair(mesh: trimesh.Trimesh) -> RepairResult:
    """Типовая починка скачанной сетки. Не меняет форму, только топологию; всё, что сделано, — в notes."""
    mesh = mesh.copy()
    notes: list[str] = []

    faces_before, verts_before = len(mesh.faces), len(mesh.vertices)
    mesh.merge_vertices()
    if len(mesh.vertices) < verts_before:
        notes.append(f"склеено совпадающих вершин: {verts_before - len(mesh.vertices)}")

    keep = mesh.nondegenerate_faces() & mesh.unique_faces()
    if not keep.all():
        mesh.update_faces(keep)
        mesh.remove_unreferenced_vertices()
        notes.append(f"удалено вырожденных и повторных треугольников: {faces_before - len(mesh.faces)}")

    if not mesh.is_winding_consistent:
        trimesh.repair.fix_winding(mesh)
        notes.append("согласовано направление обхода треугольников")
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
        notes.append("закрыты дыры" if mesh.is_watertight else "дыры закрыть не удалось — сетка остаётся открытой")
    if mesh.volume < 0:
        mesh.invert()
        notes.append("сетка была вывернута наизнанку — нормали развёрнуты")
    return RepairResult(mesh, notes)


def load_source(path: Path, fix: bool = True) -> RepairResult:
    """Оригинал ремикса: читается, при fix=True чинится. Сам файл не меняется никогда."""
    mesh = load_mesh(path)
    return repair(mesh) if fix else RepairResult(mesh)


# --- перевод между trimesh, build123d и manifold ------------------------------


def to_mesh(obj) -> trimesh.Trimesh:
    if isinstance(obj, trimesh.Trimesh):
        return obj
    from build123d import Shape

    if isinstance(obj, Shape):
        from .export import shape_to_mesh

        return shape_to_mesh(obj)
    raise TypeError(f"ожидалась сетка trimesh или тело build123d, получено {type(obj).__name__}")


def to_manifold(obj) -> manifold3d.Manifold:
    mesh = to_mesh(obj)
    m = manifold3d.Manifold(manifold3d.Mesh(
        vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
        tri_verts=np.asarray(mesh.faces, dtype=np.uint32),
    ))
    if m.status() != manifold3d.Error.NoError:
        raise ValueError(
            f"сетка не годится для булевых операций ({m.status().name}): "
            "она не замкнута или не manifold. Сначала mesh.repair(), затем cad.py check."
        )
    return m


def from_manifold(m: manifold3d.Manifold) -> trimesh.Trimesh:
    out = m.to_mesh()
    if len(out.tri_verts) == 0:
        raise ValueError(
            "после операции не осталось ни одного треугольника: инструмент целиком закрыл деталь "
            "или не пересёкся с ней (для intersect). Проверьте положение и размеры инструмента."
        )
    return trimesh.Trimesh(vertices=np.asarray(out.vert_properties[:, :3], dtype=float), faces=np.asarray(out.tri_verts), process=True)


# --- операции ---------------------------------------------------------------


def subtract(mesh: trimesh.Trimesh, *tools) -> trimesh.Trimesh:
    """Вычесть одно или несколько тел (отверстия, пазы, карманы)."""
    result = to_manifold(mesh)
    for tool in tools:
        result = result - to_manifold(tool)
    return from_manifold(result)


def add(mesh: trimesh.Trimesh, *tools) -> trimesh.Trimesh:
    """Добавить тела (бобышки, рёбра, площадки), объединив в одно."""
    result = to_manifold(mesh)
    for tool in tools:
        result = result + to_manifold(tool)
    return from_manifold(result)


def intersect(mesh: trimesh.Trimesh, tool) -> trimesh.Trimesh:
    return from_manifold(to_manifold(mesh) ^ to_manifold(tool))


def cut(mesh: trimesh.Trimesh, normal=(0, 0, 1), origin=(0, 0, 0)) -> trimesh.Trimesh:
    """Разрез плоскостью: остаётся часть, куда смотрит normal. Срез закрывается автоматически."""
    n = np.asarray(normal, dtype=float)
    n /= np.linalg.norm(n)
    offset = float(np.dot(n, np.asarray(origin, dtype=float)))
    return from_manifold(to_manifold(mesh).trim_by_plane(tuple(n), offset))


def split_by_plane(mesh: trimesh.Trimesh, normal=(0, 0, 1), origin=(0, 0, 0)) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """Обе половины: (со стороны normal, с обратной). Например, разрезать большую модель на две под стол."""
    keep = cut(mesh, normal, origin)
    other = cut(mesh, -np.asarray(normal, dtype=float), origin)
    return keep, other


def scale(mesh: trimesh.Trimesh, factors, about: str = "min") -> trimesh.Trimesh:
    """Масштаб по осям: число или (sx, sy, sz). about='min' — угол модели на месте (стоит на столе), 'center' — центр."""
    f = np.broadcast_to(np.asarray(factors, dtype=float), (3,))
    if np.any(f <= 0):
        raise ValueError(f"масштаб должен быть > 0, получено {tuple(f)}")
    pivot = mesh.bounds[0] if about == "min" else mesh.bounds.mean(axis=0)
    out = mesh.copy()
    out.vertices = (out.vertices - pivot) * f + pivot
    return out


def scale_to(mesh: trimesh.Trimesh, size, about: str = "min") -> trimesh.Trimesh:
    """Масштаб до заданных габаритов (мм); None по оси — оставить. Например scale_to(m, (None, None, 50))."""
    factors = [1.0 if s is None else s / e for s, e in zip(size, mesh.extents)]
    return scale(mesh, factors, about)


def translate(mesh: trimesh.Trimesh, offset) -> trimesh.Trimesh:
    out = mesh.copy()
    out.apply_translation(offset)
    return out


def rotate(mesh: trimesh.Trimesh, degrees, about: str = "center") -> trimesh.Trimesh:
    """Поворот на (rx, ry, rz) градусов вокруг осей X, затем Y, затем Z.

    about='center' — вокруг центра габаритов, 'min' — вокруг нижнего угла. Модель после поворота
    может уйти под стол: обычно дальше drop_to_bed. Например, положить на бок: rotate(m, (90, 0, 0)).
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
    """Зеркальная копия по оси ('x', 'y' или 'z') относительно центра габаритов: левая деталь из правой.

    Нормали остаются наружу: trimesh разворачивает обход треугольников при отражении.
    """
    if axis not in ("x", "y", "z"):
        raise ValueError(f"ось «{axis}»: нужна 'x', 'y' или 'z'")
    i = "xyz".index(axis)
    center = mesh.bounds.mean(axis=0)
    flip = np.eye(4)
    flip[i, i] = -1.0
    flip[i, 3] = 2 * center[i]
    out = mesh.copy()
    out.apply_transform(flip)
    return out


def drop_to_bed(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Опустить низ модели на Z=0."""
    return translate(mesh, (0, 0, -mesh.bounds[0][2]))
