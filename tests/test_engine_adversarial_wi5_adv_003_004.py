"""WI5-ADV-003 / WI5-ADV-004 — the stall-on-flat "teleport to the finish" bug.

Two confirmed adversarial findings (domain correctness, high), sharing one root cause.

WI5-ADV-003 — *A car that stalls METERS short of the line is reported FINISHED.*
    The WI5-ADV-002 fix over-corrected: engine.py's stall-on-flat branch
    (``if velocity <= 0.0 and acceleration <= 0.0`` with ``crossed_ramp``) now sets
    ``position = track_length; finished = True`` for ANY car that has merely left the
    ramp — regardless of how far short of the line it actually stopped. With
    STANDARD_TRACK (≈12.802 m), seed=0, a 2.0 oz RAIL_RIDER car at d_COM=0.85 in stalls
    (v -> 0) at ≈9.87 m — ≈2.93 m / ≈23% of the track short — yet ``simulate`` returns
    ``outcome = FINISHED``, ``race_time_s ≈ 4.6 s``, ``finish_velocity = 0.0``, and the
    trajectory's final point teleports straight from 9.87 m to 12.802 m at the same
    timestamp. A car that genuinely runs out of energy on the flat did NOT reach the
    line; reporting it FINISHED at the full length with v=0 corrupts the outcome,
    race_time_s, and finish_velocity for a whole band of light cars.

WI5-ADV-004 — *Heavier cars are reported SLOWER in the realistic light-car range.*
    Because the ADV-003 teleport fabricates non-physical finish times, the engine
    violates its #1 teaching principle and PRD AC-W1 ("more mass -> more PE -> faster")
    for 1–3 oz cars at the optimal, stable placement: 1.0 oz "finishes" in ≈3.54 s,
    2.0 oz in ≈4.60 s, 3.0 oz in ≈5.42 s — race_time_s INCREASES with mass. All three
    are reported FINISHED with a positive front normal force (stable, not the DNF
    cliff), so AC-W1's "within the stable zone" caveat does not excuse it. This teaches
    a young builder the exact WRONG physics (lighter is faster) — the worst possible
    bug per the profile/PRD. The existing AC-W1 monotonicity test hides it by sweeping
    only 4.0–5.0 oz, never entering the 1–3 oz region where the relationship inverts.

These tests pin the correct contract: a stable, legal car that stalls before the line
is NOT a finisher — it should report the real run (it did not reach ``track_length``),
and within the stable zone a heavier car must finish strictly faster across the
realistic light-car range, not slower. The intended resolution (a stalled-short car is
a non-finishing run, while a car that genuinely coasts to the line finishes) is for the
developer to choose; the tests only assert the observable contract, not the mechanism.

All tests are deterministic: fixed dt, fixed seed, no clock / network / unseeded RNG.

Traceability: PRD §6 AC-W1 (heavier -> strictly faster, within the stable zone),
AC-O1 (finish_velocity >= 0 and physically meaningful; trajectory monotone in position
at a fixed time), AC-O2 (FINISHED <=> the car reached the line); the educational-accuracy
NFR (§7); adversarial findings WI5-ADV-003 and WI5-ADV-004.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult

# Spec-anchored placement facts, mirrored from the PRD (NOT read from the engine).
# d_COM = 0.85 in is squarely inside the optimal zone [0.75, 1.0] in (AC-P2) and well
# above the 0.625-in instability cliff (AC-P3): the cars below are STABLE, not crashes.
STABLE_OPTIMAL_DCOM_IN = 0.85

# The finish-line tolerance below which "stalled short" is indistinguishable from
# "coasted to the line". The finding's car stalls ≈2.93 m (≈23% of the track) short —
# orders of magnitude beyond any negligible sub-step of creep. A few centimetres is a
# generous bound on "essentially at the line"; ≈2.9 m is unambiguously NOT finished.
NEAR_FINISH_TOL_M = 0.10


def _make_car(
    *,
    mass_oz: float,
    com_ahead_of_rear_axle_in: float = STABLE_OPTIMAL_DCOM_IN,
    alignment: str = "RAIL_RIDER",
    count_touching: int = 4,
) -> CarDesign:
    """The finding's exact configuration. RAIL_RIDER keeps the comparison
    seed-independent so a directional claim about *mass* is never confounded by the
    seeded ping-pong rail draw; d_COM = 0.85 in is stable + optimal."""
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(4.375),
        wheels=Wheels(
            count_touching=count_touching,
            wheel_mass=Mass.from_ounces(0.09),
            outer_radius=Length.from_inches(0.595),
            inner_radius=Length.from_inches(0.37),
            axle_radius=Length.from_inches(0.045),
        ),
        body=BodyShape(drag_coefficient=0.30, frontal_area=0.0028),
        axle=Axle(friction_coefficient=0.20),
        alignment=Alignment[alignment],
    )


def _simulate(car: CarDesign, *, dt: float = 1e-3, seed: int = 0) -> RaceResult:
    from pinewood_derby.engine import simulate
    from pinewood_derby.track import STANDARD_TRACK

    return simulate(car, STANDARD_TRACK, dt=dt, seed=seed)


def _track_length_m() -> float:
    from pinewood_derby.track import STANDARD_TRACK

    return STANDARD_TRACK.ramp_length.m + STANDARD_TRACK.flat_length.m


def _finished(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.FINISHED


def _max_moving_position(result: RaceResult) -> float:
    """The furthest position the car reached while still actually moving (v > 0).

    This excludes any fabricated final trajectory point that teleports the position to
    ``track_length`` at v = 0 without the car ever having travelled there.
    """
    moving = [p.position for p in result.trajectory if p.velocity > 1e-9]
    return max(moving) if moving else 0.0


# ───────────────────────────────────────────────────────────────────────────── #
# WI5-ADV-003 — a car that STALLS metres short must not be reported FINISHED at the
# full track length. Three independent observable symptoms of the teleport bug.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi5_adv_003_car_stalling_short_is_not_reported_finished() -> None:
    """The finding's headline repro: 2.0 oz, d_COM = 0.85 in (stable + optimal),
    RAIL_RIDER, STANDARD_TRACK, dt=1e-3, seed=0. The car actually stops moving at
    ≈9.87 m — ≈2.93 m short of the ≈12.802 m line — yet the engine reports FINISHED.
    A car that ran out of energy ≈23% short of the line did NOT finish."""
    result = _simulate(_make_car(mass_oz=2.0))
    track_length = _track_length_m()
    reached = _max_moving_position(result)
    short_by = track_length - reached

    # Precondition: this car genuinely stalls well short while moving forward.
    assert short_by > 1.0, (
        "precondition: the 2.0 oz car must actually stop moving more than a metre short "
        f"of the {track_length:.3f} m line; reached only {reached:.3f} m "
        f"(short by {short_by:.3f} m)"
    )
    assert not _finished(result), (
        "a car that ran out of energy and stopped moving "
        f"{short_by:.3f} m (~{100 * short_by / track_length:.0f}%) short of the finish "
        f"line did NOT finish; engine wrongly reported {result.outcome!r} "
        f"(race_time_s={result.race_time_s!r}). The stall-on-flat branch teleports a "
        "stalled-short car to the line."
    )


def test_wi5_adv_003_stalled_short_finish_velocity_is_not_a_fabricated_zero() -> None:
    """A genuinely FINISHED car crosses the line still moving, so finish_velocity > 0.
    The teleport bug reports FINISHED with finish_velocity = 0.0 — the tell-tale of a
    car that stalled and was then fabricated across the line. So: either the car did NOT
    finish, or (if the engine still calls it finished) it must have crossed the line
    with a positive finish velocity — never FINISHED-at-rest."""
    result = _simulate(_make_car(mass_oz=2.0))
    if _finished(result):
        assert result.finish_velocity > 0.0, (
            "a FINISHED car must cross the line still moving (finish_velocity > 0); a "
            "reported finish at finish_velocity = 0.0 is the stall-teleport artifact, "
            f"got finish_velocity={result.finish_velocity!r}"
        )


def test_wi5_adv_003_trajectory_does_not_teleport_to_the_finish_line() -> None:
    """The mechanism is visible in the trajectory: the buggy run appends a final point
    that jumps the position straight from the stall point (≈9.87 m) to the full track
    length at the SAME timestamp and v = 0. A physical trajectory never advances a large
    distance in zero time. Assert no two consecutive samples jump a non-trivial distance
    without any elapsed time."""
    result = _simulate(_make_car(mass_oz=2.0))
    traj = result.trajectory
    for prev, cur in zip(traj, traj[1:]):
        dx = cur.position - prev.position
        dt = cur.t - prev.t
        if dx > NEAR_FINISH_TOL_M:
            assert dt > 0.0, (
                f"trajectory teleports {dx:.3f} m forward (from {prev.position:.3f} m to "
                f"{cur.position:.3f} m) in zero elapsed time (t={prev.t!r}->{cur.t!r}); a "
                "stalled-short car must not be fabricated across the line"
            )


# ───────────────────────────────────────────────────────────────────────────── #
# WI5-ADV-004 — within the stable zone, a heavier car must finish strictly FASTER
# across the realistic 1–3 oz light-car range (AC-W1). The teleport artifact inverts
# this, teaching the worst possible physics.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi5_adv_004_heavier_is_not_slower_in_light_car_range() -> None:
    """The finding's repro: 1.0 oz vs 3.0 oz, both d_COM = 0.85 in (stable + optimal),
    RAIL_RIDER, seed=0. The engine reports both FINISHED yet the heavier 3.0 oz car
    SLOWER than the 1.0 oz car (≈5.42 s vs ≈3.54 s) — a direct AC-W1 violation that
    teaches 'lighter is faster'. If both are reported FINISHED, the heavier must be
    strictly faster (more mass -> more PE -> faster)."""
    light = _simulate(_make_car(mass_oz=1.0))
    heavy = _simulate(_make_car(mass_oz=3.0))

    # Both are stable (positive front normal force), so AC-W1's stable-zone caveat
    # applies — this is not the DNF cliff.
    assert light.normal_forces.front > 0.0 and heavy.normal_forces.front > 0.0, (
        "both light-car configs are stable (N_f > 0) — AC-W1's stable-zone caveat applies"
    )
    if _finished(light) and _finished(heavy):
        assert light.race_time_s is not None and heavy.race_time_s is not None
        assert heavy.race_time_s < light.race_time_s, (
            "within the stable zone the heavier car must finish STRICTLY FASTER "
            "(AC-W1: more mass -> more PE -> faster); engine reports the heavier 3.0 oz "
            f"car SLOWER ({heavy.race_time_s:.3f} s) than the 1.0 oz car "
            f"({light.race_time_s:.3f} s) — the exact wrong physics."
        )


def test_wi5_adv_004_race_time_monotonically_decreases_across_light_car_range() -> None:
    """Stronger than a single pair, and aimed squarely at the gap the existing AC-W1
    sweep leaves: across the 1–3 oz band (the realistic light-car range the current
    monotonicity test never enters), any car reported FINISHED must obey AC-W1 — a
    heavier finisher is never slower than a lighter finisher. The teleport artifact
    makes race_time_s INCREASE with mass here."""
    masses = [1.0, 1.5, 2.0, 2.5, 3.0]
    finishers: list[tuple[float, float]] = []
    for m in masses:
        r = _simulate(_make_car(mass_oz=m))
        assert r.normal_forces.front > 0.0, f"{m} oz car is stable (N_f > 0) — precondition"
        if _finished(r):
            assert r.race_time_s is not None
            assert math.isfinite(r.race_time_s)
            finishers.append((m, r.race_time_s))

    for (m_lo, t_lo), (m_hi, t_hi) in zip(finishers, finishers[1:]):
        assert t_hi <= t_lo, (
            "within the stable zone a heavier FINISHER must not be slower than a lighter "
            f"one (AC-W1); got {m_lo} oz -> {t_lo:.3f} s but {m_hi} oz -> {t_hi:.3f} s "
            "(heavier reported slower — AC-W1 inverted)"
        )


def test_wi5_adv_004_acw1_pair_is_not_a_fabricated_finish() -> None:
    """The 1–3 oz "finishes" are non-physical: the cars stalled short and were teleported
    to the line. Tie the AC-W1 violation back to its root cause — if such a car is
    reported FINISHED it must have actually reached the line still moving, not been
    fabricated there at rest."""
    for m in (1.0, 2.0, 3.0):
        r = _simulate(_make_car(mass_oz=m))
        if _finished(r):
            track_length = _track_length_m()
            reached = _max_moving_position(r)
            assert reached >= track_length - NEAR_FINISH_TOL_M, (
                f"the {m} oz car is reported FINISHED but only ever moved to "
                f"{reached:.3f} m of the {track_length:.3f} m line — a fabricated "
                "(teleported) finish, not a real one"
            )
            assert r.finish_velocity > 0.0, (
                f"the {m} oz FINISHED car must cross the line moving, not at rest; "
                f"got finish_velocity={r.finish_velocity!r}"
            )
