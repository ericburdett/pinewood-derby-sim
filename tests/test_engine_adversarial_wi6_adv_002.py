"""WI6-ADV-002 — the WI-6 placement head-start must not break the energy-ledger
closure invariant (AC-E1).

Confirmed adversarial finding (domain correctness, high):

AC-E1 / TRD §4 step 6 state the per-force energy ledger closes *by construction* for a
FINISHED run, within relative tolerance ``1e-6``:

    KE_total_final ≈ W_gravity − (W_drag + W_axle + W_rail)

The WI-6 placement head-start injects kinetic energy as an initial velocity
(``initial_velocity = sqrt(2·head_start_work/effective_inertia)``, engine.py), but that
head-start work is NEVER accumulated into the integrated ledger — the loop only
integrates from the start line forward. So the final KE carries the injected initial KE
that no ledger term accounts for, and the equation no longer closes:

    KE_final = (W_gravity − W_drag − W_axle − W_rail) + initial_KE

Measured relative error is ~10% for a placement car (e.g. rel_err ≈ 1.03e-1 at
d_COM = 0.85 in) and grows monotonically with rear bias (bigger head-start). No existing
test asserts ledger closure for a placement car, so this regression is uncaught: the
WI-6 mechanism silently breaks a global physics invariant the whole engine rests on.

These tests pin the AC-E1 contract directly — the ledger must close to relative
tolerance 1e-6 for any FINISHED placement car, across the rear-bias range WI-6 spans.
The expected relation is taken from AC-E1, never read from the engine. The fix must
account for the head-start energy in the ledger (e.g. integrate from the true release
height, or carry the head-start as a gravity-work term) so closure holds.

All tests are deterministic: fixed dt, fixed seed, RAIL_RIDER alignment (no seeded
ping-pong rail draw to confound the work accounting).

Traceability: PRD §6 AC-E1; TRD §4 step 6; adversarial finding WI6-ADV-002.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult

# AC-E1's stated closure tolerance (PRD §6 Energy / physics integrity).
AC_E1_REL_TOL = 1e-6


def _make_car(
    *,
    com_ahead_of_rear_axle_in: float,
    mass_oz: float = 5.0,
    wheelbase_in: float = 4.375,
    alignment: str = "RAIL_RIDER",
) -> CarDesign:
    """A valid baseline car parameterized by d_COM; everything else fixed so the only
    variable is the placement head-start under test. RAIL_RIDER keeps the rail work
    deterministic and seed-independent."""
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(wheelbase_in),
        wheels=Wheels(
            count_touching=4,
            wheel_mass=Mass.from_ounces(0.09),
            outer_radius=Length.from_inches(0.595),
            inner_radius=Length.from_inches(0.37),
            axle_radius=Length.from_inches(0.045),
        ),
        body=BodyShape(drag_coefficient=0.30, frontal_area=0.0028),
        axle=Axle(friction_coefficient=0.20),
        alignment=Alignment[alignment],
    )


def _simulate(car: CarDesign) -> RaceResult:
    from pinewood_derby.engine import simulate
    from pinewood_derby.track import STANDARD_TRACK

    return simulate(car, STANDARD_TRACK, dt=1e-3, seed=0)


def _finished(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.FINISHED


def _ledger_relative_error(result: RaceResult) -> float:
    """Relative error of the AC-E1 closure equation for a FINISHED run:
    KE_total_final vs W_gravity − (W_drag + W_axle + W_rail)."""
    e = result.energy
    ke_total = e.ke_linear_final + e.ke_rotational_final
    rhs = e.w_gravity - (e.w_drag + e.w_axle + e.w_rail)
    return abs(ke_total - rhs) / abs(rhs)


# ───────────────────────────────────────────────────────────────────────────── #
# WI6-ADV-002 — the headline regression: a placement car's ledger must close to the
# AC-E1 tolerance. Today the injected head-start KE leaves a ~10% gap.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi6_adv_002_placement_car_ledger_closes_to_ac_e1_tolerance() -> None:
    """For a FINISHED placement car (rear-biased d_COM = 0.85 in, well inside the
    stable zone), the energy ledger must close to AC-E1's relative tolerance 1e-6.

    Today it does not: the head-start KE injected as initial_velocity is never added to
    any ledger term, so KE_final exceeds W_gravity − losses by the head-start energy
    (~10% relative error)."""
    r = _simulate(_make_car(com_ahead_of_rear_axle_in=0.85))
    assert _finished(r), "the placement car must FINISH for an AC-E1 closure check"
    rel_err = _ledger_relative_error(r)
    assert rel_err <= AC_E1_REL_TOL, (
        f"AC-E1 requires the ledger to close within rel tol {AC_E1_REL_TOL:.0e}, but a "
        f"placement car (d_COM=0.85 in) has rel_err={rel_err:.3e}. The WI-6 head-start "
        f"KE is injected as initial velocity but never accounted for in the ledger, so "
        f"KE_final = (W_gravity − losses) + injected_KE and the equation does not close."
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI6-ADV-002 — closure must hold across the whole rear-bias range WI-6 spans; the
# finding shows the error GROWS monotonically with rear bias (bigger head-start).
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("d_com_in", [3.0, 2.0, 1.25, 1.0, 0.85, 0.7, 0.65])
def test_wi6_adv_002_ledger_closes_across_rear_bias_range(d_com_in: float) -> None:
    """Across the full stable placement range — from a forward COM (small head-start)
    to a maximally rear COM just above the cliff (large head-start) — every FINISHED
    car's ledger must close to AC-E1 tolerance. The current error scales with rear
    bias, so the rearmost cars are the worst offenders."""
    r = _simulate(_make_car(com_ahead_of_rear_axle_in=d_com_in))
    assert _finished(r), f"d_COM={d_com_in} in must FINISH for a closure check"
    rel_err = _ledger_relative_error(r)
    assert rel_err <= AC_E1_REL_TOL, (
        f"AC-E1 ledger closure must hold for d_COM={d_com_in} in (rel tol "
        f"{AC_E1_REL_TOL:.0e}), got rel_err={rel_err:.3e}. The unaccounted head-start "
        f"KE grows with rear bias, so closure fails worse as d_COM shrinks."
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI6-ADV-002 — the head-start KE is the missing term: the closure gap must not be
# explained by the injected initial kinetic energy. This pins the *cause*, so a fix
# that merely hides the gap (e.g. inflating w_gravity arbitrarily) cannot pass while
# leaving the head-start unaccounted.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi6_adv_002_closure_gap_is_not_the_injected_head_start_energy() -> None:
    """The ledger gap (KE_final − (W_gravity − losses)) must not equal the injected
    head-start KE — i.e. the head-start energy must be properly accounted for, not left
    as an unbalanced surplus in the final KE. A correctly-closing ledger has a gap of
    ~0 (to AC-E1 tolerance, in absolute joules), nowhere near the head-start KE.

    We compute the head-start KE from the *reported* head-start potential energy: the
    reported pe_initial includes the rear-bias head-start height term M·g·(L−d_COM)·sinθ
    above the ramp's own M·g·ramp_length·sinθ; that surplus is the head-start energy that
    became the injected initial KE. If the ledger closed, that energy would appear in a
    ledger term and the closure gap would be ~0, not ~head_start_energy."""
    import math

    from pinewood_derby.track import STANDARD_TRACK
    from pinewood_derby.units import Length, Mass

    d_com_in = 0.85
    car = _make_car(com_ahead_of_rear_axle_in=d_com_in)
    r = _simulate(car)
    assert _finished(r)

    e = r.energy
    ke_total = e.ke_linear_final + e.ke_rotational_final
    rhs = e.w_gravity - (e.w_drag + e.w_axle + e.w_rail)
    gap = ke_total - rhs  # absolute joules of unclosed ledger

    # Reconstruct the head-start potential energy from the spec geometry: the COM sits
    # (L − d_COM) up-ramp of the start line; that extra height carries
    # M·g·(L − d_COM)·sinθ of energy released as the injected initial KE.
    mass_kg = Mass.from_ounces(5.0).kg
    wheelbase_m = Length.from_inches(4.375).m
    d_com_m = Length.from_inches(d_com_in).m
    head_start_arc = wheelbase_m - d_com_m
    g = 9.81
    ramp_angle_rad = STANDARD_TRACK.ramp_angle.radians
    head_start_pe = mass_kg * g * head_start_arc * math.sin(ramp_angle_rad)

    # A closed ledger has gap ~ 0 (AC-E1). A ledger that drops the head-start has
    # gap ~ head_start_pe. Assert the gap is NOT the head-start energy — i.e. the
    # head-start was accounted for and the ledger closes.
    assert abs(gap) < 0.5 * head_start_pe, (
        f"the ledger gap ({gap:.4f} J) is comparable to the injected head-start energy "
        f"(~{head_start_pe:.4f} J) — confirming the WI-6 head-start KE was never added "
        f"to any ledger term. A closing ledger (AC-E1) leaves a gap of ~0 J."
    )
