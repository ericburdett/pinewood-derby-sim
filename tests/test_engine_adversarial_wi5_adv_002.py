"""WI5-ADV-002 — a stable, legal, well-placed slow car must FINISH, not DNF.

Confirmed adversarial finding (domain correctness, high):

A LEGAL, STABLE, optimally-placed light car is reported as a *crash*
(``outcome = DNF``, ``race_time_s = None``) instead of finishing slowly. With the
default ``STRAIGHT`` alignment a 4.0 oz car at d_COM = 0.85 in — squarely inside the
optimal placement zone [0.75, 1.0] in, far above the 0.625-in instability threshold,
``legal_weight = True`` — reaches the flat at ~4.6 m/s, then the additive friction
model (axle + drag + ping-pong rail) decelerates it to v = 0 a few centimetres short
of the ~12.8 m finish line, where the engine's ``if velocity <= 0.0 and
acceleration <= 0.0`` branch (engine.py:266) classifies it as DNF.

This is physically wrong and educationally harmful: real 3–4 oz derby cars on a
standard track *coast across the line slowly*; they do not crash. The DNF cliff is
defined (PRD AC-P3, TRD §4) to mean **instability / wobble** (front normal force
collapses, d_COM < 0.625 in). Giving a perfectly stable, rule-legal, well-placed car
that same "crash" verdict teaches a young builder that a valid build *failed*.

It also makes PRD AC-W1 ("within the stable zone the heavier car FINISHES strictly
faster") vacuous on the default STRAIGHT alignment, because the lighter member of a
stable mass pair never finishes at all. The WI-5 AC-W1 tests dodge this by hard-coding
``alignment = "RAIL_RIDER"`` in their helpers, so the suite stays green while the
directional claim fails under the default/real alignment.

The correct behavior (reconciling TRD §9's documented stall->DNF guard against the
PRD's domain-correctness requirement): a **stable** car (positive front normal force,
d_COM at/above the 0.625-in threshold) that merely runs out of speed should **FINISH**
with a large ``race_time_s`` — "finishes slowly", not "crashed". DNF stays reserved
for the genuine instability cliff (AC-P3).

These tests pin that contract. They are deterministic: fixed dt, fixed seed; STRAIGHT
uses the default seed so the seeded ping-pong path is reproducible.

Traceability: PRD §6 AC-P3 (DNF == instability), AC-W1 (heavier finishes faster),
AC-O2 (FINISHED <=> positive finite time); adversarial finding WI5-ADV-002.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult

# Spec-anchored placement facts, mirrored from the PRD (NOT read from the engine):
# the instability cliff lives at d_COM < 0.625 in (PRD AC-P3 / TRD §4); the optimal
# zone is [0.75, 1.0] in (PRD AC-P2). d_COM = 0.85 in is squarely stable + optimal.
STABLE_OPTIMAL_DCOM_IN = 0.85
UNSTABLE_DCOM_IN = 0.15  # < 0.625 in: the genuine wobble/crash cliff (AC-P3)


def _make_car(
    *,
    mass_oz: float,
    com_ahead_of_rear_axle_in: float = STABLE_OPTIMAL_DCOM_IN,
    alignment: str = "STRAIGHT",
    count_touching: int = 4,
) -> CarDesign:
    """A valid baseline car. Defaults to the finding's exact configuration:
    STRAIGHT alignment (the engine default a real builder gets) and a stable,
    optimal d_COM, so the only thing under test is the FINISH-vs-DNF verdict."""
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


def _finished(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.FINISHED


def _is_dnf(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.DNF


# ───────────────────────────────────────────────────────────────────────────── #
# The headline regression: the finding's *exact* repro configuration.
# A legal, stable, optimally-placed 4.0 oz STRAIGHT car must FINISH slowly, not DNF.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi5_adv_002_legal_stable_light_straight_car_finishes_not_dnf() -> None:
    """The finding's repro verbatim: 4.0 oz, d_COM = 0.85 in (optimal + stable),
    STRAIGHT alignment, STANDARD_TRACK, dt=1e-3, seed=0. The car reaches the flat at
    ~4.6 m/s and coasts almost to the line. A stable, rule-legal, well-placed car that
    merely slows down is a slow FINISHER, not a crash — so it must report FINISHED with
    a positive finite race_time_s, not DNF / None."""
    result = _simulate(_make_car(mass_oz=4.0))

    assert result.legal_weight is True, "the 4.0 oz car is rule-legal (precondition)"
    assert result.normal_forces.front > 0.0, (
        "front normal force is positive => the car is stable (not the wobble cliff); "
        f"got N_f={result.normal_forces.front!r}"
    )
    assert _finished(result), (
        "a LEGAL, STABLE, optimally-placed (d_COM=0.85 in) car that reaches the flat "
        f"and slows down must FINISH slowly, not be reported as a crash; got "
        f"{result.outcome!r} (race_time_s={result.race_time_s!r}). DNF is reserved for "
        "the instability cliff (AC-P3, d_COM < 0.625 in)."
    )
    assert result.race_time_s is not None
    assert math.isfinite(result.race_time_s) and result.race_time_s > 0.0, (
        "a slow finisher must report a positive finite race_time_s (AC-O2), "
        f"got {result.race_time_s!r}"
    )


def test_wi5_adv_002_slow_finisher_time_is_larger_than_a_fast_car() -> None:
    """'Finishes slowly' has teeth: the stable light STRAIGHT car must not only FINISH
    but do so with a LARGER race_time_s than a heavier, faster car on the same track —
    confirming the fix produces a genuinely-slow finish, not a coincidental fast one."""
    slow = _simulate(_make_car(mass_oz=4.0))            # the previously-DNF car
    fast = _simulate(_make_car(mass_oz=5.0))            # heavier => more PE => faster

    assert _finished(slow) and _finished(fast), (
        "both stable, legal cars must FINISH on the default STRAIGHT alignment"
    )
    assert slow.race_time_s is not None and fast.race_time_s is not None
    assert slow.race_time_s > fast.race_time_s, (
        "the lighter car should finish *slowly* (a larger time), not crash; "
        f"got light={slow.race_time_s:.6f}s vs heavy={fast.race_time_s:.6f}s"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# Generalization: a STABLE car that runs out of speed never DNFs. DNF == instability.
# Covers the finding's note that cars <= 3 oz at the same stable placement also DNF,
# on BOTH alignments named in the finding (STRAIGHT and RAIL_RIDER).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi5_adv_002_light_straight_cars_in_stable_zone_all_finish() -> None:
    """Every light car at a stable, optimal d_COM on the default STRAIGHT alignment
    must FINISH — none is a crash. Sweeps the 3.0–4.0 oz band the finding flags as
    wrongly DNF'ing."""
    for mass_oz in (3.0, 3.25, 3.5, 3.75, 4.0):
        result = _simulate(_make_car(mass_oz=mass_oz))
        assert result.normal_forces.front > 0.0, (
            f"{mass_oz} oz car is stable (N_f>0) — a precondition for FINISH-not-crash"
        )
        assert _finished(result), (
            f"a stable, legal {mass_oz} oz car (d_COM=0.85 in, STRAIGHT) must FINISH "
            f"slowly, not DNF; got {result.outcome!r}"
        )
        assert result.race_time_s is not None and result.race_time_s > 0.0


def test_wi5_adv_002_light_rail_rider_cars_in_stable_zone_finish() -> None:
    """The finding also calls out RAIL_RIDER: cars <= 3 oz at the same stable placement
    DNF. A 3.0 oz RAIL_RIDER car at the optimal d_COM is stable and legal, so it must
    FINISH slowly, not crash."""
    result = _simulate(_make_car(mass_oz=3.0, alignment="RAIL_RIDER"))
    assert result.normal_forces.front > 0.0, "stable car (N_f>0) precondition"
    assert _finished(result), (
        "a stable, legal 3.0 oz RAIL_RIDER car at the optimal d_COM must FINISH "
        f"slowly, not DNF; got {result.outcome!r}"
    )
    assert result.race_time_s is not None and result.race_time_s > 0.0


# ───────────────────────────────────────────────────────────────────────────── #
# AC-W1 must hold on the DEFAULT/REAL alignment, not just on the hard-coded
# RAIL_RIDER the existing WI-5 tests use. The directional claim is vacuous if the
# lighter car DNFs, so this re-asserts AC-W1 *on STRAIGHT*.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi5_adv_002_acw1_holds_on_default_straight_alignment() -> None:
    """PRD AC-W1 — within the stable zone, the heavier of two otherwise-identical cars
    finishes strictly faster. The existing AC-W1 tests pin this only on RAIL_RIDER; on
    the engine-default STRAIGHT alignment the lighter (4.0 oz) car currently DNFs, so
    the claim is vacuous. Both stable cars must FINISH and the heavier must be strictly
    faster, on STRAIGHT."""
    lighter = _simulate(_make_car(mass_oz=4.0, alignment="STRAIGHT"))
    heavier = _simulate(_make_car(mass_oz=5.0, alignment="STRAIGHT"))

    assert _finished(lighter), (
        "AC-W1 is vacuous unless the lighter stable car also FINISHES on STRAIGHT; "
        f"got {lighter.outcome!r}"
    )
    assert _finished(heavier), f"heavier car must FINISH on STRAIGHT; got {heavier.outcome!r}"
    assert lighter.race_time_s is not None and heavier.race_time_s is not None
    assert heavier.race_time_s < lighter.race_time_s, (
        "more mass => more PE => strictly faster, on the default STRAIGHT alignment "
        f"too; got heavy={heavier.race_time_s:.6f}s vs light={lighter.race_time_s:.6f}s"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# Guard: the fix must NOT erase the legitimate DNF cliff. An UNSTABLE car
# (d_COM < 0.625 in) must STILL be a DNF — DNF means instability (AC-P3), and the
# distinction between "slow but stable" (FINISH) and "unstable" (DNF) is the whole
# educational point. This pins that the fix doesn't simply make everything finish.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi5_adv_002_unstable_car_still_dnfs() -> None:
    """An unstable rear bias (d_COM = 0.5 in < 0.625 in) must STILL be a DNF with
    race_time_s = None (AC-P3). The fix must distinguish a slow-but-stable finisher
    (FINISH) from a genuine wobble/crash (DNF), not blanket-convert DNFs to finishes."""
    result = _simulate(_make_car(mass_oz=4.0, com_ahead_of_rear_axle_in=UNSTABLE_DCOM_IN))
    assert _is_dnf(result), (
        "an unstable car (d_COM=0.5 in < 0.625 in) must remain a DNF — DNF means the "
        f"instability cliff (AC-P3), not 'finished slowly'; got {result.outcome!r}"
    )
    assert result.race_time_s is None, (
        f"a DNF must report race_time_s=None (AC-O2), got {result.race_time_s!r}"
    )
