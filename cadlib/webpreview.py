"""The light 3D preview the Mini App's Print tab turns with a finger: `out/<name>.preview.bin`.

Written at build time from the mesh the build already holds, so nothing is converted later on
the small server. Format v1, little endian:

    b"CWPV", u16 version = 1, u16 flags = 0, f32 bbox[6] (min xyz, max xyz, mm), u32 groups
    per group: u8 rgba[4], u16 plate (0: not a kit plate), u16 reserved = 0,
               u32 vertices, u32 indices,
               u16 positions[3 * vertices] (quantized over the file's bbox), padding to 4 bytes,
               indices as u16 when vertices <= 65535, else u32, padding to 4 bytes

Z is up and the mesh lies as in the 3MF. Normals are computed by the viewer.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

MAGIC = b"CWPV"
VERSION = 1
MAX_TRIANGLES = 60_000
MIN_GROUP_TRIANGLES = 12
DECIMATE_TRIES = 3
DEFAULT_RGBA = (200, 200, 200, 255)
_HEADER = struct.Struct("<4sHH6fI")
_GROUP = struct.Struct("<4BHHII")
_QUANT = 65535


@dataclass(frozen=True)
class PreviewInfo:
    triangles: int
    bytes: int


def write_preview(groups, path, max_triangles: int = MAX_TRIANGLES) -> PreviewInfo:
    """Write groups [(mesh, rgba or None, plate)] as a preview at path, decimated to max_triangles in all."""
    meshes = [(_clean(mesh), tuple(rgba) if rgba else DEFAULT_RGBA, int(plate)) for mesh, rgba, plate in groups]
    meshes = [(m, rgba, plate) for m, rgba, plate in meshes if len(m.faces)]
    if not meshes:
        raise ValueError("no faces to preview")
    total = sum(len(m.faces) for m, _, _ in meshes)
    reduced = []
    for mesh, rgba, plate in meshes:
        share = max(MIN_GROUP_TRIANGLES, int(max_triangles * len(mesh.faces) / total))
        reduced.append((_decimate(mesh, share), rgba, plate))
    # The bbox of the meshes as built (AC3.1: within 0.1 mm), not of the decimated ones.
    lo = np.min([m.vertices.min(axis=0) for m, _, _ in meshes], axis=0)
    hi = np.max([m.vertices.max(axis=0) for m, _, _ in meshes], axis=0)
    span = np.where(hi - lo > 0, hi - lo, 1.0)
    out = bytearray(_HEADER.pack(MAGIC, VERSION, 0, *lo.tolist(), *hi.tolist(), len(reduced)))
    triangles = 0
    for mesh, rgba, plate in reduced:
        vertices = np.round((mesh.vertices - lo) / span * _QUANT).clip(0, _QUANT).astype("<u2")
        faces = mesh.faces.astype("<u2" if len(vertices) <= 0xFFFF else "<u4")
        out += _GROUP.pack(*rgba, plate, 0, len(vertices), faces.size)
        out += vertices.tobytes()
        out += b"\0" * (-len(out) % 4)
        out += faces.tobytes()
        out += b"\0" * (-len(out) % 4)
        triangles += len(mesh.faces)
    Path(path).write_bytes(bytes(out))
    return PreviewInfo(triangles, len(out))


def read_preview(path) -> dict:
    """{"bbox": array(6), "groups": [{"rgba", "plate", "vertices" (mm, float), "faces"}]}; ValueError on a bad file."""
    raw = Path(path).read_bytes()
    if len(raw) < _HEADER.size:
        raise ValueError("preview too short")
    magic, version, _flags, *rest = _HEADER.unpack_from(raw, 0)
    if magic != MAGIC:
        raise ValueError("not a preview file")
    if version != VERSION:
        raise ValueError(f"preview version {version}, expected {VERSION}")
    bbox, count = np.array(rest[:6], dtype=float), rest[6]
    lo, span = bbox[:3], np.where(bbox[3:] - bbox[:3] > 0, bbox[3:] - bbox[:3], 1.0)
    offset, groups = _HEADER.size, []
    for _ in range(count):
        if offset + _GROUP.size > len(raw):
            raise ValueError("preview cut short")
        r, g, b, a, plate, _reserved, nverts, nidx = _GROUP.unpack_from(raw, offset)
        offset += _GROUP.size
        vbytes = nverts * 6
        isize = 2 if nverts <= 0xFFFF else 4
        end_v = offset + vbytes
        end_i = end_v + (-end_v % 4) + nidx * isize
        if end_i > len(raw) or nidx % 3:
            raise ValueError("preview cut short")
        q = np.frombuffer(raw, dtype="<u2", count=nverts * 3, offset=offset).reshape(-1, 3)
        start_i = end_v + (-end_v % 4)
        idx = np.frombuffer(raw, dtype="<u2" if isize == 2 else "<u4", count=nidx, offset=start_i).astype(np.int64)
        if len(idx) and idx.max() >= nverts:
            raise ValueError("preview index out of range")
        groups.append({"rgba": (r, g, b, a), "plate": plate,
                       "vertices": lo + q.astype(float) / _QUANT * span, "faces": idx.reshape(-1, 3)})
        offset = end_i + (-end_i % 4)
    return {"bbox": bbox, "groups": groups}


def _clean(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """An indexed mesh to decimate. One that already shares its vertices (a build's mesh, a 3MF's)
    is used as it is, with no copy: only a triangle soup (as an STL loads without processing) is
    copied and merged, which costs memory in proportion to its size."""
    if len(mesh.vertices) <= len(mesh.faces):
        return mesh
    mesh = mesh.copy()
    mesh.merge_vertices()
    return mesh


def _decimate(mesh: trimesh.Trimesh, target: int) -> trimesh.Trimesh:
    """At most target faces: quadric decimation (fast-simplification), at most DECIMATE_TRIES passes,
    then vertex clustering for what it couldn't reduce (it stalls on some downloaded meshes, such as
    a 1.29M-face remix that stopped at 224k)."""
    if len(mesh.faces) <= target:
        return mesh
    import fast_simplification

    points, faces = mesh.vertices.astype(np.float32), mesh.faces.astype(np.int64)
    for _ in range(DECIMATE_TRIES):
        reduction = 1.0 - target / len(faces) * (0.98 if len(faces) < len(mesh.faces) else 1.0)
        before = len(faces)
        points, faces = fast_simplification.simplify(points, faces, target_reduction=reduction)
        points, faces = np.asarray(points, dtype=np.float32), np.asarray(faces, dtype=np.int64)
        if len(faces) <= target or len(faces) > before * 0.95:  # done, or it stopped reducing
            break
    if len(faces) > target:
        points, faces = _cluster(points, faces, target)
    return trimesh.Trimesh(points, faces, process=False)


def _cluster(points: np.ndarray, faces: np.ndarray, target: int) -> tuple[np.ndarray, np.ndarray]:
    """Vertex clustering on a grid, the cell grown until at most target faces are left: each cell's
    vertices merge into their mean, faces that collapse go. Coarse, but it always ends."""
    lo = points.min(axis=0)
    span = float(np.max(points.max(axis=0) - lo)) or 1.0
    cells = max(16, int(np.sqrt(target) * 2))
    while True:
        cell = span / cells
        keys = np.floor((points - lo) / cell).astype(np.int64)
        _, inverse = np.unique(keys, axis=0, return_inverse=True)
        inverse = inverse.reshape(-1)
        merged = inverse[faces]
        keep = (merged[:, 0] != merged[:, 1]) & (merged[:, 1] != merged[:, 2]) & (merged[:, 0] != merged[:, 2])
        merged = merged[keep]
        if len(merged) <= target or cells <= 16:
            count = inverse.max() + 1
            sums = np.zeros((count, 3))
            np.add.at(sums, inverse, points)
            centres = sums / np.bincount(inverse, minlength=count)[:, None]
            used, remap = np.unique(merged, return_inverse=True)
            return centres[used].astype(np.float32), remap.reshape(-1, 3)
        cells = int(cells * 0.8)
