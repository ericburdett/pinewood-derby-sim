"""WI6-ADV-003 — the reported final kinetic energies must honour their own documented
contract (``½·M·v²`` and ``Σ½·I·ω²``); the WI-6 head-start must not be silently subtracted
out of them.

Confirmed adversarial finding (domain correctness, high):

``result.py`` documents ``EnergyLedger.ke_linear_final`` as ``½·M·v²`` and
``ke_rotational_final`` as ``Σ ½·I·ω²``, and **AC-E2** states
``KE_total = ½·M·v² + Σ½·I·ω²`` with ``ω = v / R_outer``. The natural, contract-defining
``v`` for the *final* kinetic energy is the car's reported ``finish_velocity`` (the speed
the car physically carries across the finish line).

To force the AC-E1 ledger to close, the engine (engine.py lines 369-385) subtracts the
WI-6 placement head-start KE from the reported finals:

    ke_linear_final     = ½·M·v_finish²              − initial_ke·(M / effective_inertia)
    ke_rotational_final = ½·(Σ I/R²)·v_finish²        − initial_ke·(Σ I/R² / effective_inertia)

So the *reported* ``ke_linear_final`` is ~9.5% BELOW the car's actual ``½·M·v_finish²`` for
a stable placement car at d_COM = 0.85 in, and the gap GROWS monotonically with rear bias
(a bigger head-start subtracts more). The two engine invariants are mutually inconsistent
under the WI-6 head-start model: the head-start energy is excluded from ``w_gravity`` (to
keep AC-E4 d_COM-independent) AND from the reported ``ke_*_final`` (to keep AC-E1 closing),
so the reported final KE no longer equals the physical KE at ``finish_velocity``.

A downstream "where did your speed go?" UI reading these fields reports the car carrying
~10% less kinetic energy than it physically has — teaching wrong physics.

These tests pin the *contract the fields and AC-E2 state*: the reported ``ke_linear_final``
must equal ``½·M·finish_velocity²`` and ``ke_rotational_final`` must equal
``Σ ½·I·(finish_velocity / R_outer)²``, each to a tight relative tolerance. The expected
values are computed from the documented physics (mass, finish_velocity, the wheels' moment
of inertia, outer radius) — never read back from the engine's own ledger. They are
distinct from WI6-ADV-002 (which pins the AC-E1 closure equation): a fix that genuinely
accounts for the head-start in the ledger satisfies BOTH; the current "subtract it from the
reported KE" shortcut violates THIS contract while papering over closure.

All tests are deterministic: fixed dt, fixed seed, RAIL_RIDER alignment (no seeded
ping-pong rail draw to confound the velocity / work accounting).

Traceability: PRD §6 AC-E2 / Output contract; ``result.py`` EnergyLedger field contract;
adversarial finding WI6-ADV-003.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult

# The reported final KE fields are *defined* exact algebraic functions of the reported
# finish_velocity (½·M·v² etc.), so they must match to a tight relative tolerance — this
# is an identity on reported numbers, not an integration-tolerance comparison.
KE_CONTRACT_REL_TOL = 1e-6

# Fixed car geometry shared by the helper and the analytic expectation. Held constant so
# the only thing under test is whether the reported finals honour the documented contract.
_MASS_OZ = 5.0
_WHEELBASE_IN = 4.375
_WHEEL_COUNT = 4
_WHEEL_MASS_OZ = 0.09
_R_OUTER_IN = 0.595
_R_INNER_IN = 0.37
_R_AXLE_IN = 0.045


def _make_car(
    *,
    com_ahead_of_rear_axle_in: float,
    alignment: str = "RAIL_RIDER",
) -> CarDesign:
    """A valid baseline placement car parameterized by d_COM; everything else fixed so the
    only variable is the placement head-start under test. RAIL_RIDER keeps the rail work
    deterministic and seed-independent, so finish_velocity is a clean function of d_COM."""
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(_MASS_OZ),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(_WHEELBASE_IN),
        wheels=Wheels(
            count_touching=_WHEEL_COUNT,
            wheel_mass=Mass.from_ounces(_WHEEL_MASS_OZ),
            outer_radius=Length.from_inches(_R_OUTER_IN),
            inner_radius=Length.from_inches(_R_INNER_IN),
            axle_radius=Length.from_inches(_R_AXLE_IN),
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


def _mass_kg() -> float:
    from pinewood_derby.units import Mass

    return Mass.from_ounces(_MASS_OZ).kg


def _moment_of_inertia_per_wheel() -> float:
    """The single-wheel moment of inertia from the documented formula
    I = ½·m_w·(R_outer² + R_inner²) (AC-WH3), computed from the car's own geometry."""
    from pinewood_derby.car import Wheels
    from pinewood_derby.units import Length, Mass

    return Wheels(
        count_touching=_WHEEL_COUNT,
        wheel_mass=Mass.from_ounces(_WHEEL_MASS_OZ),
        outer_radius=Length.from_inches(_R_OUTER_IN),
        inner_radius=Length.from_inches(_R_INNER_IN),
        axle_radius=Length.from_inches(_R_AXLE_IN),
    ).moment_of_inertia()


def _r_outer_m() -> float:
    from pinewood_derby.units import Length

    return Length.from_inches(_R_OUTER_IN).m


def _expected_ke_linear(finish_velocity: float) -> float:
    """The documented ke_linear_final contract: ½·M·v² (result.py / AC-E2)."""
    return 0.5 * _mass_kg() * finish_velocity**2


def _expected_ke_rotational(finish_velocity: float) -> float:
    """The documented ke_rotational_final contract: Σ ½·I·ω² with ω = v / R_outer
    (result.py / AC-E2), summed over the touching wheels."""
    omega = finish_velocity / _r_outer_m()
    return _WHEEL_COUNT * 0.5 * _moment_of_inertia_per_wheel() * omega**2


# ───────────────────────────────────────────────────────────────────────────── #
# WI6-ADV-003 — the headline regression: the reported ke_linear_final must equal the
# documented ½·M·finish_velocity² for a stable placement car. Today the head-start KE
# is subtracted out, leaving the reported value ~9.5% below the physical KE.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi6_adv_003_reported_ke_linear_equals_half_m_v_squared() -> None:
    """For a FINISHED rear-biased placement car (d_COM = 0.85 in, well inside the stable
    zone), the reported ``ke_linear_final`` must equal ``½·M·finish_velocity²`` — the
    contract its own docstring and AC-E2 state.

    Today it does not: to force AC-E1 closure the engine subtracts the WI-6 head-start KE
    from the reported final, so the reported value is ~9.5% below the car's actual KE."""
    r = _simulate(_make_car(com_ahead_of_rear_axle_in=0.85))
    assert _finished(r), "the placement car must FINISH for a final-KE contract check"

    expected = _expected_ke_linear(r.finish_velocity)
    reported = r.energy.ke_linear_final
    rel_err = abs(reported - expected) / abs(expected)
    assert rel_err <= KE_CONTRACT_REL_TOL, (
        f"ke_linear_final must equal ½·M·finish_velocity² (its documented contract / "
        f"AC-E2), expected {expected:.6f} J for finish_velocity={r.finish_velocity:.6f} "
        f"m/s, but reported {reported:.6f} J (rel_err={rel_err:.3e}). The WI-6 head-start "
        f"KE is being subtracted out of the reported final, so it no longer equals the "
        f"physical kinetic energy the car carries across the line."
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI6-ADV-003 — the same contract for the rotational share: ke_rotational_final must
# equal Σ½·I·ω² with ω = finish_velocity / R_outer. The head-start subtraction hits this
# field too (split by the rotational inertia share).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi6_adv_003_reported_ke_rotational_equals_sum_half_i_omega_squared() -> None:
    """For the same FINISHED placement car, the reported ``ke_rotational_final`` must
    equal ``Σ ½·I·(finish_velocity / R_outer)²`` (result.py contract / AC-E2). Today the
    head-start KE is subtracted from this field too, so it falls below the physical
    rotational KE at the finish."""
    r = _simulate(_make_car(com_ahead_of_rear_axle_in=0.85))
    assert _finished(r), "the placement car must FINISH for a rotational-KE contract check"

    expected = _expected_ke_rotational(r.finish_velocity)
    reported = r.energy.ke_rotational_final
    rel_err = abs(reported - expected) / abs(expected)
    assert rel_err <= KE_CONTRACT_REL_TOL, (
        f"ke_rotational_final must equal Σ½·I·ω² with ω=finish_velocity/R_outer (its "
        f"documented contract / AC-E2), expected {expected:.6f} J for "
        f"finish_velocity={r.finish_velocity:.6f} m/s, but reported {reported:.6f} J "
        f"(rel_err={rel_err:.3e}). The WI-6 head-start KE is subtracted from this field "
        f"too, so the reported rotational KE is below the physical value."
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI6-ADV-003 — the contract must hold across the whole rear-bias range WI-6 spans; the
# finding shows the error GROWS monotonically with rear bias (a bigger head-start
# subtracts more), so the rearmost stable cars are the worst offenders.
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("d_com_in", [3.0, 2.0, 1.25, 1.0, 0.85, 0.7, 0.65])
def test_wi6_adv_003_ke_total_equals_physical_ke_across_rear_bias(d_com_in: float) -> None:
    """Across the full stable placement range — from a forward COM (small head-start) to a
    maximally rear COM just above the cliff (large head-start) — the reported total final
    KE (``ke_linear_final + ke_rotational_final``) must equal the physical
    ``½·M·v² + Σ½·I·ω²`` at the reported ``finish_velocity`` (AC-E2). The current
    head-start subtraction makes the gap scale with rear bias, so closure of THIS contract
    fails worse as d_COM shrinks."""
    r = _simulate(_make_car(com_ahead_of_rear_axle_in=d_com_in))
    assert _finished(r), f"d_COM={d_com_in} in must FINISH for a final-KE contract check"

    expected = _expected_ke_linear(r.finish_velocity) + _expected_ke_rotational(
        r.finish_velocity
    )
    reported = r.energy.ke_linear_final + r.energy.ke_rotational_final
    rel_err = abs(reported - expected) / abs(expected)
    assert rel_err <= KE_CONTRACT_REL_TOL, (
        f"AC-E2 requires KE_total_final = ½·M·v² + Σ½·I·ω² at finish_velocity; for "
        f"d_COM={d_com_in} in expected {expected:.6f} J but reported {reported:.6f} J "
        f"(rel_err={rel_err:.3e}). The unaccounted WI-6 head-start KE is subtracted from "
        f"the reported finals and grows with rear bias, so the reported KE drifts further "
        f"below the physical KE as d_COM shrinks."
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI6-ADV-003 — pin the *cause*: the missing energy is exactly the WI-6 head-start KE.
# This prevents a fix that merely tweaks finish_velocity or hides the gap; the reported
# finals must reflect the car's actual speed, with the head-start properly accounted for
# elsewhere (e.g. carried into w_gravity) rather than quietly docked from the KE.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi6_adv_003_missing_ke_matches_the_injected_head_start_energy() -> None:
    """The deficit between the physical final KE and the reported final KE must NOT match
    the WI-6 head-start energy — i.e. the reported finals must not be the physical KE
    minus the injected head-start.

    The head-start energy is the rear-bias potential energy the COM carries from sitting
    (L − d_COM) up-ramp of the start line: M·g·(L − d_COM)·sinθ. If the engine reports
    ½·M·v² honestly (contract satisfied), the deficit is ~0. If it subtracts the
    head-start (today's behaviour), the deficit equals that head-start energy."""
    from pinewood_derby.track import STANDARD_TRACK
    from pinewood_derby.units import Length

    d_com_in = 0.85
    r = _simulate(_make_car(com_ahead_of_rear_axle_in=d_com_in))
    assert _finished(r)

    physical_total = _expected_ke_linear(r.finish_velocity) + _expected_ke_rotational(
        r.finish_velocity
    )
    reported_total = r.energy.ke_linear_final + r.energy.ke_rotational_final
    deficit = physical_total - reported_total  # joules docked from the reported KE

    # Reconstruct the head-start energy from spec geometry: the COM sits (L − d_COM)
    # up-ramp, carrying M·g·(L − d_COM)·sinθ of energy injected as initial velocity.
    head_start_arc = Length.from_inches(_WHEELBASE_IN).m - Length.from_inches(d_com_in).m
    g = 9.81
    head_start_pe = (
        _mass_kg() * g * head_start_arc * math.sin(STANDARD_TRACK.ramp_angle.radians)
    )

    # A contract-honouring engine reports the full physical KE → deficit ~ 0, far below
    # the head-start energy. Today the deficit ≈ head_start_pe (the subtracted term).
    assert deficit < 0.5 * head_start_pe, (
        f"the reported final KE is short by {deficit:.4f} J, comparable to the injected "
        f"WI-6 head-start energy (~{head_start_pe:.4f} J) — confirming the head-start KE "
        f"is being docked from the reported finals rather than the finals honouring "
        f"½·M·v² (AC-E2 / result.py contract). A contract-honouring engine has a "
        f"deficit of ~0 J."
    )
