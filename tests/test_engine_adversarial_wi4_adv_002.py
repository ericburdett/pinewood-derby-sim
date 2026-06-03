"""WI4-ADV-002 — unstable-car DNF blows the <5 ms performance NFR by ~12x.

Adversarial finding (high, reproducible): an unstable car (``d_COM < 0.625 in``) is a
DNF whose outcome is *fully determined before the integration loop starts* — the engine
computes ``unstable = d_com < _COM_UNSTABLE_BELOW.m`` (engine.py:124) and unconditionally
force-overrides the outcome to DNF afterwards (engine.py:225-227). Yet ``simulate()`` does
**not** short-circuit: the wobble model only multiplies *rail friction*
(``force *= 10.0`` in ``_rail_force``) rather than collapsing the front normal force, so
the car never lifts and instead crawls at ~0.01 m/s. The loop therefore runs all the way
to the ``_MAX_SIM_TIME_S = 60.0 s`` wall-clock guard (~60,000 iterations at ``dt = 1e-3``)
before the predetermined DNF is emitted. The entire integration is wasted work.

Measured impact: an unstable DNF's median ``simulate()`` time is ~58 ms — roughly **12x**
the profile/PRD performance budget of **< 5 ms** (profile ``quality_bars.performance``;
PRD §7 NFR "Performance"). A FINISHED run on the same track measures ~4 ms, so the gap is
specific to the unstable path, not a baseline-speed problem.

These tests are RED against the current implementation and pin the fix: a DNF that is
known before the loop must be returned without running (or after running only the bounded
work a normal run would). The fix must not change the *behavioral* contract already pinned
by ``test_engine_e2e.py`` (the unstable car is still a DNF with ``race_time_s is None``);
it only removes the wasted ~60 s integration.

Traceability:
- profile ``quality_bars.performance``: "a single race simulation computes in < 5ms".
- PRD §7 NFR "Performance": a single ``simulate(...)`` completes in **< 5 ms**.
- TRD §8 Performance / §9 (the ``_MAX_SIM_TIME_S`` guard must bound *pathological* runs,
  not be hit on a predetermined DNF) and TRD §4 ("DNF detection ... return immediately").

Determinism: fixed ``dt`` and ``seed``; the only timing input is wall-clock duration of
``simulate()`` itself (the NFR under test). To stay robust against scheduler jitter we time
several runs and assert on the **median**, and we set the threshold with a wide margin
(the bug yields ~58 ms vs a budget of 5 ms — a ~12x gap — so any reasonable threshold gives
an unambiguous RED). No clock-of-day, network, or RNG outside the seeded engine is used.
"""

from __future__ import annotations

import statistics
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign

# The profile / PRD §7 performance budget for a single simulate() call.
_PERF_BUDGET_MS = 5.0

# Number of timed repetitions; we assert on the median so a single descheduling
# hiccup cannot flake the test. The bug's ~12x overrun dwarfs any jitter at this count.
_TIMED_RUNS = 7

# d_COM strictly below the spec's 0.625 in stability threshold => unstable => DNF.
_UNSTABLE_D_COM_IN = 0.15
# A stable d_COM in the optimal zone => a normal FINISHED run (the perf baseline).
_STABLE_D_COM_IN = 0.85


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — mirror tests/test_engine_e2e.py so construction stays consistent.
# Imports live inside the bodies so a missing module fails each criterion
# independently (true per-criterion RED) rather than aborting collection.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_car(*, com_ahead_of_rear_axle_in: float) -> CarDesign:
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
    from pinewood_derby.units import Length, Mass

    wheels = Wheels(
        count_touching=4,
        wheel_mass=Mass.from_ounces(0.09),
        outer_radius=Length.from_inches(0.595),
        inner_radius=Length.from_inches(0.37),
        axle_radius=Length.from_inches(0.045),
    )
    return CarDesign(
        mass=Mass.from_ounces(5.0),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(4.375),
        wheels=wheels,
        body=BodyShape(drag_coefficient=0.30, frontal_area=0.0028),
        axle=Axle(friction_coefficient=0.20),
        alignment=Alignment["STRAIGHT"],
    )


def _median_simulate_ms(car: Any) -> float:
    """Median wall-clock duration (ms) of ``simulate(car, ...)`` over ``_TIMED_RUNS``."""
    from pinewood_derby.engine import simulate
    from pinewood_derby.track import STANDARD_TRACK

    durations_ms: list[float] = []
    for _ in range(_TIMED_RUNS):
        start = time.perf_counter()
        simulate(car, STANDARD_TRACK, dt=1e-3, seed=0)
        durations_ms.append((time.perf_counter() - start) * 1000.0)
    return statistics.median(durations_ms)


# ───────────────────────────────────────────────────────────────────────────── #
# WI4-ADV-002 (primary) — the NFR itself: an unstable DNF must meet the < 5 ms budget.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi4_adv_002_unstable_dnf_meets_performance_budget() -> None:
    """An unstable car (``d_COM < 0.625 in``) is a predetermined DNF; ``simulate()`` on it
    must still complete within the profile/PRD performance budget of < 5 ms.

    RED today: the engine runs the full ~60,000-iteration integration up to the 60 s
    wall-clock guard before emitting the already-known DNF, so the median is ~58 ms —
    ~12x over budget. The fix short-circuits the predetermined DNF.
    """
    from pinewood_derby.result import Outcome
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(com_ahead_of_rear_axle_in=_UNSTABLE_D_COM_IN)

    # Sanity: confirm this car is in fact the DNF path the finding describes, so the
    # perf assertion is timing the *unstable* branch and not silently a finished run.
    from pinewood_derby.engine import simulate

    assert simulate(car, STANDARD_TRACK, dt=1e-3, seed=0).outcome is Outcome.DNF

    median_ms = _median_simulate_ms(car)
    assert median_ms < _PERF_BUDGET_MS, (
        f"unstable-car simulate() median {median_ms:.2f} ms exceeds the "
        f"{_PERF_BUDGET_MS} ms performance budget (profile quality_bars / PRD §7): the "
        "predetermined DNF is not short-circuited and the full integration runs to the "
        "60 s wall-clock guard"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI4-ADV-002 (root cause) — a predetermined DNF must not do unbounded extra work.
# Behavioral proxy that does not couple to integration internals: the unstable DNF
# must not take dramatically longer than a normal FINISHED run on the same track.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi4_adv_002_unstable_dnf_is_not_far_slower_than_a_finished_run() -> None:
    """The unstable DNF outcome is fully determined before the loop, so it should cost no
    more compute than a normal FINISHED run — certainly not orders of magnitude more.

    We assert the unstable run is at most a small multiple of the finished baseline's time.
    RED today: the finished run is ~4 ms while the unstable run is ~58 ms (~14x), because
    the wobble model only scales rail friction instead of collapsing the front normal
    force, so the car crawls to the 60 s guard rather than failing fast.
    """
    from pinewood_derby.result import Outcome
    from pinewood_derby.track import STANDARD_TRACK

    from pinewood_derby.engine import simulate

    unstable_car = _make_car(com_ahead_of_rear_axle_in=_UNSTABLE_D_COM_IN)
    finished_car = _make_car(com_ahead_of_rear_axle_in=_STABLE_D_COM_IN)

    # Pin both outcomes so the comparison is unstable-DNF vs normal-FINISHED.
    assert simulate(unstable_car, STANDARD_TRACK, dt=1e-3, seed=0).outcome is Outcome.DNF
    assert simulate(finished_car, STANDARD_TRACK, dt=1e-3, seed=0).outcome is Outcome.FINISHED

    finished_ms = _median_simulate_ms(finished_car)
    unstable_ms = _median_simulate_ms(unstable_car)

    # A predetermined DNF must not run materially more work than the finished baseline.
    # 3x is a generous ceiling (the bug yields ~14x); it tolerates timing noise while
    # still catching the wasted 60 s integration unambiguously.
    max_ratio = 3.0
    assert unstable_ms <= max_ratio * finished_ms, (
        f"unstable-car simulate() median {unstable_ms:.2f} ms is "
        f"{unstable_ms / finished_ms:.1f}x the finished-run baseline {finished_ms:.2f} ms; "
        "the predetermined DNF runs the full integration to the 60 s guard instead of "
        "short-circuiting"
    )
