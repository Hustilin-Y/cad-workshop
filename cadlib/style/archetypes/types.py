"""What an archetype hands back: the solid plus the hooks later stages read (supports, loads, tunables).

Part 1 does not use supports, loads or tunables itself. Load-aware orientation (part 2) reads the
loads, the FEA check and parameter fitting (part 3) read all three.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from build123d import Solid

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class Tunable:
    """A parameter an optimiser may move between `lo` and `hi`."""

    name: str
    value: float
    lo: float
    hi: float
    unit: str = "mm"


@dataclass(frozen=True)
class Load:
    """A force in newtons applied at a point of the part (design coordinates)."""

    point: Vec3
    force_n: Vec3


@dataclass(frozen=True)
class Support:
    """A planar face held fixed, found by a point on it and its outward normal."""

    point: Vec3
    normal: Vec3


@dataclass
class Archetype:
    """One printed body with its print orientation and the hooks for parts 2-4."""

    solid: Solid
    print_down: str
    allowed_print_down: tuple[str, ...]
    supports: list[Support] = field(default_factory=list)
    loads: list[Load] = field(default_factory=list)
    tunables: dict[str, Tunable] = field(default_factory=dict)


@dataclass
class Piece:
    """One printed piece of a kit."""

    solid: Solid
    print_down: str
    allowed_print_down: tuple[str, ...]


@dataclass
class Kit:
    """Several printed pieces that are assembled, with the hooks of the assembly as a whole."""

    pieces: Mapping[str, Piece]
    supports: list[Support] = field(default_factory=list)
    loads: list[Load] = field(default_factory=list)
    tunables: dict[str, Tunable] = field(default_factory=dict)
