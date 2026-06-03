"""CarDesign and its sub-objects (Wheels, BodyShape, Axle, Alignment).

The car model is dumb, validated, immutable data (TRD §3 data model, §6 validation);
all physics lives in the engine. Each frozen dataclass validates once in
``__post_init__`` and raises ``ValueError`` with a clear message on bad input. The
model is pure: no clock, network, or RNG.

Traceability (PRD §6; physics-spec §2.1/§2.2/§3.1/§3.2):

- AC-W3: ``mass <= 0`` raises; over-weight is reported later, not a construction error.
- AC-P5: ``com_ahead_of_rear_axle`` outside the open interval ``(0, wheelbase)`` raises.
- AC-WH3: ``I = ½·m_w·(R_outer² + R_inner²)``; invalid wheel geometry
  (``R_inner >= R_outer``, ``r_axle >= R_outer``, any radius/mass ``<= 0``) and
  ``count_touching ∉ {3, 4}`` raise.
- AC-A3: ``drag_coefficient <= 0`` or ``frontal_area <= 0`` raises; WEDGE/BLOCK presets.
- AC-F2 (validation portion): ``friction_coefficient < 0`` raises;
  POLISHED_GRAPHITE/UNPREPARED presets.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import ClassVar

from .units import Length, Mass

# Spec-anchored preset values (physics-spec §3.1/§3.2).
_CD_WEDGE = 0.20
_CD_BLOCK = 0.85
_MU_POLISHED_GRAPHITE = 0.10
_MU_UNPREPARED = 0.35

# Default frontal area for the body presets (PRD A5: ≈ 1.75" × 2.5"), in m².
_DEFAULT_FRONTAL_AREA = 0.0028


class Alignment(enum.Enum):
    """How the car tracks down the lane (physics-spec §3.3)."""

    STRAIGHT = "straight"        # seeded ping-pong, F_rail ~ U(1.5, 3.0) N
    RAIL_RIDER = "rail_rider"    # constant F_rail = 0.05 N


@dataclass(frozen=True)
class Wheels:
    """The car's wheels (physics-spec §2.1/§2.2).

    Raises ``ValueError`` if ``count_touching`` is not 3 or 4, any radius or the
    wheel mass is non-finite or ``<= 0``, the inner radius is ``>=`` the outer radius,
    or the axle radius is ``>=`` the outer radius.
    """

    count_touching: int     # number of wheels in contact (3 or 4)
    wheel_mass: Mass        # m_w per wheel
    outer_radius: Length    # R_outer
    inner_radius: Length    # R_inner (bore-side wall)
    axle_radius: Length     # r_axle (nail shank)

    def __post_init__(self) -> None:
        if self.count_touching not in (3, 4):
            raise ValueError(
                f"count_touching must be 3 or 4, got {self.count_touching}"
            )
        m_w = self.wheel_mass.kg
        if not math.isfinite(m_w) or m_w <= 0.0:
            raise ValueError(f"wheel_mass must be a finite > 0, got {m_w} kg")
        r_o = self.outer_radius.m
        r_i = self.inner_radius.m
        r_a = self.axle_radius.m
        if not math.isfinite(r_o) or r_o <= 0.0:
            raise ValueError(f"outer_radius must be a finite > 0, got {r_o} m")
        if not math.isfinite(r_i) or r_i <= 0.0:
            raise ValueError(f"inner_radius must be a finite > 0, got {r_i} m")
        if not math.isfinite(r_a) or r_a <= 0.0:
            raise ValueError(f"axle_radius must be a finite > 0, got {r_a} m")
        if r_i >= r_o:
            raise ValueError(
                f"inner_radius ({r_i} m) must be < outer_radius ({r_o} m)"
            )
        if r_a >= r_o:
            raise ValueError(
                f"axle_radius ({r_a} m) must be < outer_radius ({r_o} m)"
            )

    def moment_of_inertia(self) -> float:
        """Per-wheel moment of inertia ``I = ½·m_w·(R_outer² + R_inner²)`` in kg·m²."""
        r_o = self.outer_radius.m
        r_i = self.inner_radius.m
        return 0.5 * self.wheel_mass.kg * (r_o**2 + r_i**2)


@dataclass(frozen=True)
class BodyShape:
    """The car body's aerodynamic properties (physics-spec §3.1).

    Raises ``ValueError`` if ``drag_coefficient`` or ``frontal_area`` is non-finite
    or ``<= 0``.
    """

    drag_coefficient: float     # C_d
    frontal_area: float         # A [m²] (height × width)

    # Presets (assigned after the class body; declared here for typing/mypy strict).
    WEDGE: ClassVar[BodyShape]
    BLOCK: ClassVar[BodyShape]

    def __post_init__(self) -> None:
        if not math.isfinite(self.drag_coefficient) or self.drag_coefficient <= 0.0:
            raise ValueError(
                f"drag_coefficient must be a finite > 0, got {self.drag_coefficient}"
            )
        if not math.isfinite(self.frontal_area) or self.frontal_area <= 0.0:
            raise ValueError(
                f"frontal_area must be a finite > 0, got {self.frontal_area}"
            )


BodyShape.WEDGE = BodyShape(drag_coefficient=_CD_WEDGE, frontal_area=_DEFAULT_FRONTAL_AREA)
BodyShape.BLOCK = BodyShape(drag_coefficient=_CD_BLOCK, frontal_area=_DEFAULT_FRONTAL_AREA)


@dataclass(frozen=True)
class Axle:
    """The axle's friction (physics-spec §3.2).

    Raises ``ValueError`` if ``friction_coefficient`` is non-finite or ``< 0``.
    ``μ == 0`` (idealized frictionless) is allowed.
    """

    friction_coefficient: float     # μ_axle

    # Presets (assigned after the class body; declared here for typing/mypy strict).
    POLISHED_GRAPHITE: ClassVar[Axle]
    UNPREPARED: ClassVar[Axle]

    def __post_init__(self) -> None:
        if not math.isfinite(self.friction_coefficient) or self.friction_coefficient < 0.0:
            raise ValueError(
                f"friction_coefficient must be a finite >= 0, got "
                f"{self.friction_coefficient}"
            )


Axle.POLISHED_GRAPHITE = Axle(friction_coefficient=_MU_POLISHED_GRAPHITE)
Axle.UNPREPARED = Axle(friction_coefficient=_MU_UNPREPARED)


@dataclass(frozen=True)
class CarDesign:
    """An immutable, validated pinewood derby car design (TRD §3).

    Raises ``ValueError`` if the mass is non-finite or ``<= 0`` (AC-W3), the
    wheelbase is non-finite or ``<= 0``, or ``com_ahead_of_rear_axle`` is outside the
    open interval ``(0, wheelbase)`` (AC-P5). Over-weight (``mass > 5.0 oz``) is *not*
    an error; it is reported downstream as ``legal_weight = False`` (AC-W2 / A1).

    Cross-field invariant (WI3-F4): ``M`` is the *total* mass — chassis + wheels
    (physics-spec §2.1) — so the wheels in contact cannot out-mass (or equal) the
    whole car; ``count_touching · wheel_mass < mass`` must hold, leaving a positive
    chassis mass. Otherwise construction raises ``ValueError``.
    """

    mass: Mass                          # M (chassis + wheels)
    com_ahead_of_rear_axle: Length      # d_COM
    wheelbase: Length                   # L
    wheels: Wheels
    body: BodyShape
    axle: Axle
    alignment: Alignment

    def __post_init__(self) -> None:
        m = self.mass.kg
        if not math.isfinite(m) or m <= 0.0:
            raise ValueError(f"mass must be a finite > 0, got {m} kg")
        wheelbase = self.wheelbase.m
        if not math.isfinite(wheelbase) or wheelbase <= 0.0:
            raise ValueError(f"wheelbase must be a finite > 0, got {wheelbase} m")
        d_com = self.com_ahead_of_rear_axle.m
        if not math.isfinite(d_com) or not (0.0 < d_com < wheelbase):
            raise ValueError(
                f"com_ahead_of_rear_axle must be in (0, wheelbase) = "
                f"(0, {wheelbase}) m, got {d_com} m"
            )
        wheels_mass = self.wheels.count_touching * self.wheels.wheel_mass.kg
        if wheels_mass >= m:
            raise ValueError(
                f"wheels mass (count_touching * wheel_mass = {wheels_mass} kg) must be "
                f"< total mass ({m} kg) to leave a positive chassis mass"
            )
