"""dog-figurine: стилизованная фигурка белой собачки (мальтипу/ши-тцу) по фото пользователя.

Не портретная копия, а игрушечная стилизация из простых форм: пушистая круглая голова,
большие глаза-бусины, нос, висячие уши, ноги «столбиками» с пушистыми лапами,
хвост-помпон торчком. Стоит на овальной подставке — так тонкие ноги не отломятся
и фигурка устойчива.

Строится сразу сеткой в manifold3d: OCCT ненадёжно сливает растянутые сферы (B-сплайны),
а manifold объединяет любые замкнутые сетки. Ноги, шея и хвост — выпуклые оболочки
двух сфер (hull): получаются плавные «капсулы» с разной толщиной концов.
STEP для такой формы не нужен, на выходе STL и 3MF.

Оси: X — вдоль тела (голова в +X), Y — поперёк, Z вверх, подставка на Z = 0.

Сборка: uv run cad.py build parts/dog-figurine
"""

import manifold3d as mf

from cadlib.mesh import from_manifold

# --- общий масштаб: все размеры ниже умножаются на SCALE ---
SCALE = 1.0             # 1.0 ≈ 84 мм в длину с подставкой, ≈ 70 мм в высоту
SEGMENTS = 72           # гладкость сфер: сегментов на окружность

# --- подставка, мм ---
BASE = True             # овальная подставка
BASE_RX, BASE_RY, BASE_H = 42.0, 24.0, 3.0
BASE_BEVEL = 1.2        # скос верхней кромки подставки

# --- тело, мм: центры и радиусы ---
BODY_C, BODY_R = (-2.0, 0.0, 33.0), (19.0, 12.5, 12.5)
CHEST_C, CHEST_R = (13.0, 0.0, 34.0), 12.0
LEG_X_FRONT, LEG_X_BACK, LEG_Y = 13.0, -14.0, 8.0
LEG_TOP_R, LEG_BOTTOM_R = 6.0, 7.0  # ноги шире книзу — пушистые «штанишки», как после стрижки на фото
PAW_R = (7.6, 7.0, 4.5)           # лапы: сплюснутые шарики

# --- голова, мм ---
HEAD_C, HEAD_R = (22.0, 0.0, 56.0), 13.5
NECK_R = 8.0
MUZZLE_C, MUZZLE_R = (33.0, 0.0, 52.5), (6.5, 7.5, 6.0)
NOSE_C, NOSE_R = (39.2, 0.0, 54.0), 2.4
EYE_C, EYE_R = (32.0, 5.6, 58.5), 2.6   # Y зеркалится на обе стороны
EAR_C, EAR_R = (19.5, 11.0, 49.5), (5.6, 4.0, 12.0)
EAR_TILT = 12.0                    # уши чуть разведены книзу, градусы

# --- хвост, мм ---
TAIL_BASE, TAIL_BASE_R = (-17.0, 0.0, 39.0), 5.0
TAIL_TIP, TAIL_TIP_R = (-20.0, 0.0, 47.0), 4.5
TAIL_POM_C, TAIL_POM_R = (-21.0, 0.0, 51.0), (8.0, 7.5, 8.0)   # пушистый помпон у самой спины

NAME = "dog-figurine"
FORMATS = ("stl", "3mf")
EXPECTED_BODIES = 1
SECTION = ("y", 0.0)    # разрез по средней линии: видно, что всё срослось в одно тело


def _s(v):
    return tuple(c * SCALE for c in v) if isinstance(v, tuple) else v * SCALE


def _ellipsoid(center, radii, tilt_x: float = 0.0) -> mf.Manifold:
    """Эллипсоид; tilt_x — наклон вокруг оси X в градусах (для ушей)."""
    radii = radii if isinstance(radii, tuple) else (radii,) * 3
    m = mf.Manifold.sphere(1.0, SEGMENTS).scale(_s(radii))
    if tilt_x:
        m = m.rotate((tilt_x, 0, 0))
    return m.translate(_s(center))


def _capsule(p1, r1, p2, r2) -> mf.Manifold:
    """Плавная «капсула» между двумя точками: выпуклая оболочка двух сфер."""
    return mf.Manifold.batch_hull([_ellipsoid(p1, r1), _ellipsoid(p2, r2)])


def _base() -> mf.Manifold:
    h = _s(BASE_H)
    top_scale = 1 - _s(BASE_BEVEL) / _s(BASE_RX)
    plate = mf.Manifold.cylinder(h, 1.0, top_scale, SEGMENTS * 2)
    return plate.scale((_s(BASE_RX), _s(BASE_RY), 1.0))


def build(p):
    base_top = BASE_H if BASE else 0.0
    parts = [
        # Туловище: оболочка корпуса и груди — один гладкий «бочонок».
        mf.Manifold.batch_hull([_ellipsoid(BODY_C, BODY_R), _ellipsoid(CHEST_C, CHEST_R)]),
        _capsule(CHEST_C, NECK_R, HEAD_C, NECK_R),
        _ellipsoid(HEAD_C, HEAD_R),
        _ellipsoid(MUZZLE_C, MUZZLE_R),
        _ellipsoid(NOSE_C, NOSE_R),
        _capsule(TAIL_BASE, TAIL_BASE_R, TAIL_TIP, TAIL_TIP_R),
        _ellipsoid(TAIL_POM_C, TAIL_POM_R),
    ]
    for side in (1, -1):
        parts.append(_ellipsoid((EYE_C[0], EYE_C[1] * side, EYE_C[2]), EYE_R))
        parts.append(_ellipsoid((EAR_C[0], EAR_C[1] * side, EAR_C[2]), EAR_R, tilt_x=-EAR_TILT * side))
        for x in (LEG_X_FRONT, LEG_X_BACK):
            paw = (x * 1.05, LEG_Y * side, base_top + PAW_R[2] * 0.6)
            top = (x, LEG_Y * side, BODY_C[2])
            parts.append(_capsule(paw, LEG_BOTTOM_R, top, LEG_TOP_R))
            parts.append(_ellipsoid(paw, PAW_R))
    if BASE:
        parts.append(_base())

    figure = mf.Manifold.batch_boolean(parts, mf.OpType.Add)
    figure = figure.trim_by_plane((0.0, 0.0, 1.0), 0.0)   # всё ниже стола срезать
    pieces = figure.decompose()
    if len(pieces) != 1:
        raise RuntimeError(f"фигурка собралась из {len(pieces)} частей — какая-то деталь не касается остальных")
    return from_manifold(figure)
