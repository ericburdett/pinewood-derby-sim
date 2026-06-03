"""WI-5 — Weight (mass) lever: gravity work, PE accuracy, legal-weight reporting.

Behavior-driven tests for the weight lever, written against the engine's public
contract (``simulate`` + the frozen ``RaceResult``). Imports live inside each test
body so a missing/renamed symbol fails *that criterion* independently (true
per-criterion RED) rather than aborting whole-file collection.

Traceability to the WI-5 acceptance criteria (PRD §6; TRD §4 force model, §11):

- AC-W1: within the stable placement zone, the heavier of two otherwise-identical
  cars finishes with a strictly smaller race_time_s (more mass -> more PE -> faster).
- AC-W2: mass <= 5.0 oz (141.748 g) -> legal_weight = True; mass > the limit ->
  legal_weight = False, with the run still simulated normally in BOTH cases (the
  weight rule is reported, not physically enforced; PRD A1).
- AC-E4: reported energy.w_gravity equals the analytic PE drop M*g*Δh_com within a
  tolerance that shrinks as dt -> 0 (discrete gravity work converges to the exact
  potential-energy drop over the track's vertical geometry).
- AC-T1 (ramp-steepness slice): a steeper ramp angle (within (0°, 90°)) yields a
  strictly faster race_time_s for the same car.

All tests are deterministic: fixed dt, fixed seed, no clock / network / unseeded RNG.
RAIL_RIDER alignment is used wherever a clean, seed-independent comparison is wanted
so a directional claim about *weight or geometry* is never confounded by the seeded
ping-pong rail draw.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult
    from pinewood_derby.track import Track

# Spec-anchored constants, mirrored from the PRD/spec (NOT from the implementation),
# so the tests pin the *contract*, not whatever the engine happens to compute.
MAX_LEGAL_OZ = 5.0          # BSA weight limit (PRD §6 Weight / profile glossary)
G = 9.81                    # m/s² (physics-spec §1.1)


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — build valid inputs from plain numbers via the value objects.
# Mirrors tests/test_engine_e2e.py so construction stays consistent across the suite.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_car(
    *,
    mass_oz: float = 5.0,
    com_ahead_of_rear_axle_in: float = 0.85,
    wheelbase_in: float = 4.375,
    alignment: str = "RAIL_RIDER",
    count_touching: int = 4,
    drag_coefficient: float = 0.30,
    frontal_area: float = 0.0028,
    friction_coefficient: float = 0.20,
) -> CarDesign:
    """A valid, FINISHED-capable baseline car. ``alignment`` is the enum member name."""
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


def _car_from_mass_object(mass_obj: Any, *, alignment: str = "RAIL_RIDER") -> CarDesign:
    """Build the baseline car around a pre-constructed ``Mass`` (for boundary tests
    that need an exact grams/ounces value rather than a float helper arg)."""
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=mass_obj,
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


def _analytic_delta_h(track: Track) -> float:
    """Exact vertical drop of the COM over the full track geometry [m].

    The COM descends the straight ramp by ``ramp_length·sin θ`` and then the
    smooth transition arc by ``R·(1 − cos θ)`` as the path bends from θ down to the
    flat. The flat contributes no drop. This is the geometry the engine integrates
    through, so ``w_gravity`` (= Σ M·g·sin θ·ds) must converge to ``M·g·Δh_com``.
    """
    theta = track.ramp_angle.radians
    ramp_drop = track.ramp_length.m * math.sin(theta)
    arc_drop = track.transition_radius.m * (1.0 - math.cos(theta))
    return ramp_drop + arc_drop


def _finished(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.FINISHED


# ───────────────────────────────────────────────────────────────────────────── #
# AC-W1 — within the stable placement zone, the HEAVIER of two otherwise-identical
# cars finishes with a strictly smaller race_time_s (more mass -> more PE -> faster).
# ───────────────────────────────────────────────────────────────────────────── #
def test_acw1_heavier_car_finishes_strictly_faster() -> None:
    """Two cars identical except mass, both with a stable d_COM (0.85 in, inside the
    optimal zone) and both finishing: the heavier one must finish strictly sooner."""
    from pinewood_derby.track import STANDARD_TRACK

    lighter = _simulate(_make_car(mass_oz=4.0), STANDARD_TRACK, seed=0)
    heavier = _simulate(_make_car(mass_oz=5.0), STANDARD_TRACK, seed=0)

    assert _finished(lighter), "lighter baseline car should FINISH for a valid comparison"
    assert _finished(heavier), "heavier baseline car should FINISH for a valid comparison"
    assert lighter.race_time_s is not None and heavier.race_time_s is not None
    assert heavier.race_time_s < lighter.race_time_s, (
        f"heavier car ({heavier.race_time_s:.6f}s) must beat lighter "
        f"({lighter.race_time_s:.6f}s) — more mass means more PE on the slope"
    )


def test_acw1_race_time_is_monotonically_decreasing_in_mass() -> None:
    """Stronger than a single pair: across a sweep of masses inside the stable zone
    (all FINISHED), race_time_s decreases monotonically as mass increases. Guards
    against a non-monotone or coincidental single-point pass."""
    from pinewood_derby.track import STANDARD_TRACK

    masses = [4.0, 4.25, 4.5, 4.75, 5.0]
    times: list[float] = []
    for m in masses:
        r = _simulate(_make_car(mass_oz=m), STANDARD_TRACK, seed=0)
        assert _finished(r), f"car at {m} oz should FINISH for a clean monotonicity sweep"
        assert r.race_time_s is not None
        times.append(r.race_time_s)
    for m_lo, m_hi, t_lo, t_hi in zip(masses, masses[1:], times, times[1:]):
        assert t_hi < t_lo, (
            f"increasing mass {m_lo}->{m_hi} oz must decrease time, "
            f"got {t_lo:.6f}s -> {t_hi:.6f}s"
        )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-W2 — legal-weight reporting (reported, NOT physically enforced; PRD A1):
#   mass <= 5.0 oz -> legal_weight True;  mass > limit -> legal_weight False;
#   the run is simulated normally (FINISHED, positive finite time) in BOTH cases.
# ───────────────────────────────────────────────────────────────────────────── #
def test_acw2_at_the_limit_is_legal() -> None:
    """A car at exactly the 5.0 oz limit is legal (the boundary is inclusive: <=)."""
    r = _simulate(_make_car(mass_oz=MAX_LEGAL_OZ))
    assert r.legal_weight is True


def test_acw2_just_under_the_limit_is_legal() -> None:
    r = _simulate(_make_car(mass_oz=MAX_LEGAL_OZ - 0.01))
    assert r.legal_weight is True


def test_acw2_just_over_the_limit_is_illegal() -> None:
    """The off-by-a-hair adversarial boundary: a whisker over 5.0 oz is illegal."""
    r = _simulate(_make_car(mass_oz=MAX_LEGAL_OZ + 0.01))
    assert r.legal_weight is False


def test_acw2_overweight_car_is_still_simulated_normally() -> None:
    """The weight rule is *reported*, not enforced: an over-weight car still runs to a
    normal FINISHED outcome with a positive finite race_time_s (PRD A1) — and, being
    heavier, is not slower than a legal car (no hidden penalty masquerading as physics)."""
    legal = _simulate(_make_car(mass_oz=MAX_LEGAL_OZ))
    over = _simulate(_make_car(mass_oz=6.0))

    assert over.legal_weight is False
    assert _finished(over), "an over-weight car must still be simulated normally, not auto-DNF"
    assert over.race_time_s is not None
    assert math.isfinite(over.race_time_s) and over.race_time_s > 0.0
    # Heavier than the legal car => more PE => not slower. Confirms the illegality is
    # a *report*, not a physics penalty.
    assert legal.race_time_s is not None
    assert over.race_time_s <= legal.race_time_s


def test_acw2_legal_flag_is_a_strict_boolean() -> None:
    """legal_weight is a real bool (not a truthy float / None), so downstream UI logic
    can rely on the type contract."""
    assert _simulate(_make_car(mass_oz=4.0)).legal_weight is True
    assert _simulate(_make_car(mass_oz=6.0)).legal_weight is False


# ───────────────────────────────────────────────────────────────────────────── #
# AC-E4 — reported energy.w_gravity equals the analytic PE drop M*g*Δh_com within a
# tolerance that SHRINKS as dt -> 0 (gravity work converges to the exact PE drop).
# ───────────────────────────────────────────────────────────────────────────── #
def test_ace4_w_gravity_matches_analytic_pe_drop_at_fine_dt() -> None:
    """At a fine dt, the accumulated gravity work equals M·g·Δh_com to tight relative
    tolerance, where Δh_com is the exact vertical drop over the ramp + transition arc."""
    from pinewood_derby.track import STANDARD_TRACK
    from pinewood_derby.units import Mass

    car = _make_car(mass_oz=5.0)
    r = _simulate(car, STANDARD_TRACK, dt=1e-4, seed=0)

    mass_kg = Mass.from_ounces(5.0).kg
    analytic = mass_kg * G * _analytic_delta_h(STANDARD_TRACK)
    rel_err = abs(r.energy.w_gravity - analytic) / analytic
    assert rel_err < 1e-3, (
        f"w_gravity={r.energy.w_gravity:.6f} J should match M·g·Δh={analytic:.6f} J "
        f"(rel err {rel_err:.2e})"
    )


def test_ace4_pe_error_shrinks_as_dt_decreases() -> None:
    """The convergence claim itself: halving dt strictly reduces the relative error
    between w_gravity and the analytic PE drop. A single fixed-tolerance check could
    pass on a non-converging integrator; this pins that refining dt actually helps."""
    from pinewood_derby.track import STANDARD_TRACK
    from pinewood_derby.units import Mass

    car = _make_car(mass_oz=5.0)
    mass_kg = Mass.from_ounces(5.0).kg
    analytic = mass_kg * G * _analytic_delta_h(STANDARD_TRACK)

    errors: list[float] = []
    for dt in (1e-2, 1e-3, 1e-4):
        r = _simulate(car, STANDARD_TRACK, dt=dt, seed=0)
        assert _finished(r), "car must FINISH so w_gravity covers the full descent"
        errors.append(abs(r.energy.w_gravity - analytic) / analytic)

    assert errors[1] < errors[0], (
        f"refining dt 1e-2 -> 1e-3 must reduce PE error, got {errors[0]:.2e} -> {errors[1]:.2e}"
    )
    assert errors[2] < errors[1], (
        f"refining dt 1e-3 -> 1e-4 must reduce PE error, got {errors[1]:.2e} -> {errors[2]:.2e}"
    )


def test_ace4_w_gravity_scales_linearly_with_mass() -> None:
    """w_gravity = M·g·Δh is linear in M for the same track: doubling mass doubles the
    gravity work to tight tolerance. Pins that the gravity term is mass-proportional,
    not coincidentally near the analytic value for one mass."""
    from pinewood_derby.track import STANDARD_TRACK

    r1 = _simulate(_make_car(mass_oz=2.5), STANDARD_TRACK, dt=1e-4, seed=0)
    r2 = _simulate(_make_car(mass_oz=5.0), STANDARD_TRACK, dt=1e-4, seed=0)
    assert _finished(r2), "the 5.0 oz car must FINISH"
    # The lighter car may DNF on the flat; w_gravity is still accumulated over its
    # descent, but for a clean 2x check we require both to traverse the full ramp+arc.
    # The gravity work is path-geometry-only (independent of whether it finished the
    # flat), so compare the ratio.
    ratio = r2.energy.w_gravity / r1.energy.w_gravity
    assert math.isclose(ratio, 2.0, rel_tol=1e-3), (
        f"doubling mass should double w_gravity, got ratio {ratio:.6f}"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-T1 (ramp-steepness slice) — a steeper ramp angle (within (0°, 90°)) yields a
# strictly faster race_time_s for the same car.
# ───────────────────────────────────────────────────────────────────────────── #
def test_act1_steeper_ramp_is_strictly_faster() -> None:
    """Same car, two tracks differing only in ramp angle (same lengths): the steeper
    ramp delivers more PE faster, so race_time_s is strictly smaller."""
    car = _make_car(mass_oz=5.0)
    shallow = _simulate(car, _make_track(ramp_degrees=30.0), seed=0)
    steep = _simulate(car, _make_track(ramp_degrees=45.0), seed=0)

    assert _finished(shallow) and _finished(steep), "both ramps must FINISH for a clean comparison"
    assert shallow.race_time_s is not None and steep.race_time_s is not None
    assert steep.race_time_s < shallow.race_time_s, (
        f"steeper ramp (45°, {steep.race_time_s:.6f}s) must beat shallower "
        f"(30°, {shallow.race_time_s:.6f}s)"
    )


def test_act1_race_time_monotonically_decreases_with_ramp_angle() -> None:
    """A sweep of increasing ramp angles (all FINISHED) yields monotonically decreasing
    race_time_s — the steepness->speed relationship holds across the range, not just at
    one pair."""
    car = _make_car(mass_oz=5.0)
    angles = [30.0, 35.0, 40.0, 45.0, 50.0]
    times: list[float] = []
    for deg in angles:
        r = _simulate(car, _make_track(ramp_degrees=deg), seed=0)
        assert _finished(r), f"ramp at {deg}° should FINISH for a clean monotonicity sweep"
        assert r.race_time_s is not None
        times.append(r.race_time_s)
    for a_lo, a_hi, t_lo, t_hi in zip(angles, angles[1:], times, times[1:]):
        assert t_hi < t_lo, (
            f"steeper ramp {a_lo}->{a_hi}° must decrease time, got {t_lo:.6f}s -> {t_hi:.6f}s"
        )


def test_act1_steeper_ramp_yields_higher_exit_velocity() -> None:
    """The mechanism behind the faster time: a steeper ramp converts more PE to KE over
    the same ramp length, so the car leaves the ramp moving faster (exit_velocity)."""
    car = _make_car(mass_oz=5.0)
    shallow = _simulate(car, _make_track(ramp_degrees=30.0), seed=0)
    steep = _simulate(car, _make_track(ramp_degrees=45.0), seed=0)
    assert steep.exit_velocity > shallow.exit_velocity, (
        f"steeper ramp should give higher exit velocity, "
        f"got 45°={steep.exit_velocity:.4f} vs 30°={shallow.exit_velocity:.4f}"
    )


@pytest.mark.parametrize("bad_angle", [0.0, 90.0, -10.0, 120.0])
def test_act1_ramp_angle_outside_open_interval_raises(bad_angle: float) -> None:
    """The steepness lever lives on (0°, 90°): a degenerate flat (0°), a vertical
    cliff (90°), or anything outside is rejected at the Track boundary (AC-T3 guard
    underpinning the steepness slice)."""
    with pytest.raises(ValueError):
        _make_track(ramp_degrees=bad_angle)
