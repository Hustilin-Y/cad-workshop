"""rod-cap: защитная заглушка на резьбовую шпильку — накручивается как гайка, сверху шар.

Защищает детей от удара о торец шпильки. Глухая втулка с внутренней резьбой
снизу, сферическая головка сверху. Ось по Z, открытый торец втулки на Z = 0.

ПРИМЕРНАЯ МОДЕЛЬ: диаметр и шаг резьбы взяты условно, до замера шпильки.
Перед печатью целиком напечатать тестовое кольцо: parts/rod-cap-thread-test.

Сборка: uv run cad.py build parts/rod-cap
"""

from build123d import Cone, Cylinder, Pos, Sphere, fillet

from cadlib.threads import internal_thread_tube

# --- резьба шпильки (УТОЧНИТЬ ЗАМЕРОМ), мм ---
THREAD_D = 38.0         # наружный диаметр шпильки по вершинам витков: «около 38» со слов пользователя
THREAD_PITCH = 4.0      # шаг: условно, как у M36/M39; замерить (витков на 20 мм)
THREAD_DEPTH = 50.0     # на сколько накручивается: «сантиметров пять» со слов пользователя

# --- форма, выбрано по умолчанию, мм ---
SLEEVE_WALL = 5.0       # стенка втулки вокруг резьбы
BORE_EXTRA = 2.0        # глухое отверстие длиннее резьбы: место под неровный торец шпильки
TOP_WALL = 3.0          # втулка выше дна отверстия до начала шара
BALL_D = 60.0           # шар: чем больше и круглее, тем мягче удар
BALL_RISE = 12.0        # центр шара выше верха втулки
LEAD_IN = 1.5           # заходная фаска резьбы (облегчает наживление)
BOTTOM_ROUND = 2.0      # скругление нижней кромки втулки, без острых углов
OVERLAP = 1.0           # верхняя часть заходит в резьбовую трубку: слияние по объёму, а не по плоскости

NAME = "rod-cap"
EXPECTED_BODIES = 1
SECTION = ("y", 0.0)    # разрез по оси: видна резьба и толщина стенок


def sleeve_od() -> float:
    return THREAD_D + 2 * SLEEVE_WALL


def thread_d(p) -> float:
    """Диаметр резьбы в модели: номинал + зазор скользящей посадки, иначе печатная резьба закусывает."""
    return THREAD_D + p.slide_fit_mm


def threaded_part(p, depth: float):
    """Резьбовая трубка высотой depth с заходной фаской и скруглённой нижней кромкой."""
    d = thread_d(p)
    tube = internal_thread_tube(sleeve_od(), d, THREAD_PITCH, depth)
    tube = tube.cut(Pos(0, 0, LEAD_IN / 2) * Cone(d / 2 + LEAD_IN, d / 2, LEAD_IN)).solids()[0]
    outer_bottom = [e for e in tube.edges() if e.geom_type.name == "CIRCLE"
                    and abs(e.center().Z) < 1e-6 and abs(e.radius - sleeve_od() / 2) < 1e-6]
    return fillet(outer_bottom, BOTTOM_ROUND)


def bore_is_clear(body, p) -> bool:
    """Отверстие под шпильку свободно: внутри Ø вершин витков нет материала на всю глубину."""
    from cadlib.threads import minor_diameter

    probe_h = THREAD_DEPTH + BORE_EXTRA - 0.1
    probe = Pos(0, 0, probe_h / 2 + 0.05) * Cylinder(minor_diameter(thread_d(p), THREAD_PITCH) / 2 - 0.05, probe_h)
    hit = body.intersect(probe)            # пустое пересечение build123d возвращает как None
    return hit is None or hit.volume < 1e-3


def _validate(p) -> None:
    if SLEEVE_WALL < 2 * p.min_wall_mm:
        raise ValueError(f"SLEEVE_WALL {SLEEVE_WALL} мала: нужно ≥ {2 * p.min_wall_mm} под резьбой")
    if BALL_D < sleeve_od():
        raise ValueError(f"шар Ø{BALL_D} меньше втулки Ø{sleeve_od()}: торец втулки будет торчать")
    sleeve_h = THREAD_DEPTH + BORE_EXTRA + TOP_WALL
    ball_top = sleeve_h + BALL_RISE + BALL_D / 2
    cone_top = THREAD_DEPTH + BORE_EXTRA + (THREAD_D + p.slide_fit_mm) / 2
    if ball_top - cone_top < 2 * TOP_WALL:
        raise ValueError(f"над конусом полости остаётся {ball_top - cone_top:.1f} мм — шар слишком тонкий сверху")
    if THREAD_PITCH > THREAD_DEPTH / 3:
        raise ValueError("на глубине резьбы меньше трёх витков: держаться не будет")


def build(p):
    _validate(p)
    d = thread_d(p)
    sleeve_h = THREAD_DEPTH + BORE_EXTRA + TOP_WALL
    body = threaded_part(p, THREAD_DEPTH)

    # Верх: глухой стакан над резьбой (карман под торец шпильки) и шар.
    top_z0 = THREAD_DEPTH - OVERLAP
    top = Pos(0, 0, (top_z0 + sleeve_h) / 2) * Cylinder(sleeve_od() / 2, sleeve_h - top_z0)
    top += Pos(0, 0, sleeve_h + BALL_RISE) * Sphere(BALL_D / 2)
    # Полость под шпильку: цилиндр на всю глубину + потолок конусом 45° (печатается без моста Ø38).
    # Вырезается после шара: шар опускается ниже верха втулки и иначе залез бы в отверстие.
    cavity_h = THREAD_DEPTH + BORE_EXTRA
    cavity = Pos(0, 0, cavity_h / 2) * Cylinder(d / 2, cavity_h)
    cavity += Pos(0, 0, cavity_h + d / 4) * Cone(d / 2, 0, d / 2)
    top -= cavity

    body = body.fuse(top.solids()[0]).clean()
    if len(body.solids()) != 1:
        raise RuntimeError(f"заглушка собралась из {len(body.solids())} тел")
    body = body.solids()[0]
    if not bore_is_clear(body, p):
        raise RuntimeError("в отверстии под шпильку остался материал")
    return body
