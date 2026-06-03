"""WI-10 — Alignment / rail lever: a RAIL_RIDER car beats an otherwise-identical
STRAIGHT (ping-ponging) car, the STRAIGHT rail friction is a seeded draw in the spec's
[1.5, 3.0] N band whose energy is reported and reproducible, and RAIL_RIDER results are
seed-independent while STRAIGHT results vary by seed.

Behavior-driven tests written against the engine's PUBLIC contract (``simulate`` + the
frozen ``RaceResult`` / ``EnergyLedger``). Imports live inside each test body so a
missing/renamed symbol fails *that criterion* independently (per-criterion isolation)
rather than aborting whole-file collection. Mirrors the helper style of
tests/test_engine_friction_wi9.py so construction stays consistent.

Traceability to the WI-10 acceptance criteria (PRD §6; physics-spec §3.3/§5; TRD §4):

- AC-AL1 (PRD l.131): a RAIL_RIDER car (constant rail force) is strictly faster
  (smaller ``race_time_s``) than the otherwise-identical STRAIGHT (ping-ponging) car for
  a fixed seed. The directional claim — rail-riding loses *less* to the rail than
  ping-ponging, so it is faster — is the educational point of the lever (rail-riding is a
  real winning technique). The spec pins the RAIL_RIDER force at 0.05 N; the engine
  currently uses a larger constant, which is flagged here for adversarial review, but the
  *direction* (RAIL_RIDER faster) is a hard correctness requirement regardless of the
  exact magnitude.

- AC-AL2 (PRD l.133): STRAIGHT-alignment rail friction is drawn from the seeded RNG
  within [1.5, 3.0] N per step; the reported ``energy.w_rail`` reflects that draw
  (``w_rail > 0`` for a moving STRAIGHT car, ``w_rail == 0`` for a car that never moves —
  a stationary car cannot bounce off the rail); and repeated calls with the same seed
  produce the identical ``w_rail`` (reproducible).

- AC-AL3 (PRD l.136): RAIL_RIDER results are seed-independent (a bit-identical
  ``RaceResult`` across different seeds for the same car/track/dt — the rail-riding path
  consumes no RNG), while STRAIGHT results vary by seed (at least one differing observable
  field across two distinct seeds — the ping-pong path consumes the RNG); and identical
  ``(car, track, dt, seed)`` yields a bit-identical ``RaceResult`` on repeated calls.

Integrity / determinism: every test fixes ``dt`` and ``seed`` (no clock / network /
unseeded RNG). Assertions are directional / bound-based / equality-of-output — never a
magic interior magnitude beyond the spec-anchored [1.5, 3.0] N rail band and the spec's
0.05 N RAIL_RIDER constant. This file is NEW; it modifies, skips, or deletes no existing
test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult
    from pinewood_derby.track import Track

# Spec-anchored rail constants (physics-spec §3.3; PRD AC-AL1/AC-AL2), pinned here so the
# comparison references the contract rather than the engine's private constants.
RAIL_RIDER_FORCE_N = 0.05            # constant rail force for a RAIL_RIDER car (spec)
PINGPONG_RANGE_N = (1.5, 3.0)        # U(min, max) ping-pong spike band for a STRAIGHT car


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — build valid inputs from plain numbers via the value objects.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_car(
    *,
    mass_oz: float = 5.0,
    com_ahead_of_rear_axle_in: float = 0.85,
    wheelbase_in: float = 4.375,
    alignment: str = "STRAIGHT",
    count_touching: int = 4,
    wheel_oz: float = 0.09,
    outer_radius_in: float = 0.595,
    inner_radius_in: float = 0.37,
    axle_radius_in: float = 0.045,
    drag_coefficient: float = 0.30,
    frontal_area: float = 0.0028,
    friction_coefficient: float = 0.20,
) -> CarDesign:
    """A valid, FINISHED-capable baseline car. ``alignment`` is the enum member name.

    Only ``alignment`` (and, for the at-rest test, ``com_ahead_of_rear_axle_in``) is
    varied across each comparison; everything else is held identical so each test
    isolates exactly the alignment lever ("all else equal").
    """
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(wheelbase_in),
        wheels=Wheels(
            count_touching=count_touching,
            wheel_mass=Mass.from_ounces(wheel_oz),
            outer_radius=Length.from_inches(outer_radius_in),
            inner_radius=Length.from_inches(inner_radius_in),
            axle_radius=Length.from_inches(axle_radius_in),
        ),
        body=BodyShape(drag_coefficient=drag_coefficient, frontal_area=frontal_area),
        axle=Axle(friction_coefficient=friction_coefficient),
        alignment=Alignment[alignment],
    )


def _simulate(
    car: CarDesign,
    track: Track | None = None,
    *,
    dt: float = 1e-3,
    seed: int = 0,
) -> RaceResult:
    from pinewood_derby.engine import simulate

    if track is None:
        return simulate(car, dt=dt, seed=seed)
    return simulate(car, track, dt=dt, seed=seed)


def _finished(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.FINISHED


# ───────────────────────────────────────────────────────────────────────────── #
# AC-AL1 — RAIL_RIDER is strictly faster than STRAIGHT, all else equal, fixed seed.
# (physics-spec §3.3/§5)
# ───────────────────────────────────────────────────────────────────────────── #
def test_acal1_rail_rider_finishes_strictly_faster_than_straight() -> None:
    """Two cars identical except alignment — RAIL_RIDER (constant, low rail force) vs
    STRAIGHT (ping-ponging) — both FINISHED for a fixed seed: the rail-rider must finish
    strictly sooner. A car that glides consistently along one rail wastes less energy to
    rail contact than one that bounces wall-to-wall, so it carries more speed and crosses
    the line earlier. This is the educational claim of the alignment lever and is the
    direction the engine must honor regardless of the exact rail-force magnitude."""
    from pinewood_derby.track import STANDARD_TRACK

    rail_rider = _simulate(_make_car(alignment="RAIL_RIDER"), STANDARD_TRACK, seed=0)
    straight = _simulate(_make_car(alignment="STRAIGHT"), STANDARD_TRACK, seed=0)

    assert _finished(rail_rider), "RAIL_RIDER car should FINISH for a valid comparison"
    assert _finished(straight), "STRAIGHT car should FINISH for a valid comparison"
    assert rail_rider.race_time_s is not None and straight.race_time_s is not None
    assert rail_rider.race_time_s < straight.race_time_s, (
        f"RAIL_RIDER ({rail_rider.race_time_s:.6f}s) must beat the ping-ponging STRAIGHT "
        f"car ({straight.race_time_s:.6f}s) — rail-riding loses less energy to the rail"
    )


def test_acal1_rail_rider_loses_less_energy_to_the_rail_than_straight() -> None:
    """The mechanism behind the faster time: the rail-rider's reported rail energy
    ``energy.w_rail`` must be strictly less than the ping-ponging STRAIGHT car's, all else
    equal, fixed seed. Less energy drained by the rail is exactly why rail-riding wins."""
    from pinewood_derby.track import STANDARD_TRACK

    rail_rider = _simulate(_make_car(alignment="RAIL_RIDER"), STANDARD_TRACK, seed=0)
    straight = _simulate(_make_car(alignment="STRAIGHT"), STANDARD_TRACK, seed=0)

    assert _finished(rail_rider) and _finished(straight)
    assert rail_rider.energy.w_rail < straight.energy.w_rail, (
        f"RAIL_RIDER rail energy ({rail_rider.energy.w_rail:.6f} J) must be below the "
        f"STRAIGHT car's ({straight.energy.w_rail:.6f} J) — the rail-rider that wastes "
        f"less to rail contact is the one that finishes faster"
    )


def test_acal1_rail_rider_reaches_higher_finish_velocity_than_straight() -> None:
    """A second observable consequence of the directional claim: with less rail drag, the
    rail-rider carries strictly more speed across the line than the ping-ponging car."""
    from pinewood_derby.track import STANDARD_TRACK

    rail_rider = _simulate(_make_car(alignment="RAIL_RIDER"), STANDARD_TRACK, seed=0)
    straight = _simulate(_make_car(alignment="STRAIGHT"), STANDARD_TRACK, seed=0)

    assert _finished(rail_rider) and _finished(straight)
    assert rail_rider.finish_velocity > straight.finish_velocity, (
        f"RAIL_RIDER finish velocity ({rail_rider.finish_velocity:.4f} m/s) should exceed "
        f"the STRAIGHT car's ({straight.finish_velocity:.4f} m/s)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-AL2 — STRAIGHT rail friction is a seeded draw within [1.5, 3.0] N per step; the
# reported energy.w_rail reflects it (>0 moving, 0 at rest) and is reproducible.
# (physics-spec §3.3)
# ───────────────────────────────────────────────────────────────────────────── #
def test_acal2_straight_perstep_rail_force_is_within_pingpong_band() -> None:
    """Every per-step STRAIGHT rail-friction draw for a moving car must land inside the
    spec's ping-pong band [1.5, 3.0] N. The engine exposes the per-step rail force via the
    module-level ``_rail_force`` helper that the integration loop calls each step; we drive
    it with a seeded ``random.Random`` exactly as ``simulate`` does and assert the drawn
    force stays in band over many draws. This pins AC-AL2's literal claim — 'rail friction
    is drawn from the seeded RNG within [1.5, 3.0] N per step' — against the observable
    force the car actually experiences while moving."""
    import random

    from pinewood_derby.car import Alignment
    from pinewood_derby.engine import _rail_force

    lo, hi = PINGPONG_RANGE_N
    rng = random.Random(0)
    forces = [
        _rail_force(Alignment.STRAIGHT, rng, velocity=2.5) for _ in range(2000)
    ]
    assert all(f > 0.0 for f in forces), "a moving STRAIGHT car must feel a rail force"
    assert min(forces) >= lo, (
        f"the smallest STRAIGHT per-step rail force ({min(forces):.6f} N) is below the "
        f"spec's ping-pong floor of {lo} N — the draw is not in the [1.5, 3.0] N band"
    )
    assert max(forces) <= hi, (
        f"the largest STRAIGHT per-step rail force ({max(forces):.6f} N) is above the "
        f"spec's ping-pong ceiling of {hi} N — the draw is not in the [1.5, 3.0] N band"
    )


def test_acal2_moving_straight_car_reports_positive_w_rail() -> None:
    """A STRAIGHT car that actually moves down the track loses energy to the rail, so its
    reported ``energy.w_rail`` is strictly positive (the draw is reflected in the ledger)."""
    from pinewood_derby.track import STANDARD_TRACK

    straight = _simulate(_make_car(alignment="STRAIGHT"), STANDARD_TRACK, seed=0)

    assert _finished(straight), "STRAIGHT car should FINISH so it travels the full track"
    assert straight.energy.w_rail > 0.0, (
        f"a moving STRAIGHT car must report positive rail energy, got "
        f"{straight.energy.w_rail:.6e} J"
    )


def test_acal2_car_that_never_moves_reports_zero_w_rail() -> None:
    """A car that never leaves the start line cannot bounce off the rail, so its reported
    rail energy is exactly zero. An unstable rear bias (d_COM below the stability cliff) is
    a DNF that never moves — the at-rest case AC-AL2 names. ``w_rail`` must be 0.0 even for
    a STRAIGHT alignment, because no rail contact work is done while stationary."""
    from pinewood_derby.track import STANDARD_TRACK

    at_rest = _simulate(
        _make_car(alignment="STRAIGHT", com_ahead_of_rear_axle_in=0.15),
        STANDARD_TRACK,
        seed=0,
    )

    assert not _finished(at_rest), "an unstable car (d_COM < cliff) should be a DNF at rest"
    assert at_rest.race_time_s is None
    assert at_rest.energy.w_rail == 0.0, (
        f"a car that never moves must report exactly zero rail energy, got "
        f"{at_rest.energy.w_rail:.6e} J"
    )


def test_acal2_straight_w_rail_is_reproducible_for_a_fixed_seed() -> None:
    """The seeded ping-pong path is deterministic: two STRAIGHT runs with the same seed
    must report a bit-identical ``energy.w_rail``. Reproducibility of the random draw is a
    hard requirement (AC-AL2) — same seed in, same rail energy out."""
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(alignment="STRAIGHT")
    first = _simulate(car, STANDARD_TRACK, seed=7)
    second = _simulate(car, STANDARD_TRACK, seed=7)

    assert first.energy.w_rail == second.energy.w_rail, (
        f"a fixed-seed STRAIGHT run must reproduce w_rail bit-for-bit: "
        f"{first.energy.w_rail!r} vs {second.energy.w_rail!r}"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-AL3 — RAIL_RIDER is seed-independent; STRAIGHT varies by seed; identical
# (car, track, dt, seed) is bit-identical on repeat. (physics-spec §3.3)
# ───────────────────────────────────────────────────────────────────────────── #
def test_acal3_rail_rider_is_bit_identical_across_different_seeds() -> None:
    """RAIL_RIDER consumes no RNG (constant rail force), so the same car/track/dt under
    two distinct seeds must produce a bit-identical ``RaceResult`` — outcome, time,
    velocities, full energy ledger, normal forces, and the entire trajectory. The seed is
    irrelevant for a rail-rider."""
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(alignment="RAIL_RIDER")
    a = _simulate(car, STANDARD_TRACK, seed=1)
    b = _simulate(car, STANDARD_TRACK, seed=98765)

    assert a == b, (
        "RAIL_RIDER results must be seed-independent (bit-identical RaceResult across "
        f"distinct seeds); got differing results:\n  seed=1:     {a}\n  seed=98765: {b}"
    )


def test_acal3_straight_varies_by_seed() -> None:
    """STRAIGHT consumes the seeded RNG for its ping-pong draws, so two distinct seeds
    must differ in at least one observable field. Here ``energy.w_rail`` (the accumulated
    rail loss) is the field most directly driven by the random draw; it must differ."""
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(alignment="STRAIGHT")
    a = _simulate(car, STANDARD_TRACK, seed=1)
    b = _simulate(car, STANDARD_TRACK, seed=2)

    assert a.energy.w_rail != b.energy.w_rail, (
        f"STRAIGHT rail energy must vary by seed (the ping-pong path is RNG-driven); both "
        f"seeds gave w_rail={a.energy.w_rail!r}"
    )
    assert a != b, (
        "two distinct seeds must yield differing STRAIGHT RaceResults (at least one field)"
    )


def test_acal3_identical_inputs_are_bit_identical_on_repeat() -> None:
    """Determinism for the full RaceResult: identical ``(car, track, dt, seed)`` must yield
    a bit-identical result on a repeated call, including the random STRAIGHT ping-pong
    path. This is the core reproducibility guarantee the seeded engine promises."""
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(alignment="STRAIGHT")
    first = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=42)
    second = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=42)

    assert first == second, (
        "identical (car, track, dt, seed) must produce a bit-identical RaceResult on "
        f"repeat; got:\n  first:  {first}\n  second: {second}"
    )
