"""Тела под крепёж для вычитания из детали: отверстия, потай, цековка, гайки, вставки.

Соглашение: каждое тело стоит верхом на Z=0 и уходит вниз (в −Z) — это сторона входа винта.
Ставится на поверхность так: `body -= Pos(x, y, z_поверхности) * clearance_hole("M4", 5, p)`.
Для боковой грани тело поворачивают: `Pos(...) * Rot(0, 90, 0) * ...` (вход смотрит в −X).

Допуски берутся из профиля принтера (printer.toml), не из кода.
"""

from __future__ import annotations

from dataclasses import dataclass

from build123d import Cone, Cylinder, Part, Pos, RegularPolygon, Box, extrude

from .config import Profile

EPS = 0.01  # на столько тела выступают за поверхность, чтобы булева операция не оставила плёнку


@dataclass(frozen=True)
class Metric:
    d: float              # номинальный диаметр резьбы
    clear_fine: float     # отверстие под винт, точный ряд — ISO 273 (fine)
    head_d: float         # головка винта с цилиндрической головкой — ISO 4762 (dk max)
    head_h: float         # высота головки — ISO 4762 (k max)
    cbore_d: float        # цековка под ISO 4762 — DIN 974-1 (ряд 1)
    csk_d: float          # потайная головка 90° — ISO 7046-1 / ISO 14581 (dk теор. max)
    nut_s: float          # гайка под ключ — ISO 4032 (s, размер под ключ)
    nut_m: float          # высота гайки — ISO 4032 (m max)
    insert_d: float       # отверстие под термовставку (ориентир, Ruthex/CNC Kitchen стандартные)
    insert_l: float       # длина термовставки (ориентир)


# Справочные размеры, мм. Источники: ISO 273:1979, ISO 4762:2004, DIN 974-1:2008,
# ISO 7046-1:2011, ISO 4032:2012. Вставки зависят от производителя: замерьте свои
# штангенциркулем и передайте hole_d/length явно, если отличаются.
METRIC: dict[str, Metric] = {
    "M2":   Metric(2.0, 2.2, 3.8, 2.0, 4.3, 3.8, 4.0, 1.6, 3.2, 4.0),
    "M2.5": Metric(2.5, 2.7, 4.5, 2.5, 5.0, 4.7, 5.0, 2.0, 3.6, 5.7),
    "M3":   Metric(3.0, 3.2, 5.5, 3.0, 6.0, 5.5, 5.5, 2.4, 4.0, 5.7),
    "M4":   Metric(4.0, 4.3, 7.0, 4.0, 8.0, 8.4, 7.0, 3.2, 5.6, 8.1),
    "M5":   Metric(5.0, 5.3, 8.5, 5.0, 10.0, 9.3, 8.0, 4.7, 6.4, 9.5),
}


def metric(size: str) -> Metric:
    key = size.upper()
    if key not in METRIC:
        raise ValueError(f"Крепёж {size} не описан, есть: {', '.join(METRIC)}")
    return METRIC[key]


def _down_cylinder(d: float, depth: float) -> Part:
    """Цилиндр от Z=+EPS до Z=−depth."""
    return Pos(0, 0, (EPS - depth) / 2) * Cylinder(d / 2, depth + EPS)


def clearance_hole(size: str, depth: float, p: Profile) -> Part:
    """Сквозное/глухое отверстие под винт: ISO 273 fine + зазор принтера."""
    m = metric(size)
    return _down_cylinder(m.clear_fine + p.hole_clearance_mm, depth)


def counterbore_hole(size: str, depth: float, p: Profile, head_depth: float | None = None) -> Part:
    """Отверстие с цековкой под цилиндрическую головку ISO 4762 (головка утоплена заподлицо)."""
    m = metric(size)
    head_depth = m.head_h + p.layer_mm if head_depth is None else head_depth
    hole = clearance_hole(size, depth, p)
    return hole + _down_cylinder(m.cbore_d + p.hole_clearance_mm, head_depth)


def countersunk_hole(size: str, depth: float, p: Profile) -> Part:
    """Отверстие под потайной винт 90°: конус от диаметра головки до отверстия."""
    m = metric(size)
    head_d = m.csk_d + p.hole_clearance_mm
    hole_d = m.clear_fine + p.hole_clearance_mm
    cone_h = (head_d - hole_d) / 2  # 90°: высота равна разности радиусов
    cone = Pos(0, 0, -cone_h / 2 + EPS / 2) * Cone(hole_d / 2, head_d / 2 + EPS, cone_h + EPS)
    return clearance_hole(size, depth, p) + cone


def chamfer_ring(d: float, size: float = 0.6) -> Part:
    """Зенковка кромки отверстия диаметром d: фаска 45° шириной size (облегчает вход, убирает наплыв)."""
    return Pos(0, 0, -size / 2 + EPS / 2) * Cone(d / 2, d / 2 + size + EPS, size + EPS)


def nut_pocket(size: str, p: Profile, depth: float | None = None, slot: float = 0.0) -> Part:
    """Шестигранный карман под гайку ISO 4032 (плоскости вдоль X).

    slot > 0 продлевает карман вбок по +X на эту длину — паз, чтобы задвинуть гайку сбоку.
    """
    m = metric(size)
    s = m.nut_s + p.slide_fit_mm                       # размер под ключ с зазором
    depth = m.nut_m + p.layer_mm if depth is None else depth
    # RegularPolygon задаётся описанной окружностью, s = 2·R·cos30°. Вершины на 0° и 180°, значит грани вдоль X.
    hexagon = RegularPolygon(s / (3 ** 0.5), 6)
    pocket = Pos(0, 0, -depth) * extrude(hexagon, amount=depth + EPS)
    if slot > 0:
        pocket += Pos(slot / 2, 0, (EPS - depth) / 2) * Box(slot, s, depth + EPS)
    return pocket


def insert_hole(size: str, p: Profile, hole_d: float | None = None, length: float | None = None, extra: float = 1.0) -> Part:
    """Отверстие под термовставку: диаметр по производителю, глубина = длина вставки + extra под вытесненный пластик."""
    m = metric(size)
    d = m.insert_d if hole_d is None else hole_d
    length = m.insert_l if length is None else length
    return _down_cylinder(d, length + extra) + chamfer_ring(d, 0.4)
