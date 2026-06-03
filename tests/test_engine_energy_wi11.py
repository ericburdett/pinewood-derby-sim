"""WI-11 — Energy-ledger closure and numerical convergence.

Behavior-driven tests written against the engine's public contract (``simulate`` +
the frozen ``RaceResult.energy`` ledger). Imports live inside each test body so a
missing/renamed symbol fails *that criterion* independently (true per-criterion
isolation) rather than aborting whole-file collection.

These verify physics *invariants* of a FINISHED run, not magic magnitudes:

- AC-E1 (PRD §6, l.151): for a FINISHED run the per-force ledger closes by the
  discrete work-energy theorem —
  ``KE_total_final == w_gravity − (w_drag + w_axle + w_rail)`` within a relative
  tolerance of 1e-6, where ``KE_total_final = ke_linear_final + ke_rotational_final``.
  Verified on (a) a nominal low-loss car and (b) a car with non-trivial drag/axle/rail
  losses (a STRAIGHT, unprepared-axle, blunt-body car), so the closure holds even when
  the loss terms are large.
- AC-E3 (PRD §6, l.156): halving ``dt`` changes ``race_time_s`` by < 1% for a
  FINISHED run (numerical convergence / stability of the Euler integration with
  finish-line interpolation). Verified for both a RAIL_RIDER (RNG-free) car and a
  STRAIGHT (seeded ping-pong) car at a fixed seed.

Integrity / determinism (gate "QA Red"): every test fixes ``dt`` and ``seed`` (no
clock / network / unseeded RNG), restricts the closure & convergence assertions to
FINISHED runs (DNF runs have ``race_time_s = None`` and an empty/partial ledger and
are explicitly excluded / guarded), and asserts RELATIVE tolerances rather than
absolute magic numbers. The tests are written so they would FAIL if the engine left a
truncation gap in the ledger (AC-E1) or if the integration were dt-dependent beyond
1% (AC-E3) — i.e. they are real verification, not tautologies. This file is NEW; it
modifies, skips, or deletes no existing test.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult
    from pinewood_derby.track import Track

# Relative tolerances pinned from the acceptance criteria (PRD §6), not the engine.
LEDGER_REL_TOL = 1e-6        # AC-E1: discrete work-energy theorem closes to this rel tol
CONVERGENCE_REL_TOL = 0.01   # AC-E3: halving dt moves race_time_s by < 1%


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
    """A valid, FINISHED-capable baseline car. ``alignment`` is the enum member name."""
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


def _nominal_finished_car() -> CarDesign:
    """A clean, low-loss car (rail-rider, polished-ish axle, slick body)."""
    return _make_car(
        alignment="RAIL_RIDER",
        drag_coefficient=0.20,
        friction_coefficient=0.10,
    )


def _lossy_finished_car() -> CarDesign:
    """A car with NON-TRIVIAL drag / axle / rail losses, but still FINISHED.

    STRAIGHT alignment (seeded ping-pong rail force), the unprepared-axle coefficient
    (μ = 0.35) and a blunt wood-block body (C_d = 0.85). It still has enough mass /
    placement to coast across the line, so the closure assertion applies to a run where
    every loss term is large — the meaningful case for AC-E1.
    """
    return _make_car(
        alignment="STRAIGHT",
        drag_coefficient=0.85,
        friction_coefficient=0.35,
    )


def _assert_finished(result: RaceResult) -> None:
    """Guard: closure/convergence assertions are only valid on FINISHED runs."""
    from pinewood_derby.result import Outcome

    assert result.outcome is Outcome.FINISHED, (
        "ledger-closure / convergence criteria apply only to FINISHED runs; "
        f"got {result.outcome} (the test fixture must keep the car a finisher)"
    )
    assert result.race_time_s is not None and result.race_time_s > 0.0


def _ledger_relative_gap(result: RaceResult) -> float:
    """Relative gap of the work-energy ledger for a FINISHED run (AC-E1).

    KE_total_final vs (w_gravity − (w_drag + w_axle + w_rail)), as a fraction of the
    RHS magnitude — a pure relative tolerance, no absolute magic number.
    """
    e = result.energy
    ke_total_final = e.ke_linear_final + e.ke_rotational_final
    rhs = e.w_gravity - (e.w_drag + e.w_axle + e.w_rail)
    assert math.isfinite(ke_total_final)
    assert math.isfinite(rhs)
    assert abs(rhs) > 0.0, "a FINISHED run must do net positive work; RHS must be non-zero"
    return abs(ke_total_final - rhs) / abs(rhs)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-E1 — the per-force energy ledger closes for a FINISHED run.
# ───────────────────────────────────────────────────────────────────────────── #
def test_ace1_ledger_closes_for_nominal_finished_car() -> None:
    """KE_total_final ≈ w_gravity − (w_drag + w_axle + w_rail) to rel tol 1e-6."""
    result = _simulate(_nominal_finished_car(), dt=1e-3, seed=0)
    _assert_finished(result)
    rel_gap = _ledger_relative_gap(result)
    assert rel_gap < LEDGER_REL_TOL, (
        f"work-energy ledger did not close: relative gap {rel_gap:.3e} "
        f">= tol {LEDGER_REL_TOL:.0e} (AC-E1)"
    )


def test_ace1_ledger_closes_with_nontrivial_losses() -> None:
    """Closure holds even when drag/axle/rail losses are large (lossy STRAIGHT car).

    Also asserts the loss terms are genuinely non-trivial (all strictly positive), so
    this is not vacuously the same near-loss-free case as the nominal car.
    """
    result = _simulate(_lossy_finished_car(), dt=1e-3, seed=7)
    _assert_finished(result)
    e = result.energy
    assert e.w_drag > 0.0 and e.w_axle > 0.0 and e.w_rail > 0.0, (
        "the lossy fixture must exercise all three loss channels (drag/axle/rail) "
        f"non-trivially; got w_drag={e.w_drag}, w_axle={e.w_axle}, w_rail={e.w_rail}"
    )
    rel_gap = _ledger_relative_gap(result)
    assert rel_gap < LEDGER_REL_TOL, (
        f"work-energy ledger did not close under non-trivial losses: relative gap "
        f"{rel_gap:.3e} >= tol {LEDGER_REL_TOL:.0e} (AC-E1)"
    )


def test_ace1_ke_total_final_is_sum_of_linear_and_rotational() -> None:
    """KE_total_final the ledger closes to is exactly ke_linear + ke_rotational shares.

    Pins the definition of the LHS so the closure cannot be satisfied by some other
    "total" — it must be the contract's two reported KE fields.
    """
    result = _simulate(_nominal_finished_car(), dt=1e-3, seed=0)
    _assert_finished(result)
    e = result.energy
    ke_total = e.ke_linear_final + e.ke_rotational_final
    rhs = e.w_gravity - (e.w_drag + e.w_axle + e.w_rail)
    assert e.ke_linear_final > 0.0 and e.ke_rotational_final > 0.0
    assert ke_total == pytest.approx(rhs, rel=LEDGER_REL_TOL)


def test_ace1_closure_excludes_dnf_runs() -> None:
    """A DNF run is excluded from the closure assertion (it has no FINISHED ledger).

    Documents the integrity guard: DNF ⇒ race_time_s is None, so the AC-E1/AC-E3 logic
    is correctly scoped to FINISHED runs only.
    """
    from pinewood_derby.result import Outcome

    # An unstable rear bias (d_COM well below the stability cliff) is a DNF (PRD A2).
    dnf = _simulate(_make_car(com_ahead_of_rear_axle_in=0.15), dt=1e-3, seed=0)
    assert dnf.outcome is Outcome.DNF
    assert dnf.race_time_s is None


# ───────────────────────────────────────────────────────────────────────────── #
# AC-E3 — halving dt changes race_time_s by < 1% (numerical convergence).
# ───────────────────────────────────────────────────────────────────────────── #
def test_ace3_halving_dt_changes_time_under_one_percent_rail_rider() -> None:
    """A FINISHED RAIL_RIDER car's race_time_s is dt-converged (RNG-free path)."""
    car = _nominal_finished_car()
    coarse = _simulate(car, dt=1e-3, seed=0)
    fine = _simulate(car, dt=5e-4, seed=0)
    _assert_finished(coarse)
    _assert_finished(fine)
    assert coarse.race_time_s is not None and fine.race_time_s is not None
    rel_change = abs(fine.race_time_s - coarse.race_time_s) / coarse.race_time_s
    assert rel_change < CONVERGENCE_REL_TOL, (
        f"race_time_s not dt-converged: halving dt moved it by {rel_change:.3%} "
        f">= {CONVERGENCE_REL_TOL:.0%} (AC-E3)"
    )


def test_ace3_halving_dt_changes_time_under_one_percent_straight_seeded() -> None:
    """A FINISHED STRAIGHT car (seeded ping-pong) is also dt-converged at a fixed seed.

    The seed is held fixed across both dt values so the comparison isolates the
    integration step, not RNG variation.
    """
    car = _make_car(alignment="STRAIGHT")
    coarse = _simulate(car, dt=1e-3, seed=11)
    fine = _simulate(car, dt=5e-4, seed=11)
    _assert_finished(coarse)
    _assert_finished(fine)
    assert coarse.race_time_s is not None and fine.race_time_s is not None
    rel_change = abs(fine.race_time_s - coarse.race_time_s) / coarse.race_time_s
    assert rel_change < CONVERGENCE_REL_TOL, (
        f"STRAIGHT race_time_s not dt-converged at seed 11: halving dt moved it by "
        f"{rel_change:.3%} >= {CONVERGENCE_REL_TOL:.0%} (AC-E3)"
    )


def test_ace3_convergence_uses_finished_runs_only() -> None:
    """The convergence fixtures must be FINISHED at both dt values (criterion scope).

    If a fixture DNF'd, race_time_s would be None and the < 1% comparison would be
    meaningless — this asserts the criterion's "FINISHED runs only" precondition holds
    for the dt pairs actually compared above.
    """
    from pinewood_derby.result import Outcome

    car = _nominal_finished_car()
    for dt in (1e-3, 5e-4):
        result = _simulate(car, dt=dt, seed=0)
        assert result.outcome is Outcome.FINISHED
        assert result.race_time_s is not None and result.race_time_s > 0.0
