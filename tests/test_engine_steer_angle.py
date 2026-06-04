"""Continuous steer-angle alignment lever (physics-spec §3.3, extended).

The alignment lever is a smooth *valley* in steer angle rather than an on/off enum:

- 0° (no steer) → the car ping-pongs between both rails (most rail loss).
- ~3° (the rail-rider sweet spot) → it rides one rail with minimal, steady drag (least loss).
- well past 3° → the steered wheel scrubs the rail and loses speed again.

These behavior-driven tests pin the new lever against the engine's public contract
(``simulate`` + ``RaceResult``/``EnergyLedger`` + ``CarDesign.effective_steer_deg``). They
also pin the back-compatibility guarantee that anchors the additive design: ``steer_angle_deg``
0° reproduces the legacy ``Alignment.STRAIGHT`` result bit-for-bit, and the sweet spot
reproduces ``Alignment.RAIL_RIDER`` bit-for-bit, so no existing test changes meaning.

Determinism: every test fixes ``dt`` and ``seed``. This file is NEW; it modifies, skips, or
deletes no existing test.
"""

from __future__ import annotations

import pytest

from pinewood_derby.car import (
    RAIL_RIDER_STEER_DEG,
    STRAIGHT_STEER_DEG,
    Alignment,
    Axle,
    BodyShape,
    CarDesign,
    Wheels,
)
from pinewood_derby.engine import simulate
from pinewood_derby.result import Outcome
from pinewood_derby.track import STANDARD_TRACK
from pinewood_derby.units import Length, Mass


def _car(*, steer: float | None = None, alignment: Alignment = Alignment.RAIL_RIDER) -> CarDesign:
    """A finished-capable baseline; only the alignment lever varies across a comparison."""
    return CarDesign(
        mass=Mass.from_ounces(5.0),
        com_ahead_of_rear_axle=Length.from_inches(0.85),
        wheelbase=Length.from_inches(4.375),
        wheels=Wheels(
            count_touching=4,
            wheel_mass=Mass.from_ounces(0.09),
            outer_radius=Length.from_inches(0.595),
            inner_radius=Length.from_inches(0.37),
            axle_radius=Length.from_inches(0.045),
        ),
        body=BodyShape(drag_coefficient=0.30, frontal_area=0.0028),
        axle=Axle(friction_coefficient=0.20),
        alignment=alignment,
        steer_angle_deg=steer,
    )


def _time(steer: float) -> float:
    result = simulate(_car(steer=steer), STANDARD_TRACK, dt=1e-3, seed=0)
    assert result.race_time_s is not None, f"steer={steer}° should FINISH"
    return result.race_time_s


# ── effective_steer_deg: the enum maps onto the steer axis; explicit value wins ──────────
def test_effective_steer_derives_from_enum_when_unset() -> None:
    assert _car(alignment=Alignment.STRAIGHT).effective_steer_deg == STRAIGHT_STEER_DEG
    assert _car(alignment=Alignment.RAIL_RIDER).effective_steer_deg == RAIL_RIDER_STEER_DEG


def test_explicit_steer_overrides_the_enum() -> None:
    assert _car(steer=7.0, alignment=Alignment.STRAIGHT).effective_steer_deg == 7.0


# ── Back-compat: the endpoints reproduce the legacy enum bit-for-bit ─────────────────────
def test_zero_steer_reproduces_straight_bit_for_bit() -> None:
    by_steer = simulate(_car(steer=0.0), STANDARD_TRACK, dt=1e-3, seed=0)
    by_enum = simulate(_car(alignment=Alignment.STRAIGHT), STANDARD_TRACK, dt=1e-3, seed=0)
    assert by_steer == by_enum


def test_sweet_spot_reproduces_rail_rider_bit_for_bit() -> None:
    by_steer = simulate(_car(steer=RAIL_RIDER_STEER_DEG), STANDARD_TRACK, dt=1e-3, seed=0)
    by_enum = simulate(_car(alignment=Alignment.RAIL_RIDER), STANDARD_TRACK, dt=1e-3, seed=0)
    assert by_steer == by_enum


# ── The valley: the sweet spot is faster than both too-little and too-much steer ─────────
def test_sweet_spot_beats_no_steer_pingpong() -> None:
    assert _time(RAIL_RIDER_STEER_DEG) < _time(0.0)


def test_sweet_spot_beats_over_steer() -> None:
    assert _time(RAIL_RIDER_STEER_DEG) < _time(8.0)


def test_over_steer_loses_more_to_the_rail_than_the_sweet_spot() -> None:
    sweet = simulate(_car(steer=RAIL_RIDER_STEER_DEG), STANDARD_TRACK, dt=1e-3, seed=0)
    over = simulate(_car(steer=9.0), STANDARD_TRACK, dt=1e-3, seed=0)
    assert over.energy.w_rail > sweet.energy.w_rail


def test_over_steer_still_finishes_it_is_a_slowdown_not_a_dnf() -> None:
    over = simulate(_car(steer=10.0), STANDARD_TRACK, dt=1e-3, seed=0)
    assert over.outcome is Outcome.FINISHED


# ── A pinned (steer ≥ sweet spot) car is RNG-free; an under-steered one varies by seed ───
def test_pinned_car_is_seed_independent() -> None:
    a = simulate(_car(steer=5.0), STANDARD_TRACK, dt=1e-3, seed=1)
    b = simulate(_car(steer=5.0), STANDARD_TRACK, dt=1e-3, seed=98765)
    assert a == b


def test_under_steered_car_still_ping_pongs_and_varies_by_seed() -> None:
    a = simulate(_car(steer=1.0), STANDARD_TRACK, dt=1e-3, seed=1)
    b = simulate(_car(steer=1.0), STANDARD_TRACK, dt=1e-3, seed=2)
    assert a.energy.w_rail != b.energy.w_rail


# ── Validation ───────────────────────────────────────────────────────────────────────────
def test_negative_steer_angle_raises() -> None:
    with pytest.raises(ValueError, match="steer_angle_deg"):
        _car(steer=-1.0)
