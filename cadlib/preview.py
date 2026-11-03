"""PNG-превью сетки: изометрия + три проекции. Без GPU и без GUI (backend Agg)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import trimesh  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

# (заголовок, elev, azim, ось глубины): изометрия и три ортогональные проекции.
# Ось, направленную на зрителя, на проекциях прячем: её подписи сливаются в кашу.
VIEWS = (
    ("Изометрия", 30, -60, None),
    ("Сверху (XY)", 90, -90, "z"),
    ("Спереди (XZ)", 0, -90, "y"),
    ("Справа (YZ)", 0, 0, "x"),
)
BASE_COLOR = np.array([0.35, 0.55, 0.85])
LIGHT_DIR = np.array([0.4, -0.6, 0.7]) / np.linalg.norm([0.4, -0.6, 0.7])
MAX_FACES = 60_000


def render_preview(mesh: trimesh.Trimesh, path: Path, title: str = "") -> Path:
    if len(mesh.faces) > MAX_FACES:
        mesh = mesh.simplify_quadric_decimation(face_count=MAX_FACES)
    tris = mesh.triangles
    shade = 0.35 + 0.65 * np.clip(mesh.face_normals @ LIGHT_DIR, 0, 1)
    colors = np.clip(BASE_COLOR[None, :] * shade[:, None], 0, 1)

    lo, hi = mesh.bounds
    center = (lo + hi) / 2
    half = max(hi - lo) / 2 * 1.05
    size = hi - lo

    fig = plt.figure(figsize=(10, 10), dpi=110)
    for i, (name, elev, azim, depth_axis) in enumerate(VIEWS, start=1):
        ax = fig.add_subplot(2, 2, i, projection="3d")
        # Рёбра того же цвета, что и грани, иначе видны швы между треугольниками.
        ax.add_collection3d(Poly3DCollection(tris, facecolors=colors, edgecolors=colors, linewidths=0.3))
        for setter, c in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), center):
            setter(c - half, c + half)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=elev, azim=azim)
        ax.set_title(name)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Z")
        ax.tick_params(labelsize=7)
        if depth_axis:
            ax.set_proj_type("ortho")
            getattr(ax, f"set_{depth_axis}ticks")([])
            getattr(ax, f"set_{depth_axis}label")("")
    fig.suptitle(f"{title}  {size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f} мм".strip())
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path
