"""Trace the logo layers from the "relief" picture (assets/logo/shiba-styles-front.webp) → cadlib/logo_shiba.json.

Run: uv run python tools/logo_extract.py [--debug folder]

How it works:
1. The picture's left panel is classified by the nearest palette colour: background, ginger, white,
   dark, red, pink.
2. The masks make up the layers: silhouette, bow, knot, muzzle mask, eyes, nose, mouth, tongue.
3. Each layer is made symmetric (averaged with its mirror about the muzzle's axis) and smoothed.
4. The contours are simplified and saved in normalised coordinates: logo height = 1,
   the bounds' centre at (0, 0), Y up.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from scipy import ndimage as nd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "logo" / "shiba-styles-front.webp"
OUT = ROOT / "cadlib" / "logo_shiba.json"
PANEL = (30, 40, 500, 600)       # the left "relief" panel, px
PALETTE = {
    "bg": (145, 145, 145), "tan": (192, 160, 115), "white": (212, 208, 195),
    "dark": (55, 50, 42), "red": (145, 65, 42), "pink": (182, 112, 112),
}
SMOOTH_PX = 3.5                  # mask smoothing (Gaussian sigma), px: removes the ripple from the render's shading
SIMPLIFY_PX = 0.7                # contour simplification, px


def classify(im: np.ndarray) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """(denoised masks, raw masks): fine details such as the corners of the smile exist only in the raw ones."""
    names = list(PALETTE)
    centers = np.array([PALETTE[n] for n in names], float)
    cls = (((im[..., None, :] - centers) ** 2).sum(-1)).argmin(-1)
    raw = {n: cls == i for i, n in enumerate(names)}
    return {n: nd.binary_opening(v) for n, v in raw.items()}, raw


def largest(mask: np.ndarray, count: int = 1) -> np.ndarray:
    lab, k = nd.label(mask)
    if k == 0:
        return mask
    sizes = nd.sum(mask, lab, range(1, k + 1))
    keep = np.argsort(sizes)[::-1][:count] + 1
    return np.isin(lab, keep)


def symmetrize(mask: np.ndarray, axis_x: float) -> np.ndarray:
    """Average of the mask and its mirror about the vertical x = axis_x, then smoothing."""
    h, w = mask.shape
    xs = np.arange(w)
    src = np.clip(np.round(2 * axis_x - xs).astype(int), 0, w - 1)
    m = mask.astype(float)
    sym = (m + m[:, src]) / 2
    return nd.gaussian_filter(sym, SMOOTH_PX)


def rdp(p: np.ndarray, eps: float) -> np.ndarray:
    if len(p) < 3:
        return p
    a, b = p[0], p[-1]
    ab = b - a
    length = np.hypot(*ab)
    v = p - a
    d = np.abs(ab[0] * v[:, 1] - ab[1] * v[:, 0]) / length if length > 0 else np.hypot(v[:, 0], v[:, 1])
    i = int(np.argmax(d))
    if d[i] > eps:
        return np.vstack([rdp(p[: i + 1], eps)[:-1], rdp(p[i:], eps)])
    return np.array([a, b])


def contours(field: np.ndarray) -> list[np.ndarray]:
    """Closed 0.5-level contours of the smoothed mask (x, y in px)."""
    fig = plt.figure()
    cs = plt.contour(field, [0.5])
    loops = [np.array(seg) for seg in cs.allsegs[0] if len(seg) > 8]
    plt.close(fig)
    return [rdp(np.vstack([l, l[:1]]), SIMPLIFY_PX)[:-1] for l in loops]


def extract(debug: Path | None = None) -> dict:
    im = np.asarray(Image.open(SOURCE).convert("RGB").crop(PANEL)).astype(float)
    m, raw = classify(im)
    h, w = im.shape[:2]
    yy = np.arange(h)[:, None] * np.ones((1, w))

    fg = largest(nd.binary_fill_holes(nd.binary_closing(~m["bg"], iterations=2)))
    white = largest(nd.binary_fill_holes(m["white"]))
    # The axis follows the silhouette's bounds: the muzzle mask in the picture is slightly asymmetric.
    cols = np.argwhere(fg)[:, 1]
    axis_x = float((cols.min() + cols.max()) / 2)

    red = m["red"]
    bow_top = np.argwhere(largest(red, 3))[:, 0].min() - 12
    bow = nd.binary_fill_holes(nd.binary_closing((red | m["dark"]) & (yy > bow_top), iterations=3)) & fg
    bow = largest(bow)
    knot = largest(red & (np.abs(np.arange(w)[None, :] - axis_x) < 40) & bow)
    knot = nd.binary_fill_holes(knot)

    face_dark = m["dark"] & (yy < bow_top) & white_or_near(white)
    white_cx = float(np.argwhere(white)[:, 1].mean())
    nose = largest(face_dark & near_axis(w, h, white_cx, 60) & (yy < np.argwhere(white)[:, 0].mean()))
    # The mouth comes from the raw mask: denoising eats the thin corners of the smile.
    raw_dark = raw["dark"] & (yy < bow_top) & white_or_near(white)
    below_nose = yy > np.argwhere(nose)[:, 0].max() + 5
    mouth = largest(nd.binary_fill_holes(nd.binary_closing((raw_dark | raw["pink"]) & below_nose, iterations=2)))
    # The tongue is split by a dark groove: close it first, then fill.
    tongue = largest(nd.binary_fill_holes(nd.binary_closing(m["pink"], iterations=5)) & mouth)
    eyes = largest(m["dark"] & ~white & (yy < np.argwhere(nose)[:, 0].min()) & (yy > np.argwhere(white)[:, 0].min() - 30), 2)

    # Each group of layers has its own axis: the render shows the relief's side wall on the right,
    # so the silhouette's centre is shifted from the muzzle's. Each group is mirrored about its own axis,
    # and in the data all axes are aligned at x = 0.
    face_axis = float(np.argwhere(nose)[:, 1].mean())
    bow_cols = np.argwhere(bow)[:, 1]
    bow_axis = float((bow_cols.min() + bow_cols.max()) / 2)
    axes = {"silhouette": axis_x, "bow": bow_axis, "knot": bow_axis, "mask": face_axis, "eyes": face_axis,
            "nose": face_axis, "mouth": face_axis, "tongue": face_axis}
    masks = {"silhouette": fg, "bow": bow, "knot": knot, "mask": white, "eyes": eyes, "nose": nose,
             "mouth": mouth, "tongue": tongue}
    layers = {name: symmetrize(masks[name], axes[name]) for name in masks}
    sil = np.argwhere(layers["silhouette"] > 0.5)
    y0, y1 = sil[:, 0].min(), sil[:, 0].max()
    scale = 1.0 / (y1 - y0)
    yc = (y0 + y1) / 2

    data = {"source": SOURCE.name, "panel_px": PANEL, "height_px": int(y1 - y0), "layers": {}}
    for name, field in layers.items():
        loops = contours(field)
        data["layers"][name] = [[[round((x - axes[name]) * scale, 5), round((yc - y) * scale, 5)] for x, y in loop]
                                for loop in loops]
    if debug:
        debug.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(6, 7), dpi=110)
        ax.imshow(im.astype(np.uint8))
        colors = {"silhouette": "r", "bow": "orange", "knot": "y", "mask": "c", "eyes": "m", "nose": "lime",
                  "mouth": "b", "tongue": "pink"}
        for name, field in layers.items():   # in picture coordinates, shifted to the silhouette's common axis
            for loop in contours(field):
                loop = loop + [axis_x - axes[name], 0]
                ax.plot(*np.vstack([loop, loop[:1]]).T, color=colors[name], lw=1.4)
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(debug / "layers_overlay.png")
        plt.close(fig)
    return data


def white_or_near(white: np.ndarray) -> np.ndarray:
    """The area of the muzzle mask with a margin: the dark features lie on it or at its edge."""
    return nd.binary_dilation(white, iterations=6)


def near_axis(w: int, h: int, axis_x: float, half: float) -> np.ndarray:
    return np.abs(np.arange(w)[None, :] - axis_x) * np.ones((h, 1)) < half


if __name__ == "__main__":
    dbg = Path(sys.argv[sys.argv.index("--debug") + 1]) if "--debug" in sys.argv else None
    result = extract(dbg)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print({k: len(v) for k, v in result["layers"].items()}, "→", OUT)
