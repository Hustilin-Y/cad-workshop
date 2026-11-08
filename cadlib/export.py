"""Экспорт тела build123d или готовой сетки в STEP/STL/3MF одним вызовом."""

from __future__ import annotations

import tempfile
from pathlib import Path

import trimesh
from build123d import Shape, export_step, export_stl

DEFAULT_FORMATS = ("step", "stl", "3mf")
MESH_FORMATS = ("stl", "3mf")  # из сетки STEP не получить, только из B-rep

# Точность тесселяции: 0.02 мм по хорде — в 20 раз меньше сопла 0.4, файлы при этом вдвое легче, чем при 0.01.
LINEAR_TOL_MM = 0.02
ANGULAR_TOL_RAD = 0.1


def export_all(
    shape: Shape,
    out_dir: Path,
    name: str,
    formats: tuple[str, ...] = DEFAULT_FORMATS,
) -> dict[str, Path]:
    """Пишет файлы out_dir/name.<ext>, возвращает {формат: путь}. Сетка тесселируется один раз на STL и 3MF."""
    unknown = set(formats) - set(DEFAULT_FORMATS)
    if unknown:
        raise ValueError(f"Неизвестный формат: {', '.join(sorted(unknown))}")
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    if "step" in formats:
        path = out_dir / f"{name}.step"
        export_step(shape, path)
        written["step"] = path
    if "stl" in formats or "3mf" in formats:
        # STL пишет сам OCCT (быстро), 3MF собирается из того же STL, чтобы сетки совпадали.
        stl = out_dir / f"{name}.stl"
        export_stl(shape, stl, tolerance=LINEAR_TOL_MM, angular_tolerance=ANGULAR_TOL_RAD)
        mesh = _drop_degenerate(trimesh.load(stl, force="mesh"), stl)
        if "3mf" in formats:
            written |= export_mesh(mesh, out_dir, name, ("3mf",))
        if "stl" in formats:
            written["stl"] = stl
        else:
            stl.unlink()
    return {fmt: written[fmt] for fmt in formats}


def _drop_degenerate(mesh: trimesh.Trimesh, stl: Path) -> trimesh.Trimesh:
    """OCCT пишет треугольники нулевой площади на полюсах сфер: убираем их и переписываем STL."""
    keep = mesh.nondegenerate_faces()
    if keep.all():
        return mesh
    mesh.update_faces(keep)
    mesh.remove_unreferenced_vertices()
    mesh.export(stl, file_type="stl")
    return mesh


def export_mesh(
    mesh: trimesh.Trimesh,
    out_dir: Path,
    name: str,
    formats: tuple[str, ...] = MESH_FORMATS,
) -> dict[str, Path]:
    """То же для готовой сетки (ремиксы STL). STEP пропускается: его из сетки не сделать."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for fmt in formats:
        if fmt == "step":
            continue
        if fmt not in MESH_FORMATS:
            raise ValueError(f"Неизвестный формат: {fmt}")
        path = out_dir / f"{name}.{fmt}"
        mesh.export(path, file_type=fmt)
        written[fmt] = path
    return written


def shape_to_mesh(shape: Shape) -> trimesh.Trimesh:
    """Тесселяция B-rep в trimesh с точностью экспорта (через временный STL: так быстрее, чем через Python)."""
    with tempfile.TemporaryDirectory() as tmp:
        stl = Path(tmp) / "shape.stl"
        export_stl(shape, stl, tolerance=LINEAR_TOL_MM, angular_tolerance=ANGULAR_TOL_RAD)
        return trimesh.load(stl, force="mesh", process=True)
