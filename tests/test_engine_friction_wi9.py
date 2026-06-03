"""WI-9 — Axle-friction lever: polished+graphite axles are faster, and the axle
resistive force / reported energy follow the spec formula and scale with the friction
coefficient μ.

Behavior-driven tests written against the engine's PUBLIC contract (``simulate`` + the
frozen ``RaceResult`` / ``EnergyLedger``) only. Imports live inside each test body so a
missing/renamed symbol fails *that criterion* independently (true per-criterion
isolation) rather than aborting whole-file collection.

Traceability to the WI-9 acceptance criteria (PRD §6; physics-spec §3.2; TRD §4 force
model / §11):

- AC-F1 (PRD l.125): polished + graphite axles (μ = 0.10) yield a strictly smaller
  ``race_time_s`` than unprepared / no-lube axles (μ = 0.35), all else equal.
- AC-F2 (PRD l.127): the axle resistive force follows
  ``F_axle = N_wheel·μ·(r_axle / R_outer)`` (per-wheel normal load summed over the N
  touching wheels = the total normal load) and the reported ``energy.w_axle`` strictly
  increases with μ, all else equal, on FINISHED runs.

Because the engine's ``F_axle`` is never exposed directly, AC-F2 is verified through the
formula's *structural consequences* on the observable ``energy.w_axle`` field, all else
equal — never by reaching into engine internals:

1. **Linear in μ (the ``μ`` factor):** with μ = 0 the axle term vanishes
   (``w_axle == 0``); a low-friction sweep where the trajectory is nearly frozen shows
   ``w_axle`` rising in near-proportion to μ.
2. **The ``(r_axle / R_outer)`` factor:** holding μ and everything else fixed, a larger
   ``r_axle`` (bigger axle-to-wheel radius ratio) increases ``w_axle``; a larger
   ``R_outer`` decreases it.
3. **The normal-load factor ``N_wheel``:** a heavier car (larger total normal load
   ``M·g``) loses strictly more to the axle than a lighter one over the same descent.
4. **Monotonicity:** ``w_axle`` strictly increases across a μ sweep on FINISHED runs.

Integrity / determinism: every test fixes ``dt`` and ``seed`` (no clock / network /
unseeded RNG) and uses RAIL_RIDER alignment so the seeded ping-pong rail draw never
confounds a directional axle claim. Assertions are directional / structural / bound-based
— never a magic magnitude. This file is NEW; it modifies, skips, or deletes no existing
test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult
    from pinewood_derby.track import Track

# Spec-anchored axle-prep presets (physics-spec §3.2; TRD §5), pinned here so the
# comparison references the contract rather than the engine's private constants.
MU_POLISHED_GRAPHITE = 0.10
MU_UNPREPARED = 0.35


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — build valid inputs from plain numbers via the value objects.
# Mirrors tests/test_engine_wheels_wi7.py so construction stays consistent.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_car(
    *,
    mass_oz: float = 5.0,
    com_ahead_of_rear_axle_in: float = 0.85,
    wheelbase_in: float = 4.375,
    alignment: str = "RAIL_RIDER",
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

    Only the axle/geometry fields relevant to a given AC are varied across each
    comparison; everything else is held identical so each test isolates exactly one
    lever ("all else equal").
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
# AC-F1 — polished + graphite axles (μ = 0.10) are strictly faster than unprepared /
# no-lube axles (μ = 0.35), all else equal. (physics-spec §3.2)
# ───────────────────────────────────────────────────────────────────────────── #
def test_acf1_polished_graphite_finishes_strictly_faster_than_unprepared() -> None:
    """Two cars identical except the axle friction coefficient — polished+graphite
    (μ = 0.10) vs unprepared/no-lube (μ = 0.35) — both FINISHED: the low-friction car
    must finish strictly sooner. Less bore friction means a larger net force down the
    track, so the car accelerates more and crosses the line earlier."""
    from pinewood_derby.track import STANDARD_TRACK

    polished = _simulate(
        _make_car(friction_coefficient=MU_POLISHED_GRAPHITE), STANDARD_TRACK, seed=0
    )
    unprepared = _simulate(
        _make_car(friction_coefficient=MU_UNPREPARED), STANDARD_TRACK, seed=0
    )

    assert _finished(polished), "polished+graphite car should FINISH for a valid comparison"
    assert _finished(unprepared), "unprepared car should FINISH for a valid comparison"
    assert polished.race_time_s is not None and unprepared.race_time_s is not None
    assert polished.race_time_s < unprepared.race_time_s, (
        f"polished+graphite car ({polished.race_time_s:.6f}s) must beat the unprepared "
        f"car ({unprepared.race_time_s:.6f}s) — lower μ means less axle bore friction"
    )


def test_acf1_polished_graphite_reaches_higher_finish_velocity() -> None:
    """The mechanism behind the faster time: with less axle friction dragging on it,
    the polished+graphite car carries strictly more speed across the line."""
    from pinewood_derby.track import STANDARD_TRACK

    polished = _simulate(
        _make_car(friction_coefficient=MU_POLISHED_GRAPHITE), STANDARD_TRACK, seed=0
    )
    unprepared = _simulate(
        _make_car(friction_coefficient=MU_UNPREPARED), STANDARD_TRACK, seed=0
    )

    assert _finished(polished) and _finished(unprepared)
    assert polished.finish_velocity > unprepared.finish_velocity, (
        f"polished finish velocity ({polished.finish_velocity:.4f} m/s) should exceed "
        f"unprepared ({unprepared.finish_velocity:.4f} m/s)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-F2 — F_axle = N_wheel·μ·(r_axle / R_outer); reported energy.w_axle strictly
# increases with μ, all else equal, on FINISHED runs. (physics-spec §3.2)
#
# Verified structurally through observable energy.w_axle (the formula's consequences),
# never by reaching into private engine internals.
# ───────────────────────────────────────────────────────────────────────────── #
def test_acf2_w_axle_strictly_increases_with_mu() -> None:
    """Sweep μ across a range of FINISHED runs, all else equal: the reported axle
    energy ``energy.w_axle`` must strictly increase at every step. This is the direct
    behavioral statement of AC-F2 ("w_axle increases with μ") — F_axle is linear in μ,
    so the work it removes over the run grows with μ."""
    from pinewood_derby.track import STANDARD_TRACK

    mus = [0.05, 0.10, 0.20, 0.35, 0.50]
    runs = [
        _simulate(_make_car(friction_coefficient=mu), STANDARD_TRACK, seed=0)
        for mu in mus
    ]
    for mu, r in zip(mus, runs):
        assert _finished(r), f"car at μ={mu} should FINISH for a valid w_axle comparison"

    w_axles = [r.energy.w_axle for r in runs]
    for mu_a, mu_b, wa, wb in zip(mus, mus[1:], w_axles, w_axles[1:]):
        assert wb > wa, (
            f"energy.w_axle must strictly increase with μ: at μ={mu_a} w_axle={wa:.6f} J "
            f"but at μ={mu_b} w_axle={wb:.6f} J (expected larger)"
        )


def test_acf2_w_axle_vanishes_when_mu_is_zero() -> None:
    """The ``μ`` factor of ``F_axle = N_wheel·μ·(r_axle/R_outer)`` directly: an
    idealized frictionless axle (μ = 0) makes the whole axle term vanish, so the run
    reports exactly zero axle energy. With friction present the axle energy is strictly
    positive. This pins F_axle's proportionality to μ at the boundary via an observable
    field, without coupling to engine internals."""
    from pinewood_derby.track import STANDARD_TRACK

    frictionless = _simulate(
        _make_car(friction_coefficient=0.0), STANDARD_TRACK, seed=0
    )
    with_friction = _simulate(
        _make_car(friction_coefficient=0.20), STANDARD_TRACK, seed=0
    )

    assert _finished(frictionless) and _finished(with_friction)
    assert frictionless.energy.w_axle == 0.0, (
        f"a frictionless axle (μ=0) must report exactly zero axle energy, got "
        f"{frictionless.energy.w_axle:.6e} J"
    )
    assert with_friction.energy.w_axle > 0.0, (
        f"a car with axle friction must lose energy to the axle, got "
        f"{with_friction.energy.w_axle:.6e} J"
    )


def test_acf2_w_axle_is_near_proportional_to_mu_in_low_friction_regime() -> None:
    """The *linear-in-μ* structure of ``F_axle = N_wheel·μ·(r_axle/R_outer)`` behaviorally:
    in a low-friction regime the trajectory is nearly frozen across μ, so the axle work
    (the path integral of a force that is exactly linear in μ) should scale very nearly
    in proportion to μ. Doubling μ from 0.02 to 0.04 must roughly double w_axle (within a
    loose 10% band that allows for the small trajectory shift), and likewise 0.02→0.06
    triples it. This confirms F_axle's μ-proportionality without inspecting internals."""
    from pinewood_derby.track import STANDARD_TRACK

    base = _simulate(_make_car(friction_coefficient=0.02), STANDARD_TRACK, seed=0)
    double = _simulate(_make_car(friction_coefficient=0.04), STANDARD_TRACK, seed=0)
    triple = _simulate(_make_car(friction_coefficient=0.06), STANDARD_TRACK, seed=0)

    assert _finished(base) and _finished(double) and _finished(triple)
    w0 = base.energy.w_axle
    assert w0 > 0.0, "low-friction baseline must still lose some energy to the axle"

    ratio_2x = double.energy.w_axle / w0
    ratio_3x = triple.energy.w_axle / w0
    assert 1.8 <= ratio_2x <= 2.2, (
        f"doubling μ should ~double w_axle (linear-in-μ force); got ratio {ratio_2x:.4f} "
        f"(expected ≈ 2.0)"
    )
    assert 2.7 <= ratio_3x <= 3.3, (
        f"tripling μ should ~triple w_axle (linear-in-μ force); got ratio {ratio_3x:.4f} "
        f"(expected ≈ 3.0)"
    )


def test_acf2_w_axle_increases_with_axle_to_wheel_radius_ratio() -> None:
    """The ``(r_axle / R_outer)`` factor of the formula: holding μ and everything else
    fixed, a larger axle radius (bigger r_axle/R_outer) increases the axle resistive
    force and so increases the reported axle energy. A thinner axle shank (smaller
    r_axle) loses strictly less — a real derby principle (thin, polished axles)."""
    from pinewood_derby.track import STANDARD_TRACK

    thin = _simulate(_make_car(axle_radius_in=0.030), STANDARD_TRACK, seed=0)
    thick = _simulate(_make_car(axle_radius_in=0.060), STANDARD_TRACK, seed=0)

    assert _finished(thin) and _finished(thick)
    assert thick.energy.w_axle > thin.energy.w_axle, (
        f"a thicker axle (larger r_axle/R_outer) must lose more to the axle: "
        f"thick w_axle={thick.energy.w_axle:.6f} J should exceed thin "
        f"w_axle={thin.energy.w_axle:.6f} J"
    )


def test_acf2_w_axle_decreases_with_larger_outer_radius() -> None:
    """The reciprocal side of the ``(r_axle / R_outer)`` factor: holding μ, r_axle and
    everything else fixed, a larger outer wheel radius shrinks the r_axle/R_outer ratio
    and so reduces the axle resistive force and the reported axle energy."""
    from pinewood_derby.track import STANDARD_TRACK

    small_wheel = _simulate(_make_car(outer_radius_in=0.500), STANDARD_TRACK, seed=0)
    big_wheel = _simulate(_make_car(outer_radius_in=0.700), STANDARD_TRACK, seed=0)

    assert _finished(small_wheel) and _finished(big_wheel)
    assert big_wheel.energy.w_axle < small_wheel.energy.w_axle, (
        f"a larger R_outer (smaller r_axle/R_outer) must lose less to the axle: "
        f"big-wheel w_axle={big_wheel.energy.w_axle:.6f} J should be below small-wheel "
        f"w_axle={small_wheel.energy.w_axle:.6f} J"
    )


def test_acf2_w_axle_increases_with_normal_load() -> None:
    """The normal-load factor ``N_wheel`` (per-wheel load summed over the touching
    wheels = total normal load M·g) of the formula: a heavier car presses its axles down
    harder, so it loses strictly more energy to axle friction over the same descent than
    a lighter car, all else equal. Verifies F_axle's dependence on the normal load via an
    observable field."""
    from pinewood_derby.track import STANDARD_TRACK

    light = _simulate(_make_car(mass_oz=3.0), STANDARD_TRACK, seed=0)
    heavy = _simulate(_make_car(mass_oz=5.0), STANDARD_TRACK, seed=0)

    assert _finished(light), "3 oz car should FINISH for a valid normal-load comparison"
    assert _finished(heavy), "5 oz car should FINISH for a valid normal-load comparison"
    assert heavy.energy.w_axle > light.energy.w_axle, (
        f"a heavier car (larger normal load N) must lose more to the axle: heavy "
        f"w_axle={heavy.energy.w_axle:.6f} J should exceed light "
        f"w_axle={light.energy.w_axle:.6f} J"
    )
