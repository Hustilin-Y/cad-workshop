"""Filament estimate for the build report: grams of plastic and, if a spool price is set, cost.

No slicer here, so the estimate is a simple model of how slicers fill a part: shells (walls,
top and bottom) as thick as the profile's minimum wall all over the surface, and the inside
filled at the infill share from printer.toml. Expect it within about ±20% of the slicer's figure;
the solid mass is shown too as a hard upper bound. Print time can't be estimated without slicing.
"""

from __future__ import annotations

from dataclasses import dataclass

import trimesh

from .config import Profile


@dataclass(frozen=True)
class Estimate:
    solid_g: float
    printed_g: float
    cost: float | None  # in the currency of printer.toml, None without a spool price

    def summary(self, profile: Profile) -> str:
        text = (
            f"≈ {self.printed_g:.0f} g of {profile.material} at {profile.infill_share * 100:.0f}% infill "
            f"(solid: {self.solid_g:.0f} g)"
        )
        if self.cost is not None:
            text += f", ≈ {self.cost:.0f} {profile.currency}"
        return text


def estimate(mesh: trimesh.Trimesh, profile: Profile) -> Estimate:
    volume_cm3 = max(float(mesh.volume), 0.0) / 1000.0
    shell_cm3 = min(volume_cm3, float(mesh.area) * profile.min_wall_mm / 1000.0)
    printed_cm3 = shell_cm3 + profile.infill_share * (volume_cm3 - shell_cm3)
    solid_g = volume_cm3 * profile.density_g_cm3
    printed_g = printed_cm3 * profile.density_g_cm3
    cost = printed_g / 1000.0 * profile.price_per_kg if profile.price_per_kg else None
    return Estimate(solid_g, printed_g, cost)
