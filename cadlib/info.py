"""Model summary for `cad.py inspect`: what we are dealing with before a remix."""

from __future__ import annotations

import numpy as np
import trimesh

from .checks import base_area, overhang_fraction

TOP_FACETS = 3


def describe(mesh: trimesh.Trimesh) -> list[tuple[str, str]]:
    lo, hi = mesh.bounds
    size = hi - lo
    bodies = mesh.split(only_watertight=False)
    rows = [
        ("Size", f"{size[0]:.2f} × {size[1]:.2f} × {size[2]:.2f} mm (X × Y × Z)"),
        ("Bounds", f"X {lo[0]:.2f}…{hi[0]:.2f}, Y {lo[1]:.2f}…{hi[1]:.2f}, Z {lo[2]:.2f}…{hi[2]:.2f}"),
        ("Volume", f"{mesh.volume:.1f} mm³ ({mesh.volume / 1000:.2f} cm³)"),
        ("Surface area", f"{mesh.area:.1f} mm²"),
        ("Bodies", f"{len(bodies)}" + (f" (volumes: {', '.join(f'{b.volume:.0f}' for b in bodies[:6])} mm³)" if len(bodies) > 1 else "")),
        ("Triangles", f"{len(mesh.faces)}"),
        ("Watertight", "yes" if mesh.is_watertight else "NO"),
        ("Area on the bed", f"{base_area(mesh):.1f} mm² (faces at the lowest Z)"),
        ("Overhangs > 45°", f"{overhang_fraction(mesh) * 100:.1f}% of the area as the file lies"),
    ]
    rows += _largest_flats(mesh)
    if not (lo[2] == 0 or abs(lo[2]) < 1e-6):
        rows.append(("Note", f"the model doesn't stand on Z=0 (bottom at {lo[2]:.2f} mm); the slicer drops it to the bed itself"))
    return rows


def _largest_flats(mesh: trimesh.Trimesh) -> list[tuple[str, str]]:
    """The largest flat faces: candidates for the side to put on the bed."""
    if len(mesh.facets) == 0:
        return [("Flat faces", "none (an organic or heavily tessellated model)")]
    order = np.argsort(mesh.facets_area)[::-1][:TOP_FACETS]
    z_min = mesh.bounds[0][2]
    rows = []
    for rank, idx in enumerate(order, start=1):
        n = mesh.facets_normal[idx]
        on_bed = bool(np.all(np.abs(mesh.triangles[mesh.facets[idx]][:, :, 2] - z_min) < 0.01))
        rows.append((f"Flat face #{rank}", f"{mesh.facets_area[idx]:.1f} mm², normal ({n[0]:+.2f}, {n[1]:+.2f}, {n[2]:+.2f}){_dir(n, on_bed)}"))
    return rows


def _dir(n: np.ndarray, on_bed: bool) -> str:
    axis = int(np.argmax(np.abs(n)))
    if abs(n[axis]) < 0.99:
        return ", slanted"
    if axis == 2 and n[2] < 0:
        return ", faces down, on the bed" if on_bed else ", faces down, above the bed"
    names = {(2, 1): ", faces up", (0, 1): ", +X", (0, -1): ", −X", (1, 1): ", +Y", (1, -1): ", −Y"}
    return names[(axis, int(np.sign(n[axis])))]
