"""Loads any supported file (STL/3MF/STEP) into a trimesh.Trimesh in mm."""

from __future__ import annotations

from pathlib import Path

import trimesh

SUPPORTED = (".stl", ".3mf", ".obj", ".step", ".stp")
MM_UNITS = ("mm", "millimeter", "millimeters")


def load_mesh(path: Path) -> trimesh.Trimesh:
    """One mesh from a file; scenes (a 3MF with several objects) are merged into one."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"format {ext} isn't supported, expected: {', '.join(SUPPORTED)}")
    if ext in (".step", ".stp"):
        from build123d import import_step

        from .export import shape_to_mesh

        return shape_to_mesh(import_step(path))
    loaded = trimesh.load(path, force="mesh", process=True)
    if not isinstance(loaded, trimesh.Trimesh) or len(loaded.faces) == 0:
        raise ValueError(f"could not read a mesh from {path}")
    # 3MF stores units (unit="inch" etc.); trimesh records them but doesn't convert. STL has no units: take mm.
    if loaded.units and loaded.units.lower() not in MM_UNITS:
        loaded.convert_units("millimeters")
    return loaded
