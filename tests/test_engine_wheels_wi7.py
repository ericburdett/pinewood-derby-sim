"""WI-7 — Wheels / rotational-inertia lever: fewer & lighter wheels are faster, and
the rotational KE share is correct and shrinks accordingly.

Behavior-driven tests written against the engine's public contract (``simulate`` +
the frozen ``RaceResult``). Imports live inside each test body so a missing/renamed
symbol fails *that criterion* independently (true per-criterion isolation) rather than
aborting whole-file collection.

Traceability to the WI-7 acceptance criteria (PRD §6; TRD §4 force model / §11):

- AC-WH1 (PRD l.109): a 3-wheels-touching car finishes with a strictly smaller
  race_time_s than the otherwise-identical 4-wheel car (less rotational inertia + one
  fewer axle's friction).
- AC-WH2 (PRD l.112): lightweight wheels (reduced wheel_mass, up to 60%) yield a
  strictly smaller race_time_s than standard wheels (lower I -> more energy in
  linear KE).
- AC-E2 (PRD l.154): KE_total = ½·M·v² + Σ ½·I·ω² with ω = v / R_outer; the
  rotational fraction ke_rotational_final / (ke_linear_final + ke_rotational_final)
  is > 0 for massive wheels and strictly DECREASES when wheels are lightened or one
  wheel is lifted (3-wheel). Verified on FINISHED runs.

Integrity / determinism: every test fixes dt and seed (no clock / network / unseeded
RNG), uses RAIL_RIDER alignment so the seeded ping-pong rail draw never confounds a
directional wheel claim, and asserts directional relationships / bounds / the spec's
exact KE identity — never a magic magnitude. This file is NEW; it modifies, skips, or
deletes no existing test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult
    from pinewood_derby.track import Track

# Standard per-wheel mass from the spec/constants (physics-spec §1.1; TRD §5), pinned
# here so the lightweight-wheel comparison references the contract, not the engine.
STD_WHEEL_OZ = 0.09


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — build valid inputs from plain numbers via the value objects.
# Mirrors tests/test_engine_weight_wi5.py so construction stays consistent.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_car(
    *,
    mass_oz: float = 5.0,
    com_ahead_of_rear_axle_in: float = 0.85,
    wheelbase_in: float = 4.375,
    alignment: str = "RAIL_RIDER",
    count_touching: int = 4,
    wheel_oz: float = STD_WHEEL_OZ,
    outer_radius_in: float = 0.595,
    inner_radius_in: float = 0.37,
    axle_radius_in: float = 0.045,
    drag_coefficient: float = 0.30,
    frontal_area: float = 0.0028,
    friction_coefficient: float = 0.20,
) -> CarDesign:
    """A valid, FINISHED-capable baseline car. ``alignment`` is the enum member name.

    Only the wheel-related fields are varied across the WI-7 comparisons; everything
    else is held identical so each test isolates exactly one lever ("all else equal").
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


def _rotational_fraction(result: RaceResult) -> float:
    """ke_rotational_final / (ke_linear_final + ke_rotational_final) for a run.

    This is the rotational share of the car's final kinetic energy — the quantity
    AC-E2 requires to be > 0 with massive wheels and to shrink as the wheels are
    lightened or one is lifted (3-wheel).
    """
    e = result.energy
    total = e.ke_linear_final + e.ke_rotational_final
    assert total > 0.0, "a FINISHED run must have positive final kinetic energy"
    return e.ke_rotational_final / total


# ───────────────────────────────────────────────────────────────────────────── #
# AC-WH1 — a 3-wheels-touching car is strictly faster than the otherwise-identical
# 4-wheel car (less rotational inertia + one fewer axle's friction). (spec §5)
# ───────────────────────────────────────────────────────────────────────────── #
def test_acwh1_three_wheel_finishes_strictly_faster_than_four_wheel() -> None:
    """Two cars identical except wheel count (3 vs 4 touching), both FINISHED: the
    3-wheel car must finish strictly sooner. Lifting one wheel removes its rotational
    inertia contribution and one axle's bore friction, so the car accelerates more."""
    from pinewood_derby.track import STANDARD_TRACK

    four = _simulate(_make_car(count_touching=4), STANDARD_TRACK, seed=0)
    three = _simulate(_make_car(count_touching=3), STANDARD_TRACK, seed=0)

    assert _finished(four), "4-wheel baseline car should FINISH for a valid comparison"
    assert _finished(three), "3-wheel car should FINISH for a valid comparison"
    assert four.race_time_s is not None and three.race_time_s is not None
    assert three.race_time_s < four.race_time_s, (
        f"3-wheel car ({three.race_time_s:.6f}s) must beat the 4-wheel car "
        f"({four.race_time_s:.6f}s) — one fewer wheel means less rotational inertia "
        f"and one fewer axle's friction"
    )


def test_acwh1_three_wheel_reaches_higher_finish_velocity() -> None:
    """The mechanism behind the faster time: with less effective inertia and one less
    axle dragging, the 3-wheel car carries more speed across the line."""
    from pinewood_derby.track import STANDARD_TRACK

    four = _simulate(_make_car(count_touching=4), STANDARD_TRACK, seed=0)
    three = _simulate(_make_car(count_touching=3), STANDARD_TRACK, seed=0)

    assert _finished(four) and _finished(three)
    assert three.finish_velocity > four.finish_velocity, (
        f"3-wheel finish velocity ({three.finish_velocity:.4f} m/s) should exceed "
        f"4-wheel ({four.finish_velocity:.4f} m/s)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-WH2 — lightweight wheels (reduced wheel_mass, up to 60%) yield a strictly
# smaller race_time_s than standard wheels (lower I -> more energy in linear KE).
# ───────────────────────────────────────────────────────────────────────────── #
def test_acwh2_lightweight_wheels_finish_strictly_faster() -> None:
    """Two cars identical except per-wheel mass — standard vs a 60%-reduced (0.4×)
    lightweight wheel — both FINISHED: the lightweight-wheel car must finish strictly
    sooner. Lower wheel mass means lower moment of inertia, so less of the descent's
    energy is locked into spinning the wheels and more goes to forward speed."""
    from pinewood_derby.track import STANDARD_TRACK

    standard = _simulate(_make_car(wheel_oz=STD_WHEEL_OZ), STANDARD_TRACK, seed=0)
    # 60% lighter wheels (the PRD's "up to 60%" reduction).
    light = _simulate(_make_car(wheel_oz=STD_WHEEL_OZ * 0.4), STANDARD_TRACK, seed=0)

    assert _finished(standard), "standard-wheel car should FINISH for a valid comparison"
    assert _finished(light), "lightweight-wheel car should FINISH for a valid comparison"
    assert standard.race_time_s is not None and light.race_time_s is not None
    assert light.race_time_s < standard.race_time_s, (
        f"lightweight-wheel car ({light.race_time_s:.6f}s) must beat standard-wheel "
        f"({standard.race_time_s:.6f}s) — lower I leaves more energy for linear KE"
    )


def test_acwh2_race_time_monotonically_decreases_as_wheels_lighten() -> None:
    """Stronger than a single pair: across a sweep of decreasing wheel masses (all
    FINISHED), race_time_s decreases monotonically as the wheels get lighter. Guards
    against a non-monotone or coincidental single-point pass."""
    from pinewood_derby.track import STANDARD_TRACK

    # From standard down to 40% of standard (a 60% reduction), heaviest first.
    fractions = [1.0, 0.85, 0.7, 0.55, 0.4]
    times: list[float] = []
    for f in fractions:
        r = _simulate(_make_car(wheel_oz=STD_WHEEL_OZ * f), STANDARD_TRACK, seed=0)
        assert _finished(r), f"wheels at {f:.2f}× standard mass should FINISH for the sweep"
        assert r.race_time_s is not None
        times.append(r.race_time_s)
    for f_hi, f_lo, t_hi, t_lo in zip(fractions, fractions[1:], times, times[1:]):
        assert t_lo < t_hi, (
            f"lightening wheels {f_hi:.2f}×->{f_lo:.2f}× standard mass must decrease "
            f"time, got {t_hi:.6f}s -> {t_lo:.6f}s"
        )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-E2 — KE_total = ½·M·v² + Σ ½·I·ω² (ω = v / R_outer); the rotational fraction is
# > 0 for massive wheels and strictly DECREASES when wheels are lightened or a wheel
# is lifted (3-wheel). Verified on FINISHED runs.
# ───────────────────────────────────────────────────────────────────────────── #
def test_ace2_kinetic_energy_matches_linear_plus_rotational_formula() -> None:
    """The reported energy split must equal the spec's identity exactly: with the
    car's finish velocity v, ke_linear_final = ½·M·v² and
    ke_rotational_final = Σ ½·I·ω² = N·½·I·(v/R_outer)². Pins the engine's KE bookkeeping
    to the literal AC-E2 formula, not just to a self-consistent internal value."""
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(wheel_oz=STD_WHEEL_OZ)
    r = _simulate(car, STANDARD_TRACK, seed=0)
    assert _finished(r), "car must FINISH so the finish velocity drives the KE check"

    v = r.finish_velocity
    mass_kg = car.mass.kg
    r_outer = car.wheels.outer_radius.m
    inertia = car.wheels.moment_of_inertia()
    n_wheels = car.wheels.count_touching

    expected_linear = 0.5 * mass_kg * v**2
    expected_rotational = n_wheels * 0.5 * inertia * (v / r_outer) ** 2

    assert abs(r.energy.ke_linear_final - expected_linear) <= 1e-9 * max(
        1.0, expected_linear
    ), (
        f"ke_linear_final={r.energy.ke_linear_final:.9f} must equal ½·M·v²="
        f"{expected_linear:.9f}"
    )
    assert abs(r.energy.ke_rotational_final - expected_rotational) <= 1e-9 * max(
        1.0, expected_rotational
    ), (
        f"ke_rotational_final={r.energy.ke_rotational_final:.9f} must equal "
        f"Σ½·I·ω²={expected_rotational:.9f} with ω=v/R_outer"
    )


def test_ace2_rotational_fraction_is_positive_for_massive_wheels() -> None:
    """With real (massive) wheels, some of the descent's energy is always tied up in
    spinning them, so the rotational fraction of final KE is strictly positive."""
    from pinewood_derby.track import STANDARD_TRACK

    r = _simulate(_make_car(wheel_oz=STD_WHEEL_OZ), STANDARD_TRACK, seed=0)
    assert _finished(r)
    frac = _rotational_fraction(r)
    assert frac > 0.0, (
        f"rotational fraction must be > 0 for massive wheels, got {frac:.6f}"
    )


def test_ace2_rotational_fraction_strictly_decreases_when_wheels_lightened() -> None:
    """Lightening the wheels lowers their moment of inertia, so a strictly smaller
    share of the final kinetic energy is rotational. The fraction must strictly drop."""
    from pinewood_derby.track import STANDARD_TRACK

    standard = _simulate(_make_car(wheel_oz=STD_WHEEL_OZ), STANDARD_TRACK, seed=0)
    light = _simulate(_make_car(wheel_oz=STD_WHEEL_OZ * 0.4), STANDARD_TRACK, seed=0)
    assert _finished(standard) and _finished(light)

    f_std = _rotational_fraction(standard)
    f_light = _rotational_fraction(light)
    assert f_light < f_std, (
        f"lightening wheels must shrink the rotational fraction, got "
        f"standard={f_std:.6f} vs light={f_light:.6f}"
    )


def test_ace2_rotational_fraction_strictly_decreases_when_one_wheel_lifted() -> None:
    """Lifting one wheel (3-wheel touch) removes that wheel's rotational inertia from
    the system, so the rotational share of the final KE must strictly fall versus the
    otherwise-identical 4-wheel car."""
    from pinewood_derby.track import STANDARD_TRACK

    four = _simulate(_make_car(count_touching=4), STANDARD_TRACK, seed=0)
    three = _simulate(_make_car(count_touching=3), STANDARD_TRACK, seed=0)
    assert _finished(four) and _finished(three)

    f_four = _rotational_fraction(four)
    f_three = _rotational_fraction(three)
    assert f_three < f_four, (
        f"lifting one wheel (3-wheel) must shrink the rotational fraction, got "
        f"4-wheel={f_four:.6f} vs 3-wheel={f_three:.6f}"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# Determinism guard — every WI-7 comparison must be reproducible (fixed dt + seed),
# so the directional claims above are never a flake (AC-AL3 spirit; gate "deterministic").
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi7_results_are_deterministic_across_repeated_calls() -> None:
    """The same (car, track, dt, seed) yields a bit-identical race_time_s and KE split
    on repeat — the wheel-lever tests rest on reproducible runs, not chance."""
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(count_touching=3, wheel_oz=STD_WHEEL_OZ * 0.4)
    a = _simulate(car, STANDARD_TRACK, seed=0)
    b = _simulate(car, STANDARD_TRACK, seed=0)
    assert a.race_time_s == b.race_time_s
    assert a.energy.ke_linear_final == b.energy.ke_linear_final
    assert a.energy.ke_rotational_final == b.energy.ke_rotational_final
