"""PNG-превью сетки: изометрия + три проекции и, по желанию, разрез. Без GPU и без GUI (backend Agg).

Виды рисуются в 2D: треугольники проецируются на плоскость экрана, задние грани отбрасываются,
остальные рисуются от дальних к ближним. Это быстрее и честнее по масштабу, чем mplot3d.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402

AXES = {"x": 0, "y": 1, "z": 2}
BASE_COLOR = np.array([0.35, 0.55, 0.85])
SECTION_COLOR = "#d9534f"
LIGHT_DIR = np.array([0.4, -0.6, 0.7]) / np.linalg.norm([0.4, -0.6, 0.7])
EDGE_COLOR = np.array([0.08, 0.12, 0.22, 1.0])
EDGE_WIDTH = 0.5
FEATURE_DEG = 30.0  # рёбра острее этого угла рисуются линией
PREVIEW_MAX_FACES = 150_000  # выше этого виды рисуются по упрощённой сетке (на PNG разницы не видно)


def _iso_basis() -> np.ndarray:
    """Строки: вправо, вверх, к зрителю. Изометрия с камерой спереди-справа-сверху."""
    toward = np.array([1.0, -1.0, 1.0]) / np.sqrt(3)
    right = np.array([1.0, 1.0, 0.0]) / np.sqrt(2)
    up = np.cross(toward, right)
    return np.array([right, up, toward])


# (заголовок, базис экрана, подписи осей или None для изометрии)
VIEWS = (
    ("Изометрия", _iso_basis(), None),
    ("Сверху (XY)", np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], float), ("X", "Y")),
    ("Спереди (XZ)", np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float), ("X", "Z")),
    ("Справа (YZ)", np.array([[0, 1, 0], [0, 0, 1], [1, 0, 0]], float), ("Y", "Z")),
)


def render_preview(
    mesh: trimesh.Trimesh,
    path: Path,
    title: str = "",
    section: str | tuple[str, float] | None = None,
) -> Path:
    """section: 'x' | 'y' | 'z' — разрез перпендикулярно оси через центр, или ('y', 28.0) — на заданной координате."""
    section_at = None
    if isinstance(section, (tuple, list)):
        section, section_at = section[0], float(section[1])
    size = mesh.extents
    shown = _for_drawing(mesh)

    ncols = 3 if section else 2
    fig, axes = plt.subplots(2, ncols, figsize=(5.5 * ncols, 10), dpi=100)
    slots = [axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]]
    for ax, view in zip(slots, VIEWS):
        _draw_view(ax, shown, *view)
    if section:
        _draw_section(axes[0, 2], mesh, section, section_at)
        axes[1, 2].axis("off")

    fig.suptitle(f"{title}  {size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f} мм".strip())
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def _for_drawing(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Упрощённая копия для видов, если треугольников больше PREVIEW_MAX_FACES.

    Каждый треугольник вида — объект matplotlib: сетка в 330 тыс. граней занимала ~1 ГБ памяти,
    скачанная модель на миллион с лишним не влезла бы в небольшой сервер. Разрез, размеры
    и проверки считаются по исходной сетке.
    """
    if len(mesh.faces) <= PREVIEW_MAX_FACES:
        return mesh
    return mesh.simplify_quadric_decimation(face_count=PREVIEW_MAX_FACES)


def _draw_view(ax, mesh: trimesh.Trimesh, name: str, basis: np.ndarray, labels: tuple[str, str] | None) -> None:
    toward = basis[2]
    facing = mesh.face_normals @ toward
    visible = facing > 1e-6

    # Грани: экранные x, y и глубина; свет от источника плюс подсветка «к зрителю».
    tris = mesh.triangles[visible] @ basis.T
    light = 0.6 * np.clip(mesh.face_normals[visible] @ LIGHT_DIR, 0, 1) + 0.4 * facing[visible]
    face_colors = np.clip(BASE_COLOR[None, :] * (0.35 + 0.65 * light)[:, None], 0, 1)
    face_rgba = np.hstack([face_colors, np.ones((len(face_colors), 1))])

    # Контурные рёбра: острые (> FEATURE_DEG) рядом с видимой гранью и силуэт (видимая | невидимая).
    pairs = mesh.face_adjacency
    vis_a, vis_b = visible[pairs[:, 0]], visible[pairs[:, 1]]
    sharp = mesh.face_adjacency_angles > np.radians(FEATURE_DEG)
    edge_mask = (sharp & (vis_a | vis_b)) | (vis_a != vis_b)
    segs = mesh.vertices[mesh.face_adjacency_edges[edge_mask]] @ basis.T

    # Грани и рёбра в одной очереди от дальних к ближним; ребро чуть «ближе» своих граней, чтобы лечь поверх.
    depth = np.concatenate([tris[:, :, 2].mean(axis=1), segs[:, :, 2].max(axis=1) + 1e-3])
    polys = [t[:, :2] for t in tris] + [s[:, :2] for s in segs]
    edge_rgba = np.tile(EDGE_COLOR, (len(segs), 1))
    fill = np.vstack([face_rgba, np.zeros((len(segs), 4))])
    stroke = np.vstack([face_rgba, edge_rgba])           # у граней обводка в цвет грани, иначе видны швы
    widths = np.concatenate([np.full(len(tris), 0.3), np.full(len(segs), EDGE_WIDTH)])
    # Сглаживание только у рёбер: у граней оно даёт светлые щели между соседними треугольниками.
    antialiased = np.concatenate([np.zeros(len(tris), bool), np.ones(len(segs), bool)])
    order = np.argsort(depth, kind="stable")
    ax.add_collection(PolyCollection(
        [polys[i] for i in order], facecolors=fill[order], edgecolors=stroke[order], linewidths=widths[order],
        antialiaseds=antialiased[order], closed=False,
    ))

    pts = tris[:, :, :2].reshape(-1, 2)
    if len(pts):
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        pad = max(hi - lo) * 0.04 + 0.5
        ax.set_xlim(lo[0] - pad, hi[0] + pad)
        ax.set_ylim(lo[1] - pad, hi[1] + pad)
    ax.set_aspect("equal")
    ax.set_title(name)
    if labels is None:
        ax.axis("off")
    else:
        ax.set_xlabel(f"{labels[0]}, мм")
        ax.set_ylabel(f"{labels[1]}, мм")
        ax.grid(True, linewidth=0.3)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=8)


def section_loops(mesh: trimesh.Trimesh, axis: str, at: float | None = None) -> list[np.ndarray]:
    """Замкнутые контуры сечения в плоских координатах (две оставшиеся оси, мм)."""
    i = AXES[axis]
    normal = np.eye(3)[i]
    origin = mesh.bounds.mean(axis=0)
    if at is not None:
        origin[i] = at
    path3d = mesh.section(plane_normal=normal, plane_origin=origin)
    if path3d is None:
        return []
    keep = [j for j in range(3) if j != i]
    return [loop[:, keep] for loop in path3d.discrete if len(loop) >= 3]


def _draw_section(ax, mesh: trimesh.Trimesh, axis: str, at: float | None) -> None:
    loops = section_loops(mesh, axis, at)
    labels = {"x": ("Y", "Z"), "y": ("X", "Z"), "z": ("X", "Y")}[axis]
    pos = at if at is not None else mesh.bounds.mean(axis=0)[AXES[axis]]
    ax.set_title(f"Разрез {axis.upper()} = {pos:.1f} мм")
    ax.set_xlabel(f"{labels[0]}, мм")
    ax.set_ylabel(f"{labels[1]}, мм")
    ax.set_aspect("equal")
    ax.grid(True, linewidth=0.3)
    ax.tick_params(labelsize=8)
    if not loops:
        ax.text(0.5, 0.5, "плоскость не пересекает модель", ha="center", transform=ax.transAxes)
        return
    patch = PathPatch(_compound_path(loops), facecolor=SECTION_COLOR, edgecolor="black", linewidth=0.6)
    ax.add_patch(patch)
    pts = np.vstack(loops)
    pad = max(np.ptp(pts, axis=0)) * 0.05 + 1
    ax.set_xlim(pts[:, 0].min() - pad, pts[:, 0].max() + pad)
    ax.set_ylim(pts[:, 1].min() - pad, pts[:, 1].max() + pad)


def _compound_path(loops: list[np.ndarray]) -> MplPath:
    """Контуры в один путь: внешние против часовой, дырки по часовой, чтобы заливка не закрывала дыры."""
    paths = [MplPath(loop) for loop in loops]
    verts, codes = [], []
    for k, loop in enumerate(loops):
        depth = sum(1 for j, p in enumerate(paths) if j != k and p.contains_point(loop[0]))
        ccw = _signed_area(loop) > 0
        if ccw != (depth % 2 == 0):
            loop = loop[::-1]
        verts.extend(loop)
        codes.extend([MplPath.MOVETO] + [MplPath.LINETO] * (len(loop) - 1))
    return MplPath(np.array(verts), codes)


def _signed_area(loop: np.ndarray) -> float:
    x, y = loop[:, 0], loop[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
