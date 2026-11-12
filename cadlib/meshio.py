"""Загрузка любого поддерживаемого файла (STL/3MF/STEP) в trimesh.Trimesh в мм."""

from __future__ import annotations

from pathlib import Path

import trimesh

SUPPORTED = (".stl", ".3mf", ".obj", ".step", ".stp")
MM_UNITS = ("mm", "millimeter", "millimeters")


def load_mesh(path: Path) -> trimesh.Trimesh:
    """Одна сетка из файла; сцены (3MF с несколькими объектами) склеиваются в одну."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"Формат {ext} не поддерживается, нужны: {', '.join(SUPPORTED)}")
    if ext in (".step", ".stp"):
        from build123d import import_step

        from .export import shape_to_mesh

        return shape_to_mesh(import_step(path))
    loaded = trimesh.load(path, force="mesh", process=True)
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise ValueError(f"Не удалось прочитать сетку из {path}")
    # 3MF хранит единицы (unit="inch" и т. п.), trimesh их запоминает, но не пересчитывает. STL единиц не знает: считаем мм.
    if loaded.units and loaded.units.lower() not in MM_UNITS:
        loaded.convert_units("millimeters")
    return loaded
