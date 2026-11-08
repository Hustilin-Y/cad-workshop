"""Лого мастерской: мультяшная сиба-ину с бабочкой — «барельеф» и «контурный» стили.

Само лого (картинка и контуры) — собственность владельца мастерской, не входит в репозиторий
и не распространяется под MIT. Этот код без данных лого собирает детали без него.

Контуры слоёв сняты с картинки пользователя (assets/logo/shiba-styles-front.webp) скриптом
tools/logo_extract.py и лежат в logo_shiba.json рядом: высота лого = 1, центр (0, 0), Y вверх.
Слои: silhouette (голова + бабочка), mask (белая маска морды), eyes, nose, mouth, tongue,
bow (бабочка), knot (узел). Поверх картинки: глаза увеличены (EYE_SCALE), добавлены брови-«точки»
сибы (brows, BROW_*) — по просьбе пользователя.

Стили (оба плоские по слоям — читаются от ~15 мм и годятся для многоцветной печати):
  logo_relief()  — барельеф: основа по силуэту, бортик по контуру головы, маска выше,
                   глаза и нос выше маски, пасть утоплена, язык внутри, бабочка с бортиком;
  logo_outline() — контурный: стенки по границам зон, глаза и нос залиты.
Плюс logo_svg() — цветная плоская версия для наклеек, render_colors() — цветное превью.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import manifold3d as mf
import numpy as np

DATA = Path(__file__).with_name("logo_shiba.json")
SEGMENTS = 32
SIMPLIFY_MM = 0.04      # точность контуров: всё мельче для сопла 0.4 не существует
TERRACE_INSET = 0.05    # верхняя терраса уже нижней (см. _terraces)

# Глаза и брови — доли высоты лого (на картинке глаза мелкие, по просьбе пользователя крупнее).
EYE_SCALE = 1.6         # увеличение глаз вокруг их центров
BROW_DX = 0.004         # бровь чуть наружу от центра глаза
BROW_DY = 0.072         # бровь над глазом
BROW_RX = 0.030         # полуоси овала брови
BROW_RY = 0.017
BROW_TILT = 18.0        # наклон брови, градусы: внутренний конец выше

COLORS = {   # цвета зон для превью и SVG (как на исходной картинке)
    "fur": "#d2a46a", "mask": "#f3efe4", "dark": "#3b3530", "tongue": "#e6909a", "bow": "#b8432c",
    "rim": "#b98c55",
}


def logo_available() -> bool:
    """Есть ли данные лого. Лого — собственность владельца мастерской и в репозиторий не входит:
    logo_shiba.json и исходная картинка лежат только локально (см. .gitignore и README)."""
    return DATA.exists()


@lru_cache(maxsize=1)
def _data() -> dict:
    if not DATA.exists():
        raise FileNotFoundError(
            f"нет данных лого {DATA.name}: лого не входит в публичный репозиторий. "
            "Положите assets/logo/shiba-styles-front.webp и запустите tools/logo_extract.py"
        )
    return json.loads(DATA.read_text(encoding="utf-8"))


def aspect() -> float:
    """Ширина / высота лого."""
    pts = np.vstack([np.array(loop) for loop in _data()["layers"]["silhouette"]])
    return float(np.ptp(pts[:, 0]) / np.ptp(pts[:, 1]))


def _eyes_and_brows() -> tuple[list, list]:
    """Глаза, увеличенные в EYE_SCALE раз вокруг своих центров, и брови-«точки» над ними."""
    eyes, brows = [], []
    for loop in _data()["layers"]["eyes"]:
        p = np.array(loop)
        c = p.mean(axis=0)
        eyes.append(((p - c) * EYE_SCALE + c).tolist())
        side = 1.0 if c[0] > 0 else -1.0
        center = c + [side * BROW_DX, BROW_DY]
        t = np.linspace(0, 2 * np.pi, 40, endpoint=False)
        ell = np.column_stack([BROW_RX * np.cos(t), BROW_RY * np.sin(t)])
        a = np.radians(-side * BROW_TILT)          # внутренний конец брови выше наружного
        rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        brows.append((ell @ rot.T + center).tolist())
    return eyes, brows


def layers(height: float) -> dict[str, mf.CrossSection]:
    """Слои лого в мм при высоте height (уши — низ бабочки)."""
    raw = dict(_data()["layers"])
    raw["eyes"], raw["brows"] = _eyes_and_brows()
    out = {}
    for name, loops in raw.items():
        scaled = [[(x * height, y * height) for x, y in loop] for loop in loops]
        # Контуры сняты с точностью ~0.002 высоты: на 20 мм это вершины через 0.03 мм, после
        # округления в STL они слипаются в вырожденные треугольники. 0.04 мм — в 10 раз точнее сопла.
        out[name] = mf.CrossSection(scaled, mf.FillRule.NonZero).simplify(SIMPLIFY_MM)
    return out


def _band(shape: mf.CrossSection, width: float) -> mf.CrossSection:
    """Полоса шириной width внутри границы фигуры."""
    return shape - shape.offset(-width, mf.JoinType.Round, 2.0, SEGMENTS)


def _extrude(cs: mf.CrossSection, z0: float, z1: float) -> mf.Manifold:
    return mf.Manifold.extrude(cs, z1 - z0).translate((0, 0, z0))


def _clean(cs: mf.CrossSection, eps: float = 0.05) -> mf.CrossSection:
    """Убрать касания в точку и щели тоньше 2·eps: иначе после экспорта сетка не манифолдна."""
    j = mf.JoinType.Round
    closed = cs.offset(eps, j, 2.0, SEGMENTS).offset(-eps, j, 2.0, SEGMENTS)
    return closed.offset(-eps, j, 2.0, SEGMENTS).offset(eps, j, 2.0, SEGMENTS).simplify(SIMPLIFY_MM / 2)


def _terraces(levels: list[tuple[float, mf.CrossSection]]) -> mf.Manifold:
    """Тело из террас: [(высота верха, область)], каждая область внутри предыдущей."""
    slabs, z0, prev = [], 0.0, None
    for z1, region in levels:
        # Верхняя терраса на TERRACE_INSET уже нижней: совпадающие стенки соседних террас дают
        # рёбра нулевой длины и неманифолдную сетку. Ступенька 0.05 мм при печати не видна.
        inner = None if prev is None else prev.offset(-TERRACE_INSET, mf.JoinType.Miter, 2.0, SEGMENTS)
        region = _clean(region if prev is None else region ^ inner)
        slabs.append(_extrude(region, z0, z1))
        z0, prev = z1, region
    return _drop_slivers(mf.Manifold.batch_boolean(slabs, mf.OpType.Add))


def _drop_slivers(m: mf.Manifold, min_volume: float = 1e-3) -> mf.Manifold:
    """Выбросить осколки нулевого объёма, которые иногда оставляют булевы операции."""
    parts = [p for p in m.decompose() if p.volume() > min_volume]
    return mf.Manifold.compose(parts) if len(parts) > 1 else parts[0]


def logo_relief(height: float, base: float = 0.8, step: float = 0.4, rim: float | None = None) -> mf.Manifold:
    """Барельеф (стиль 1). Низ на Z = 0, основа base мм, каждый уровень выше на step мм.

    Уровни: основа (рыжая шерсть) → бортик головы, маска, бабочка → глаза, нос, узел, бортик бабочки.
    Пасть утоплена на step ниже основы, язык — на уровне основы внутри пасти.
    rim — ширина бортиков; по умолчанию 3% высоты, но не меньше 0.8 мм (2 линии сопла 0.4).
    """
    L = layers(height)
    rim = max(0.8, 0.03 * height) if rim is None else rim
    head = L["silhouette"] - L["bow"]
    mouth_open = L["mouth"] - L["tongue"]
    features = L["eyes"] + L["nose"] + L["brows"]
    bow_rim = _band(L["bow"], rim * 0.8)
    if base - step <= 0:
        raise ValueError("основа должна быть толще шага: пасть утоплена на step ниже основы")

    return _terraces([
        (base - step, L["silhouette"]),                                   # дно пасти
        (base, L["silhouette"] - mouth_open),                             # основа (шерсть), язык
        (base + step, (_band(L["silhouette"], rim) - L["bow"])            # бортик головы
                      + ((L["mask"] ^ head) - L["mouth"])                 # маска без пасти
                      + L["bow"] + features),                             # бабочка, глаза, нос
        (base + 2 * step, bow_rim + L["knot"] + features),                # бортик бабочки, узел, глаза, нос
    ])


def logo_outline(height: float, wall: float = 1.0, line: float | None = None) -> mf.Manifold:
    """Контурный стиль (2): стенки высотой wall по границам зон, глаза и нос залиты.

    line — толщина стенок; по умолчанию 3% высоты, но не меньше 0.8 мм.
    """
    L = layers(height)
    line = max(0.8, 0.03 * height) if line is None else line
    head = L["silhouette"] - L["bow"]
    lines = (_band(L["silhouette"], line) - L["bow"]
             + _band(L["mask"] ^ head, line)
             + _band(L["mouth"], line)
             + _band(L["bow"], line)
             + _band(L["knot"], line)
             + L["eyes"] + L["nose"] + L["brows"])
    return _drop_slivers(_extrude(_clean(lines), 0, wall))


LOGO_EMBED = 0.1        # выпуклое лого утоплено в грань: слияние по объёму
DEBOSS_GAP = 0.4        # канавка вокруг вдавленного лого (ниша шире силуэта)


def _frame(origin, normal, up) -> np.ndarray:
    """Матрица 3×4: локальные оси лого (X вправо, Y вверх, Z к зрителю) → мир.

    normal — наружная нормаль грани (к зрителю), up — куда смотрят уши лого.
    """
    n = np.asarray(normal, float)
    n /= np.linalg.norm(n)
    u = np.asarray(up, float)
    u = u - n * (u @ n)
    if np.linalg.norm(u) < 1e-9:
        raise ValueError("направление «вверх» параллельно нормали грани")
    u /= np.linalg.norm(u)
    x = np.cross(u, n)
    return np.column_stack([x, u, n, np.asarray(origin, float)])


def _check_footprint(body: mf.Manifold, footprint: mf.CrossSection, frame: np.ndarray) -> None:
    """Под всем лого — ровная сплошная грань: выше поверхности пусто, на 0.3 мм ниже — сплошной материал."""
    area = footprint.area()
    above = _extrude(footprint, 0.02, 2.0).transform(frame)
    below = _extrude(footprint, -0.3, -0.02).transform(frame)
    over = (body ^ above).volume()
    under = (body ^ below).volume()
    if over > 0.01 * area:
        raise ValueError("лого не помещается: над гранью в этом месте есть материал (грань не ровная или не наружная)")
    if under < 0.98 * area * 0.28:
        raise ValueError("лого не помещается: под ним не сплошная грань (край, скругление, отверстие или углубление)")


def place_logo(body, origin, normal, up=(0, 0, 1), height: float = 20.0, mode: str = "emboss",
               base: float = 0.8, step: float = 0.4, check: bool = True):
    """Поставить лого-барельеф на ровную грань детали. Возвращает trimesh (STEP у такой детали не будет).

    body   — тело build123d, trimesh или manifold;
    origin — центр лого на поверхности грани, normal — наружная нормаль, up — куда смотрят уши;
    mode   — "emboss": барельеф над гранью (высота base + 2·step);
             "deboss": ниша по силуэту с канавкой DEBOSS_GAP, барельеф внутри заподлицо с гранью.
    """
    from .mesh import from_manifold, to_manifold

    m = body if isinstance(body, mf.Manifold) else to_manifold(body)
    frame = _frame(origin, normal, up)
    sil = layers(height)["silhouette"]
    total = base + 2 * step
    if mode == "emboss":
        if check:
            _check_footprint(m, sil, frame)
        logo = logo_relief(height, base + LOGO_EMBED, step).translate((0, 0, -LOGO_EMBED))
        result = m + logo.transform(frame)
    elif mode == "deboss":
        niche = sil.offset(DEBOSS_GAP, mf.JoinType.Round, 2.0, SEGMENTS)
        if check:
            _check_footprint(m, niche, frame)
        pocket = _extrude(niche, -total, 1.0)
        logo = logo_relief(height, base + LOGO_EMBED, step).translate((0, 0, -total - LOGO_EMBED))
        result = (m - pocket.transform(frame)) + logo.transform(frame)
    else:
        raise ValueError(f"mode: 'emboss' или 'deboss', получено {mode!r}")
    return from_manifold(_drop_slivers(result))


def _svg_path(cs: mf.CrossSection, w: float, h: float, pad: float) -> str:
    d = []
    for loop in cs.to_polygons():
        pts = " L ".join(f"{x + w / 2 + pad:.3f} {h / 2 + pad - y:.3f}" for x, y in loop)
        d.append(f"M {pts} Z")
    return " ".join(d)


def _color_parts(height: float) -> list[tuple[str, mf.CrossSection]]:
    """Слои в порядке наложения с цветами исходной картинки (для SVG и цветного превью)."""
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
    """Цветная плоская версия для наклеек и печати: слои в цветах исходной картинки."""
    w = height * aspect()
    pad = 1.0
    parts = _color_parts(height)
    paths = "".join(f'<path fill="{c}" fill-rule="nonzero" d="{_svg_path(cs, w, height, pad)}"/>' for c, cs in parts)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w + 2 * pad:.2f}mm" height="{height + 2 * pad:.2f}mm" '
           f'viewBox="0 0 {w + 2 * pad:.3f} {height + 2 * pad:.3f}">{paths}</svg>')
    Path(path).write_text(svg, encoding="utf-8")


def render_colors(path, height: float = 40.0) -> None:
    """Цветное превью плоской версии (как на наклейке или при многоцветной печати)."""
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
    """Вид сверху одноцветной печати: чем выше поверхность, тем светлее; утопленное — темнее."""
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
