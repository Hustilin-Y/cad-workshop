import pytest
from build123d import Plane

from cadlib.config import load_profile
from cadlib.style.members import catenary, curved_beam, rib, taper_beam, truss

P = load_profile()


def test_taper_area():
    f = taper_beam((0, 0), (100, 0), 10, 4, p=P)
    assert f.area == pytest.approx(100 * 7, rel=1e-3)


def test_catenary_sag():
    pts = catenary((0, 0), (100, 0), 20)
    assert min(v for _, v in pts) == pytest.approx(-20, abs=0.05)
    assert pts[0] == pytest.approx((0, 0)) and pts[-1] == pytest.approx((100, 0))


def test_truss_is_one_face():
    f = truss([(0, 0), (60, 0), (30, 30)], [(0, 1), (1, 2), (2, 0)], 3, 6, p=P)
    assert len(f.faces()) == 1


def test_thin_member_rejected():
    with pytest.raises(ValueError, match="min_wall"):
        taper_beam((0, 0), (50, 0), 0.5, 0.5, p=P)


def test_curved_beam_is_one_valid_face():
    centre = [(0, 0), (30, 15), (60, 20), (90, 10)]
    f = curved_beam(centre, [8, 7, 6, 5], p=P)
    assert f.is_valid and len(f.wires()) == 1
    assert f.area == pytest.approx(95 * 6.5, rel=0.1)
    with pytest.raises(ValueError, match="min_wall"):
        curved_beam(centre, [8, 7, 0.4, 5], p=P)


def test_truss_rejects_thin_bar_and_node():
    nodes = [(0, 0), (60, 0), (30, 30)]
    ms = [(0, 1), (1, 2), (2, 0)]
    with pytest.raises(ValueError, match="min_wall"):
        truss(nodes, ms, 0.3, 6, p=P)
    with pytest.raises(ValueError, match="min_wall"):
        truss(nodes, ms, 3, 0.3, p=P)


def test_rib_straight_path_is_flat_ended_box():
    s = rib([(0, 0), (40, 0)], 3, 4, Plane.XZ, p=P)
    bb = s.bounding_box()
    assert s.is_valid
    assert bb.size.X == pytest.approx(40, abs=1e-3)  # flat ends: length equals the path
    assert bb.size.Z == pytest.approx(3, abs=1e-3)  # width runs along v
    assert bb.size.Y == pytest.approx(4, abs=1e-3)  # height along the plane normal
    assert s.volume == pytest.approx(40 * 3 * 4, rel=1e-3)


def test_rib_bent_path():
    s = rib([(0, 0), (40, 0), (40, 30)], 3, 4, Plane.XZ, p=P)
    bb = s.bounding_box()
    assert s.is_valid
    assert bb.size.Y == pytest.approx(4, abs=1e-3)
    assert bb.size.X == pytest.approx(41.5, abs=1e-2)  # round join overshoots by width / 2
    assert bb.size.Z == pytest.approx(31.5, abs=1e-2)  # first leg is 3 wide around v = 0
    assert 825 < s.volume < 850  # two legs, minus the shared corner square, plus the round join
    with pytest.raises(ValueError, match="min_wall"):
        rib([(0, 0), (10, 0)], 0.2, 4, Plane.XZ, p=P)
