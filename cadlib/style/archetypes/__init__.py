"""Archetypes: whole parts composed from the style toolkit."""

from cadlib.style.archetypes.cantilever import CantileverSpec, cantilever
from cadlib.style.archetypes.hanger import EndProfile, HangerSpec, hanger_kit
from cadlib.style.archetypes.types import Archetype, Kit, Load, Piece, Support, Tunable

__all__ = [
    "Archetype", "CantileverSpec", "EndProfile", "HangerSpec", "Kit", "Load", "Piece", "Support", "Tunable",
    "cantilever", "hanger_kit",
]
