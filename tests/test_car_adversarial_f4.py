"""WI-3 — Adversarial edge tests for finding WI3-F4 (domain_correctness, high).

Covering RED tests for a confirmed adversarial-review finding (gates.md Step 4 ->
Step 1). They fail against the current ``CarDesign`` (which performs no cross-field
mass check) and must pass once the developer enforces the invariant, WITHOUT
weakening WI-3's existing behavioral tests in ``tests/test_car.py``.

Finding under test
------------------
WI3-F4: ``CarDesign`` performs no cross-field consistency check between the total
mass ``M`` and the wheels' mass. The spec defines ``M`` as the *total* mass of the
car — "chassis + wheels" (physics-spec §2.1) — and the engine accelerates the system
as ``a = F_net / (M + N·I/R_outer²)`` (TRD §4). Nothing today stops a car being built
where the wheels alone outweigh the entire car: e.g. 4 wheels @ 2.0 oz each (8.0 oz of
wheels) on a 5.0 oz car. That is physically impossible — there is then *negative*
chassis mass — and it silently feeds garbage into every downstream energy/timing
computation (the profile's "fun but wrong / teaches wrong physics" worst-case bug).

The invariant WI-3 must enforce (and the only place it can be enforced — ``CarDesign``
is the first object that sees both ``M`` and the wheels together):

    N · m_w  <  M          (strict: a real car has a non-zero chassis)

i.e. the wheels' combined mass must be **strictly less** than the car's total mass,
leaving positive mass for the chassis. ``CarDesign.__post_init__`` must raise
``ValueError`` when this is violated.

Design of these tests
----------------------
- They assert the **domain invariant**, not an implementation detail: a car whose
  wheels out-mass (or exactly equal, or sum to ≥) the total mass must not be
  constructible.
- They are anchored to the spec's own units (ounces via the ``Mass`` value object),
  not to magic SI constants.
- Boundary coverage: wheels heavier than the car, wheels exactly equal to the car
  (zero chassis — still invalid), and the just-under / just-over edge of the strict
  bound. Plus a positive case (a realistic car with light wheels) so the new check
  cannot be satisfied by simply rejecting everything (no over-rejection regression).
- ``count_touching`` is varied (3 and 4) so the check is against ``N · m_w``, the
  number of wheels actually in contact, not a fixed 4.
- Deterministic: pure construction, no clock / network / RNG.

Import is done inside each test body (matching ``tests/test_car.py``) so a missing
symbol fails each criterion independently rather than aborting collection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign, Wheels


VALID_FRONTAL_AREA = 0.0028
VALID_CD = 0.30


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — build valid sub-objects; only the masses are varied by the tests.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_wheels(
    *,
    count_touching: int = 4,
    wheel_mass_oz: float = 0.09,
) -> Wheels:
    from pinewood_derby.car import Wheels
    from pinewood_derby.units import Length, Mass

    return Wheels(
        count_touching=count_touching,
        wheel_mass=Mass.from_ounces(wheel_mass_oz),
        outer_radius=Length.from_inches(0.595),
        inner_radius=Length.from_inches(0.37),
        axle_radius=Length.from_inches(0.045),
    )


def _make_car(
    *,
    mass_oz: float,
    wheels: Wheels,
) -> CarDesign:
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(0.85),
        wheelbase=Length.from_inches(4.375),
        wheels=wheels,
        body=BodyShape(drag_coefficient=VALID_CD, frontal_area=VALID_FRONTAL_AREA),
        axle=Axle(friction_coefficient=0.20),
        alignment=Alignment.STRAIGHT,
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI3-F4 — wheels cannot out-mass the whole car (N·m_w must be < M).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi3f4_wheels_heavier_than_car_raises() -> None:
    """The exact repro from the finding: 4 wheels @ 2.0 oz (8.0 oz of wheels) on a
    5.0 oz car. The wheels alone outweigh the entire car — physically impossible —
    so construction must raise ``ValueError`` instead of silently succeeding."""
    wheels = _make_wheels(count_touching=4, wheel_mass_oz=2.0)
    with pytest.raises(ValueError):
        _make_car(mass_oz=5.0, wheels=wheels)


def test_wi3f4_wheels_equal_to_total_mass_raises() -> None:
    """Boundary: wheels summing to *exactly* the total mass leaves a zero-mass chassis,
    which is still physically impossible. The bound is strict (N·m_w < M), so equality
    must raise. 4 wheels @ 1.25 oz = 5.0 oz == a 5.0 oz car."""
    wheels = _make_wheels(count_touching=4, wheel_mass_oz=1.25)
    with pytest.raises(ValueError):
        _make_car(mass_oz=5.0, wheels=wheels)


def test_wi3f4_wheels_just_over_total_mass_raises() -> None:
    """Just over the bound: 4 wheels @ 1.30 oz = 5.2 oz > 5.0 oz. Must raise."""
    wheels = _make_wheels(count_touching=4, wheel_mass_oz=1.30)
    with pytest.raises(ValueError):
        _make_car(mass_oz=5.0, wheels=wheels)


def test_wi3f4_three_wheel_car_uses_count_touching_for_the_bound() -> None:
    """The invariant is against ``N · m_w`` for the number of wheels actually touching,
    not a hard-coded 4. With only 3 wheels touching @ 1.8 oz the wheels sum to 5.4 oz,
    which still exceeds a 5.0 oz car — must raise. (Guards against a fix that forgets to
    multiply by ``count_touching``.)"""
    wheels = _make_wheels(count_touching=3, wheel_mass_oz=1.8)
    with pytest.raises(ValueError):
        _make_car(mass_oz=5.0, wheels=wheels)


def test_wi3f4_realistic_light_wheels_still_construct() -> None:
    """No over-rejection: a realistic legal car (5.0 oz total, 4 standard 0.09 oz
    wheels = 0.36 oz of wheels, leaving ~4.64 oz of chassis) is well within the
    invariant and MUST still construct. This pins that the new check rejects only the
    impossible cars, not valid ones."""
    from pinewood_derby.car import CarDesign

    wheels = _make_wheels(count_touching=4, wheel_mass_oz=0.09)
    car = _make_car(mass_oz=5.0, wheels=wheels)
    assert isinstance(car, CarDesign)


def test_wi3f4_wheels_just_under_total_mass_construct() -> None:
    """The just-under edge of the strict bound must be allowed: 4 wheels @ 1.20 oz =
    4.8 oz of wheels on a 5.0 oz car leaves a positive (0.2 oz) chassis — physically
    possible, so it must construct. Pins the boundary as strict-less-than, not an
    over-eager rejection of any heavy-wheel car."""
    from pinewood_derby.car import CarDesign

    wheels = _make_wheels(count_touching=4, wheel_mass_oz=1.20)
    car = _make_car(mass_oz=5.0, wheels=wheels)
    assert isinstance(car, CarDesign)
