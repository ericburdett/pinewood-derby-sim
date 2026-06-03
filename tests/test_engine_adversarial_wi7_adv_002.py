"""WI7-ADV-002 — the count-independent axle-friction fix (WI7-ADV-001) must not leave
the suite RED: the pre-existing WI4-ADV-003 stall-DNF tests regressed and must be
reconciled, while a genuine at-rest stall path is still reachable on valid input.

Confirmed adversarial finding (domain-correctness / regression / gate-integrity, high,
reproducible):

The WI-7 engine change (WI7-ADV-001) removed the non-physical ``×N`` wheel-count
multiplier from the axle-friction term so that the total axle friction is now
count-INDEPENDENT (spec §3.2 / TRD §4: each wheel carries the per-wheel normal load
``F_normal / N`` and the sum over the N wheels cancels the count). That fix is
physically correct and is pinned by ``tests/test_engine_adversarial_wi7_adv_001.py`` —
it MUST be preserved.

But dropping the ``×N`` multiplier reduced the total axle friction ~4× (a 4-wheel car),
which moved the *ramp-stall threshold* — the ``μ`` at which gravity can no longer start
the car from rest on the 30° STANDARD_TRACK ramp — from the old count-multiplied value
(``μ ≈ 1.9``) up to the count-independent value (measured ``μ ≈ 6.6`` at the BSA-default
geometry). The pre-existing ``tests/test_engine_adversarial_wi4_adv_003.py`` stall
fixtures were calibrated to the OLD threshold: they use ``μ = 2.0`` to force a
stall-at-rest, asserting ``max(velocity) == 0.0`` and a fast no-progress termination.
Under the new (correct) friction a ``μ = 2.0`` car instead ACCELERATES (measured
~4.19 m/s) and travels metres down the ramp before running out of energy, so two
pre-existing WI-4 tests now FAIL and the full suite is RED:

    tests/test_engine_adversarial_wi4_adv_003.py::
        test_wi4_adv_003_stall_on_incline_dnf_meets_performance_budget
    tests/test_engine_adversarial_wi4_adv_003.py::
        test_wi4_adv_003_no_progress_stall_terminates_without_hitting_wall_clock_guard

This violates the hard WI-7 rule that engine fixes must keep ALL existing tests green
and the gate (gates.md Step 2 "Full suite green" / Step 4 loop-exit). The WI-7 friction
change is defensible per spec; it simply was not reconciled with the WI-4 stall
calibration. The fix (handed to the dev — those WI-4 fixtures are pre-existing test
files OUTSIDE QA's edit scope) is to re-establish a TRUE at-rest stall in the WI-4
fixtures: raise ``μ`` above the new count-independent ramp-stall threshold (≈ 6.6 at the
default geometry) so the documented stall car genuinely stalls again, WITHOUT touching
the WI-4 assertions' intent (still a no-progress, fast-failing DNF) and WITHOUT undoing
the count-independent friction WI7-ADV-001 mandates.

These tests are NEW; they modify, skip, or delete no existing test file. They pin the
finding at two levels:

1. **The regression itself (gate integrity):** the pre-existing WI4-ADV-003 module must
   pass against the production engine. RED today (2 of its tests fail). We run that
   module as a hermetic subprocess and assert it exits 0, so this test is decoupled from
   any specific ``μ`` the dev chooses for the reconciled fixtures — it goes GREEN exactly
   when the regression is healed, however the dev re-establishes the stall.

2. **The physical invariant behind it (domain correctness):** under the *current*
   count-independent friction there must STILL exist a valid high-``μ`` input that
   genuinely stalls the car at rest on the ramp and fails fast (zero progress, a correct
   DNF that terminates long before the 60 s wall-clock guard). This both proves the
   stall path is reachable for the dev to recalibrate onto, and guards that the
   reconciliation does not delete the fast no-progress stall guard the WI-4 finding
   established. It also documents the regression directly: the WI-4 fixtures' historical
   ``μ = 2.0`` no longer produces an at-rest stall under the corrected physics.

Determinism: every fixture uses ``Alignment.RAIL_RIDER`` (constant, RNG-free rail force)
with a fixed ``dt`` and ``seed``, so behaviour is a pure function of inputs. The
subprocess invocation is hermetic (cache + coverage plugins disabled) and its outcome is
a deterministic function of the engine under test — no clock-of-day, network, or unseeded
RNG. No wall-clock timing is asserted in this file.

Traceability: physics-spec §3.2 / §4.1 (count-independent axle friction); TRD §4
("load shared by count"); TRD §9 (the ``_MAX_SIM_TIME_S`` guard must bound pathological
runs, not be hit on valid input); PRD §6 AC-O2 (DNF ⇒ ``race_time_s is None``); gates.md
Step 2/Step 4 (green-suite invariant); adversarial findings WI7-ADV-001 / WI7-ADV-002.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign

# The pre-existing WI4-ADV-003 stall-DNF module that the WI-7 friction change regressed.
# This file lives alongside it in tests/, so resolve it relative to this file.
_WI4_ADV_003_MODULE = Path(__file__).with_name("test_engine_adversarial_wi4_adv_003.py")

# A friction coefficient comfortably ABOVE the new count-independent ramp-stall threshold
# (measured ≈ 6.6 at the BSA-default geometry below). A μ this high cannot be started from
# rest on the 30° ramp, so the car stalls at velocity 0 — a valid input (car.py only
# rejects μ < 0). This is the band the reconciled WI-4 fixtures must move onto.
_STALL_MU = 8.0

# The WI-4 fixtures' historical stall coefficient, calibrated to the OLD count-multiplied
# friction. Under the corrected count-independent friction this no longer stalls the car
# at rest — that is the regression this finding is about.
_HISTORICAL_WI4_STALL_MU = 2.0

# A generous simulated-time ceiling: a true no-progress stall must terminate far below
# this and far below the engine's 60 s wall-clock guard (TRD §9). 1 s = 1000 steps at
# dt = 1e-3, well above any few-step stall detector and far below the 60 s guard.
_MAX_SIMULATED_T_S = 1.0


def _make_car(*, friction_coefficient: float) -> CarDesign:
    """A valid, STABLE, legal car (d_COM in the optimal zone — NOT the instability-cliff
    DNF path) whose only varied parameter is the axle friction. Mirrors the WI4-ADV-003
    fixture geometry so the stall behaviour is compared on the same car family."""
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
        com_ahead_of_rear_axle=Length.from_inches(0.85),
        wheelbase=Length.from_inches(4.375),
        wheels=wheels,
        body=BodyShape(drag_coefficient=0.30, frontal_area=0.0028),
        axle=Axle(friction_coefficient=friction_coefficient),
        # RAIL_RIDER => RNG-free => fully deterministic behaviour.
        alignment=Alignment["RAIL_RIDER"],
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI7-ADV-002 (primary — the regression / gate integrity): the WI-7 friction change
# must not leave the pre-existing WI4-ADV-003 stall-DNF suite RED. We run that module
# as a hermetic subprocess and require it to pass. This is decoupled from any specific
# μ the dev picks for the reconciled fixtures — it goes GREEN exactly when the
# regression is healed, however the at-rest stall is re-established.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi7_adv_002_pre_existing_wi4_adv_003_stall_suite_still_passes() -> None:
    """The WI-7 count-independent axle-friction fix regressed the pre-existing
    WI4-ADV-003 stall-DNF tests (their ``μ = 2.0`` car no longer stalls at rest, so
    ``max(velocity) == 0.0`` and the fast-termination assertions fail), leaving the
    full suite RED in violation of the hard WI-7 rule and gates.md Step 2/Step 4.

    RED today: this subprocess exits non-zero because two WI4-ADV-003 tests fail. It
    goes GREEN when the dev reconciles the WI-4 stall fixtures (raise μ above the new
    count-independent ramp-stall threshold ≈ 6.6) so a true at-rest stall is restored,
    without touching the count-independent friction WI7-ADV-001 mandates."""
    assert _WI4_ADV_003_MODULE.exists(), (
        f"expected the pre-existing WI4-ADV-003 stall module at {_WI4_ADV_003_MODULE}"
    )

    # Hermetic subprocess: disable the cache and the coverage plugin (the project's
    # default addopts inject --cov) so nested coverage cannot perturb the run, and clear
    # addopts so only this one module is collected. The exit code is a deterministic
    # function of the engine under test.
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(_WI4_ADV_003_MODULE),
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:cov",
        ],
        capture_output=True,
        text=True,
        cwd=str(_WI4_ADV_003_MODULE.parent.parent),
    )

    assert completed.returncode == 0, (
        "the pre-existing WI4-ADV-003 stall-DNF suite must pass against the production "
        "engine, but it is RED: the WI-7 count-independent axle-friction fix made the "
        "friction ~4x smaller, moving the ramp-stall threshold from mu~1.9 to mu~6.6, so "
        "the WI-4 fixtures' mu=2.0 'stall' car now accelerates instead of stalling at "
        "rest. The dev must re-establish a true at-rest stall in the WI-4 fixtures "
        "(raise mu above the new threshold) without weakening their intent or undoing "
        "WI7-ADV-001's count-independent friction.\n"
        f"--- pytest stdout ---\n{completed.stdout}\n"
        f"--- pytest stderr ---\n{completed.stderr}"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI7-ADV-002 (root cause — the regressed physics): the historical WI-4 stall input
# (μ = 2.0) no longer stalls the car at rest under the corrected count-independent
# friction. This documents the regression directly and is deterministic + timing-free.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi7_adv_002_historical_mu_2_no_longer_stalls_at_rest() -> None:
    """The WI-4 stall fixtures used ``μ = 2.0`` to force a stall-at-rest, calibrated to
    the OLD count-multiplied friction (ramp-stall threshold ~1.9). Under the corrected
    count-INDEPENDENT friction (WI7-ADV-001) the friction is ~4x smaller, so ``μ = 2.0``
    no longer stalls: the car accelerates and moves down the ramp. This pins the root
    cause of the regression — the fixture coefficient is now below the stall threshold.

    RED today is NOT expected here: this test asserts the *current* (regressed) physical
    fact, so it PASSES against the production engine and stays passing after the dev
    reconciles the WI-4 fixtures (the dev changes the WI-4 fixture's μ, not the engine's
    μ=2.0 behaviour). It exists to make the regression's mechanism an explicit, named,
    deterministic record next to the failing subprocess, and to guard that the
    count-independent friction is not silently reverted (which would re-stall μ=2.0)."""
    from pinewood_derby.engine import simulate
    from pinewood_derby.result import Outcome
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(friction_coefficient=_HISTORICAL_WI4_STALL_MU)
    result = simulate(car, STANDARD_TRACK, dt=1e-3, seed=0)

    # Under the corrected friction this car MOVES — it does not stall at rest — which is
    # exactly why the WI-4 fixtures (which assert max velocity == 0) now fail.
    max_velocity = max(p.velocity for p in result.trajectory)
    assert max_velocity > 0.0, (
        f"with the corrected count-independent friction, a mu={_HISTORICAL_WI4_STALL_MU} "
        f"car no longer stalls at rest on the ramp (it reaches {max_velocity:.4f} m/s); "
        "this is the regression the WI-4 stall fixtures must be recalibrated for. If this "
        "fails (the car stalls at rest), the count-independent friction WI7-ADV-001 "
        "mandates has been reverted."
    )
    # It is still a non-finishing run (it runs out of energy short of the line), so the
    # DNF contract (AC-O2) is intact — only the AT-REST assumption is violated.
    assert result.outcome is Outcome.DNF
    assert result.race_time_s is None


# ───────────────────────────────────────────────────────────────────────────── #
# WI7-ADV-002 (the reconciliation target): a valid at-rest stall path must still exist
# under the corrected friction, and it must fail fast (no-progress, far below the 60 s
# wall-clock guard) while remaining a correct DNF. This is the band the WI-4 fixtures
# must move onto, and it guards that the no-progress stall guard is preserved.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi7_adv_002_high_mu_still_stalls_at_rest_and_fails_fast() -> None:
    """Under the corrected count-independent friction there must STILL be a valid input
    that stalls the car at rest on the ramp. A car with ``μ`` above the new ramp-stall
    threshold (≈ 6.6 at the default geometry) must make ZERO progress, terminate as a
    no-progress stall long before the 60 s wall-clock guard (TRD §9), and report a
    correct DNF (AC-O2: ``race_time_s is None``). This proves the reconciliation target
    is reachable and guards that the fast no-progress stall guard the WI-4 finding
    established is not deleted while healing the regression.

    Deterministic and timing-free: asserts on the trajectory (a pure function of inputs),
    not wall-clock. RED would mean either no valid input can stall the car at rest (the
    WI-4 fixtures could not be reconciled at all) or the no-progress stall guard ground to
    the wall-clock guard."""
    from pinewood_derby.engine import simulate
    from pinewood_derby.result import Outcome
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car(friction_coefficient=_STALL_MU)
    result = simulate(car, STANDARD_TRACK, dt=1e-3, seed=0)

    # A genuine at-rest stall: the car never leaves the start line.
    assert max(p.velocity for p in result.trajectory) == 0.0, (
        f"a mu={_STALL_MU} car must stall at rest on the 30deg ramp under the corrected "
        "count-independent friction (its ramp-stall threshold is ~6.6); if it moves, no "
        "valid high-friction input stalls the car at rest and the WI-4 stall fixtures "
        "cannot be reconciled without re-introducing the count multiplier WI7-ADV-001 "
        "forbids"
    )
    assert max(p.position for p in result.trajectory) == 0.0

    # Behavioral DNF contract (AC-O2) preserved.
    assert result.outcome is Outcome.DNF
    assert result.race_time_s is None

    # Fails fast: terminated as a no-progress stall, not ground to the 60 s guard.
    final_simulated_t = result.trajectory[-1].t
    assert final_simulated_t <= _MAX_SIMULATED_T_S, (
        f"an at-rest stall must be detected and terminated fast; it integrated to "
        f"simulated t={final_simulated_t:.3f} s, i.e. the wall-clock guard, instead of "
        "the no-progress stall guard firing (TRD §9: the guard must bound pathological "
        "runs, not be hit on valid input)"
    )
