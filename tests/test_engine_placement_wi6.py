"""WI-6 — Weight placement (d_COM): rear-bias speed gain, normal-force distribution,
and the DNF stability cliff.

Behavior-driven tests for the placement lever, written against the engine's public
contract (``simulate`` + the frozen ``RaceResult``). Imports live inside each test
body so a missing/renamed symbol fails *that criterion* independently (true
per-criterion RED) rather than aborting whole-file collection.

Traceability to the WI-6 acceptance criteria (PRD §6 Placement; TRD §4 d_COM wiring):

- AC-P1: within the stable range, *decreasing* d_COM (mass shifted rearward) strictly
  decreases race_time_s (rear bias sits higher on the ramp / pushes longer).
- AC-P2: a car with d_COM in the optimal zone [0.75 in, 1.0 in] FINISHES and is
  strictly faster than the same car at d_COM = 1.25 in (forward = stable but slow).
- AC-P3 (graded placement model): as d_COM drops below the tippy onset (~0.625 in at the
  standard wheelbase) the front goes light and the car gets *tippy* — it still FINISHES but
  progressively slower (wander). Only when the front load has essentially collapsed
  (d_COM ≲ 0.26 in, front-load fraction ≲ 0.06) can it not run at all → DNF with
  race_time_s = None, while still returning the partial trajectory and energy ledger.
- AC-P4: on the flat, reported normal forces satisfy N_f = M·g·(d_COM/L) and
  N_r = M·g·(1 − d_COM/L) within tolerance, with N_f + N_r ≈ M·g, and N_f → 0 as
  d_COM → 0.

All tests are deterministic: fixed dt, fixed seed, no clock / network / unseeded RNG.
RAIL_RIDER alignment is used so a directional claim about *placement* is never
confounded by the seeded ping-pong rail draw. All physical expectations are derived
from the PRD/spec (M·g·d_COM/L, the [0.75, 1.0] in zone, the 0.625 in cliff), never
read back from the implementation, so the tests pin the *contract*.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult
    from pinewood_derby.track import Track

# Spec-anchored constants (PRD §6 Placement; TRD §5 placement zones).
G = 9.81                       # m/s² (physics-spec §1.1)
WHEELBASE_IN = 4.375           # L (PRD A4 BSA-typical default)
COM_OPTIMAL_IN = (0.75, 1.0)   # optimal zone [0.75 in, 1.0 in] (spec §4.2)
COM_FORWARD_SLOW_IN = 1.25     # stable-but-slow comparison point (AC-P2)
COM_TIPPY_ONSET_IN = 0.625     # front starts going light here → tippy/slower but still finishes
COM_CRASH_BELOW_IN = 0.2625    # front load essentially gone (fraction ~0.06) → genuine DNF


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — build valid inputs from plain numbers via the value objects.
# Mirrors tests/test_engine_weight_wi5.py so construction stays consistent.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_car(
    *,
    com_ahead_of_rear_axle_in: float,
    mass_oz: float = 5.0,
    wheelbase_in: float = WHEELBASE_IN,
    alignment: str = "RAIL_RIDER",
    count_touching: int = 4,
    drag_coefficient: float = 0.30,
    frontal_area: float = 0.0028,
    friction_coefficient: float = 0.20,
) -> CarDesign:
    """A valid baseline car parameterized only by d_COM (everything else fixed),
    so a difference in race_time_s can only come from the placement lever."""
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(wheelbase_in),
        wheels=Wheels(
            count_touching=count_touching,
            wheel_mass=Mass.from_ounces(0.09),
            outer_radius=Length.from_inches(0.595),
            inner_radius=Length.from_inches(0.37),
            axle_radius=Length.from_inches(0.045),
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


def _is_dnf(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.DNF


# ───────────────────────────────────────────────────────────────────────────── #
# AC-P1 — within the stable range, DECREASING d_COM (mass shifted rearward)
# strictly DECREASES race_time_s. Rear bias sits higher on the ramp and pushes
# longer, so smaller d_COM => more PE / longer push => faster.
# ───────────────────────────────────────────────────────────────────────────── #
def test_acp1_rearward_com_finishes_strictly_faster() -> None:
    """Two cars identical except d_COM, both stable and both finishing: the more
    rearward (smaller d_COM) one must finish strictly sooner."""
    from pinewood_derby.track import STANDARD_TRACK

    forward = _simulate(_make_car(com_ahead_of_rear_axle_in=1.0), STANDARD_TRACK, seed=0)
    rearward = _simulate(_make_car(com_ahead_of_rear_axle_in=0.75), STANDARD_TRACK, seed=0)

    assert _finished(forward), "the forward (d_COM=1.0 in) car should FINISH for a valid comparison"
    assert _finished(rearward), "the rearward (d_COM=0.75 in) car should FINISH for a valid comparison"
    assert forward.race_time_s is not None and rearward.race_time_s is not None
    assert rearward.race_time_s < forward.race_time_s, (
        f"more rearward d_COM (0.75 in, {rearward.race_time_s:.6f}s) must beat more "
        f"forward d_COM (1.0 in, {forward.race_time_s:.6f}s) — rear bias sits higher "
        f"on the ramp and pushes longer"
    )


def test_acp1_race_time_monotonically_decreases_as_com_moves_rearward() -> None:
    """Stronger than a single pair: across a sweep of stable d_COM values (all
    FINISHED), race_time_s decreases monotonically as d_COM decreases (mass moves
    rearward). Guards against a non-monotone or coincidental single-point pass."""
    from pinewood_derby.track import STANDARD_TRACK

    # Descending d_COM = increasingly rearward bias, all inside the stable range
    # (>= 0.625 in cliff, spanning the optimal zone and a touch above).
    d_coms_in = [1.0, 0.9, 0.8, 0.7, 0.65]
    times: list[float] = []
    for d in d_coms_in:
        r = _simulate(_make_car(com_ahead_of_rear_axle_in=d), STANDARD_TRACK, seed=0)
        assert _finished(r), f"d_COM={d} in should FINISH for a clean monotonicity sweep"
        assert r.race_time_s is not None
        times.append(r.race_time_s)
    for d_hi, d_lo, t_hi, t_lo in zip(d_coms_in, d_coms_in[1:], times, times[1:]):
        assert t_lo < t_hi, (
            f"moving d_COM rearward {d_hi}->{d_lo} in must decrease time, "
            f"got {t_hi:.6f}s -> {t_lo:.6f}s"
        )


def test_acp1_rearward_com_yields_higher_exit_velocity() -> None:
    """The mechanism behind the faster time: a more rearward COM starts higher on
    the ramp, converting more PE to KE over the descent, so the car leaves the ramp
    moving faster (exit_velocity)."""
    from pinewood_derby.track import STANDARD_TRACK

    forward = _simulate(_make_car(com_ahead_of_rear_axle_in=1.0), STANDARD_TRACK, seed=0)
    rearward = _simulate(_make_car(com_ahead_of_rear_axle_in=0.75), STANDARD_TRACK, seed=0)
    assert rearward.exit_velocity > forward.exit_velocity, (
        f"a more rearward COM should give a higher exit velocity, got "
        f"d_COM=0.75 in -> {rearward.exit_velocity:.4f} m/s vs "
        f"d_COM=1.0 in -> {forward.exit_velocity:.4f} m/s"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-P2 — a car with d_COM in the optimal zone [0.75 in, 1.0 in] FINISHES and is
# strictly faster than the same car at d_COM = 1.25 in (forward = stable but slow).
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("optimal_in", [COM_OPTIMAL_IN[0], 0.85, COM_OPTIMAL_IN[1]])
def test_acp2_optimal_zone_finishes_and_beats_forward_125(optimal_in: float) -> None:
    """A car placed anywhere in the optimal zone [0.75, 1.0] in finishes and is
    strictly faster than the same car at the stable-but-forward d_COM = 1.25 in."""
    from pinewood_derby.track import STANDARD_TRACK

    optimal = _simulate(
        _make_car(com_ahead_of_rear_axle_in=optimal_in), STANDARD_TRACK, seed=0
    )
    forward = _simulate(
        _make_car(com_ahead_of_rear_axle_in=COM_FORWARD_SLOW_IN), STANDARD_TRACK, seed=0
    )

    assert _finished(optimal), (
        f"an optimal-zone car (d_COM={optimal_in} in) must FINISH (AC-P2)"
    )
    assert _finished(forward), (
        "the forward d_COM=1.25 in car must FINISH (stable but slow), for a valid comparison"
    )
    assert optimal.race_time_s is not None and forward.race_time_s is not None
    assert optimal.race_time_s < forward.race_time_s, (
        f"optimal-zone d_COM={optimal_in} in ({optimal.race_time_s:.6f}s) must be "
        f"strictly faster than forward d_COM=1.25 in ({forward.race_time_s:.6f}s)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-P3 (graded) — below the tippy onset the car is tippy but still FINISHES (slower);
# only when the front load has essentially collapsed (d_COM ≲ 0.26 in) is it a DNF.
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("unstable_in", [0.25, 0.2, 0.1])
def test_acp3_collapsed_front_is_dnf_with_no_time(unstable_in: float) -> None:
    """Only when the front load has essentially collapsed (d_COM ≲ 0.26 in, front-load
    fraction ≲ 0.06) can the car not run at all: a DNF with race_time_s = None."""
    from pinewood_derby.track import STANDARD_TRACK

    r = _simulate(_make_car(com_ahead_of_rear_axle_in=unstable_in), STANDARD_TRACK, seed=0)
    assert _is_dnf(r), (
        f"d_COM={unstable_in} in (front load collapsed) must be a DNF (cannot run)"
    )
    assert r.race_time_s is None, (
        f"a DNF must report race_time_s = None, got {r.race_time_s!r}"
    )


def test_acp3_tippy_zone_finishes_but_slower_than_the_sweet_spot() -> None:
    """The graded model: between the crash threshold and the tippy onset the car still
    FINISHES, but a more-rearward (tippier) car is SLOWER than one near the onset — the
    front going light costs speed (wander), it is not a sharp cliff above the crash."""
    from pinewood_derby.track import STANDARD_TRACK

    near_onset = _simulate(_make_car(com_ahead_of_rear_axle_in=0.6), STANDARD_TRACK, seed=0)
    deep_tippy = _simulate(_make_car(com_ahead_of_rear_axle_in=0.4), STANDARD_TRACK, seed=0)
    assert _finished(near_onset) and _finished(deep_tippy), "both are above the crash → FINISH"
    assert near_onset.race_time_s is not None and deep_tippy.race_time_s is not None
    assert deep_tippy.race_time_s > near_onset.race_time_s, (
        f"a tippier car (d_COM=0.4 in, {deep_tippy.race_time_s:.4f}s) must be SLOWER than one "
        f"near the onset (0.6 in, {near_onset.race_time_s:.4f}s) — graded wander, not a cliff"
    )


def test_acp3_dnf_just_below_collapse_vs_finish_just_above() -> None:
    """The genuine collapse is a sharp boundary: a hair below it the car can't run (DNF),
    a hair above it still finishes (tippy). The gradual part is the slowdown *approaching*
    the collapse, but the final inability-to-run is itself a clean threshold."""
    from pinewood_derby.track import STANDARD_TRACK

    below = _simulate(
        _make_car(com_ahead_of_rear_axle_in=COM_CRASH_BELOW_IN - 0.02), STANDARD_TRACK, seed=0
    )
    above = _simulate(
        _make_car(com_ahead_of_rear_axle_in=COM_CRASH_BELOW_IN + 0.05), STANDARD_TRACK, seed=0
    )
    assert _is_dnf(below), "just below the collapse threshold must DNF"
    assert below.race_time_s is None, "the DNF below the collapse must have race_time_s = None"
    assert _finished(above), "just above the collapse threshold must still FINISH (tippy)"
    assert above.race_time_s is not None, "a finisher above the collapse must have a real time"


def test_acp3_dnf_still_returns_trajectory_and_energy_ledger() -> None:
    """Even on a DNF the engine returns the partial trajectory and the energy ledger
    up to the failure (PRD A2) — the result is well-formed so the UI can still show
    *where* and *why* the car crashed, never a bare None or a truncated object."""
    import math

    from pinewood_derby.result import EnergyLedger, NormalForces, TrajectoryPoint
    from pinewood_derby.track import STANDARD_TRACK

    r = _simulate(_make_car(com_ahead_of_rear_axle_in=0.15), STANDARD_TRACK, seed=0)
    assert _is_dnf(r) and r.race_time_s is None

    # A partial trajectory is still present, well-formed, and finite up to the failure.
    assert isinstance(r.trajectory, tuple)
    assert len(r.trajectory) >= 1, "a DNF must still report the trajectory up to the failure"
    for p in r.trajectory:
        assert isinstance(p, TrajectoryPoint)
        assert math.isfinite(p.t) and math.isfinite(p.position)
        assert math.isfinite(p.velocity) and math.isfinite(p.angle)
        assert p.velocity >= 0.0, "velocities are non-negative (AC-O1)"

    # The energy ledger up to the failure is present and every field is finite.
    assert isinstance(r.energy, EnergyLedger)
    for field in (
        r.energy.pe_initial,
        r.energy.ke_linear_final,
        r.energy.ke_rotational_final,
        r.energy.w_gravity,
        r.energy.w_drag,
        r.energy.w_axle,
        r.energy.w_rail,
    ):
        assert math.isfinite(field), "every energy-ledger field must be finite on a DNF"

    # The normal forces (the *reason* for the crash) are still reported and finite.
    assert isinstance(r.normal_forces, NormalForces)
    assert math.isfinite(r.normal_forces.front) and math.isfinite(r.normal_forces.rear)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-P4 — on the flat, reported normal forces satisfy
#   N_f = M·g·(d_COM/L)  and  N_r = M·g·(1 − d_COM/L)  within tolerance,
#   with N_f + N_r ≈ M·g, and N_f → 0 as d_COM → 0.
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("d_com_in", [0.75, 0.85, 1.0, 1.25, 2.0])
def test_acp4_normal_forces_match_static_distribution(d_com_in: float) -> None:
    """For a stable, finishing car, the reported front/rear normal forces equal the
    static lever-arm distribution N_f = M·g·(d_COM/L), N_r = M·g·(1 − d_COM/L)."""
    import math

    from pinewood_derby.track import STANDARD_TRACK
    from pinewood_derby.units import Length, Mass

    car = _make_car(com_ahead_of_rear_axle_in=d_com_in)
    r = _simulate(car, STANDARD_TRACK, seed=0)

    mass_kg = Mass.from_ounces(5.0).kg
    weight = mass_kg * G
    d_com_m = Length.from_inches(d_com_in).m
    wheelbase_m = Length.from_inches(WHEELBASE_IN).m

    expected_front = weight * (d_com_m / wheelbase_m)
    expected_rear = weight * (1.0 - d_com_m / wheelbase_m)

    assert math.isclose(r.normal_forces.front, expected_front, rel_tol=1e-9, abs_tol=1e-9), (
        f"N_f for d_COM={d_com_in} in: got {r.normal_forces.front:.6f} N, "
        f"expected M·g·(d_COM/L) = {expected_front:.6f} N"
    )
    assert math.isclose(r.normal_forces.rear, expected_rear, rel_tol=1e-9, abs_tol=1e-9), (
        f"N_r for d_COM={d_com_in} in: got {r.normal_forces.rear:.6f} N, "
        f"expected M·g·(1 − d_COM/L) = {expected_rear:.6f} N"
    )


def test_acp4_normal_forces_sum_to_weight() -> None:
    """N_f + N_r ≈ M·g for any placement: all the car's weight rests on the axles
    on the flat (vertical-equilibrium invariant)."""
    import math

    from pinewood_derby.track import STANDARD_TRACK
    from pinewood_derby.units import Mass

    weight = Mass.from_ounces(5.0).kg * G
    for d_com_in in (0.7, 0.85, 1.0, 1.5, 3.0):
        r = _simulate(_make_car(com_ahead_of_rear_axle_in=d_com_in), STANDARD_TRACK, seed=0)
        total = r.normal_forces.front + r.normal_forces.rear
        assert math.isclose(total, weight, rel_tol=1e-9, abs_tol=1e-9), (
            f"N_f + N_r for d_COM={d_com_in} in must equal M·g={weight:.6f} N, "
            f"got {total:.6f} N"
        )


def test_acp4_front_normal_force_vanishes_as_com_moves_to_rear_axle() -> None:
    """N_f → 0 as d_COM → 0 (the COM directly over the rear axle puts no load on the
    front): the front normal force shrinks monotonically toward zero with d_COM and
    is arbitrarily small for a tiny d_COM. This is the *physical reason* a too-rearward
    car wobbles, underpinning the AC-P3 cliff."""
    import math

    from pinewood_derby.track import STANDARD_TRACK
    from pinewood_derby.units import Length, Mass

    weight = Mass.from_ounces(5.0).kg * G
    wheelbase_m = Length.from_inches(WHEELBASE_IN).m

    # Decreasing d_COM toward the rear axle; N_f must shrink monotonically toward 0.
    d_coms_in = [1.0, 0.5, 0.1, 0.01, 0.001]
    fronts: list[float] = []
    for d in d_coms_in:
        r = _simulate(_make_car(com_ahead_of_rear_axle_in=d), STANDARD_TRACK, seed=0)
        d_m = Length.from_inches(d).m
        expected = weight * (d_m / wheelbase_m)
        assert math.isclose(r.normal_forces.front, expected, rel_tol=1e-9, abs_tol=1e-12), (
            f"N_f for d_COM={d} in: got {r.normal_forces.front:.8f} N, "
            f"expected {expected:.8f} N"
        )
        fronts.append(r.normal_forces.front)

    for d_hi, d_lo, f_hi, f_lo in zip(d_coms_in, d_coms_in[1:], fronts, fronts[1:]):
        assert f_lo < f_hi, (
            f"N_f must shrink as d_COM moves rearward {d_hi}->{d_lo} in, "
            f"got {f_hi:.8f} N -> {f_lo:.8f} N"
        )
    # The smallest d_COM drives N_f arbitrarily close to 0 (the limit N_f → 0).
    assert fronts[-1] < 1e-3, (
        f"N_f must approach 0 as d_COM → 0, got {fronts[-1]:.8f} N at d_COM=0.001 in"
    )
    assert fronts[-1] > 0.0, "N_f stays strictly positive for a strictly positive d_COM"
