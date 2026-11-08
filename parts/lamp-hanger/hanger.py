r"""lamp-hanger: общая геометрия подвеса LED-лампы для растений (3 детали).

Схема (вид спереди, X вдоль лампы, Z вверх, потолок на Z = 0):

        [=== планка 70 ===]          ← к потолку двумя потайными саморезами 6 мм
       /ласточка    ласточка\
      /                      \       ← диагональные балки плеч
     |                        |      ← вертикальные стойки (над колыбельками свободно)
   [колыбелька]==лампа==[колыбелька + паз под штекер Ø14]
     левое плечо              правое плечо

Плечо вдвигается шипом «ласточкин хвост» в гнездо планки спереди (+Y) назад до упора
и фиксируется бугорком-защёлкой. Лампа заводится спереди под балками и защёлкивается
вниз в колыбельки. Все детали плеча имеют общую заднюю плоскость Y = −ARM_D/2:
на ней плечо печатается лёжа на боку.

Все детали собираются здесь; папки lamp-hanger*, lamp-hanger-arm-* только вызывают
нужную функцию. Сборка с лампой для просмотра: assembly(p).
"""

from build123d import (
    Box, Cylinder, Plane, Polygon, Pos, Rot, Sphere, extrude, mirror,
)

from cadlib import fasteners as f
from cadlib.finish import bevel, soften

# --- лампа (замеры пользователя), мм ---
LAMP_L = 470.0          # длина лампы между торцами
PLUG_END_W = 32.0       # правый торец (с разъёмом): широкая сторона трапеции, замер
PLUG_END_NARROW_W = 17.0  # правый торец: узкая сторона трапеции (внизу), замер
PLUG_END_H = 16.5       # правый торец: высота, замер (16–16.5)
POCKET_NARROW_EXTRA = 3.0  # дно кармана шире узкой стороны: высота скоса не замерена, карман
                           # со стенками 45° от дна шириной 17+3 вмещает любую трапецию со скосом положе 45°
FLAT_END_W = 32.0       # левый торец (плоский): ширина, замер
FLAT_END_H = 7.2        # левый торец: толщина, замер
FLAT_END_Z = 0.0        # низ левого торца относительно низа правого (лампа прямая, низы на одном уровне — ПРЕДПОЛОЖЕНИЕ)
PLUG_HOLE_D = 14.0      # отверстие под штекер, задано пользователем
PLUG_HOLE_Z = None      # центр отверстия от низа лампы; None = середина высоты торца

# --- подвес, мм ---
DROP = 200.0            # от потолка до низа лампы, задано пользователем
MOUNT_L = 70.0          # длина потолочной планки, задано пользователем
SCREW_D = 6.0           # саморезы 6 мм с потаем, задано пользователем
SCREW_X = 14.0          # саморезы на ±SCREW_X от центра планки
SCREW_HEAD_D = None     # None = Ø12 по DIN 7997; лучше замерить

# --- конструкция, выбрано по умолчанию, мм ---
ARM_D = 38.0            # глубина (по Y) планки, ступицы и колыбелек: торец 32 + зазор + стенки по 2.8
MOUNT_H = 18.0          # высота планки и ступицы плеча
HUB_L = 12.0            # длина ступицы плеча по X
BEAM_T = 8.0            # толщина балки и стойки в плоскости XZ
BEAM_D = 10.0           # глубина балки и стойки по Y (от задней плоскости)
POST_ABOVE = 32.0       # стойка поднимается над колыбелькой: место, чтобы завести лампу спереди
CRADLE_L = 20.0         # насколько торец лампы лежит в колыбельке (вдоль X)
CRADLE_FLOOR = 3.0      # дно колыбельки
END_WALL = 6.0          # торцевая стенка колыбельки (она же низ стойки)
LAMP_CLEAR = 1.0        # зазор по длине лампы между торцевыми стенками (на обе стороны)
LIP = 0.8               # защёлкивающий бортик колыбельки: выступ внутрь
LIP_H = 1.6             # высота бортика над лампой (со скосом-заходом сверху)

# --- ласточкин хвост, мм ---
DT_NECK = 8.0           # шип у ступицы (по Z)
DT_TIP = 12.0           # шип на конце (по Z) — расширение и держит
DT_DEPTH = 8.0          # длина шипа (по X)
DT_BACK = 3.0           # задняя стенка гнезда в планке — упор
DETENT = 0.6            # бугорок-защёлка на шипе: выступ
DETENT_R = 1.4          # радиус бугорка

# --- отделка, мм (см. cadlib/finish.py: вертикальные при печати рёбра скругляем, у стола — фаска) ---
ROUND_R = 2.5           # рёбра плеча, вертикальные при печати (контур в XZ), и углы планки
TOP_R = 1.0             # рёбра верхних при печати граней
BED_CHAMFER = 0.5       # фаска рёбер на столе: против «слоновьей ноги»
MOUNT_FACE_R = 1.5      # лицевая (комнатная) сторона планки

EPS = 0.01


# --- общие ---------------------------------------------------------------------


def _xz_prism(points, y0: float, y1: float):
    """Призма из многоугольника в плоскости XZ, по Y от y0 до y1."""
    face = Plane.XZ * Polygon(*points, align=None)        # на Plane.XZ локальная y — это Z мира
    solid = extrude(face, amount=y1 - y0)
    bb = solid.bounding_box()
    return Pos(0, y0 - bb.min.Y, 0) * solid


def _yz_prism(points, x0: float, x1: float):
    """Призма из многоугольника в плоскости YZ, по X от x0 до x1."""
    face = Plane.YZ * Polygon(*points, align=None)        # на Plane.YZ локальные x, y — это Y, Z мира
    solid = extrude(face, amount=x1 - x0)
    bb = solid.bounding_box()                              # направление выдавливания зависит от нормали грани — выравниваем по факту
    return Pos(x0 - bb.min.X, 0, 0) * solid


def _dovetail(clear: float, depth_extra: float):
    """Профиль шипа в XZ для правого плеча: от торца планки x = MOUNT_L/2 внутрь (−X)."""
    x0 = MOUNT_L / 2
    zc = -MOUNT_H / 2
    neck, tip = DT_NECK / 2 + clear, DT_TIP / 2 + clear
    x_tip = x0 - DT_DEPTH - depth_extra
    return [(x0 + EPS, zc - neck), (x_tip, zc - tip), (x_tip, zc + tip), (x0 + EPS, zc + neck)]


def _detent_pos():
    return (MOUNT_L / 2 - DT_DEPTH, ARM_D / 2 - 6.0, -MOUNT_H / 2)


# --- потолочная планка -----------------------------------------------------------


def _mount_finish(body):
    """Отделка планки до вырезов: углы R, лицевая сторона мягко, потолочная (стол при печати) — фаска."""
    from build123d import Axis

    corners = [e for e in body.edges().filter_by(Axis.Z)]
    body, _ = soften(body.solids()[0], corners, ROUND_R)
    face_room = body.faces().sort_by(Axis.Z)[0]          # Z = −MOUNT_H: в комнату, при печати сверху
    body, _ = soften(body, list(face_room.edges()), MOUNT_FACE_R)
    face_ceiling = body.faces().sort_by(Axis.Z)[-1]      # Z = 0: к потолку, при печати на столе
    body, _ = bevel(body, list(face_ceiling.edges()), BED_CHAMFER)
    return body


def mount(p):
    c = p.slide_fit_mm / 2
    body = _mount_finish(Pos(0, 0, -MOUNT_H / 2) * Box(MOUNT_L, ARM_D, MOUNT_H))
    y_back = -ARM_D / 2 + DT_BACK
    for side in (1, -1):
        socket = _xz_prism(_dovetail(c, 0.3), y_back, ARM_D / 2 + 1)
        dimple = Pos(*_detent_pos()) * Sphere(DETENT_R + 0.1)
        tool = socket + Pos(-0.3, 0, 0) * dimple
        body -= tool if side == 1 else mirror(tool, about=Plane.YZ)

    screw = f.wood_screw_countersunk_hole(SCREW_D, MOUNT_H, p, SCREW_HEAD_D)
    for x in (SCREW_X, -SCREW_X):   # вход снизу (со стороны комнаты), вверх в потолок
        body -= Pos(x, 0, -MOUNT_H) * Rot(180, 0, 0) * screw
    return body


# --- плечо ------------------------------------------------------------------------


def _lamp_end(right: bool):
    """(ширина, высота, низ относительно −DROP, скосы низа) торца лампы."""
    if right:
        run = (PLUG_END_W - PLUG_END_NARROW_W - POCKET_NARROW_EXTRA) / 2
        return PLUG_END_W, PLUG_END_H, 0.0, (run, run)   # скос кармана 45°
    return FLAT_END_W, FLAT_END_H, FLAT_END_Z, (0.0, 0.0)


def _cradle_x():
    """(начало кармана, внутренняя грань торцевой стенки, наружная грань) по X для правой стороны."""
    x_in = LAMP_L / 2 + LAMP_CLEAR / 2
    return x_in - CRADLE_L, x_in, x_in + END_WALL


def _pocket_profile(w: float, h: float, chamfer, top: float, bottom: float):
    """Сечение кармана в YZ: прямоугольник со скошенными нижними углами, открыт сверху до top."""
    cw, ch = chamfer
    hw = w / 2
    return [(-hw + cw, bottom), (hw - cw, bottom), (hw, bottom + ch), (hw, top + 1),
            (-hw, top + 1), (-hw, bottom + ch)]


def arm_right_handed(p, right: bool):
    """Плечо в правом исполнении (лампа в −X от колыбельки). Левое получают зеркалом."""
    w, h, dz, chamfer = _lamp_end(right)
    w += p.slide_fit_mm
    lamp_bottom = -DROP + dz
    lamp_top = lamp_bottom + h
    cradle_top = lamp_top + LIP_H
    floor_z = lamp_bottom - CRADLE_FLOOR
    x_pocket, x_wall_in, x_wall_out = _cradle_x()
    y_back = -ARM_D / 2
    post_y1 = y_back + BEAM_D

    # Ступица и шип.
    x_hub0 = MOUNT_L / 2
    body = Pos(x_hub0 + HUB_L / 2, 0, -MOUNT_H / 2) * Box(HUB_L, ARM_D, MOUNT_H)
    tongue_y0 = y_back + DT_BACK + 0.3
    body += _xz_prism(_dovetail(0, 0), tongue_y0, ARM_D / 2)
    dx, dy, dz_ = _detent_pos()
    body += Pos(dx + DETENT_R - DETENT, dy, dz_) * Sphere(DETENT_R)

    # Колыбелька с торцевой стенкой.
    body += Pos((x_pocket + x_wall_out) / 2, 0, (floor_z + cradle_top) / 2) * Box(x_wall_out - x_pocket, ARM_D, cradle_top - floor_z)
    pocket = _pocket_profile(w, h, chamfer, cradle_top, lamp_bottom)
    body -= _yz_prism(pocket, x_pocket - 1, x_wall_in)
    # Бортики-защёлки: треугольник с пологим заходом сверху.
    for s in (1, -1):
        y_wall = s * w / 2
        y_in_wall = y_wall + s * 0.5   # основание бортика утоплено в стенку: слияние по объёму, а не по плоскости
        lip = [(y_in_wall, lamp_top + 0.3), (y_wall - s * LIP, lamp_top + 0.5), (y_in_wall, cradle_top)]
        body += _yz_prism(lip, x_pocket, x_wall_in)

    # Стойка над торцевой стенкой и диагональная балка от ступицы к верху стойки.
    post_top = cradle_top + POST_ABOVE
    body += Pos((x_wall_in + x_wall_out) / 2, (y_back + post_y1) / 2, (floor_z + post_top) / 2) * Box(
        END_WALL, BEAM_D, post_top - floor_z)
    ax, az = x_hub0 + HUB_L / 2, -MOUNT_H / 2
    cx, cz = (x_wall_in + x_wall_out) / 2, post_top - BEAM_T / 2
    body += _beam(ax, az, cx, cz, y_back, post_y1)

    if right:
        hz = lamp_bottom + (h / 2 if PLUG_HOLE_Z is None else PLUG_HOLE_Z)
        slot = Pos(x_wall_in + END_WALL / 2, 0, hz) * Rot(0, 90, 0) * Cylinder(PLUG_HOLE_D / 2, END_WALL + 2)
        slot += Pos(x_wall_in + END_WALL / 2, 0, (hz + cradle_top + 1) / 2) * Box(END_WALL + 2, PLUG_HOLE_D, cradle_top + 1 - hz)
        body -= slot
    _validate(p, ax, az, cx, cz, x_pocket, cradle_top, post_y1, right)
    return _arm_finish(body, x_pocket, x_wall_in, w, lamp_bottom, cradle_top)


def _arm_finish(body, x_pocket, x_wall_in, w, lamp_bottom, cradle_top):
    """Отделка плеча. Плечо печатается на задней плоскости Y = −ARM_D/2, поэтому:
    рёбра вдоль Y (вертикальные при печати) — скругление ROUND_R, рёбра верхних граней — TOP_R,
    рёбра на задней плоскости — фаска BED_CHAMFER. Рабочие места не трогаем: шип и торец ступицы
    (x ≤ MOUNT_L/2), карман колыбельки, куда ложится торец лампы.
    """
    from build123d import Axis

    x_joint = MOUNT_L / 2 + 0.05

    def functional(e) -> bool:
        c = e.center()
        if c.X <= x_joint:
            return True
        in_pocket_x = x_pocket - 0.1 <= c.X <= x_wall_in + 0.1
        in_pocket_yz = abs(c.Y) <= w / 2 + 0.1 and lamp_bottom - 0.1 <= c.Z <= cradle_top + 0.1
        return in_pocket_x and in_pocket_yz

    body = body.solids()[0]
    vertical = [e for e in body.edges().filter_by(Axis.Y) if not functional(e)]
    body, _ = soften(body, vertical, ROUND_R)

    # Верхние при печати грани (ступица, колыбелька, балка со стойкой) — каждая своим контуром:
    # одной операцией на все грани OCCT не справляется.
    top_centers = [fc.center() for fc in body.faces() if fc.normal_at().Y > 0.999]
    for c in top_centers:
        face = min((fc for fc in body.faces() if fc.normal_at().Y > 0.999), key=lambda fc: (fc.center() - c).length)
        body, _ = soften(body, [e for e in face.edges() if not functional(e)], TOP_R)

    bed = body.faces().sort_by(Axis.Y)[0]
    body, _ = bevel(body, list(bed.edges()), BED_CHAMFER)
    return body


def _beam(ax, az, cx, cz, y0, y1):
    """Балка толщиной BEAM_T между точками A и C (в XZ), с запасом заходит в ступицу и стойку."""
    import math

    length = math.hypot(cx - ax, cz - az)
    ux, uz = (cx - ax) / length, (cz - az) / length
    nx, nz = -uz * BEAM_T / 2, ux * BEAM_T / 2
    ext = BEAM_T / 2
    a = (ax - ux * ext, az - uz * ext)
    c = (cx + ux * ext, cz + uz * ext)
    pts = [(a[0] + nx, a[1] + nz), (c[0] + nx, c[1] + nz), (c[0] - nx, c[1] - nz), (a[0] - nx, a[1] - nz)]
    return _xz_prism(pts, y0, y1)


def _validate(p, ax, az, cx, cz, x_pocket, cradle_top, post_y1, right):
    import math

    # Под балкой над колыбелькой должно хватать места завести лампу спереди и опустить её.
    slope = (cz - az) / (cx - ax)
    z_center = az + (x_pocket - ax) * slope
    z_bottom = z_center - BEAM_T / 2 / math.cos(math.atan(abs(slope)))
    _, h, _, _ = _lamp_end(right)
    need = cradle_top + h + 3
    if z_bottom < need:
        raise ValueError(f"балка над колыбелькой низко ({z_bottom:.1f} < {need:.1f}): увеличьте POST_ABOVE")
    if right and post_y1 > -PLUG_HOLE_D / 2 - 1:
        raise ValueError("стойка заходит на паз под штекер: уменьшите BEAM_D")
    if min(BEAM_T, BEAM_D, END_WALL, CRADLE_FLOOR) < 2 * p.min_wall_mm:
        raise ValueError("слишком тонкие элементы плеча для сопла")
    if (ARM_D - max(PLUG_END_W, FLAT_END_W) - p.slide_fit_mm) / 2 < 2 * p.min_wall_mm:
        raise ValueError("стенки колыбельки тоньше двух минимальных стенок")


def arm(p, side: str):
    """side: 'right' (с пазом под штекер) или 'left'. Левое — зеркало по X своей геометрии."""
    if side == "right":
        return arm_right_handed(p, right=True)
    return mirror(arm_right_handed(p, right=False), about=Plane.YZ)


def assembly(p):
    """Планка, оба плеча и условная лампа — только для просмотра, не для печати."""
    w, h, _, _ = _lamp_end(True)
    lamp = Pos(0, 0, -DROP + FLAT_END_H / 2) * Box(LAMP_L, w - 2, FLAT_END_H)
    return [mount(p), arm(p, "right"), arm(p, "left"), lamp]
