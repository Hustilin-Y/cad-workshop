"""Экспорт тела build123d в STEP/STL/3MF одним вызовом."""

from __future__ import annotations

from pathlib import Path

from build123d import Mesher, Shape, Unit, export_step, export_stl

DEFAULT_FORMATS = ("step", "stl", "3mf")

# Точность тесселяции: 0.01 мм по хорде достаточно для любого сопла, файлы остаются небольшими.
LINEAR_TOL_MM = 0.01
ANGULAR_TOL_RAD = 0.1


def export_all(
    shape: Shape,
    out_dir: Path,
    name: str,
    formats: tuple[str, ...] = DEFAULT_FORMATS,
) -> dict[str, Path]:
    """Пишет файлы out_dir/name.<ext>, возвращает {формат: путь}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for fmt in formats:
        path = out_dir / f"{name}.{fmt}"
        if fmt == "step":
            export_step(shape, path)
        elif fmt == "stl":
            export_stl(shape, path, tolerance=LINEAR_TOL_MM, angular_tolerance=ANGULAR_TOL_RAD)
        elif fmt == "3mf":
            mesher = Mesher(unit=Unit.MM)
            mesher.add_shape(shape, linear_deflection=LINEAR_TOL_MM, angular_deflection=ANGULAR_TOL_RAD)
            mesher.write(str(path))
        else:
            raise ValueError(f"Неизвестный формат: {fmt}")
        written[fmt] = path
    return written
