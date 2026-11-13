"""place_logo: the logo goes on a face raised and sunk, an unfit place is refused."""

import pytest
from build123d import Box, Cylinder, Pos

from cadlib.logo import aspect, logo_available, logo_relief, place_logo
from cadlib.mesh import to_manifold

pytestmark = pytest.mark.skipif(not logo_available(), reason="the logo data is not in the repository")


@pytest.fixture
def block():
    return Pos(0, 0, 5) * Box(40, 40, 10)   # top face Z = 10


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
    assert mesh.bounds[1][2] == pytest.approx(10, abs=0.01)     # nothing sticks out above the face
    assert mesh.volume < plain                                   # the niche is deeper than the relief in places


def test_side_face_orientation(block):
    # Side face X = 20, ears up (+Z): the logo stands on it and spans the logo height in Z.
    mesh = place_logo(block, (20, 0, 5), (1, 0, 0), up=(0, 0, 1), height=8)
    assert mesh.bounds[1][0] == pytest.approx(20 + 1.6, abs=0.01)
    assert mesh.extents[2] == pytest.approx(10, abs=0.01)        # an 8 mm logo inside a 10 mm high face


def test_rejects_hole_and_edge(block):
    holed = block - Pos(5, 0, 5) * Cylinder(2, 12)
    with pytest.raises(ValueError, match="isn't solid face"):
        place_logo(holed, (0, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20)
    with pytest.raises(ValueError, match="isn't solid face"):
        place_logo(block, (15, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20)   # hangs over the edge
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
    # base 4 layers + 2 levels of 2 layers: 1.6 mm at a 0.2 layer, 3.2 mm at a 0.4 layer
    assert thin.bounds[1][2] == pytest.approx(10 + 1.6, abs=0.01)
    assert thick.bounds[1][2] == pytest.approx(10 + 3.2, abs=0.01)
    # near an edge: with a margin of 2 lines of a 0.4 nozzle (0.8 mm) the logo fits, with 2 lines of a 0.8 nozzle (1.6 mm) it doesn't
    w = 20 * aspect()
    x = 20 - w / 2 - 1.2
    place_logo(block, (x, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20, p=load_profile(nozzle=0.4))
    with pytest.raises(ValueError, match="doesn't fit"):
        place_logo(block, (x, 0, 10), (0, 0, 1), up=(0, 1, 0), height=20, p=load_profile(nozzle=0.8))
