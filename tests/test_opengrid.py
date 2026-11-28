"""openGrid and Multiconnect interface tools: sizes measured from the official modeling files."""

import os
from pathlib import Path

import numpy as np
import pytest
from build123d import Pos, Rot, import_step

from cadlib import opengrid as og
from cadlib.config import load_profile
from cadlib.export import shape_to_mesh
from cadlib.mesh import to_manifold
from cadlib.preview import section_loops

P = load_profile()
SOURCE = os.environ.get("CAD_OPENGRID_SOURCE")
needs_source = pytest.mark.skipif(
    not SOURCE, reason="set CAD_OPENGRID_SOURCE to the official openGrid package folder to compare"
)


def _width_at(part, z: float, y: float) -> float:
    """Width along X of the solid's section Z=z, measured on the line Y=y."""
    xs = []
    for loop in section_loops(shape_to_mesh(part), "z", z):
        pts = np.vstack([loop, loop[:1]])
        for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
            if (y1 - y) * (y2 - y) <= 0 and y1 != y2:
                xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    return max(xs) - min(xs) if xs else 0.0


# --- Multiconnect slot ---------------------------------------------------------------------------


def test_slot_profile():
    slot = og.multiconnect_slot(30, flare=False)
    assert _width_at(slot, -0.2, -15) == pytest.approx(15.3, abs=0.02)  # neck
    assert _width_at(slot, -3.5, -15) == pytest.approx(20.3, abs=0.02)  # wide part
    bb = slot.bounding_box()
    assert bb.min.Z == pytest.approx(-og.SLOT_DEPTH, abs=0.01)
    assert bb.max.Z > 0                                                  # sticks out by EPS


def test_slot_closed_end_is_up():
    # the part hangs on the connector by the closed end: closed end above (+Y), open end below
    slot = og.multiconnect_slot(30, flare=False)
    assert slot.bounding_box().max.Y == pytest.approx(10.15, abs=0.03)
    assert slot.bounding_box().min.Y == pytest.approx(-30, abs=0.01)


def test_slot_detent():
    slot = og.multiconnect_slot(30, detent=True, flare=False)
    # below the connector, so the part can't lift off
    assert _width_at(slot, -3.5, -3.55) == pytest.approx(19.518, abs=0.03)
    assert _width_at(slot, -3.5, -12) == pytest.approx(20.3, abs=0.02)
    assert _width_at(slot, -0.2, -3.55) == pytest.approx(15.3, abs=0.02)  # the neck is untouched


def test_slot_flare():
    flared = og.multiconnect_slot(30)
    plain = og.multiconnect_slot(30, flare=False)
    assert _width_at(flared, -0.05, -29.9) == pytest.approx(22.0, abs=0.1)
    assert _width_at(plain, -0.05, -29.9) == pytest.approx(15.3, abs=0.02)
    # the funnel stops at the open end: nothing is cut beyond it
    assert flared.bounding_box().min.Y == pytest.approx(-30, abs=0.01)


def test_slot_too_short():
    with pytest.raises(ValueError, match="10.15"):
        og.multiconnect_slot(8)
    with pytest.raises(ValueError, match="10.15"):
        og.multiconnect_slot(8.5, detent=True)
    og.multiconnect_slot(10.2, detent=True)


# --- openGrid snap -------------------------------------------------------------------------------


@pytest.mark.parametrize("lite,height", [(False, 6.8), (True, 3.4)])
def test_snap_size(lite, height):
    bb = og.snap(lite=lite).bounding_box()
    assert (bb.size.X, bb.size.Y) == (pytest.approx(25.6, abs=0.01), pytest.approx(25.6, abs=0.01))
    assert bb.min.Z == pytest.approx(0, abs=0.01)
    assert bb.max.Z == pytest.approx(height, abs=0.01)


def test_snap_octagon():
    s = og.snap()
    assert _width_at(s, 0.5, 0) == pytest.approx(24.8, abs=0.02)        # front plate, across flats
    corner = 24.8 / 2 - 4.818                                            # where the 45° corner starts
    assert _width_at(s, 5.8, 12.39) == pytest.approx(2 * (corner + 0.01), abs=0.05)  # wall side


@pytest.mark.parametrize("lite,flat_z,plain_z", [(False, 2.4, 0.5), (True, 2.3, 0.4)])
def test_snap_bumps(lite, flat_z, plain_z):
    # latch bumps 0.4 proud on each side, nearer the wall than the front; none at the front plate
    s = og.snap(lite=lite)
    assert _width_at(s, flat_z, 0) == pytest.approx(25.6, abs=0.02)
    assert _width_at(s, plain_z, 0) == pytest.approx(24.8, abs=0.02)


def test_snap_slits():
    loops = section_loops(shape_to_mesh(og.snap()), "z", 3.0)
    # the outline plus four slits, each 0.6 × 12.4
    slits = [lp for lp in loops if min(np.ptp(lp, axis=0)) < 1.0]
    assert len(slits) == 4
    for lp in slits:
        assert sorted(np.round(np.ptp(lp, axis=0), 2)) == [pytest.approx(0.6, abs=0.02), pytest.approx(12.4, abs=0.03)]
        assert np.abs(lp).max(axis=0).max() == pytest.approx(11.7, abs=0.02)


@pytest.mark.parametrize("lite", [False, True])
def test_snap_single_body(lite):
    assert len(og.snap(lite=lite).solids()) == 1


# --- placement and checks ------------------------------------------------------------------------


def test_grid_positions():
    assert og.grid_positions(84) == [(-28.0, 0.0), (0.0, 0.0), (28.0, 0.0)]
    assert og.grid_positions(56) == [(-14.0, 0.0), (14.0, 0.0)]
    assert og.grid_positions(20) == []
    assert sorted(og.grid_positions(56, 56)) == [(-14.0, -14.0), (-14.0, 14.0), (14.0, -14.0), (14.0, 14.0)]


def test_require_cells():
    og.require_cells(28)
    og.require_cells(56, 28)
    with pytest.raises(ValueError, match="28"):
        og.require_cells(27.9)
    with pytest.raises(ValueError, match="28"):
        og.require_cells(56, 20)


def test_bottom_back_turn_keeps_slot_direction():
    # a back face at the bottom of a part: Rot(0, 180, 0) turns the tool up into the part, open end still down
    slot = Rot(0, 180, 0) * og.multiconnect_slot(26)
    bb = slot.bounding_box()
    assert bb.min.Z < 0.1 and bb.max.Z == pytest.approx(og.SLOT_DEPTH, abs=0.01)
    assert bb.min.Y == pytest.approx(-26, abs=0.01)


def test_require_back():
    og.require_back(og.SLOT_DEPTH + P.min_wall_mm, P)
    with pytest.raises(ValueError, match="6.4"):
        og.require_back(og.SLOT_DEPTH + P.min_wall_mm - 0.01, P)


# --- against the official files ------------------------------------------------------------------


def _sym_diff_share(ours, official_meshes) -> float:
    a = to_manifold(shape_to_mesh(ours))
    b = to_manifold(official_meshes[0])
    for extra in official_meshes[1:]:
        b = b + to_manifold(extra)
    inter = (a ^ b).volume()
    return (a.volume() + b.volume() - 2 * inter) / b.volume()


def _official(rel: str):
    mesh = shape_to_mesh(import_step(Path(SOURCE) / rel))
    return list(mesh.split(only_watertight=True)) or [mesh]


@needs_source
def test_slot_matches_official():
    # official: connector centre at (-25, 64), open end toward -Y at 37.5, back face at Z = -6
    ours = Pos(-25, 64, -6) * og.multiconnect_slot(26.5, detent=True, flare=False)
    assert _sym_diff_share(ours, _official("Multiconnect modeling files/snap-in-slot-negative.step")) < 0.01
    plain = Pos(0, 65.5, -6) * og.multiconnect_slot(28, flare=False)
    official = _official("Multiconnect modeling files/slot-negative.step")
    official += _official("Multiconnect modeling files/half-round-negative.step")
    assert _sym_diff_share(plain, official) < 0.01


@needs_source
@pytest.mark.parametrize("lite,rel", [
    (False, "Snap modeling files/openGrid Bare Snap.step"),
    (True, "Snap modeling files/openGrid Bare Lite Snap.step"),
])
def test_snap_matches_official(lite, rel):
    # official: wall side at Z = 0, front at the top. Ours: front at Z = 0, wall side up.
    height = 3.4 if lite else 6.8
    ours = Pos(0, 0, height) * Rot(180, 0, 0) * og.snap(lite=lite)
    assert _sym_diff_share(ours, _official(rel)) < 0.01


def test_opengrid_test_pieces_build(capsys, repo_copy):
    from cad import main

    folder = repo_copy("calibration/opengrid")
    assert main(["build", str(folder)]) == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out and "WARN" not in out
