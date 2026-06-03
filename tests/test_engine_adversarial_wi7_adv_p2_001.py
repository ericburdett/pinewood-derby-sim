"""WI7-ADV-P2-001 — the count-independent axle-friction fix (WI7-ADV-001) left the full
suite RED: the pre-existing WI4-ADV-003 stall-DNF fixtures are calibrated to the OLD
count-multiplied ramp-stall threshold and no longer describe a real at-rest stall.

Confirmed adversarial finding (domain-correctness / gate-integrity / regression, high,
reproducible):

The WI-7 engine change (WI7-ADV-001) removed the non-physical ``×N`` wheel-count
multiplier from the axle-friction term, so total axle friction is now count-INDEPENDENT
(physics-spec §3.2 / TRD §4: each wheel carries the per-wheel normal load ``F_normal / N``
and the sum over the N wheels cancels the count). That fix is physically correct and is
pinned by ``tests/test_engine_adversarial_wi7_adv_001.py`` — it MUST be PRESERVED.

But dropping the ``×N`` multiplier reduced the total axle friction ~4× for a 4-wheel car,
which moved the ramp-stall threshold — the ``μ`` at which gravity can no longer start the
car from rest on the 30° STANDARD_TRACK ramp — from the old count-multiplied value
(``μ ≈ 1.9``) up to the count-independent value (``μ ≈ 6.6`` at the BSA-default geometry).
The pre-existing ``tests/test_engine_adversarial_wi4_adv_003.py`` stall fixtures were
calibrated to the OLD threshold: they use ``μ = 2.0`` to force a stall-at-rest and assert
``max(velocity) == 0.0`` / ``max(position) == 0.0`` / a fast no-progress termination.
Under the corrected friction a ``μ = 2.0`` car instead ACCELERATES (reaches ~4.19 m/s),
travels down the ramp, and runs out of energy on the flat at simulated ``t ≈ 3.57 s``, so
three tests fail and the full suite is RED:

    tests/test_engine_adversarial_wi4_adv_003.py::
        test_wi4_adv_003_stall_on_incline_dnf_meets_performance_budget
    tests/test_engine_adversarial_wi4_adv_003.py::
        test_wi4_adv_003_no_progress_stall_terminates_without_hitting_wall_clock_guard
    tests/test_engine_adversarial_wi7_adv_002.py::
        test_wi7_adv_002_pre_existing_wi4_adv_003_stall_suite_still_passes

This violates the hard WI-7 rule that engine fixes must keep ALL existing tests green and
gates.md Step 2 (full suite green) / Step 4 (loop-exit). The WI-7 friction change is
defensible per spec and must be PRESERVED; the reconciliation is DEV-owned — those WI-4
stall fixtures are pre-existing test files OUTSIDE QA's edit scope. The dev must raise the
WI-4 fixtures' ``μ`` above the new count-independent stall threshold (≈ 6.6; e.g.
``μ = 8.0`` as WI7-ADV-002 documents) so a genuine at-rest stall is restored, WITHOUT
re-introducing the ``×N`` count multiplier WI7-ADV-001 forbids and WITHOUT weakening the
WI-4 assertions' intent (still a no-progress, fast-failing DNF).

These tests are NEW; they modify, skip, or delete no existing test file. They pin the
finding at two decoupled levels:

1. **The regression / gate integrity (the failing thing):** the production engine, run
   against the WHOLE pre-existing tests/ directory, must leave it green. RED today because
   three tests fail under the live engine. This is decoupled from whatever ``μ`` the dev
   picks for the reconciled WI-4 fixtures — it goes GREEN exactly when the regression is
   healed, however the at-rest stall is re-established, without depending on the engine's
   own private guard names.

2. **The deterministic physical root cause (jitter-free):** the historical WI-4 stall
   input ``μ = 2.0`` no longer produces an at-rest stall under the corrected friction (the
   car MOVES), while a ``μ`` above the new threshold (8.0) genuinely stalls at rest and
   fails fast. This documents the regression's mechanism without any wall-clock timing
   (which the finding notes is inflated by the coverage plugin under full-suite load), and
   guards both directions: that the count-independent friction is not silently reverted and
   that a valid at-rest stall path the WI-4 fixtures can be reconciled onto still exists.

Determinism: every car uses ``Alignment.RAIL_RIDER`` (constant, RNG-free rail force) with a
fixed ``dt`` and ``seed``, so behaviour is a pure function of inputs. The subprocess
invocation is hermetic (cache + coverage plugins disabled) and its exit code is a
deterministic function of the engine under test — no clock-of-day, network, or unseeded
RNG, and no wall-clock duration is asserted.

Traceability: physics-spec §3.2 / §4.1 (count-independent axle friction); TRD §4 ("load
shared by count"); TRD §9 (the wall-clock guard must bound pathological runs, not be hit on
valid input); PRD §6 AC-O2 (DNF ⇒ ``race_time_s is None``); gates.md Step 2 (full suite
green) / Step 4 (loop-exit); adversarial findings WI7-ADV-001 / WI7-ADV-002 / WI7-ADV-P2-001.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign

# The whole pre-existing tests/ directory; running the live engine against it must be green.
_TESTS_DIR = Path(__file__).parent
_PROJECT_ROOT = _TESTS_DIR.parent

# This very module — excluded from the hermetic full-suite run below so it cannot recurse
# into a subprocess of itself.
_SELF = Path(__file__).name

# The WI-4 fixtures' historical stall coefficient, calibrated to the OLD count-multiplied
# friction (old ramp-stall threshold ≈ 1.9). Under the corrected count-INDEPENDENT friction
# this no longer stalls the car at rest — that is the regression this finding documents.
_HISTORICAL_WI4_STALL_MU = 2.0

# A friction coefficient comfortably ABOVE the new count-independent ramp-stall threshold
# (≈ 6.6 at the BSA-default geometry below). This is a VALID input (car.py only rejects
# μ < 0) and is the band the reconciled WI-4 fixtures must move onto.
_STALL_MU = 8.0

# A generous simulated-time ceiling: a true no-progress stall must terminate far below this
# and far below the engine's 60 s wall-clock guard. 1 s = 1000 steps at dt = 1e-3.
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
# WI7-ADV-P2-001 (primary — the regression / gate integrity): the live production
# engine, run against the WHOLE pre-existing tests/ directory, must leave it green.
# RED today because the WI-7 count-independent friction fix regressed the WI4-ADV-003
# stall fixtures (and the WI7-ADV-002 subprocess wrapper of them). Decoupled from any
# specific μ the dev picks — it goes GREEN exactly when the regression is healed.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi7_adv_p2_001_full_suite_is_green_against_live_engine() -> None:
    """The WI-7 count-independent axle-friction fix (WI7-ADV-001, correct per spec) left
    the full suite RED: the pre-existing WI4-ADV-003 ``μ = 2.0`` stall fixtures no longer
    describe an at-rest stall (the car now accelerates to ~4.19 m/s), so they — and the
    WI7-ADV-002 subprocess that wraps them — fail. That violates the hard WI-7 rule
    (engine fixes keep ALL existing tests green) and gates.md Step 2 / Step 4.

    RED today: this subprocess collects the whole pre-existing tests/ directory against the
    live engine and exits non-zero because three tests fail. It goes GREEN when the dev
    reconciles the WI-4 stall fixtures (raise μ above the new count-independent threshold
    ≈ 6.6) so a true at-rest stall is restored — WITHOUT reverting WI7-ADV-001's
    count-independent friction. Decoupled from the engine's private guard names and from
    whichever μ the dev chooses.
    """
    assert _TESTS_DIR.is_dir(), f"expected the pre-existing tests/ dir at {_TESTS_DIR}"

    # Hermetic subprocess: clear the project's default addopts (which inject --cov) and
    # disable the cache + coverage plugins so a nested coverage run cannot perturb results.
    # Deselect THIS module so the run cannot recurse into a subprocess of itself; collect
    # everything else in tests/. The exit code is a deterministic function of the engine.
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(_TESTS_DIR),
            f"--ignore={Path(__file__)}",
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
        cwd=str(_PROJECT_ROOT),
    )

    assert completed.returncode == 0, (
        "the full pre-existing test suite must be green against the production engine, but "
        "it is RED: the WI-7 count-independent axle-friction fix made the friction ~4x "
        "smaller, moving the ramp-stall threshold from mu~1.9 to mu~6.6, so the WI-4 "
        "fixtures' mu=2.0 'stall' car now accelerates (~4.19 m/s) instead of stalling at "
        "rest. The dev must re-establish a true at-rest stall in the pre-existing WI-4 "
        "fixtures (raise mu above the new threshold, e.g. 8.0) without weakening their "
        "intent or undoing WI7-ADV-001's count-independent friction.\n"
        f"--- pytest stdout ---\n{completed.stdout}\n"
        f"--- pytest stderr ---\n{completed.stderr}"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI7-ADV-P2-001 (root cause — the regressed physics, deterministic + timing-free):
# the historical WI-4 stall input (μ = 2.0) no longer stalls the car at rest, while a
# μ above the new threshold (8.0) genuinely stalls at rest and fails fast. This both
# documents the regression's mechanism and proves the reconciliation target exists.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi7_adv_p2_001_historical_mu_2_moves_but_high_mu_stalls_at_rest() -> None:
    """The WI-4 stall fixtures used ``μ = 2.0`` to force a stall-at-rest, calibrated to the
    OLD count-multiplied friction (ramp-stall threshold ≈ 1.9). Under the corrected
    count-INDEPENDENT friction (WI7-ADV-001) the friction is ~4x smaller, so ``μ = 2.0``
    no longer stalls: the car accelerates and travels down the ramp — exactly why the
    historical WI-4 ``max(velocity) == 0`` assertions now fail. Meanwhile a ``μ`` above the
    new threshold (8.0, a valid input) still stalls the car at rest and fails fast, which
    is the band the WI-4 fixtures must be reconciled onto.

    This is the deterministic, jitter-free record of the regression (no wall-clock timing —
    the finding notes the coverage plugin inflates that under full-suite load). It guards
    BOTH directions: if μ=2.0 ever stalls again the count-independent friction was reverted,
    and if μ=8.0 ever fails to stall at rest there is no valid input the WI-4 fixtures can
    be reconciled onto without re-introducing the count multiplier.

    This test PASSES against the production engine today (it asserts the CURRENT, regressed
    physical facts) and stays passing after the dev recalibrates the WI-4 fixtures (the dev
    changes the WI-4 fixture μ, not the engine's μ=2.0 / μ=8.0 behaviour). The RED that
    proves the OPEN defect is carried by the full-suite subprocess test above; this test is
    the named, deterministic mechanism beside it (a valid verification of the engine's
    current behaviour and the reconciliation target).
    """
    from pinewood_derby.engine import simulate
    from pinewood_derby.result import Outcome
    from pinewood_derby.track import STANDARD_TRACK

    # --- The regressed input: μ = 2.0 now MOVES (it did not, under the old ×N friction). ---
    moving = simulate(
        _make_car(friction_coefficient=_HISTORICAL_WI4_STALL_MU),
        STANDARD_TRACK,
        dt=1e-3,
        seed=0,
    )
    max_v_moving = max(p.velocity for p in moving.trajectory)
    assert max_v_moving > 0.0, (
        f"with the corrected count-independent friction a mu={_HISTORICAL_WI4_STALL_MU} car "
        f"no longer stalls at rest on the ramp (it reaches {max_v_moving:.4f} m/s); this is "
        "the regression the pre-existing WI-4 stall fixtures must be recalibrated for. If "
        "this fails (the car stalls at rest), WI7-ADV-001's count-independent friction has "
        "been reverted."
    )
    # Still a non-finishing run (runs out of energy short of the line) => DNF contract intact.
    assert moving.outcome is Outcome.DNF
    assert moving.race_time_s is None

    # --- The reconciliation target: a μ above the new threshold genuinely stalls at rest. ---
    stalled = simulate(
        _make_car(friction_coefficient=_STALL_MU),
        STANDARD_TRACK,
        dt=1e-3,
        seed=0,
    )
    assert max(p.velocity for p in stalled.trajectory) == 0.0, (
        f"a mu={_STALL_MU} car must stall at rest on the 30deg ramp under the corrected "
        "count-independent friction (its ramp-stall threshold is ~6.6); if it moves, no "
        "valid high-friction input stalls the car at rest and the WI-4 stall fixtures "
        "cannot be reconciled without re-introducing the count multiplier WI7-ADV-001 "
        "forbids"
    )
    assert max(p.position for p in stalled.trajectory) == 0.0

    # The high-mu stall is a correct DNF (AC-O2) and fails fast — the no-progress stall
    # guard fires long before the 60 s wall-clock guard (TRD §9). Deterministic: asserted
    # on the trajectory's simulated time, not wall-clock.
    assert stalled.outcome is Outcome.DNF
    assert stalled.race_time_s is None
    final_simulated_t = stalled.trajectory[-1].t
    assert final_simulated_t <= _MAX_SIMULATED_T_S, (
        f"an at-rest stall must be detected and terminated fast; it integrated to simulated "
        f"t={final_simulated_t:.3f} s, i.e. the wall-clock guard, instead of the no-progress "
        "stall guard firing (TRD §9: the guard must bound pathological runs, not be hit on "
        "valid input)"
    )
