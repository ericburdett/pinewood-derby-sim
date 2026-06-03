"""WI4-ADV-003 — a car that stalls on an INCLINED section blows the <5 ms perf NFR by ~10x.

Adversarial finding (high, reproducible): a car whose axle friction is large enough that
gravity cannot overcome it at rest on the ramp (``mu >= ~1.9`` on the 30deg STANDARD_TRACK)
is clamped to ``velocity = 0`` every step but keeps integrating until the
``_MAX_SIM_TIME_S = 60.0 s`` wall-clock guard (~60,000 iterations at ``dt = 1e-3``). Measured
~50 ms per ``simulate()`` call — over **10x** the profile / PRD §7 NFR budget of **< 5 ms**.

Root cause (engine.py): the only fast stall guard inside the loop is
``if velocity <= 0.0 and f_gravity <= 0.0: break`` (engine.py:253). On the ramp and inside
the transition arc ``theta > 0`` so ``f_gravity = M*g*sin(theta) > 0`` and the guard NEVER
fires there. The car makes zero progress (``position`` and ``velocity`` stay 0.0) yet loops
to the 60 s guard. This is the SAME defect class as the already-fixed WI4-ADV-002 (a DNF
grinding to the wall-clock guard and blowing the perf budget); the ADV-002 fix only
short-circuited the *unstable-d_COM* path and left this *stall-on-incline* path open.

``mu >= 1.9`` is physically unrealistic but is a VALID accepted input — ``car.py`` only raises
for ``friction_coefficient < 0`` (TRD §6: ``axle.friction_coefficient >= 0``), and the
performance NFR is stated for "a single race simulation" with no input qualification. The car
still produces a *correct* DNF (``race_time_s is None``); only the wasted ~60 s of integration
must be removed (detect a no-progress stall regardless of incline, or cap no-progress steps).

These tests are RED against the current implementation and pin the fix without coupling to
integration internals: a car that never makes progress must fail fast, not grind to the wall
clock. The behavioral DNF contract (already pinned by ``test_engine_e2e.py`` / WI-4) must be
preserved: this car stays a DNF with ``race_time_s is None``.

Traceability:
- profile ``quality_bars.performance``: "a single race simulation computes in < 5ms".
- PRD §7 NFR "Performance": a single ``simulate(...)`` completes in **< 5 ms**.
- TRD §9: the ``_MAX_SIM_TIME_S`` guard "must bound pathological runs, not be hit"; here it is
  hit on ordinary valid input.
- AC-O2: DNF ⇒ ``race_time_s is None`` and ``outcome = DNF`` (the contract the fix must keep).

Determinism: the stall car uses ``Alignment.RAIL_RIDER`` (RNG-free, seed-independent) so the
only timing input is the wall-clock duration of ``simulate()`` itself (the NFR under test).
We time several runs and assert on the **median** to be robust against scheduler jitter, and
set thresholds with a wide margin (the bug yields ~50 ms vs a 5 ms budget — a ~10x gap — so
any reasonable threshold gives an unambiguous RED). No clock-of-day, network, or unseeded RNG.
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
# hiccup cannot flake the test. The bug's ~10x overrun dwarfs any jitter at this count.
_TIMED_RUNS = 7

# Axle friction high enough that gravity cannot start the car on the 30deg ramp
# (the count-independent ramp-stall threshold is mu ~= 6.6 at the BSA-default geometry;
# see WI7-ADV-002) => the car stalls at velocity 0 on the incline. This is a VALID
# input (car.py only raises for friction_coefficient < 0). Recalibrated from the
# historical mu = 2.0 (which matched the OLD count-multiplied friction) to mu = 8.0
# after WI7-ADV-001 made the axle friction count-INDEPENDENT (spec §3.2 / TRD §4),
# per the reconciliation WI7-ADV-002 hands to the developer: the at-rest no-progress
# stall intent is preserved, only the triggering mu tracks the corrected physics.
_STALL_MU = 8.0
# A polished/graphite axle => a normal FINISHED run (the perf baseline).
_FAST_MU = 0.10


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — mirror tests/test_engine_e2e.py / test_engine_adversarial_wi4_adv_002.py
# so construction stays consistent. Imports live inside the bodies so a missing
# module fails each criterion independently (true per-criterion RED) rather than
# aborting collection.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_car(*, friction_coefficient: float) -> CarDesign:
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
        # A stable d_COM in the optimal zone — this is NOT the WI4-ADV-002
        # unstable path; the DNF here is caused by friction stalling on the incline.
        com_ahead_of_rear_axle=Length.from_inches(0.85),
        wheelbase=Length.from_inches(4.375),
        wheels=wheels,
        body=BodyShape(drag_coefficient=0.30, frontal_area=0.0028),
        axle=Axle(friction_coefficient=friction_coefficient),
        # RAIL_RIDER => RNG-free => fully deterministic timing/behavior.
        alignment=Alignment["RAIL_RIDER"],
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
# WI4-ADV-003 (primary) — the NFR itself: a stall-on-incline DNF must meet < 5 ms.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi4_adv_003_stall_on_incline_dnf_meets_performance_budget() -> None:
    """A car that stalls on the inclined ramp (``mu = 2.0``, a valid input) is a DNF;
    ``simulate()`` on it must still complete within the profile/PRD budget of < 5 ms.

    RED today: the car never moves, but the only fast stall guard requires
    ``f_gravity <= 0.0`` which is false on the ramp (theta > 0), so the loop runs the full
    ~60,000-iteration integration to the 60 s wall-clock guard — median ~50 ms, >10x over
    budget. The fix must detect a no-progress stall regardless of incline.
    """
    from pinewood_derby.engine import simulate
    from pinewood_derby.result import Outcome
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(friction_coefficient=_STALL_MU)

    # Sanity: confirm this car is in fact the stall DNF the finding describes, so the
    # perf assertion is timing the *stall-on-incline* branch and not silently a finished
    # run or the already-fixed WI4-ADV-002 unstable-d_COM branch.
    result = simulate(car, STANDARD_TRACK, dt=1e-3, seed=0)
    assert result.outcome is Outcome.DNF

    median_ms = _median_simulate_ms(car)
    assert median_ms < _PERF_BUDGET_MS, (
        f"stall-on-incline simulate() median {median_ms:.2f} ms exceeds the "
        f"{_PERF_BUDGET_MS} ms performance budget (profile quality_bars / PRD §7): a car "
        "that never moves on the ramp is not short-circuited because the fast stall guard "
        "requires f_gravity <= 0 (false on the incline), so the full integration runs to "
        "the 60 s wall-clock guard (TRD §9: that guard must not be hit on valid input)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI4-ADV-003 (root cause) — a no-progress stall must not cost orders of magnitude
# more compute than a normal FINISHED run. Behavioral proxy, no coupling to internals.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi4_adv_003_stall_dnf_is_not_far_slower_than_a_finished_run() -> None:
    """A car that makes zero progress fails fast in principle, so it must cost no more
    compute than a normal FINISHED run on the same track — certainly not orders of magnitude.

    RED today: the finished run is ~3 ms while the stall run is ~50 ms (~17x), because the
    stall-on-incline path runs the full integration to the 60 s guard rather than failing
    fast. We assert the stall run is at most a small multiple of the finished baseline.
    """
    from pinewood_derby.engine import simulate
    from pinewood_derby.result import Outcome
    from pinewood_derby.track import STANDARD_TRACK

    stall_car = _make_car(friction_coefficient=_STALL_MU)
    finished_car = _make_car(friction_coefficient=_FAST_MU)

    # Pin both outcomes so the comparison is stall-DNF vs normal-FINISHED.
    assert simulate(stall_car, STANDARD_TRACK, dt=1e-3, seed=0).outcome is Outcome.DNF
    assert (
        simulate(finished_car, STANDARD_TRACK, dt=1e-3, seed=0).outcome
        is Outcome.FINISHED
    )

    finished_ms = _median_simulate_ms(finished_car)
    stall_ms = _median_simulate_ms(stall_car)

    # A car that never moves must not run materially more work than the finished baseline.
    # 3x is a generous ceiling (the bug yields ~17x); it tolerates timing noise while
    # still catching the wasted 60 s integration unambiguously.
    max_ratio = 3.0
    assert stall_ms <= max_ratio * finished_ms, (
        f"stall-on-incline simulate() median {stall_ms:.2f} ms is "
        f"{stall_ms / finished_ms:.1f}x the finished-run baseline {finished_ms:.2f} ms; "
        "a car that makes zero progress on the ramp runs the full integration to the 60 s "
        "guard instead of failing fast"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI4-ADV-003 (behavioral, time-free) — pin the no-progress defect via the trajectory
# WITHOUT timing, so the fix is also nailed deterministically and jitter-free. A car
# that never advances from the start line must terminate in far fewer than the
# 60 s / dt ≈ 60,000 wall-clock-guard steps, while STILL being a correct DNF (AC-O2).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi4_adv_003_no_progress_stall_terminates_without_hitting_wall_clock_guard() -> None:
    """A car that never leaves the start line must be detected as a no-progress stall and
    terminate quickly, not integrate to the ``_MAX_SIM_TIME_S = 60 s`` wall-clock guard.

    This is the deterministic, timing-free pin of the defect: we assert on the simulated
    elapsed time of the returned trajectory (a pure function of inputs), not wall-clock.
    The DNF behavioral contract is preserved: outcome is DNF and ``race_time_s is None``.

    RED today: the returned trajectory's final ``t`` is ~60 s (the wall-clock guard,
    ~60,000 integration steps) even though the car's position and velocity never leave 0,
    because the fast stall guard never fires on the incline (f_gravity > 0).
    """
    from pinewood_derby.engine import simulate
    from pinewood_derby.result import Outcome
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(friction_coefficient=_STALL_MU)
    result = simulate(car, STANDARD_TRACK, dt=1e-3, seed=0)

    # Behavioral DNF contract (AC-O2) — the fix must preserve this.
    assert result.outcome is Outcome.DNF
    assert result.race_time_s is None

    # Confirm this is genuinely the no-progress stall the finding describes: the car
    # never moves off the start line (max velocity and max position are 0).
    assert max(p.velocity for p in result.trajectory) == 0.0
    assert max(p.position for p in result.trajectory) == 0.0

    # A no-progress car must be detected and terminated long before the 60 s wall-clock
    # guard. We allow a generous simulated-time ceiling (1 s = 1000 steps at dt=1e-3),
    # far above any reasonable few-step stall detector and far below the 60 s guard the
    # bug hits, so this is an unambiguous RED that does not over-constrain the fix.
    final_simulated_t = result.trajectory[-1].t
    max_simulated_t = 1.0
    assert final_simulated_t <= max_simulated_t, (
        f"a car that never leaves the start line integrated to simulated t="
        f"{final_simulated_t:.3f} s (~{int(round(final_simulated_t / 1e-3))} steps), i.e. "
        f"the {_MAX_SIM_TIME_S_HINT} s wall-clock guard, instead of being detected as a "
        "no-progress stall and terminating fast (TRD §9: the guard must bound pathological "
        "runs, not be hit on valid input)"
    )


# A documentation hint only (the engine's private guard constant); not imported from the
# engine so this test stays decoupled from internal names.
_MAX_SIM_TIME_S_HINT = 60
