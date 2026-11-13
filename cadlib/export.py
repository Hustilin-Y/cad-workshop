"""Export a build123d solid or a finished mesh to STEP/STL/3MF in one call."""

from __future__ import annotations

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
            for chunk in _chunks(mesh.vertices):
                out.write("".join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in chunk).encode())
            out.write(b"</vertices><triangles>")
            for chunk in _chunks(mesh.faces):
                out.write("".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in chunk).encode())
            out.write(tail.encode())


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
