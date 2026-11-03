"""Загрузка любого поддерживаемого файла (STL/3MF/STEP) в trimesh.Trimesh в мм."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh


def load_mesh(path: Path) -> trimesh.Trimesh:
    """Одна сетка из файла; сцены (3MF с несколькими объектами) склеиваются в одну."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".step", ".stp"):
        return _step_to_mesh(path)
    loaded = trimesh.load(path, force="mesh", process=True)
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise ValueError(f"Не удалось прочитать сетку из {path}")
    return loaded


def _step_to_mesh(path: Path) -> trimesh.Trimesh:
    from build123d import import_step

    shape = import_step(path)
    verts, tris = shape.tessellate(0.01, 0.1)
    vertices = np.array([(v.X, v.Y, v.Z) for v in verts], dtype=float)
    return trimesh.Trimesh(vertices=vertices, faces=np.array(tris, dtype=np.int64), process=True)
