"""WI-2 — Track model: validation, angle_at(position), STANDARD_TRACK constant.

Behavior-driven RED tests, written before implementation. The module
``pinewood_derby.track`` does not exist yet, so each test imports it inside the test
body: a missing module then fails each criterion *independently* (true per-criterion
RED) instead of aborting whole-file collection with a single import error.

Traceability to the WI-2 acceptance criteria (PRD §6 Track; TRD §3 data model, §6
validation; physics-spec §1.2):

- AC-T3 (validation): any length <= 0, ramp_angle not in (0°, 90°), or
  transition_radius < 0 raises ValueError; valid tracks construct successfully.
- AC-T3 (constant): a STANDARD_TRACK constant exists matching the spec
  (10 ft ramp @ 30°, transition arc, ~32 ft flat).
- AC-T2 (angle_at): returns the ramp angle while on the ramp, 0 on the flat, and a
  continuous, monotonic interpolation through the transition arc with no discontinuous
  jump (verified at the ramp/arc/flat boundaries).
- Immutability: Track is a frozen, validated input object (supports AC-T1's
  'explicit validated input').

All tests are deterministic: no clock, network, or RNG. Track geometry is pure.
"""

from __future__ import annotations

import dataclasses
import math
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pinewood_derby.track import Track

# Spec-anchored constants (physics-spec §1.2). Mirrored here so assertions are anchored
# to the spec, not to whatever magic numbers the implementation happens to pick.
RAMP_FEET = 10.0
RAMP_DEGREES = 30.0
FLAT_FEET_MIN = 25.0
FLAT_FEET_MAX = 32.0
FLAT_FEET_NOMINAL = 32.0  # PRD AC-T3 / TRD §3: "~32 ft flat"

FT_TO_M = 0.3048  # 12 * 0.0254

ABS_TOL = 1e-9


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers
# ───────────────────────────────────────────────────────────────────────────── #
def _make_track(
    *,
    ramp_feet: float = RAMP_FEET,
    ramp_degrees: float = RAMP_DEGREES,
    transition_inches: float = 6.0,
    flat_feet: float = FLAT_FEET_NOMINAL,
) -> Track:
    """Construct a valid Track from plain numbers via the unit value objects."""
    from pinewood_derby.track import Track
    from pinewood_derby.units import Angle, Length

    return Track(
        ramp_length=Length.from_feet(ramp_feet),
        ramp_angle=Angle.from_degrees(ramp_degrees),
        transition_radius=Length.from_inches(transition_inches),
        flat_length=Length.from_feet(flat_feet),
    )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-T3 — validation: invalid tracks raise ValueError
# ───────────────────────────────────────────────────────────────────────────── #
def test_act3_valid_track_constructs_successfully() -> None:
    """A track with all-valid inputs constructs without raising (the positive case)."""
    track = _make_track()
    from pinewood_derby.track import Track

    assert isinstance(track, Track)


def test_act3_zero_ramp_length_raises() -> None:
    with pytest.raises(ValueError):
        _make_track(ramp_feet=0.0)


def test_act3_negative_ramp_length_raises() -> None:
    with pytest.raises(ValueError):
        _make_track(ramp_feet=-1.0)


def test_act3_zero_flat_length_raises() -> None:
    with pytest.raises(ValueError):
        _make_track(flat_feet=0.0)


def test_act3_negative_flat_length_raises() -> None:
    with pytest.raises(ValueError):
        _make_track(flat_feet=-5.0)


def test_act3_ramp_angle_at_or_below_zero_raises() -> None:
    """ramp_angle must be strictly > 0° (open lower bound)."""
    with pytest.raises(ValueError):
        _make_track(ramp_degrees=0.0)
    with pytest.raises(ValueError):
        _make_track(ramp_degrees=-10.0)


def test_act3_ramp_angle_at_or_above_ninety_raises() -> None:
    """ramp_angle must be strictly < 90° (open upper bound)."""
    with pytest.raises(ValueError):
        _make_track(ramp_degrees=90.0)
    with pytest.raises(ValueError):
        _make_track(ramp_degrees=120.0)


def test_act3_negative_transition_radius_raises() -> None:
    with pytest.raises(ValueError):
        _make_track(transition_inches=-0.5)


def test_act3_zero_transition_radius_is_valid_sharp_transition() -> None:
    """transition_radius == 0 is the boundary the rule *allows* (>= 0): a sharp corner.

    The rule is `transition_radius < 0` raises; 0 must NOT raise. This pins the
    inclusive boundary so the implementation cannot over-reject.
    """
    track = _make_track(transition_inches=0.0)
    from pinewood_derby.track import Track

    assert isinstance(track, Track)


def test_act3_interior_angles_construct_successfully() -> None:
    """Angles strictly inside (0°, 90°) are all valid."""
    for deg in (1.0, 15.0, 30.0, 45.0, 89.0):
        track = _make_track(ramp_degrees=deg)
        assert track.ramp_angle.degrees == pytest.approx(deg, abs=1e-9)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-T3 — STANDARD_TRACK constant matches the spec
# ───────────────────────────────────────────────────────────────────────────── #
def test_act3_standard_track_exists_and_is_a_track() -> None:
    from pinewood_derby.track import STANDARD_TRACK, Track

    assert isinstance(STANDARD_TRACK, Track)


def test_act3_standard_track_ramp_is_ten_feet_at_thirty_degrees() -> None:
    from pinewood_derby.track import STANDARD_TRACK

    assert STANDARD_TRACK.ramp_length.feet == pytest.approx(RAMP_FEET, abs=1e-9)
    assert STANDARD_TRACK.ramp_angle.degrees == pytest.approx(RAMP_DEGREES, abs=1e-9)


def test_act3_standard_track_flat_is_about_thirty_two_feet() -> None:
    """Spec §1.2: flat is a 25–32 ft runout; PRD/TRD pin '~32 ft'."""
    from pinewood_derby.track import STANDARD_TRACK

    flat_ft = STANDARD_TRACK.flat_length.feet
    assert FLAT_FEET_MIN <= flat_ft <= FLAT_FEET_MAX
    assert flat_ft == pytest.approx(FLAT_FEET_NOMINAL, abs=0.5)


def test_act3_standard_track_has_nonnegative_transition_arc() -> None:
    """Spec models a smooth circular-arc transition; a real arc has radius > 0."""
    from pinewood_derby.track import STANDARD_TRACK

    assert STANDARD_TRACK.transition_radius.m > 0.0


# ───────────────────────────────────────────────────────────────────────────── #
# Immutability — Track is a frozen, validated input object (supports AC-T1)
# ───────────────────────────────────────────────────────────────────────────── #
def test_track_is_frozen_dataclass() -> None:
    from pinewood_derby.track import Track
    from pinewood_derby.units import Length

    track = _make_track()
    assert dataclasses.is_dataclass(Track)
    assert track.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    with pytest.raises(dataclasses.FrozenInstanceError):
        track.flat_length = Length.from_feet(1.0)  # type: ignore[misc]


def test_track_equal_by_value() -> None:
    """Frozen dataclasses compare by value — needed for use as a validated input."""
    assert _make_track() == _make_track()


# ───────────────────────────────────────────────────────────────────────────── #
# AC-T2 — angle_at(position): ramp angle on ramp, 0 on flat, continuous monotonic arc
# ───────────────────────────────────────────────────────────────────────────── #
def _ramp_angle_rad() -> float:
    return math.radians(RAMP_DEGREES)


def test_act2_angle_on_ramp_equals_ramp_angle() -> None:
    """Anywhere strictly on the ramp, angle_at returns the constant ramp angle."""
    track = _make_track()
    ramp_len_m = track.ramp_length.m
    expected = _ramp_angle_rad()
    # Sample interior points of the ramp (avoid the very end where the arc begins).
    for frac in (0.0, 0.1, 0.5, 0.9):
        pos = frac * ramp_len_m * 0.95  # stay clear of the transition zone
        assert track.angle_at(pos) == pytest.approx(expected, abs=1e-9)


def test_act2_angle_on_flat_is_zero() -> None:
    """Deep on the flat, angle_at returns 0."""
    track = _make_track()
    total = track.ramp_length.m + track.flat_length.m
    # Sample well past the transition, into the flat runout.
    start_of_flat = track.ramp_length.m + track.transition_radius.m * math.pi
    for pos in (start_of_flat + 0.5, (start_of_flat + total) / 2.0, total):
        assert track.angle_at(pos) == pytest.approx(0.0, abs=1e-9)


def test_act2_angle_is_continuous_no_discontinuous_jump() -> None:
    """The piecewise angle profile is continuous: small steps in position produce
    small steps in angle (no abrupt cliff at the ramp/arc/flat boundaries).

    We bound the per-sample angle change. A discontinuous jump (e.g. ramp angle ->
    0 with no arc, or a sign flip) would exceed the bound and fail.
    """
    track = _make_track()
    total = track.ramp_length.m + track.flat_length.m
    n = 4000
    dx = total / n
    prev = track.angle_at(0.0)
    # Continuity bound: the angle can change by at most a small amount per dx.
    # The whole ramp_angle is shed across the arc; arc_len ~= R * ramp_angle.
    # max slope = ramp_angle / arc_len = 1/R rad per metre. Allow generous slack.
    max_slope = 1.0 / track.transition_radius.m
    bound = max_slope * dx * 3.0 + 1e-6
    for i in range(1, n + 1):
        pos = i * dx
        cur = track.angle_at(pos)
        assert abs(cur - prev) <= bound, (
            f"discontinuous jump at position {pos:.4f} m: "
            f"{prev:.6f} -> {cur:.6f} (bound {bound:.6f})"
        )
        prev = cur


def test_act2_angle_is_monotonic_nonincreasing() -> None:
    """Through the transition the angle decreases monotonically from the ramp angle
    down to 0 — it never rises back up (no overshoot / oscillation)."""
    track = _make_track()
    total = track.ramp_length.m + track.flat_length.m
    n = 4000
    dx = total / n
    prev = track.angle_at(0.0)
    tol = 1e-9
    for i in range(1, n + 1):
        cur = track.angle_at(i * dx)
        assert cur <= prev + tol, (
            f"angle increased at {i * dx:.4f} m: {prev:.6f} -> {cur:.6f}"
        )
        prev = cur


def test_act2_angle_spans_full_range_ramp_to_zero() -> None:
    """The profile actually starts at the ramp angle and ends at 0 — the interpolation
    spans the full range rather than collapsing to a constant."""
    track = _make_track()
    total = track.ramp_length.m + track.flat_length.m
    assert track.angle_at(0.0) == pytest.approx(_ramp_angle_rad(), abs=1e-9)
    assert track.angle_at(total) == pytest.approx(0.0, abs=1e-9)


def test_act2_arc_midpoint_is_strictly_between_ramp_and_flat() -> None:
    """Somewhere in the transition the angle takes an intermediate value strictly
    between the ramp angle and 0 — i.e. a real interpolation exists (not a step)."""
    track = _make_track()
    ramp_len_m = track.ramp_length.m
    arc_len = track.transition_radius.m * _ramp_angle_rad()
    mid = ramp_len_m + arc_len / 2.0
    a = track.angle_at(mid)
    assert 0.0 < a < _ramp_angle_rad()


def test_act2_angle_returns_radians_within_bounds() -> None:
    """angle_at returns radians, always within [0, ramp_angle] — never negative, never
    exceeding the ramp angle, across the whole track."""
    track = _make_track()
    total = track.ramp_length.m + track.flat_length.m
    ramp = _ramp_angle_rad()
    n = 500
    for i in range(n + 1):
        a = track.angle_at(i * total / n)
        assert math.isfinite(a)
        assert -1e-9 <= a <= ramp + 1e-9
