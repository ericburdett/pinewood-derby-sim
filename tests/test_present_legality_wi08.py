"""Feature 0008 — legality inspection + the drag-physics priority-order guard.

Two things this feature touches that need pinning:

- ``legality_report`` (pure): the inspection checklist used by the UI — weight (the one
  universal rule) plus the typical-but-league-dependent dimensional limits (width, length,
  height).
- The drag physics now feeds on REAL body dimensions (frontal area = width × height) with
  real linear-in-area drag. The small effective-area FRACTION keeps aerodynamics the
  SMALLEST lever (AC-ED1); these tests re-prove that invariant at the LEGAL-MAXIMUM body
  size, so expanding the design space can't let aero out-rank weight/friction.
"""

from __future__ import annotations

import pytest

from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
from pinewood_derby.engine import simulate
from pinewood_derby.present import legality_report, present
from pinewood_derby.result import Outcome
from pinewood_derby.track import STANDARD_TRACK
from pinewood_derby.units import Length, Mass

IN2_TO_M2 = 0.0254**2
LEGAL = {"mass_oz": 5.0, "width_in": 1.75, "height_in": 2.5, "length_in": 7.0}


def _report(**overrides: float) -> list[dict[str, object]]:
    args = {**LEGAL, **overrides}
    return legality_report(**args)  # type: ignore[arg-type]


def _by_rule(report: list[dict[str, object]]) -> dict[str, bool]:
    return {str(r["rule"]): bool(r["ok"]) for r in report}


# ── legality_report ──────────────────────────────────────────────────────────── #
def test_a_legal_car_passes_every_rule() -> None:
    assert all(r["ok"] for r in _report())


def test_report_entries_carry_rule_value_and_requirement() -> None:
    for entry in _report():
        assert set(entry) == {"rule", "ok", "value", "requirement"}
        assert isinstance(entry["rule"], str) and entry["rule"]
        assert isinstance(entry["value"], str) and entry["value"]
        assert isinstance(entry["requirement"], str) and entry["requirement"]


@pytest.mark.parametrize(
    ("override", "failing_rule"),
    [
        ({"mass_oz": 6.0}, "Weight"),
        ({"width_in": 3.0}, "Width"),
        ({"length_in": 8.0}, "Length"),
        ({"height_in": 4.0}, "Height"),
    ],
)
def test_each_violation_fails_only_its_own_rule(override: dict[str, float], failing_rule: str) -> None:
    flags = _by_rule(_report(**override))
    assert flags[failing_rule] is False, f"{failing_rule} should fail for {override}"
    for rule, ok in flags.items():
        if rule != failing_rule:
            assert ok is True, f"{rule} should still pass when only {failing_rule} is violated"


def test_values_exactly_at_the_limit_are_legal() -> None:
    flags = _by_rule(
        _report(mass_oz=5.0, width_in=2.75, length_in=7.0, height_in=3.5)
    )
    assert all(flags.values()), f"boundary values must be legal, got {flags}"


# ── drag physics priority-order guard (AC-ED1 at the expanded design space) ────── #
def _car(*, width_in: float, height_in: float, cd: float, mu: float = 0.10) -> CarDesign:
    return CarDesign(
        mass=Mass.from_ounces(5.0),
        com_ahead_of_rear_axle=Length.from_inches(0.85),
        wheelbase=Length.from_inches(4.375),
        wheels=Wheels(
            count_touching=4,
            wheel_mass=Mass.from_ounces(0.09),
            outer_radius=Length.from_inches(0.595),
            inner_radius=Length.from_inches(0.37),
            axle_radius=Length.from_inches(0.045),
        ),
        body=BodyShape(drag_coefficient=cd, frontal_area=width_in * height_in * IN2_TO_M2),
        axle=Axle(friction_coefficient=mu),
        alignment=Alignment.RAIL_RIDER,
    )


def _air_share(car: CarDesign) -> tuple[str | None, float]:
    view = present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=0), car)
    losses = [b for b in view.breakdown if not b.is_kept]
    dominant = max(losses, key=lambda b: b.proportion).key if losses else None
    air = next((b.proportion for b in view.breakdown if b.key == "air"), 0.0)
    return dominant, air


def test_aero_stays_the_smallest_lever_even_at_a_legal_max_body() -> None:
    """A legal-maximum body (2.75 × 3.5 in) with the bluntest legal shape (Cd 0.85), every
    other lever optimal, must STILL not surface aerodynamics as the dominant loss — the
    small effective-area fraction keeps aero subordinate (AC-ED1) even with real linear-in-
    area drag across the expanded, real-dimension design space."""
    dominant, air = _air_share(_car(width_in=2.75, height_in=3.5, cd=0.85))
    assert dominant is not None and dominant != "air", (
        f"aerodynamics became the dominant loss ({dominant}) at the legal-max body — the "
        f"priority order inverted (air share {air:.3f})"
    )


def test_bigger_frontal_area_increases_drag_but_does_not_dominate() -> None:
    """Drag genuinely responds to frontal area (a big body loses more to air than a small
    one) — yet aero remains subordinate in both cases."""
    _, small_air = _air_share(_car(width_in=1.75, height_in=1.5, cd=0.85))
    big_dom, big_air = _air_share(_car(width_in=2.75, height_in=3.5, cd=0.85))
    assert big_air > small_air, "a larger frontal area must lose more speed to air"
    assert big_dom != "air", "aero must still not dominate at the larger body"


def test_a_big_body_car_still_finishes() -> None:
    result = simulate(_car(width_in=2.75, height_in=3.5, cd=0.85), STANDARD_TRACK, dt=1e-3, seed=0)
    assert result.outcome is Outcome.FINISHED


def test_drag_scales_linearly_with_frontal_area() -> None:
    """Feature 0008 restored real linear-in-area drag (F_drag ∝ A): doubling the body's
    frontal area roughly DOUBLES the energy lost to air — clearly more than the old
    sub-linear √2 response — so body size genuinely affects the race."""
    small = simulate(_car(width_in=1.5, height_in=1.5, cd=0.85), STANDARD_TRACK, dt=1e-3, seed=0)
    big = simulate(_car(width_in=3.0, height_in=1.5, cd=0.85), STANDARD_TRACK, dt=1e-3, seed=0)
    ratio = big.energy.w_drag / small.energy.w_drag  # 2x width ⇒ 2x frontal area
    assert ratio > 1.8, f"doubling frontal area should ~double drag (linear); got {ratio:.3f}x"
    assert big.race_time_s is not None and small.race_time_s is not None
    assert big.race_time_s > small.race_time_s, "a bigger body must finish slower"
