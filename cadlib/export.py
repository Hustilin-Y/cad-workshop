"""Export a build123d solid or a finished mesh to STEP/STL/3MF in one call."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import trimesh
from build123d import Shape, export_step, export_stl

DEFAULT_FORMATS = ("step", "stl", "3mf")
MESH_FORMATS = ("stl", "3mf")  # STEP can't come from a mesh, only from B-rep

# Tessellation: 0.02 mm chordal deviation, 20× finer than a 0.4 nozzle, with files half the size of 0.01.
LINEAR_TOL_MM = 0.02
ANGULAR_TOL_RAD = 0.1


def export_all(
    shape: Shape,
    out_dir: Path,
    name: str,
    formats: tuple[str, ...] = DEFAULT_FORMATS,
) -> dict[str, Path]:
    """Writes out_dir/name.<ext>, returns {format: path}. The mesh is tessellated once for STL and 3MF."""
    unknown = set(formats) - set(DEFAULT_FORMATS)
    if unknown:
        raise ValueError(f"unknown format: {', '.join(sorted(unknown))}")
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    if "step" in formats:
        path = out_dir / f"{name}.step"
        export_step(shape, path)
        written["step"] = path
    if "stl" in formats or "3mf" in formats:
        # OCCT writes the STL itself (fast); the 3MF is made from that same STL so the meshes match.
        stl = out_dir / f"{name}.stl"
        export_stl(shape, stl, tolerance=LINEAR_TOL_MM, angular_tolerance=ANGULAR_TOL_RAD)
        mesh = trimesh.load(stl, force="mesh")
        if drop_degenerate(mesh):
            mesh.export(stl, file_type="stl")
        if "3mf" in formats:
            written |= export_mesh(mesh, out_dir, name, ("3mf",))
        if "stl" in formats:
            written["stl"] = stl
        else:
            stl.unlink()
    return {fmt: written[fmt] for fmt in formats}


def drop_degenerate(mesh: trimesh.Trimesh) -> bool:
    """OCCT tessellates sphere poles and roundings with zero-area triangles: drop them in place.

    Otherwise the mesh looks open and falls apart into "bodies". True if anything was dropped.
    """
    keep = mesh.nondegenerate_faces()
    if keep.all():
        return False
    mesh.update_faces(keep)
    mesh.remove_unreferenced_vertices()
    return True


def export_mesh(
    mesh: trimesh.Trimesh,
    out_dir: Path,
    name: str,
    formats: tuple[str, ...] = MESH_FORMATS,
) -> dict[str, Path]:
    """The same for a finished mesh (STL remixes). STEP is skipped: it can't be made from a mesh."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for fmt in formats:
        if fmt == "step":
            continue
        if fmt not in MESH_FORMATS:
            raise ValueError(f"unknown format: {fmt}")
        path = out_dir / f"{name}.{fmt}"
        if fmt == "3mf":
            write_3mf(mesh, path, name)
        else:
            mesh.export(path, file_type=fmt)
        written[fmt] = path
    return written


_3MF_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
    "</Types>"
)
_3MF_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    "</Relationships>"
)


def write_3mf(mesh: trimesh.Trimesh, path: Path, name: str) -> None:
    """3MF to the core specification only (core 2015/02), with no extensions.

    trimesh writes 3MF with the production extension (p:UUID): Bambu Studio takes such a file
    for one of its projects, looks for settings in it and complains "invalid config". A plain core 3MF
    opens as ordinary geometry.
    """
    import zipfile
    from xml.sax.saxutils import quoteattr

    head = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        '<metadata name="Application">cad-workshop</metadata>'
        f'<resources><object id="1" name={quoteattr(name)} type="model"><mesh><vertices>'
    )
    tail = '</triangles></mesh></object></resources><build><item objectid="1"/></build></model>'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _3MF_CONTENT_TYPES)
        z.writestr("_rels/.rels", _3MF_RELS)
        # Written in chunks: one string for a million-triangle model would take hundreds of MB.
        with z.open("3D/3dmodel.model", "w", force_zip64=True) as out:
            out.write(head.encode())
            _write_mesh_body(out, mesh)
            out.write(tail.encode())


def _write_mesh_body(out, mesh: trimesh.Trimesh) -> None:
    """Vertices, then "</vertices><triangles>", then triangles: the inside of <mesh><vertices>…</triangles>."""
    for chunk in _chunks(mesh.vertices):
        out.write("".join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in chunk).encode())
    out.write(b"</vertices><triangles>")
    for chunk in _chunks(mesh.faces):
        out.write("".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in chunk).encode())


# --- a set of parts in one 3MF, plate by plate --------------------------------------------------

# Bambu Studio lays its plates out in a grid of ceil(√n) columns, each plate the bed's size plus a fifth of it as a gap
# (LOGICAL_PART_PLATE_GAP in its source); objects placed inside a plate's square belong to that plate.
BAMBU_PLATE_GAP = 1 / 5
PART_GAP_MM = 10          # between parts sharing a plate


def plate_origin(index: int, count: int, bed_xy: tuple[float, float]) -> tuple[float, float]:
    """Front-left corner of plate `index` (0-based) of `count` in Bambu Studio's scene."""
    cols = math.isqrt(count)
    if cols * cols < count:
        cols += 1
    row, col = divmod(index, cols)
    return col * bed_xy[0] * (1 + BAMBU_PLATE_GAP), -row * bed_xy[1] * (1 + BAMBU_PLATE_GAP)


def layout_plate(meshes: list[trimesh.Trimesh], bed_xy: tuple[float, float], margin: float) -> list[tuple[float, float]]:
    """Centres (XY, on the bed) for meshes sharing a plate: rows left to right, the block centred on the bed.
    Raises ValueError when they don't fit inside the bed minus `margin` on each side."""
    usable_x, usable_y = bed_xy[0] - 2 * margin, bed_xy[1] - 2 * margin
    rows: list[list[int]] = [[]]
    width = 0.0
    for i, m in enumerate(meshes):
        w = m.extents[0]
        if rows[-1] and width + PART_GAP_MM + w > usable_x:
            rows.append([])
            width = 0.0
        width += (PART_GAP_MM if rows[-1] else 0) + w
        rows[-1].append(i)
    row_w = [sum(meshes[i].extents[0] for i in r) + PART_GAP_MM * (len(r) - 1) for r in rows]
    row_h = [max(meshes[i].extents[1] for i in r) for r in rows]
    total_h = sum(row_h) + PART_GAP_MM * (len(rows) - 1)
    if max(row_w) > usable_x or total_h > usable_y:
        raise ValueError(f"{max(row_w):.0f} × {total_h:.0f} mm of parts on a {usable_x:.0f} × {usable_y:.0f} mm plate")
    centres: list[tuple[float, float]] = [(0.0, 0.0)] * len(meshes)
    y = (bed_xy[1] + total_h) / 2
    for r, w, h in zip(rows, row_w, row_h):
        x = (bed_xy[0] - w) / 2
        for i in r:
            centres[i] = (x + meshes[i].extents[0] / 2, y - h / 2)
            x += meshes[i].extents[0] + PART_GAP_MM
        y -= h + PART_GAP_MM
    return centres


def write_plates_3mf(
    plates: list[list[tuple[str, trimesh.Trimesh]]],
    path: Path,
    bed_xy: tuple[float, float],
    margin: float,
) -> list[list[tuple[float, float]]]:
    """One 3MF with every part as its own object, plate by plate, for Bambu Studio.

    plates: per plate, (name, mesh) pairs, each mesh already turned as printed (its bottom is placed on the bed).
    The file stays core 3MF (no production extension, no Bambu project settings, so Bambu Studio opens it as
    geometry with your current printer and plastic); Metadata/model_settings.config adds the plates, and every
    object stands inside its plate's square. Returns the centres used, per plate, in the plate's own coordinates.
    """
    import zipfile
    from xml.sax.saxutils import quoteattr

    if not plates or not all(plates):
        raise ValueError("every plate needs at least one part")
    layouts = []
    for n, plate in enumerate(plates, 1):
        try:
            layouts.append(layout_plate([m for _, m in plate], bed_xy, margin))
        except ValueError as e:
            raise ValueError(f"plate {n} ({', '.join(name for name, _ in plate)}): {e}") from e

    head = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
        '<metadata name="Application">cad-workshop</metadata><resources>'
    )
    items, cfg_objects, cfg_plates = [], [], []
    oid = 0
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _3MF_CONTENT_TYPES)
        z.writestr("_rels/.rels", _3MF_RELS)
        with z.open("3D/3dmodel.model", "w", force_zip64=True) as out:
            out.write(head.encode())
            for n, (plate, centres) in enumerate(zip(plates, layouts)):
                ox, oy = plate_origin(n, len(plates), bed_xy)
                instances = []
                for (name, mesh), (cx, cy) in zip(plate, centres):
                    oid += 1
                    local = mesh.copy()
                    lo, hi = local.bounds
                    local.apply_translation((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
                    out.write(f'<object id="{oid}" name={quoteattr(name)} type="model"><mesh><vertices>'.encode())
                    _write_mesh_body(out, local)
                    out.write(b"</triangles></mesh></object>")
                    items.append(f'<item objectid="{oid}" transform="1 0 0 0 1 0 0 0 1 '
                                 f'{ox + cx:.4f} {oy + cy:.4f} 0" printable="1"/>')
                    cfg_objects.append(
                        f'<object id="{oid}"><metadata key="name" value={quoteattr(name)}/>'
                        f'<metadata key="extruder" value="1"/><part id="{oid}" subtype="normal_part">'
                        f'<metadata key="name" value={quoteattr(name)}/>'
                        '<metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/></part></object>')
                    instances.append(f'<model_instance><metadata key="object_id" value="{oid}"/>'
                                     f'<metadata key="instance_id" value="0"/>'
                                     f'<metadata key="identify_id" value="{oid}"/></model_instance>')
                cfg_plates.append(f'<plate><metadata key="plater_id" value="{n + 1}"/><metadata key="plater_name" value=""/>'
                                  f'<metadata key="locked" value="false"/>{"".join(instances)}</plate>')
            out.write(f'</resources><build>{"".join(items)}</build></model>'.encode())
        z.writestr("Metadata/model_settings.config",
                   f'<?xml version="1.0" encoding="UTF-8"?>\n<config>{"".join(cfg_objects)}{"".join(cfg_plates)}</config>')
    return layouts


_3MF_CHUNK_ROWS = 50_000


def _chunks(rows):
    for start in range(0, len(rows), _3MF_CHUNK_ROWS):
        yield rows[start:start + _3MF_CHUNK_ROWS]


def shape_to_mesh(shape: Shape) -> trimesh.Trimesh:
    """Tessellate B-rep into trimesh at export precision (through a temporary STL: faster than through Python)."""
    with tempfile.TemporaryDirectory() as tmp:
        stl = Path(tmp) / "shape.stl"
        export_stl(shape, stl, tolerance=LINEAR_TOL_MM, angular_tolerance=ANGULAR_TOL_RAD)
        mesh = trimesh.load(stl, force="mesh", process=True)
    drop_degenerate(mesh)
    return mesh
