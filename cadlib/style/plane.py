"""Sketch-plane helpers: where "up" in print lies inside a sketch plane."""

from __future__ import annotations

import math

import numpy as np
from build123d import Plane

from cadlib.checks import down_vector

_FLAT_EPS = 0.1


def in_plane_up(plane: Plane, print_down) -> tuple[float, float] | None:
    """Print "up" (opposite of print_down, +Z by default) as a unit (u, v) in the plane's axes.

    None when its in-plane length is below 0.1, i.e. the plane lies flat in print.
    """
    up = np.array([0.0, 0.0, 1.0]) if print_down is None else -down_vector(print_down)
    u = float(np.dot(up, np.array(tuple(plane.x_dir))))
    v = float(np.dot(up, np.array(tuple(plane.y_dir))))
    n = math.hypot(u, v)
    if n < _FLAT_EPS:
        return None
    return (u / n, v / n)
