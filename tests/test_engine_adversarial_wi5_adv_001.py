"""WI5-ADV-001 — legal-weight reporting must honor the gram limit AC-W2 names.

Confirmed adversarial finding (domain correctness / boundaries, high):

PRD AC-W2 states *both* representations of the legal limit explicitly:
``mass <= 5.0 oz (141.748 g) -> legal_weight = True``. A builder weighs a real car
in grams to the stated 141.748 g limit; the engine must report that car legal.

The engine computes ``legal_weight = mass <= _MAX_MASS.kg`` with
``_MAX_MASS = Mass.from_ounces(5.0)`` and the truncated factor ``OZ_TO_KG = 0.0283495``,
giving a threshold of ``0.1417475 kg``. But ``Mass.from_grams(141.748).kg = 0.141748``,
which is ``> 0.1417475``, so a car the AC says is legal is reported ``legal_weight = False``.
The two limit figures AC-W2 names no longer agree at the boundary they name.

These tests pin the *contract* AC-W2 states (the 141.748 g figure), not whatever the
engine's float path happens to compute. They are deterministic: fixed dt, fixed seed,
RAIL_RIDER alignment (no seeded ping-pong draw to confound the boolean report).

Traceability: PRD §6 AC-W2; adversarial finding WI5-ADV-001.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult

# The legal limit AC-W2 names, in the unit a real builder weighs in. AC-W2:
# "mass <= 5.0 oz (141.748 g) -> legal_weight = True". This gram figure is part of
# the approved contract, mirrored here from the PRD (NOT read from the engine).
AC_W2_LIMIT_GRAMS = 141.748


def _car_from_mass(mass_obj: Any) -> CarDesign:
    """A valid, FINISHED-capable baseline car built around a given ``Mass``.

    RAIL_RIDER alignment + a stable d_COM keep the run clean and deterministic so the
    boolean ``legal_weight`` report is the only thing under test."""
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
        alignment=Alignment["RAIL_RIDER"],
    )


def _simulate(car: CarDesign) -> RaceResult:
    from pinewood_derby.engine import simulate
    from pinewood_derby.track import STANDARD_TRACK

    return simulate(car, STANDARD_TRACK, dt=1e-3, seed=0)


# ───────────────────────────────────────────────────────────────────────────── #
# WI5-ADV-001 — the core regression: the gram limit AC-W2 explicitly names is legal.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi5_adv_001_car_at_named_gram_limit_is_legal() -> None:
    """A car weighing exactly 141.748 g — the figure AC-W2 names as the legal limit —
    must report legal_weight = True. The boundary is inclusive (``<=``).

    Today the engine reports False because its 5.0 oz threshold (via the truncated
    0.0283495 factor) lands at 141.7475 g, just below the gram figure the same AC names.
    """
    from pinewood_derby.units import Mass

    result = _simulate(_car_from_mass(Mass.from_grams(AC_W2_LIMIT_GRAMS)))
    assert result.legal_weight is True, (
        f"AC-W2 names 141.748 g as the legal limit (<=), but a car at exactly that "
        f"weight reported legal_weight={result.legal_weight!r}. The 5.0 oz threshold "
        f"and the 141.748 g figure AC-W2 also names must agree at the boundary."
    )


def test_wi5_adv_001_just_under_named_gram_limit_is_legal() -> None:
    """A whisker below the named gram limit is unambiguously legal — guards the ``<=``
    direction so the boundary fix can't overshoot into rejecting under-limit cars."""
    from pinewood_derby.units import Mass

    result = _simulate(_car_from_mass(Mass.from_grams(AC_W2_LIMIT_GRAMS - 0.001)))
    assert result.legal_weight is True, (
        f"a car at {AC_W2_LIMIT_GRAMS - 0.001} g (under the AC-W2 limit) must be legal, "
        f"got legal_weight={result.legal_weight!r}"
    )


def test_wi5_adv_001_both_named_limit_representations_agree() -> None:
    """AC-W2 names the limit two ways — 5.0 oz and (141.748 g) — as the SAME quantity.
    A car at each representation must get the SAME legal_weight verdict (both True).

    Pins the contradiction directly: the float-ounce path is trivially legal, but the
    gram path the AC equally endorses is not, so the two disagree at the named boundary.
    """
    from pinewood_derby.units import Mass

    at_ounce_limit = _simulate(_car_from_mass(Mass.from_ounces(5.0)))
    at_gram_limit = _simulate(_car_from_mass(Mass.from_grams(AC_W2_LIMIT_GRAMS)))

    assert at_ounce_limit.legal_weight is True, (
        "the 5.0 oz limit AC-W2 names must be legal"
    )
    assert at_gram_limit.legal_weight == at_ounce_limit.legal_weight, (
        "AC-W2 names the limit as both 5.0 oz and 141.748 g — they are the same quantity, "
        f"so legal_weight must match, got oz={at_ounce_limit.legal_weight!r} vs "
        f"g={at_gram_limit.legal_weight!r}"
    )
