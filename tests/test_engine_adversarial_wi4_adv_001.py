"""WI4-ADV-001 — non-finite ``seed`` breaks determinism (AC-AL3).

Adversarial finding (high, reproducible): ``simulate()`` validates ``dt`` for
finiteness (engine.py: ``math.isfinite(dt)``) but performs **no** validation on
``seed``. A non-finite seed flows unchecked into ``random.Random(seed)``. Because
``float('nan') != float('nan')``, CPython's ``Random`` cannot use NaN as a
reproducible seed and falls back to **entropy-based** seeding — so the STRAIGHT
ping-pong path becomes nondeterministic. That directly violates AC-AL3
("identical ``(car, track, dt, seed)`` -> bit-identical ``RaceResult``"), one of
WI-4's three core contracts. The dt-vs-seed validation asymmetry makes this a
defect, not a design choice.

These tests are RED against the current implementation and pin the fix: validate
``seed`` at the ``simulate()`` boundary (mirroring the ``dt`` check) so a
non-finite seed cannot silently produce nondeterministic results.

The two tests encode the contract from two angles:

- ``test_*_nan_seed_raises_value_error`` — the recommended boundary fix: a
  non-finite seed is rejected with ``ValueError``, exactly as a non-finite ``dt``
  already is. This is the validation-asymmetry the finding calls out.
- ``test_*_nan_seed_is_deterministic`` — the underlying AC-AL3 invariant itself:
  *if* a non-finite seed is ever accepted, repeated identical calls must still be
  bit-identical. (A pass would also be satisfied by the raising fix, since
  ``pytest.raises`` consumes the violation; the test is written so the only way to
  reach the determinism assertion is when the call did **not** raise.)

All tests are deterministic: no clock, no network, no RNG outside the engine.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — mirror tests/test_engine_e2e.py so construction stays consistent.
# Imports are inside the bodies so a missing module fails each criterion
# independently (true per-criterion RED) rather than aborting collection.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_wheels(*, count_touching: int = 4) -> Any:
    from pinewood_derby.car import Wheels
    from pinewood_derby.units import Length, Mass

    return Wheels(
        count_touching=count_touching,
        wheel_mass=Mass.from_ounces(0.09),
        outer_radius=Length.from_inches(0.595),
        inner_radius=Length.from_inches(0.37),
        axle_radius=Length.from_inches(0.045),
    )


def _straight_car() -> CarDesign:
    """A valid baseline STRAIGHT car: its ping-pong rail path consumes the seeded RNG,
    so its w_rail is the field that exposes any nondeterminism in the seed plumbing."""
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(5.0),
        com_ahead_of_rear_axle=Length.from_inches(0.85),
        wheelbase=Length.from_inches(4.375),
        wheels=_make_wheels(),
        body=BodyShape(drag_coefficient=0.30, frontal_area=0.0028),
        axle=Axle(friction_coefficient=0.20),
        alignment=Alignment["STRAIGHT"],
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI4-ADV-001 — boundary validation: a non-finite seed is rejected (mirrors dt).
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("bad_seed", [float("nan"), float("inf"), float("-inf")])
def test_wi4_adv_001_non_finite_seed_raises_value_error(bad_seed: float) -> None:
    """The recommended fix: ``simulate()`` validates ``seed`` at the boundary just like
    it validates ``dt``. A non-finite seed (NaN / +-inf) is a malformed, non-reproducible
    input and must raise ``ValueError`` rather than flow into ``random.Random(seed)``.

    RED today: the engine only checks ``dt`` finiteness, so a non-finite seed is accepted
    and no error is raised."""
    from pinewood_derby.engine import simulate
    from pinewood_derby.track import STANDARD_TRACK

    with pytest.raises(ValueError):
        simulate(_straight_car(), STANDARD_TRACK, dt=1e-3, seed=bad_seed)


# ───────────────────────────────────────────────────────────────────────────── #
# WI4-ADV-001 — AC-AL3 invariant: a NaN seed must never yield nondeterminism.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi4_adv_001_nan_seed_must_not_be_nondeterministic() -> None:
    """AC-AL3 directly: identical ``(car, track, dt, seed)`` must produce a bit-identical
    ``RaceResult`` across repeated calls — including when ``seed`` is non-finite.

    Today a NaN seed reaches ``random.Random(nan)``; since ``nan != nan`` CPython falls
    back to entropy seeding, so ten identical calls yield ten *different* w_rail values
    (the finding's repro). This test fails for that reason.

    The fix may take either correct form and this test passes for both:
      * reject the non-finite seed with ``ValueError`` (the recommended boundary fix), or
      * make a non-finite seed deterministic.
    Either way, identical calls must never silently diverge."""
    from pinewood_derby.engine import simulate
    from pinewood_derby.track import STANDARD_TRACK

    car = _straight_car()

    try:
        results = [
            simulate(car, STANDARD_TRACK, dt=1e-3, seed=float("nan")).energy.w_rail
            for _ in range(10)
        ]
    except ValueError:
        # Boundary-validation fix: a non-finite seed is rejected outright, so it can
        # never produce a nondeterministic result. Contract upheld.
        return

    # If the engine accepted the seed, AC-AL3 still binds: every call must agree.
    assert all(math.isfinite(r) for r in results), "w_rail must be finite"
    assert len(set(results)) == 1, (
        "non-finite seed produced nondeterministic results across identical calls — "
        f"AC-AL3 violated: {len(set(results))} distinct values from 10 identical calls"
    )
