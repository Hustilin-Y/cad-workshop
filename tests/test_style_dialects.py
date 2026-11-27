import pytest
from build123d import Plane, Polyline, extrude, make_face

from cadlib.config import load_profile
from cadlib.style.dialects import DIALECTS, finish_extrusion, get_dialect

P = load_profile()


def _l_extrusion(depth: float):
    pts = [(0, 0), (40, 0), (40, 10), (10, 10), (10, 40), (0, 40), (0, 0)]
    face = make_face(Polyline(*pts))
    return extrude(face, depth)


def test_unknown_name_lists_all_four():
    with pytest.raises(ValueError) as e:
        get_dialect("baroque")
    msg = str(e.value)
    assert "'baroque'" in msg
    for name in ("gothic", "gaudi", "hitech", "parametric"):
        assert name in msg


def test_table():
    assert set(DIALECTS) == {"gothic", "gaudi", "hitech", "parametric"}
    assert get_dialect("gaudi").opening == "catenary" and get_dialect("gaudi").taper == 0.45
    assert get_dialect("hitech").lattice == "tri"


@pytest.mark.parametrize("name", list(DIALECTS))
def test_finish_extrusion_one_valid_solid(name):
    out = finish_extrusion(_l_extrusion(10), get_dialect(name), 10, None, P)
    assert len(out.solids()) == 1 and out.is_valid


def test_gaudi_removes_more_than_hitech():
    body = _l_extrusion(10)
    gaudi = finish_extrusion(body, get_dialect("gaudi"), 10, "-z", P)
    hitech = finish_extrusion(body, get_dialect("hitech"), 10, "-z", P)
    assert body.volume - gaudi.volume > body.volume - hitech.volume > 0
