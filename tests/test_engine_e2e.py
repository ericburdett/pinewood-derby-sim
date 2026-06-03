"""WI-4 — Minimal end-to-end ``simulate()``: output contract, purity, determinism.

Behavior-driven RED tests, written before implementation. The modules
``pinewood_derby.engine`` and ``pinewood_derby.result`` do not exist yet, so each
test imports them inside the test body: a missing module then fails each criterion
*independently* (true per-criterion RED) instead of aborting whole-file collection
with a single import error.

Traceability to the WI-4 acceptance criteria (PRD §6 Output contract / Purity;
TRD §3 data model, §4 integration, §11 traceability):

- AC-O1: simulate(car, track, *, dt, seed) returns an immutable RaceResult exposing
  outcome, race_time_s (None iff not FINISHED), exit_velocity, top_speed,
  finish_velocity, energy, normal_forces (N_f, N_r), legal_weight, and a down-sampled
  trajectory (<= ~500 TrajectoryPoints of t/position/velocity/angle); all numeric
  outputs are finite and velocities >= 0.
- AC-O2: a FINISHED run has race_time_s > 0 and finite; a DNF run has
  race_time_s is None and outcome = DNF.
- AC-AL3 (determinism): identical (car, track, dt, seed) yields a bit-identical
  RaceResult across repeated calls, including the random STRAIGHT ping-pong path;
  RAIL_RIDER results are seed-independent.
- AC-PU1 (purity): the engine performs no file I/O and no network access, holds no
  module-level mutable state, and is composed of pure functions / frozen dataclasses
  (all randomness flows through a local random.Random(seed)); a default-baseline car
  on STANDARD_TRACK runs to a FINISHED outcome.
- AC-T1 (length-monotonicity slice): a longer total track yields a longer race_time_s
  for the same car.

All tests are deterministic: no clock, network, or RNG outside a fixed seed.
"""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult
    from pinewood_derby.track import Track

# Spec-anchored constants (mirrored from the spec/TRD, not the implementation).
RAIL_F_RAIL_RIDER = 0.05  # N (constant for RAIL_RIDER)
MAX_TRAJECTORY_POINTS = 500  # PRD A7 / TRD §4: down-sample to <= ~500 points
TRAJECTORY_TOLERANCE = 50  # allow a little slack around the "~500" target


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — build valid inputs from plain numbers via the existing value objects.
# The car helpers mirror tests/test_car.py so construction stays consistent.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_wheels(
    *,
    count_touching: int = 4,
    wheel_mass_oz: float = 0.09,
    outer_radius_in: float = 0.595,
    inner_radius_in: float = 0.37,
    axle_radius_in: float = 0.045,
) -> Any:
    from pinewood_derby.car import Wheels
    from pinewood_derby.units import Length, Mass

    return Wheels(
        count_touching=count_touching,
        wheel_mass=Mass.from_ounces(wheel_mass_oz),
        outer_radius=Length.from_inches(outer_radius_in),
        inner_radius=Length.from_inches(inner_radius_in),
        axle_radius=Length.from_inches(axle_radius_in),
    )


def _make_car(
    *,
    mass_oz: float = 5.0,
    com_ahead_of_rear_axle_in: float = 0.85,
    wheelbase_in: float = 4.375,
    alignment: str = "STRAIGHT",
    count_touching: int = 4,
    drag_coefficient: float = 0.30,
    frontal_area: float = 0.0028,
    friction_coefficient: float = 0.20,
) -> CarDesign:
    """A valid, FINISHED-capable baseline car. `alignment` is the enum member name."""
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(wheelbase_in),
        wheels=_make_wheels(count_touching=count_touching),
        body=BodyShape(drag_coefficient=drag_coefficient, frontal_area=frontal_area),
        axle=Axle(friction_coefficient=friction_coefficient),
        alignment=Alignment[alignment],
    )


def _make_track(
    *,
    ramp_feet: float = 10.0,
    ramp_degrees: float = 30.0,
    transition_inches: float = 6.0,
    flat_feet: float = 32.0,
) -> Track:
    from pinewood_derby.track import Track
    from pinewood_derby.units import Angle, Length

    return Track(
        ramp_length=Length.from_feet(ramp_feet),
        ramp_angle=Angle.from_degrees(ramp_degrees),
        transition_radius=Length.from_inches(transition_inches),
        flat_length=Length.from_feet(flat_feet),
    )


def _simulate(car: CarDesign, track: Track | None = None, *, dt: float = 1e-3, seed: int = 0) -> RaceResult:
    from pinewood_derby.engine import simulate

    if track is None:
        return simulate(car, dt=dt, seed=seed)
    return simulate(car, track, dt=dt, seed=seed)


def _finished_result(*, seed: int = 0) -> RaceResult:
    """A baseline car that should run to a FINISHED outcome on the STANDARD_TRACK."""
    from pinewood_derby.track import STANDARD_TRACK

    return _simulate(_make_car(), STANDARD_TRACK, dt=1e-3, seed=seed)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-O1 — RaceResult output contract: required fields, immutability, finiteness.
# ───────────────────────────────────────────────────────────────────────────── #
def test_aco1_simulate_returns_raceresult() -> None:
    from pinewood_derby.result import RaceResult

    result = _finished_result()
    assert isinstance(result, RaceResult)


def test_aco1_raceresult_exposes_all_required_fields() -> None:
    """The contract names every field the deferred UI / sign-off depends on."""
    result = _finished_result()
    for field in (
        "outcome",
        "race_time_s",
        "exit_velocity",
        "top_speed",
        "finish_velocity",
        "energy",
        "normal_forces",
        "legal_weight",
        "trajectory",
    ):
        assert hasattr(result, field), f"RaceResult missing required field: {field}"


def test_aco1_raceresult_is_frozen_immutable() -> None:
    from pinewood_derby.result import RaceResult

    result = _finished_result()
    assert dataclasses.is_dataclass(RaceResult)
    assert result.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.top_speed = 0.0  # type: ignore[misc]


def test_aco1_normal_forces_expose_front_and_rear() -> None:
    """normal_forces carries N_f (front) and N_r (rear), both finite and >= 0."""
    nf = _finished_result().normal_forces
    assert hasattr(nf, "front") and hasattr(nf, "rear")
    assert math.isfinite(nf.front) and math.isfinite(nf.rear)
    assert nf.front >= 0.0 and nf.rear >= 0.0


def test_aco1_energy_ledger_fields_are_finite() -> None:
    """The energy breakdown is exposed and every reported term is a finite number."""
    energy = _finished_result().energy
    for field in (
        "pe_initial",
        "ke_linear_final",
        "ke_rotational_final",
        "w_gravity",
        "w_drag",
        "w_axle",
        "w_rail",
    ):
        assert hasattr(energy, field), f"EnergyLedger missing field: {field}"
        assert math.isfinite(getattr(energy, field)), f"{field} is not finite"


def test_aco1_scalar_velocity_outputs_are_finite_and_nonnegative() -> None:
    """exit_velocity, top_speed, finish_velocity are finite and velocities >= 0."""
    result = _finished_result()
    for field in ("exit_velocity", "top_speed", "finish_velocity"):
        v = getattr(result, field)
        assert math.isfinite(v), f"{field} is not finite"
        assert v >= 0.0, f"{field} must be >= 0, got {v}"


def test_aco1_top_speed_is_the_maximum_velocity() -> None:
    """top_speed bounds every other reported velocity and every trajectory velocity —
    a behavioral invariant of 'top speed', not an arbitrary field."""
    result = _finished_result()
    assert result.top_speed >= result.exit_velocity - 1e-9
    assert result.top_speed >= result.finish_velocity - 1e-9
    for pt in result.trajectory:
        assert pt.velocity <= result.top_speed + 1e-9


def test_aco1_trajectory_is_downsampled_within_cap() -> None:
    """The trajectory is a non-empty, bounded down-sample (<= ~500 points, A7)."""
    traj = _finished_result().trajectory
    assert len(traj) > 0
    assert len(traj) <= MAX_TRAJECTORY_POINTS + TRAJECTORY_TOLERANCE


def test_aco1_trajectory_points_expose_t_position_velocity_angle() -> None:
    """Each TrajectoryPoint carries the four fields the UI animates, all finite,
    with velocity >= 0."""
    traj = _finished_result().trajectory
    for pt in traj:
        for field in ("t", "position", "velocity", "angle"):
            assert hasattr(pt, field), f"TrajectoryPoint missing field: {field}"
            assert math.isfinite(getattr(pt, field)), f"trajectory {field} not finite"
        assert pt.velocity >= 0.0, f"trajectory velocity must be >= 0, got {pt.velocity}"


def test_aco1_trajectory_time_and_position_are_nondecreasing() -> None:
    """The down-sampled trajectory is ordered in time and the car never moves
    backward up the track (t and position are non-decreasing)."""
    traj = _finished_result().trajectory
    for prev, cur in zip(traj, traj[1:]):
        assert cur.t >= prev.t - 1e-12, "trajectory time went backward"
        assert cur.position >= prev.position - 1e-9, "trajectory position went backward"


def test_aco1_trajectory_is_an_immutable_sequence() -> None:
    """trajectory is a tuple (immutable) so the frozen RaceResult is fully immutable."""
    traj = _finished_result().trajectory
    assert isinstance(traj, tuple)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-O2 — FINISHED => race_time_s > 0 & finite; DNF => race_time_s None & DNF.
# ───────────────────────────────────────────────────────────────────────────── #
def test_aco2_finished_run_has_positive_finite_race_time() -> None:
    from pinewood_derby.result import Outcome

    result = _finished_result()
    assert result.outcome is Outcome.FINISHED
    assert result.race_time_s is not None
    assert math.isfinite(result.race_time_s)
    assert result.race_time_s > 0.0


def test_aco2_dnf_run_has_none_race_time_and_dnf_outcome() -> None:
    """An unstable car (d_COM below the spec's 0.625 in threshold) is a DNF: the
    outcome is DNF and race_time_s is exactly None (PRD A2 'legible cliff')."""
    from pinewood_derby.result import Outcome
    from pinewood_derby.track import STANDARD_TRACK

    dnf_car = _make_car(com_ahead_of_rear_axle_in=0.15)  # < 0.625 in unstable threshold
    result = _simulate(dnf_car, STANDARD_TRACK, dt=1e-3, seed=0)
    assert result.outcome is Outcome.DNF
    assert result.race_time_s is None


def test_aco2_race_time_is_none_iff_not_finished() -> None:
    """The 'None iff not FINISHED' biconditional, checked both directions on two runs."""
    from pinewood_derby.result import Outcome
    from pinewood_derby.track import STANDARD_TRACK

    finished = _finished_result()
    dnf = _simulate(_make_car(com_ahead_of_rear_axle_in=0.15), STANDARD_TRACK, dt=1e-3, seed=0)

    assert (finished.race_time_s is None) == (finished.outcome is not Outcome.FINISHED)
    assert (dnf.race_time_s is None) == (dnf.outcome is not Outcome.FINISHED)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-AL3 — Determinism: bit-identical RaceResult across repeated calls; RAIL_RIDER
# is seed-independent; STRAIGHT (ping-pong) is seed-sensitive but seed-reproducible.
# ───────────────────────────────────────────────────────────────────────────── #
def test_acal3_straight_run_is_bit_identical_across_repeated_calls() -> None:
    """Same (car, track, dt, seed) -> the *entire* RaceResult compares equal across
    repeated calls, including the seeded ping-pong path (frozen dataclasses == by value)."""
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(alignment="STRAIGHT")
    r1 = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=12345)
    r2 = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=12345)
    assert r1 == r2


def test_acal3_straight_trajectory_is_bit_identical_pointwise() -> None:
    """Stronger than ==: every trajectory float is bit-for-bit identical (no drift in
    the seeded random ping-pong path)."""
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(alignment="STRAIGHT")
    r1 = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=999)
    r2 = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=999)
    assert len(r1.trajectory) == len(r2.trajectory)
    for p1, p2 in zip(r1.trajectory, r2.trajectory):
        assert p1 == p2
    assert r1.race_time_s == r2.race_time_s
    assert r1.energy == r2.energy


def test_acal3_straight_run_depends_on_seed() -> None:
    """The STRAIGHT ping-pong path actually consumes the RNG: different seeds produce
    different rail-energy outcomes (otherwise the seed plumbing is a no-op and the
    determinism guarantee is vacuous)."""
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(alignment="STRAIGHT")
    a = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=1)
    b = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=2)
    assert a.energy.w_rail != b.energy.w_rail


def test_acal3_rail_rider_is_seed_independent() -> None:
    """RAIL_RIDER uses a constant rail force, not the RNG: results must be identical
    across different seeds."""
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(alignment="RAIL_RIDER")
    a = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=1)
    b = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=99999)
    assert a == b


# ───────────────────────────────────────────────────────────────────────────── #
# AC-PU1 — Purity: no I/O, no network, no module-level mutable state; pure functions
# / frozen dataclasses; default-baseline car on STANDARD_TRACK FINISHES.
# ───────────────────────────────────────────────────────────────────────────── #
def test_acpu1_default_baseline_car_on_standard_track_finishes() -> None:
    from pinewood_derby.result import Outcome
    from pinewood_derby.track import STANDARD_TRACK

    result = _simulate(_make_car(), STANDARD_TRACK)
    assert result.outcome is Outcome.FINISHED


def test_acpu1_repeated_calls_do_not_drift_no_hidden_state() -> None:
    """No module-level mutable state: a fresh first call equals the result after many
    intervening calls with other inputs (no accumulation / no global RNG bleed)."""
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(alignment="STRAIGHT")
    first = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=7)
    # Perturb global state via many other simulations with different seeds/cars.
    for s in range(20):
        _simulate(_make_car(mass_oz=4.0 + 0.01 * s, alignment="STRAIGHT"), STANDARD_TRACK, dt=1e-3, seed=s)
        _simulate(_make_car(alignment="RAIL_RIDER"), STANDARD_TRACK, dt=1e-3, seed=s + 1)
    again = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=7)
    assert first == again


def test_acpu1_engine_uses_seeded_local_rng_not_module_global() -> None:
    """All randomness flows through a local random.Random(seed): if the engine reseeded
    or used the module-global `random`, calls interleaved with external random.seed()
    would change. Pin that the engine is immune to the global RNG state."""
    import random

    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(alignment="STRAIGHT")
    random.seed(0)
    a = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=42)
    random.seed(123456789)
    for _ in range(50):
        random.random()
    b = _simulate(car, STANDARD_TRACK, dt=1e-3, seed=42)
    assert a == b


def test_acpu1_engine_source_has_no_io_or_network() -> None:
    """Static guardrail: the engine module performs no file I/O / no network access and
    does not touch the module-global random. Scans the source for forbidden tokens."""
    import pinewood_derby.engine as engine_mod

    source = Path(engine_mod.__file__).read_text(encoding="utf-8")
    forbidden = ("open(", "import socket", "import urllib", "import requests", "import http")
    for token in forbidden:
        assert token not in source, f"engine.py must not perform I/O/network: found {token!r}"
    # Must construct a local seeded RNG, not call the module-global random functions.
    assert "random.Random(" in source, "engine must use a local random.Random(seed)"


def test_acpu1_engine_public_types_are_frozen_dataclasses() -> None:
    """The engine's value types (result + ledger + trajectory) are frozen dataclasses —
    pure immutable data, no hidden mutable state."""
    from pinewood_derby.result import (
        EnergyLedger,
        NormalForces,
        RaceResult,
        TrajectoryPoint,
    )

    for cls in (RaceResult, EnergyLedger, NormalForces, TrajectoryPoint):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True  # type: ignore[attr-defined]


# ───────────────────────────────────────────────────────────────────────────── #
# AC-T1 (length-monotonicity slice) — a longer total track => longer race_time_s.
# (The steeper-ramp half of the full AC-T1 is covered in the force-model work item.)
# ───────────────────────────────────────────────────────────────────────────── #
def test_act1_longer_track_yields_longer_race_time() -> None:
    """Same car, two tracks differing only by a longer flat runout: the longer total
    track takes strictly more time to finish (more distance to cover)."""
    from pinewood_derby.result import Outcome

    car = _make_car(alignment="RAIL_RIDER")  # seed-independent for a clean comparison
    short_track = _make_track(flat_feet=20.0)
    long_track = _make_track(flat_feet=40.0)

    short = _simulate(car, short_track, dt=1e-3, seed=0)
    long = _simulate(car, long_track, dt=1e-3, seed=0)

    assert short.outcome is Outcome.FINISHED
    assert long.outcome is Outcome.FINISHED
    assert short.race_time_s is not None and long.race_time_s is not None
    assert long.race_time_s > short.race_time_s
