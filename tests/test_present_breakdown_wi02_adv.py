"""WI02-PRESENT-BREAKDOWN — adversarial RED tests for the "Where did your speed go?"
ranked energy breakdown (``pinewood_derby.present._breakdown`` / ``present``).

Covers confirmed finding **ADV-WI02-001** (category: boundaries, severity: high).

The bug
-------
``_breakdown()`` normalizes every ``LossBar`` by ``w_gravity`` and guards **only the
exact-zero** case (``if delivered <= 0.0: return ()``). A light, forward-COM,
``STRAIGHT``-aligned car creeps a few microns off the start line and stalls almost
immediately. The engine still records a **tiny-but-positive** ``w_gravity`` (~5e-7 J)
while the integrated ``w_rail`` (~8e-7 J) **exceeds** it. The exact-zero guard does not
fire, so the bars no longer partition the delivered energy: with the canonical repro the
``rails`` bar gets ``proportion ≈ 1.6119`` and the five bars sum to ``≈ 1.6577``.

This violates two contracts at once:

- **TRD §4 normalization invariant** — "bars sum to ~1" (the per-force ledger is supposed
  to close against ``w_gravity``; in this near-stationary region it does not, because a
  near-zero divisor explodes a barely-larger numerator).
- **The WI02 suite's own asserted bounds** —
  ``test_all_proportions_are_finite_nonnegative_fractions`` requires ``0 <= proportion <=
  1 + 1e-9``, and the sum-to-1 tests require ``sum ≈ 1.0``. Those existing tests pass only
  because the WI02 ``_stalled_car`` fixture is a ``mu=5.0`` ``RAIL_RIDER`` that descends
  ~4.24 m; the near-stationary ``STRAIGHT`` stall region is never exercised.

Kid-facing impact (the profile's "a result a kid can't make sense of" = usability bug):
a chart claiming **"you lost 161% of your speed to bumping the rails."**

Why these tests, and why they are RED now
-----------------------------------------
``_breakdown`` is already implemented (WI01/WI02), so the defect is **live** — these tests
go RED against the current code, and fail **for the right reason** (an out-of-range
proportion / a sum far from 1, not an import or fixture error). They pin the *region* the
existing fixtures miss: a low-mass, forward-COM, ``STRAIGHT`` car whose run stalls within
microns of the line, leaving ``0 < w_gravity < w_rail``.

The fix is a presentation concern only (AC-G1 / TRD §4): the breakdown must keep the bars a
true partition of the delivered energy (each in ``[0, 1]``, summing to ~1) — e.g. by
guarding the degenerate near-stationary ledger the same way a tip is guarded, or otherwise
not surfacing a >100% loss. No engine physics changes.

All tests are deterministic: a single fixed seed, no clock / network / unseeded RNG.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest

from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
from pinewood_derby.engine import simulate
from pinewood_derby.present import present
from pinewood_derby.result import Outcome
from pinewood_derby.track import STANDARD_TRACK
from pinewood_derby.units import Length, Mass

if TYPE_CHECKING:
    from pinewood_derby.result import RaceResult

# The fixed seed the UI pins so a design's time/breakdown is reproducible (PRD A6).
FIXED_SEED = 0


def _make_wheels() -> Wheels:
    return Wheels(
        count_touching=4,
        wheel_mass=Mass.from_ounces(0.09),
        outer_radius=Length.from_inches(0.595),
        inner_radius=Length.from_inches(0.37),
        axle_radius=Length.from_inches(0.045),
    )


def _near_stationary_straight_stall_car() -> CarDesign:
    """The canonical ADV-WI02-001 repro: a **light (1.0 oz)**, **forward-COM (1.0 in,
    well above the stability cliff so it is NOT a tip)**, ``STRAIGHT`` car. It creeps a
    few microns off the line and stalls immediately, leaving ``w_gravity`` tiny-but-
    positive (~5e-7 J) while the integrated ``w_rail`` (~8e-7 J) **exceeds** it. The
    exact-zero guard in ``_breakdown`` does not fire, so the ``rails`` proportion blows
    past 1 (~1.61) and the bars no longer sum to ~1 (~1.66).

    This is a STALLED run (real multi-point trajectory, ``w_gravity > 0``), NOT a tip
    (which has an all-zero ledger), and NOT a finisher — it sits in the region the WI02
    ``mu=5.0`` ``RAIL_RIDER`` fixture never visits.
    """
    return CarDesign(
        mass=Mass.from_ounces(1.0),
        com_ahead_of_rear_axle=Length.from_inches(1.0),
        wheelbase=Length.from_inches(4.375),
        wheels=_make_wheels(),
        body=BodyShape(drag_coefficient=0.30, frontal_area=0.0028),
        axle=Axle(friction_coefficient=0.35),
        alignment=Alignment.STRAIGHT,
    )


def _simulate(car: CarDesign) -> RaceResult:
    return simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)


def _track_length_m() -> float:
    return STANDARD_TRACK.ramp_length.m + STANDARD_TRACK.flat_length.m


# ───────────────────────────────────────────────────────────────────────────── #
# Sanity guard — pin the fixture as the exact degenerate ledger the finding names, so
# a later engine change can't silently turn it into a finisher / tip and hollow these
# tests out. This asserts the TEST INPUT, not the SUT.
# ───────────────────────────────────────────────────────────────────────────── #
def test_fixture_is_a_near_stationary_stall_with_rail_exceeding_gravity() -> None:
    """The repro car is a STALLED DNF that barely moved: a real (multi-point) trajectory
    stopping within microns of the line, with ``0 < w_gravity`` yet ``w_rail > w_gravity``
    — the exact degenerate ledger that makes a w_gravity-normalized bar exceed 1."""
    r = _simulate(_near_stationary_straight_stall_car())
    assert r.outcome is Outcome.DNF, "fixture must be a non-finish (stall), not a finisher"
    assert len(r.trajectory) > 1, "a stall has a real multi-point trajectory (not a tip)"
    last = r.trajectory[-1].position
    assert 0.0 < last < _track_length_m(), "stopped short, between start and finish line"
    assert last < 1e-3, "stalled within ~a millimeter of the line — the boundary region"
    e = r.energy
    # The crux: gravity work is positive (so the exact-zero guard misses it) but rail
    # work is LARGER (so rail / w_gravity > 1). This is what the breakdown must survive.
    assert e.w_gravity > 0.0, "tiny-but-positive gravity work — the guard does NOT fire"
    assert e.w_rail > e.w_gravity, "rail loss exceeds delivered gravity work (the trap)"


# ───────────────────────────────────────────────────────────────────────────── #
# ADV-WI02-001 — the normalization invariant must hold in the near-stationary region:
# every proportion is a finite share in [0, 1] and the bars sum to ~1 (TRD §4).
# ───────────────────────────────────────────────────────────────────────────── #
def test_near_stationary_stall_proportions_stay_within_unit_range() -> None:
    """ADV-WI02-001: no breakdown bar may exceed 1 (or be negative / non-finite). With
    the current code the ``rails`` bar is ~1.6119 — a chart claiming "you lost 161% of
    your speed to bumping the rails," which a kid can't make sense of (a usability bug).
    This mirrors the WI02 suite's own asserted bound (0 <= proportion <= 1 + 1e-9), now
    exercised in the region the existing fixtures miss."""
    view = present(_simulate(_near_stationary_straight_stall_car()),
                   _near_stationary_straight_stall_car())
    for bar in view.breakdown:
        assert math.isfinite(bar.proportion), (
            f"bar {bar.key!r} proportion is not finite: {bar.proportion}"
        )
        assert 0.0 <= bar.proportion <= 1.0 + 1e-9, (
            f"bar {bar.key!r} proportion {bar.proportion} escapes [0, 1] — a near-"
            f"stationary stall must never surface a >100% (or negative) loss"
        )


def test_near_stationary_stall_proportions_sum_to_one() -> None:
    """ADV-WI02-001: the bars must partition the delivered energy — they sum to ~1.0
    (TRD §4 normalization invariant). With the current code the five bars sum to ~1.6577,
    so the chart no longer represents a whole. (If the correct fix is to suppress the
    breakdown for this degenerate near-stationary ledger — as a tip is suppressed — an
    empty breakdown is also acceptable: see the companion guard test below.)"""
    view = present(_simulate(_near_stationary_straight_stall_car()),
                   _near_stationary_straight_stall_car())
    if view.breakdown == ():
        pytest.skip(
            "breakdown suppressed for the degenerate near-stationary ledger — the "
            "no-misleading-bars guard test covers that fix path"
        )
    total = sum(bar.proportion for bar in view.breakdown)
    assert total == pytest.approx(1.0, abs=1e-6), (
        f"near-stationary stall bars sum {total} != 1.0 — they no longer partition the "
        f"delivered energy (TRD §4)"
    )


def test_near_stationary_stall_emits_no_misleading_breakdown() -> None:
    """ADV-WI02-001, stated as the kid-facing contract independent of the chosen fix:
    the breakdown for this near-stationary stall must **not** mislead. It is acceptable
    EITHER to keep the bars a valid partition (each in [0, 1], summing to ~1) OR to
    suppress the breakdown entirely (emit no bars — as a tip's all-zero ledger is
    suppressed). What is NOT acceptable is the current state: a populated chart whose
    dominant bar claims a >100% loss.

    This single assertion is the load-bearing one: it fails today (``rails`` ~1.6119,
    sum ~1.6577) and passes under either correct remediation."""
    view = present(_simulate(_near_stationary_straight_stall_car()),
                   _near_stationary_straight_stall_car())
    bars = view.breakdown
    if bars == ():
        return  # suppressed — a valid, non-misleading outcome
    for bar in bars:
        assert 0.0 <= bar.proportion <= 1.0 + 1e-9, (
            f"misleading bar: {bar.key!r} claims proportion {bar.proportion} "
            f"(a >100% or negative loss a kid can't make sense of)"
        )
    total = sum(bar.proportion for bar in bars)
    assert total == pytest.approx(1.0, abs=1e-6), (
        f"misleading chart: bars sum to {total}, not a whole (~1.0)"
    )
