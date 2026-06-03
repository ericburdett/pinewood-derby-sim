"""WI6-ADV-001 — the DNF stability cliff must key on the front-load FRACTION, not an
absolute d_COM distance.

Confirmed adversarial finding (domain correctness, high):

The engine keys instability on an ABSOLUTE distance
(``unstable = d_com < _COM_UNSTABLE_BELOW.m`` = 0.625 in, engine.py), independent of
the wheelbase ``L``. But the physical stability the spec describes is the front-load
FRACTION ``N_f / (M·g) = d_COM / L`` (physics-spec §4.2: "the front normal force N_f
approaches zero on the flat"; AC-P4: ``N_f = M·g·(d_COM/L)``). Because the threshold
ignores ``L``, the model inverts for non-standard wheelbases:

- A tail-heavy car (wheelbase = 8 in, d_COM = 0.7 in -> only 8.7% of weight on the
  front, marginally stable) FINISHES.
- A maximally nose-heavy car (wheelbase = 1 in, d_COM = 0.6 in -> 60% of weight on
  the front, maximally stable) is reported DNF.

The more nose-heavy / more stable car is the one declared a crash. This teaches wrong
physics (a nose-heavy car cannot wobble off the line from front-lift) and is squarely
in WI-6's named scope (the DNF stability cliff).

These tests pin the *contract* the spec/AC-P3/AC-P4 state — instability is governed by
the front-load fraction ``d_COM / L`` reaching the spec's collapse threshold — not the
absolute-distance shortcut the engine currently takes. They are derived from the
fraction the spec names; the canonical BSA wheelbase (4.375 in) is used to express the
fraction at the named 0.625 in cliff so the standard-wheelbase behaviour is unchanged.

All tests are deterministic: fixed dt, fixed seed, RAIL_RIDER alignment (no seeded
ping-pong draw to confound a placement claim).

Traceability: PRD §6 AC-P3/AC-P4; physics-spec §4.2; adversarial finding WI6-ADV-001.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult

# Spec-anchored constants (PRD §6 Placement; TRD §5 placement zones).
STD_WHEELBASE_IN = 4.375        # L (PRD A4 BSA-typical default)
# The genuine front-load COLLAPSE (graded placement model): only when the front carries
# essentially nothing can the car not run at all (DNF). Above it the car is tippy/slower but
# still finishes. The threshold is a front-load FRACTION (N_f/(M·g) = d_COM/L), NOT a raw
# distance — the physical invariant the engine must key on (a long-wheelbase tail-heavy car
# below the fraction still DNFs; a short nose-heavy car above it finishes). This is the WI6-
# ADV-001 point, preserved; only the threshold value changed with the graded model.
CRASH_FRONT_FRACTION = 0.06              # front load essentially gone → DNF
COM_CRASH_BELOW_IN = CRASH_FRONT_FRACTION * STD_WHEELBASE_IN  # ≈ 0.2625 in at the std wheelbase


def _make_car(
    *,
    com_ahead_of_rear_axle_in: float,
    wheelbase_in: float = STD_WHEELBASE_IN,
    mass_oz: float = 5.0,
    alignment: str = "RAIL_RIDER",
) -> CarDesign:
    """A valid baseline car parameterized by d_COM and wheelbase; everything else
    fixed so the only thing under test is how placement governs stability."""
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(wheelbase_in),
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


def _simulate(car: CarDesign) -> RaceResult:
    from pinewood_derby.engine import simulate
    from pinewood_derby.track import STANDARD_TRACK

    return simulate(car, STANDARD_TRACK, dt=1e-3, seed=0)


def _is_dnf(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.DNF


def _finished(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.FINISHED


# ───────────────────────────────────────────────────────────────────────────── #
# WI6-ADV-001 — the exact reported inversion: a marginally-stable tail-heavy car
# finishes while a maximally-stable nose-heavy car is declared DNF. The verdicts
# are physically backwards.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi6_adv_001_nose_heavy_car_is_not_dnf() -> None:
    """A maximally nose-heavy car (wheelbase = 1 in, d_COM = 0.6 in -> 60% of the
    weight on the front axle) is the MOST stable placement possible: it cannot lift
    its front and wobble off the line. It must NOT be a DNF.

    The engine declares it DNF only because 0.6 in < the absolute 0.625 in threshold,
    ignoring that the wheelbase is 1 in (so the front carries 60% of the load)."""
    nose_heavy = _simulate(
        _make_car(com_ahead_of_rear_axle_in=0.6, wheelbase_in=1.0)
    )
    front_fraction = 0.6 / 1.0
    assert not _is_dnf(nose_heavy), (
        f"a car with {front_fraction:.0%} of its weight on the front axle "
        f"(wheelbase=1 in, d_COM=0.6 in) is maximally stable and cannot wobble off "
        f"the line, but the engine reported {nose_heavy.outcome}. Instability must "
        f"key on the front-load fraction d_COM/L, not an absolute d_COM distance."
    )


def test_wi6_adv_001_stability_verdict_is_not_inverted_across_wheelbases() -> None:
    """The reported inversion in one assertion: the tail-heavy car (8.7% front load)
    must not OUTLAST the nose-heavy car (60% front load) in stability. Whatever the
    cliff is, the car with more weight on its front cannot be the one that crashes
    while the near-tail-balanced car finishes."""
    tail_heavy = _simulate(
        _make_car(com_ahead_of_rear_axle_in=0.7, wheelbase_in=8.0)
    )   # front load 0.7/8 = 8.7%
    nose_heavy = _simulate(
        _make_car(com_ahead_of_rear_axle_in=0.6, wheelbase_in=1.0)
    )   # front load 0.6/1 = 60%

    inverted = _finished(tail_heavy) and _is_dnf(nose_heavy)
    assert not inverted, (
        "physically inverted stability verdict: the tail-heavy car (8.7% front load, "
        f"{tail_heavy.outcome}) finished while the nose-heavy car (60% front load, "
        f"{nose_heavy.outcome}) was declared a crash. A car with more weight on its "
        "front is MORE stable, not less."
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI6-ADV-001 — the cliff must scale with wheelbase: a tail-heavy car below the
# fractional collapse threshold must DNF even at a long wheelbase.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi6_adv_001_long_wheelbase_below_fractional_cliff_is_dnf() -> None:
    """A long-wheelbase car whose front-load FRACTION is below the collapse threshold must
    DNF — even though its absolute d_COM (0.3 in) is above any small inch number. wheelbase=8
    in, d_COM=0.3 in -> front fraction 3.75%, well under the ~6% collapse fraction: the front
    is effectively unloaded, so the car cannot run. The verdict keys on the FRACTION, not the
    distance (the WI6-ADV-001 invariant)."""
    front_fraction = 0.3 / 8.0
    assert front_fraction < CRASH_FRONT_FRACTION, (
        "sanity: this car's front-load fraction must be below the collapse threshold"
    )
    r = _simulate(_make_car(com_ahead_of_rear_axle_in=0.3, wheelbase_in=8.0))
    assert _is_dnf(r), (
        f"a car with only {front_fraction:.1%} of its weight on the front "
        f"(wheelbase=8 in, d_COM=0.3 in) is below the front-collapse fraction "
        f"({CRASH_FRONT_FRACTION:.1%}) and must DNF, regardless of its absolute "
        f"d_COM, got {r.outcome}."
    )
    assert r.race_time_s is None, "a DNF must report race_time_s = None"


# ───────────────────────────────────────────────────────────────────────────── #
# WI6-ADV-001 — the standard wheelbase behaviour the named 0.625 in cliff encodes
# must be unchanged (a fractional cliff calibrated at L = 4.375 in reproduces it).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi6_adv_001_standard_wheelbase_collapse_threshold() -> None:
    """At the canonical BSA wheelbase the fraction-based collapse threshold (graded model)
    must hold: a hair below the ~0.2625 in collapse point DNFs, a hair above still finishes
    (tippy). This guards the standard-wheelbase contract while the threshold stays a fraction."""
    below = _simulate(
        _make_car(
            com_ahead_of_rear_axle_in=COM_CRASH_BELOW_IN - 0.02,
            wheelbase_in=STD_WHEELBASE_IN,
        )
    )
    above = _simulate(
        _make_car(
            com_ahead_of_rear_axle_in=COM_CRASH_BELOW_IN + 0.05,
            wheelbase_in=STD_WHEELBASE_IN,
        )
    )
    assert _is_dnf(below), (
        "at the standard wheelbase, just below the front-collapse point must DNF"
    )
    assert _finished(above), (
        "at the standard wheelbase, just above the collapse point must still FINISH (tippy)"
    )
