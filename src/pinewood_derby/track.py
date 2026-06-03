"""Track model: validated geometry, ``angle_at(position)``, and ``STANDARD_TRACK``.

The track is a frozen, validated input to the engine (PRD §6 Track, TRD §3/§6,
physics-spec §1.2). It is composed of three zones along the car's arc-position ``s``:

- **Ramp** ``[0, ramp_length]`` — a straight incline at the constant ``ramp_angle``.
- **Transition** ``(ramp_length, ramp_length + arc_length]`` — a smooth circular arc
  that sheds the angle from ``ramp_angle`` down to ``0`` so the normal force does not
  spike at an abrupt corner (spec §1.2). Its arc length is ``transition_radius·θ``.
- **Flat** — the horizontal runout at angle ``0``.

``angle_at`` is therefore continuous and monotonically non-increasing from the ramp
angle to ``0``. The model is pure: no clock, network, or RNG.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .units import Angle, Length

# Standard competition track (physics-spec §1.2; PRD/TRD pin "~32 ft flat").
_STD_RAMP_FEET = 10.0
_STD_RAMP_DEGREES = 30.0
_STD_FLAT_FEET = 32.0
_STD_TRANSITION_INCHES = 6.0


@dataclass(frozen=True)
class Track:
    """A validated, immutable derby track (ramp → transition arc → flat).

    Raises ``ValueError`` if any length is non-finite or ``<= 0``, the ramp angle is
    outside the open interval ``(0°, 90°)``, the transition radius is non-finite or
    ``< 0``, or the transition arc (``transition_radius·ramp_angle``) does not fit
    within the flat zone (which would leave the declared "flat" still inclined).
    """

    ramp_length: Length
    ramp_angle: Angle
    transition_radius: Length
    flat_length: Length

    def __post_init__(self) -> None:
        if not math.isfinite(self.ramp_length.m) or self.ramp_length.m <= 0.0:
            raise ValueError(f"ramp_length must be a finite > 0, got {self.ramp_length.m} m")
        if not math.isfinite(self.flat_length.m) or self.flat_length.m <= 0.0:
            raise ValueError(f"flat_length must be a finite > 0, got {self.flat_length.m} m")
        if not (0.0 < self.ramp_angle.radians < 1.5707963267948966):  # 0 < θ < 90°
            raise ValueError(
                f"ramp_angle must be in (0°, 90°), got {self.ramp_angle.degrees}°"
            )
        if not math.isfinite(self.transition_radius.m) or self.transition_radius.m < 0.0:
            raise ValueError(
                f"transition_radius must be a finite >= 0, got {self.transition_radius.m} m"
            )
        # The transition arc (s = R·θ) is consumed within the flat zone; if it is
        # longer than the flat, the car is still inclined at the declared track end —
        # a geometrically inconsistent "flat that is still steep" (spec §1.2).
        arc_length = self.transition_radius.m * self.ramp_angle.radians
        if arc_length > self.flat_length.m:
            raise ValueError(
                f"transition arc ({arc_length} m) must fit within the flat zone "
                f"({self.flat_length.m} m); the declared flat would still be inclined"
            )

    def angle_at(self, position_m: float) -> float:
        """Track angle (radians) at arc-position ``position_m`` along the track.

        Returns the constant ramp angle on the ramp, ``0`` on the flat, and a
        continuous, monotonic linear interpolation through the transition arc. The
        result is clamped to ``[0, ramp_angle]``.
        """
        ramp_len = self.ramp_length.m
        ramp_angle = self.ramp_angle.radians

        if position_m <= ramp_len:
            return ramp_angle

        # Arc length over which the full ramp angle is shed (s = R·θ).
        arc_length = self.transition_radius.m * ramp_angle
        if arc_length <= 0.0:
            # Sharp transition (radius 0): angle drops to flat immediately past the ramp.
            return 0.0

        into_arc = position_m - ramp_len
        if into_arc >= arc_length:
            return 0.0

        # Linear blend from ramp_angle (start of arc) down to 0 (end of arc).
        return ramp_angle * (1.0 - into_arc / arc_length)


STANDARD_TRACK = Track(
    ramp_length=Length.from_feet(_STD_RAMP_FEET),
    ramp_angle=Angle.from_degrees(_STD_RAMP_DEGREES),
    transition_radius=Length.from_inches(_STD_TRANSITION_INCHES),
    flat_length=Length.from_feet(_STD_FLAT_FEET),
)
