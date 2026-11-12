"""place_logo: лого встаёт на грань выпуклым и вдавленным, неподходящее место отвергается."""

import pytest
from build123d import Box, Cylinder, Pos

from cadlib.logo import aspect, logo_available, logo_relief, place_logo
from cadlib.mesh import to_manifold

pytestmark = pytest.mark.skipif(not logo_available(), reason="данные лого не входят в репозиторий")


@pytest.fixture
def block():
    return Pos(0, 0, 5) * Box(40, 40, 10)   # верхняя грань Z = 10


def test_emboss_on_top(block):
    plain = to_manifold(block).volume()
    mesh = place_logo(block, (0, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20)
    assert mesh.is_watertight and len(mesh.split(only_watertight=False)) == 1
    assert mesh.bounds[1][2] == pytest.approx(10 + 0.8 + 0.8, abs=0.01)
    assert mesh.volume == pytest.approx(plain + logo_relief(20).volume(), rel=0.02)


def test_deboss_flush_with_face(block):
    plain = to_manifold(block).volume()
    mesh = place_logo(block, (0, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20, mode="deboss")
    assert mesh.is_watertight and len(mesh.split(only_watertight=False)) == 1
    assert mesh.bounds[1][2] == pytest.approx(10, abs=0.01)     # ничего не торчит над гранью
    assert mesh.volume < plain                                   # ниша глубже рельефа местами


def test_side_face_orientation(block):
    # Боковая грань X = 20, уши вверх (+Z): лого стоит на ней, по Z занимает высоту лого.
    mesh = place_logo(block, (20, 0, 5), (1, 0, 0), up=(0, 0, 1), height=8)
    assert mesh.bounds[1][0] == pytest.approx(20 + 1.6, abs=0.01)
    assert mesh.extents[2] == pytest.approx(10, abs=0.01)        # лого 8 мм внутри грани высотой 10


def test_rejects_hole_and_edge(block):
    holed = block - Pos(5, 0, 5) * Cylinder(2, 12)
    with pytest.raises(ValueError, match="не сплошная"):
        place_logo(holed, (0, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20)
    with pytest.raises(ValueError, match="не сплошная"):
        place_logo(block, (15, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20)   # свисает за край
    with pytest.raises(ValueError):
        place_logo(block, (0, 0, 10), (0, 0, 1), up=(0, 0, 1), height=20)    # up ∥ normal


def test_aspect_reasonable():
    assert 0.6 < aspect() < 1.0


def test_profile_at_nozzle_04_changes_nothing(block):
    from cadlib.config import load_profile

    plain = place_logo(block, (0, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20)
    with_p = place_logo(block, (0, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20, p=load_profile(nozzle=0.4))
    assert with_p.volume == pytest.approx(plain.volume, rel=1e-6)


def test_bigger_nozzle_makes_taller_relief_and_wider_margin(block):
    from cadlib.config import load_profile

    thin = place_logo(block, (0, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20, p=load_profile(nozzle=0.4))
    thick = place_logo(block, (0, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20, p=load_profile(nozzle=0.8))
    # основа 4 слоя + 2 уровня по 2 слоя: 1.6 мм при слое 0.2, 3.2 мм при слое 0.4
    assert thin.bounds[1][2] == pytest.approx(10 + 1.6, abs=0.01)
    assert thick.bounds[1][2] == pytest.approx(10 + 3.2, abs=0.01)
    # у края: с отступом в 2 линии сопла 0.4 (0.8 мм) лого влезает, с 2 линиями сопла 0.8 (1.6 мм) — нет
    w = 20 * aspect()
    x = 20 - w / 2 - 1.2
    place_logo(block, (x, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20, p=load_profile(nozzle=0.4))
    with pytest.raises(ValueError, match="не помещается"):
        place_logo(block, (x, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20, p=load_profile(nozzle=0.8))
