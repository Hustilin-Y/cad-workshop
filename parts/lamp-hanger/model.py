"""lamp-hanger: потолочная планка подвеса лампы (деталь 1 из 3), с лого мастерской.

Вся геометрия и параметры подвеса — в hanger.py рядом; плечи — в lamp-hanger-arm-right/-left.
Лого — барельеф на лицевой (комнатной) стороне между потаями саморезов: смотрит в комнату,
а при печати оказывается сверху, где поверхность самая чистая.
Печать: потолочной стороной на стол.

С лого деталь выходит сеткой (STL/3MF, без STEP); LOGO = False вернёт STEP.

Сборка: uv run cad.py build parts/lamp-hanger
"""

import importlib.util
from pathlib import Path

from cadlib.logo import logo_available, place_logo

_spec = importlib.util.spec_from_file_location("hanger", Path(__file__).resolve().parent / "hanger.py")
hanger = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hanger)

# --- лого, мм ---
LOGO = True
LOGO_H = 24.0           # высота лого: самое крупное, при котором ниша между выемками саморезов (Ø6.2 на ±14 мм) — со стенкой ≥ 0.8 мм
LOGO_MODE = "deboss"    # "deboss" — утоплено заподлицо (по просьбе пользователя), "emboss" — выпуклое

NAME = "lamp-hanger-mount"
EXPECTED_BODIES = 1
SECTION = ("y", 0.0)    # разрез через саморезы и гнёзда


def build(p):
    body = hanger.mount(p)
    if not LOGO:
        return body
    if not logo_available():
        print("  лого: данных лого нет в этой копии проекта — планка без лого")
        return body
    # Лицевая сторона — Z = −MOUNT_H, смотрит вниз в комнату; уши лого — от зрителя, стоящего спереди (+Y).
    return place_logo(body, (0, 0, -hanger.MOUNT_H), (0, 0, -1), up=(0, -1, 0), height=LOGO_H, mode=LOGO_MODE)
