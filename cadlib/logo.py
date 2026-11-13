"""The workshop's logo: a cartoon shiba inu with a bow tie, in "relief" and "outline" styles.

The logo itself (the picture and its contours) belongs to the workshop's owner: it is not in the
repository and not under the MIT licence. Without the logo data this code builds parts without it.

The layer contours were traced from the owner's picture (assets/logo/shiba-styles-front.webp) by
tools/logo_extract.py and live in logo_shiba.json next to this file: logo height = 1, centre
(0, 0), Y up. Layers: silhouette (head + bow), mask (the white muzzle), eyes, nose, mouth, tongue,
bow, knot. On top of the picture, at the owner's request: bigger eyes (EYE_SCALE) and the shiba's
dot eyebrows (brows, BROW_*).

Styles (both flat by layers: they read from about 15 mm and suit multi-colour printing):
  logo_relief()  — relief: a base in the silhouette, a rim along the head's outline, the mask
                   higher, eyes and nose above the mask, the mouth sunk, the tongue inside it,
                   the bow with a rim;
  logo_outline() — outline: walls along the borders of the zones, eyes and nose filled.
Plus logo_svg() — a flat colour version for stickers, render_colors() — a colour preview.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import manifold3d as mf
import numpy as np

DATA = Path(__file__).with_name("logo_shiba.json")
SEGMENTS = 32
SIMPLIFY_MM = 0.04      # contour precision: anything finer doesn't exist for a 0.4 nozzle
# Defaults without a profile: nozzle 0.4, layer 0.2. With a profile (place_logo(..., p=p)) everything
# below is derived from its nozzle and layer, so the logo's walls stay printable with a 0.6–0.8 nozzle.
NOZZLE_DEFAULT = 0.4
LAYER_DEFAULT = 0.2
MIN_LINE_LINES = 2      # rims, walls and the margin to an edge: no thinner than 2 nozzle lines
BASE_LAYERS = 4         # the relief's base: 4 layers
STEP_LAYERS = 2         # each next level: 2 layers
TERRACE_INSET = 0.05    # an upper terrace is narrower than the one below (see _terraces)

# Eyes and brows, as shares of the logo height (the picture's eyes are small; the owner asked for bigger).
EYE_SCALE = 1.6         # eyes scaled around their centres
BROW_DX = 0.004         # a brow sits slightly outward of the eye's centre
BROW_DY = 0.072         # a brow above the eye
BROW_RX = 0.030         # semi-axes of the brow's oval
BROW_RY = 0.017
BROW_TILT = 18.0        # brow tilt, degrees: the inner end higher

COLORS = {   # zone colours for the preview and the SVG (as in the source picture)
    "fur": "#d2a46a", "mask": "#f3efe4", "dark": "#3b3530", "tongue": "#e6909a", "bow": "#b8432c",
    "rim": "#b98c55",
}


def logo_available() -> bool:
    """Whether the logo data is here. The logo belongs to the workshop's owner and isn't in the
    repository: logo_shiba.json and the source picture exist only locally (see .gitignore and README)."""
    return DATA.exists()


class LogoMissing(FileNotFoundError):
    """The logo data isn't in this copy (CI, the server): a logo-only part can't be built here."""


@lru_cache(maxsize=1)
def _data() -> dict:
    if not DATA.exists():
        raise LogoMissing(
            f"no logo data {DATA.name}: the logo isn't in the public repository. "
            "Put assets/logo/shiba-styles-front.webp in place and run tools/logo_extract.py"
        )
    return json.loads(DATA.read_text(encoding="utf-8"))


def aspect() -> float:
    """Logo width / height."""
    pts = np.vstack([np.array(loop) for loop in _data()["layers"]["silhouette"]])
    return float(np.ptp(pts[:, 0]) / np.ptp(pts[:, 1]))


def _eyes_and_brows() -> tuple[list, list]:
    """Eyes scaled EYE_SCALE times around their centres, and the dot brows above them."""
    eyes, brows = [], []
    for loop in _data()["layers"]["eyes"]:
        p = np.array(loop)
        c = p.mean(axis=0)
        eyes.append(((p - c) * EYE_SCALE + c).tolist())
        side = 1.0 if c[0] > 0 else -1.0
        center = c + [side * BROW_DX, BROW_DY]
        t = np.linspace(0, 2 * np.pi, 40, endpoint=False)
        ell = np.column_stack([BROW_RX * np.cos(t), BROW_RY * np.sin(t)])
        a = np.radians(-side * BROW_TILT)          # the brow's inner end higher than the outer
        rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        brows.append((ell @ rot.T + center).tolist())
    return eyes, brows


def layers(height: float) -> dict[str, mf.CrossSection]:
    """The logo's layers in mm at the given height (ears to the bottom of the bow)."""
    raw = dict(_data()["layers"])
    raw["eyes"], raw["brows"] = _eyes_and_brows()
    out = {}
    for name, loops in raw.items():
        scaled = [[(x * height, y * height) for x, y in loop] for loop in loops]
        # Contours were traced to about 0.002 of the height: at 20 mm that's a vertex every 0.03 mm,
        # which STL rounding merges into degenerate triangles. 0.04 mm is still 10× finer than the nozzle.
        out[name] = mf.CrossSection(scaled, mf.FillRule.NonZero).simplify(SIMPLIFY_MM)
    return out


def _band(shape: mf.CrossSection, width: float) -> mf.CrossSection:
    """A band of the given width inside the shape's border."""
    return shape - shape.offset(-width, mf.JoinType.Round, 2.0, SEGMENTS)


def _extrude(cs: mf.CrossSection, z0: float, z1: float) -> mf.Manifold:
    return mf.Manifold.extrude(cs, z1 - z0).translate((0, 0, z0))


def _clean(cs: mf.CrossSection, eps: float = 0.05) -> mf.CrossSection:
    """Remove point contacts and gaps thinner than 2·eps: otherwise the exported mesh isn't manifold."""
    j = mf.JoinType.Round
    closed = cs.offset(eps, j, 2.0, SEGMENTS).offset(-eps, j, 2.0, SEGMENTS)
    return closed.offset(-eps, j, 2.0, SEGMENTS).offset(eps, j, 2.0, SEGMENTS).simplify(SIMPLIFY_MM / 2)


def _terraces(levels: list[tuple[float, mf.CrossSection]]) -> mf.Manifold:
    """A solid of terraces: [(top height, region)], each region inside the previous one."""
    slabs, z0, prev = [], 0.0, None
    for z1, region in levels:
        # An upper terrace is TERRACE_INSET narrower than the one below: coinciding walls of
        # neighbouring terraces give zero-length edges and a non-manifold mesh. A 0.05 mm step doesn't show in print.
        inner = None if prev is None else prev.offset(-TERRACE_INSET, mf.JoinType.Miter, 2.0, SEGMENTS)
        region = _clean(region if prev is None else region ^ inner)
        slabs.append(_extrude(region, z0, z1))
        z0, prev = z1, region
    return _drop_slivers(mf.Manifold.batch_boolean(slabs, mf.OpType.Add))


def _drop_slivers(m: mf.Manifold, min_volume: float = 1e-3) -> mf.Manifold:
    """Drop the zero-volume slivers boolean operations sometimes leave."""
    parts = [p for p in m.decompose() if p.volume() > min_volume]
    return mf.Manifold.compose(parts) if len(parts) > 1 else parts[0]


def logo_relief(height: float, base: float = 0.8, step: float = 0.4, rim: float | None = None,
                min_line: float = MIN_LINE_LINES * NOZZLE_DEFAULT) -> mf.Manifold:
    """Relief (style 1). Bottom at Z = 0, a base of `base` mm, each level `step` mm higher.

    Levels: base (the ginger fur) → head rim, mask, bow → eyes, nose, knot, bow rim.
    The mouth is sunk one step below the base, the tongue at base level inside it.
    rim — width of the rims; by default 3% of the height but no less than min_line (2 nozzle lines).
    """
    L = layers(height)
    rim = max(min_line, 0.03 * height) if rim is None else rim
    head = L["silhouette"] - L["bow"]
    mouth_open = L["mouth"] - L["tongue"]
    features = L["eyes"] + L["nose"] + L["brows"]
    bow_rim = _band(L["bow"], rim * 0.8)
    if base - step <= 0:
        raise ValueError("the base must be thicker than a step: the mouth is sunk one step below the base")

    return _terraces([
        (base - step, L["silhouette"]),                                   # bottom of the mouth
        (base, L["silhouette"] - mouth_open),                             # base (fur), tongue
        (base + step, (_band(L["silhouette"], rim) - L["bow"])            # head rim
                      + ((L["mask"] ^ head) - L["mouth"])                 # mask without the mouth
                      + L["bow"] + features),                             # bow, eyes, nose
        (base + 2 * step, bow_rim + L["knot"] + features),                # bow rim, knot, eyes, nose
    ])


def logo_outline(height: float, wall: float = 1.0, line: float | None = None,
                 min_line: float = MIN_LINE_LINES * NOZZLE_DEFAULT) -> mf.Manifold:
    """Outline style (2): walls `wall` high along the borders of the zones, eyes and nose filled.

    line — wall thickness; by default 3% of the height but no less than min_line (2 nozzle lines).
    """
    L = layers(height)
    line = max(min_line, 0.03 * height) if line is None else line
    head = L["silhouette"] - L["bow"]
    lines = (_band(L["silhouette"], line) - L["bow"]
             + _band(L["mask"] ^ head, line)
             + _band(L["mouth"], line)
             + _band(L["bow"], line)
             + _band(L["knot"], line)
             + L["eyes"] + L["nose"] + L["brows"])
    return _drop_slivers(_extrude(_clean(lines), 0, wall))


LOGO_EMBED = 0.1        # a raised logo is sunk into the face a little so the two merge by volume
DEBOSS_GAP = 0.4        # groove around a sunk logo with a 0.4 nozzle (one nozzle line)


def _frame(origin, normal, up) -> np.ndarray:
    """3×4 matrix: the logo's local axes (X right, Y up, Z toward the viewer) → the world.

    normal — the face's outward normal (toward the viewer), up — where the logo's ears point.
    """
    n = np.asarray(normal, float)
    n /= np.linalg.norm(n)
    u = np.asarray(up, float)
    u = u - n * (u @ n)
    if np.linalg.norm(u) < 1e-9:
        raise ValueError("the 'up' direction is parallel to the face normal")
    u /= np.linalg.norm(u)
    x = np.cross(u, n)
    return np.column_stack([x, u, n, np.asarray(origin, float)])


def _check_footprint(body: mf.Manifold, footprint: mf.CrossSection, frame: np.ndarray) -> None:
    """A flat solid face under the whole logo: nothing above the surface, solid material 0.3 mm below."""
    area = footprint.area()
    above = _extrude(footprint, 0.02, 2.0).transform(frame)
    below = _extrude(footprint, -0.3, -0.02).transform(frame)
    over = (body ^ above).volume()
    under = (body ^ below).volume()
    if over > 0.01 * area:
        raise ValueError("the logo doesn't fit: there is material above the face here (the face isn't flat or isn't outer)")
    missing = area - under / 0.28        # mm² of area with no material below
    if missing > 0.1:                    # an absolute tolerance: even a small overlap with a hole leaves a thin wall
        raise ValueError(f"the logo doesn't fit: {missing:.1f} mm² under it isn't solid face "
                         "(an edge, a rounding, a hole or a recess closer than the margin)")


def place_logo(body, origin, normal, up=(0, 0, 1), height: float = 20.0, mode: str = "emboss",
               base: float | None = None, step: float | None = None, check: bool = True,
               margin: float | None = None, p=None):
    """Put the logo relief on a flat face of a part. Returns a trimesh (such a part has no STEP).

    body   — a build123d solid, a trimesh or a manifold;
    origin — the logo's centre on the face, normal — the face's outward normal, up — where the ears point;
    mode   — "emboss": relief above the face (base + 2·step high);
             "deboss": a niche in the silhouette with a one-nozzle-line groove, the relief inside flush with the face;
    p      — printer profile: the defaults below follow its nozzle and layer. Without p, as for a 0.4 nozzle;
    base, step — base height and level step: by default 4 and 2 layers (0.8 and 0.4 at a 0.2 layer);
    margin — how much solid face the logo needs around it, by default 2 nozzle lines: otherwise the
             wall between the logo and an edge or a hole comes out thinner than the printer can print.
    """
    from .mesh import from_manifold, to_manifold

    nozzle = p.nozzle_mm if p is not None else NOZZLE_DEFAULT
    layer = p.layer_mm if p is not None else LAYER_DEFAULT
    base = BASE_LAYERS * layer if base is None else base
    step = STEP_LAYERS * layer if step is None else step
    margin = MIN_LINE_LINES * nozzle if margin is None else margin
    gap = DEBOSS_GAP * nozzle / NOZZLE_DEFAULT
    min_line = MIN_LINE_LINES * nozzle
    m = body if isinstance(body, mf.Manifold) else to_manifold(body)
    frame = _frame(origin, normal, up)
    sil = layers(height)["silhouette"]
    total = base + 2 * step
    def with_margin(cs):
        return cs.offset(margin, mf.JoinType.Round, 2.0, SEGMENTS) if margin > 0 else cs

    if mode == "emboss":
        if check:
            _check_footprint(m, with_margin(sil), frame)
        logo = logo_relief(height, base + LOGO_EMBED, step, min_line=min_line).translate((0, 0, -LOGO_EMBED))
        result = m + logo.transform(frame)
    elif mode == "deboss":
        niche = sil.offset(gap, mf.JoinType.Round, 2.0, SEGMENTS)
        if check:
            _check_footprint(m, with_margin(niche), frame)
        pocket = _extrude(niche, -total, 1.0)
        logo = logo_relief(height, base + LOGO_EMBED, step, min_line=min_line).translate((0, 0, -total - LOGO_EMBED))
        result = (m - pocket.transform(frame)) + logo.transform(frame)
    else:
        raise ValueError(f"mode: 'emboss' or 'deboss', got {mode!r}")
    return from_manifold(_drop_slivers(result))


def _svg_path(cs: mf.CrossSection, w: float, h: float, pad: float) -> str:
    d = []
    for loop in cs.to_polygons():
        pts = " L ".join(f"{x + w / 2 + pad:.3f} {h / 2 + pad - y:.3f}" for x, y in loop)
        d.append(f"M {pts} Z")
    return " ".join(d)


def _color_parts(height: float) -> list[tuple[str, mf.CrossSection]]:
    """Layers in stacking order with the source picture's colours (for the SVG and the colour preview)."""
    L = layers(height)
    head = L["silhouette"] - L["bow"]
    return [
        (COLORS["fur"], L["silhouette"]),
        (COLORS["rim"], _band(L["silhouette"], max(0.8, 0.03 * height)) - L["bow"]),
        (COLORS["mask"], L["mask"] ^ head),
        (COLORS["dark"], L["mouth"]),
        (COLORS["tongue"], L["tongue"]),
        (COLORS["dark"], L["eyes"] + L["nose"]),
        (COLORS["mask"], L["brows"]),
        (COLORS["dark"], L["bow"]),
        (COLORS["bow"], L["bow"].offset(-max(0.6, 0.025 * height), mf.JoinType.Round, 2.0, SEGMENTS)),
        (COLORS["dark"], L["knot"]),
        (COLORS["bow"], L["knot"].offset(-max(0.5, 0.02 * height), mf.JoinType.Round, 2.0, SEGMENTS)),
    ]


def logo_svg(path, height: float = 40.0) -> None:
    """A flat colour version for stickers and print: layers in the source picture's colours."""
    w = height * aspect()
    pad = 1.0
    parts = _color_parts(height)
    paths = "".join(f'<path fill="{c}" fill-rule="nonzero" d="{_svg_path(cs, w, height, pad)}"/>' for c, cs in parts)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w + 2 * pad:.2f}mm" height="{height + 2 * pad:.2f}mm" '
           f'viewBox="0 0 {w + 2 * pad:.3f} {height + 2 * pad:.3f}">{paths}</svg>')
    Path(path).write_text(svg, encoding="utf-8")


def render_colors(path, height: float = 40.0) -> None:
    """A colour preview of the flat version (as a sticker or a multi-colour print)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MplPath

    fig, ax = plt.subplots(figsize=(5, 5 / aspect()), dpi=150)
    for color, cs in _color_parts(height):
        for loop in cs.to_polygons():
            ax.add_patch(PathPatch(MplPath(np.vstack([loop, loop[:1]]), closed=True), facecolor=color, edgecolor="none"))
    w = height * aspect()
    ax.set_xlim(-w / 2 - 1, w / 2 + 1)
    ax.set_ylim(-height / 2 - 1, height / 2 + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("#9a9a9a")
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)


def render_top(mesh, path, title: str = "", color=(0.80, 0.62, 0.40)) -> None:
    """Top view of a single-colour print: the higher the surface, the lighter; sunk parts darker."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    up = mesh.face_normals[:, 2] > 0.5
    tris = mesh.triangles[up]
    z = tris[:, :, 2].mean(axis=1)
    order = np.argsort(z)
    tris, z = tris[order], z[order]
    zn = (z - z.min()) / max(np.ptp(z), 1e-9)
    k = 0.45 + 0.7 * zn
    colors = np.clip(np.asarray(color)[None, :] * k[:, None], 0, 1)
    lo, hi = mesh.bounds[0][:2], mesh.bounds[1][:2]
    size = hi - lo
    fig, ax = plt.subplots(figsize=(10, 10 * size[1] / size[0] + 0.6), dpi=130)
    ax.add_collection(PolyCollection(tris[:, :, :2], facecolors=colors, edgecolors="none", antialiaseds=False))
    ax.set_xlim(lo[0] - 1, hi[0] + 1)
    ax.set_ylim(lo[1] - 1, hi[1] + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("#9a9a9a")
    if title:
        ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
