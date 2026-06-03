"""Unit value objects and SI type aliases for the physics engine.

Per the profile ("don't pass bare floats where grams vs ounces could be confused")
and TRD §2:

- Boundary **value objects** (frozen dataclasses) carry units and convert explicitly:
  ``Mass`` (kg/ounces), ``Length`` (m/inches/feet), ``Angle`` (radians/degrees).
  Each stores a single canonical SI value and exposes named-unit accessors so a
  round-trip conversion is exact within float tolerance.
- Hot-loop internals use plain SI ``float``s tagged with ``NewType`` aliases
  (``Meters``, ``MetersPerSecond``, ``Newtons``, ``Joules``, ``Kilograms``,
  ``Radians``) for readability without per-step allocation.
- Conversion factors are centralized here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NewType

# ── Centralized conversion factors (TRD §2) ──────────────────────────────────
OZ_TO_KG = 0.0283495
IN_TO_M = 0.0254
GRAMS_PER_KG = 1000.0
INCHES_PER_FOOT = 12.0

# ── SI NewType aliases for the integration hot loop ──────────────────────────
Meters = NewType("Meters", float)
MetersPerSecond = NewType("MetersPerSecond", float)
Newtons = NewType("Newtons", float)
Joules = NewType("Joules", float)
Kilograms = NewType("Kilograms", float)
Radians = NewType("Radians", float)


@dataclass(frozen=True)
class Mass:
    """A mass, stored canonically in kilograms."""

    kg: float

    @classmethod
    def from_ounces(cls, ounces: float) -> Mass:
        return cls(ounces * OZ_TO_KG)

    @classmethod
    def from_grams(cls, grams: float) -> Mass:
        return cls(grams / GRAMS_PER_KG)

    @property
    def ounces(self) -> float:
        return self.kg / OZ_TO_KG


@dataclass(frozen=True)
class Length:
    """A length, stored canonically in metres."""

    m: float

    @classmethod
    def from_inches(cls, inches: float) -> Length:
        return cls(inches * IN_TO_M)

    @classmethod
    def from_feet(cls, feet: float) -> Length:
        return cls(feet * INCHES_PER_FOOT * IN_TO_M)

    @property
    def inches(self) -> float:
        return self.m / IN_TO_M

    @property
    def feet(self) -> float:
        return self.inches / INCHES_PER_FOOT


@dataclass(frozen=True)
class Angle:
    """An angle, stored canonically in radians."""

    radians: float

    @classmethod
    def from_degrees(cls, degrees: float) -> Angle:
        return cls(math.radians(degrees))

    @property
    def degrees(self) -> float:
        return math.degrees(self.radians)
