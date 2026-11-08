"""Лого мастерской: оба стиля замкнуты на всех размерах, слои на месте, SVG пишется."""

import pytest

from cadlib.logo import aspect, layers, logo_available, logo_outline, logo_relief, logo_svg
from cadlib.mesh import from_manifold

pytestmark = pytest.mark.skipif(not logo_available(), reason="данные лого не входят в репозиторий")


@pytest.mark.parametrize("height", [15, 20, 40, 80])
def test_relief_closed_and_sized(height):
    mesh = from_manifold(logo_relief(height))
    assert mesh.is_watertight and mesh.volume > 0
    assert len(mesh.split(only_watertight=False)) == 1
    assert mesh.extents[1] == pytest.approx(height, rel=0.01)
    assert mesh.extents[0] == pytest.approx(height * aspect(), rel=0.01)


@pytest.mark.parametrize("height", [15, 20, 40])
def test_outline_closed(height):
    mesh = from_manifold(logo_outline(height))
    assert mesh.is_watertight and mesh.volume > 0
    # Островки: сеть стенок головы, глаза, брови, нос, контур пасти (лежит внутри маски) —
    # на детали все стоят на поверхности и срастаются с ней.
    assert 1 <= len(mesh.split(only_watertight=False)) <= 8


def test_layers_nested():
    L = layers(40)
    for name in ("mask", "eyes", "nose", "mouth", "tongue", "bow", "knot"):
        assert L[name].area() > 0, name
        assert (L[name] - L["silhouette"].offset(0.5)).area() < 1e-3, f"{name} вылезает за силуэт"
    assert (L["tongue"] - L["mouth"].offset(0.3)).area() < 1e-3
    assert (L["knot"] - L["bow"].offset(0.3)).area() < 1e-3


def test_svg(tmp_path):
    path = tmp_path / "logo.svg"
    logo_svg(path, 40)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("<svg") and text.count("<path") >= 8
