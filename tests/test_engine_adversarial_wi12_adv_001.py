"""WI12-ADV-001 — the aero-vs-wheels priority order inverts at a spec-conformant
frontal area (domain-correctness, high).

AC-ED1 (PRD §6 l.169; assumption A6; profile "Constraints" / "Domain & glossary")
pins aerodynamics as the *smallest* lever: "Minor at derby speeds … Keep this
appropriately small so kids learn the real priority order (weight & friction first)."
The engine must teach that wheel choice (3-vs-4 + lighter wheels) outranks body shape.

The existing WI-12 suite (``test_engine_priority_order_wi12.py``) only checks the lever
ordering at the single point ``frontal_area = 0.0028`` m² — the PRD A5 *default*
(≈ 1.75" × 2.5"). But A5 explicitly makes frontal area a tunable, body-shape-dependent
input, and the drag loss the engine charges scales LINEARLY with A (a constant
``drag_factor`` multiplier in ``engine.py``), while the wheels improvement is
area-INDEPENDENT (rotational inertia). So as a caller picks a slightly taller/wider —
but still entirely spec-conformant — front profile, the BLOCK→WEDGE body swap eventually
buys MORE ``race_time_s`` than lightening + lifting a wheel. The crossover sits at
``frontal_area ≈ 0.0035`` m², only ~25% above the documented default: a realistic value
for a chunky-but-legal body. Above it the engine teaches that body shape outranks wheel
choice, directly contradicting the spec/profile priority order (AC-ED1 violated).

Repro (mirrors the WI-12 helper, set ``frontal_area = 0.0036``, within A5's tunable
range): baseline mass 4.0 oz, COM 1.0 in, 4 heavy wheels @ 0.10 oz, C_d 0.85, μ 0.35,
STRAIGHT, dt 1e-3, seed 0 → FINISHED at ≈ 4.34824 s. The BLOCK→WEDGE aero improvement
(≈ 0.08818 s) is GREATER than the 3-wheel + 50%-lighter-wheels improvement
(≈ 0.08429 s): aero is no longer the smallest lever.

The fix is in the engine's drag calibration (the ``_DRAG_EFFECTIVE_AREA_FRACTION`` knob
was tuned to pass at exactly the default area, not across A5's realistic range), NOT in
the tests: aero must remain the smallest lever across the documented frontal-area band.

Behavior-driven, against the PUBLIC contract (``simulate`` + frozen ``RaceResult``)
only — never engine internals. Imports live inside each test body so a missing/renamed
symbol fails *that* test independently rather than aborting whole-file collection.

Integrity / determinism: every run fixes ``dt = 1e-3`` and ``seed = 0`` (no clock /
network / unseeded RNG). This file is NEW; it modifies, skips, or deletes no existing
test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult

# ── PRD A5 frontal-area band (spec/PRD-anchored, NOT engine internals). ──────────
# The documented default body cross-section is ≈ 1.75" × 2.5" = 0.0028 m² (PRD A5).
# A5 makes A a tunable, body-shape-dependent input; a chunky-but-legal body can present
# a noticeably larger front. 0.0036 m² (~25% over the default) is well inside any
# reasonable derby body profile and is the area used in the WI12-ADV-001 repro.
_A5_DEFAULT_FRONTAL_AREA = 0.0028          # m² — PRD A5 documented default (≈1.75"×2.5")
_CONFORMANT_LARGER_FRONTAL_AREA = 0.0036   # m² — within A5's tunable range (~25% over)

# ── Spec-anchored lever endpoints (physics-spec §2/§3; PRD §6). ──────────────────
_CD_WEDGE = 0.20            # streamlined wedge body (best aero)
_CD_BLOCK = 0.85            # blunt wood-block body (worst aero)

# ── The all-levers-worst baseline, mirroring the WI-12 helper exactly, but with the
# frontal area parameterized so the lever ordering can be probed across A5's range. ──
_BASE = dict(
    mass_oz=4.0,                 # under the cap, FINISHED, stable
    com_ahead_of_rear_axle_in=1.0,
    count_touching=4,            # all four wheels touching (most rotational inertia)
    wheel_oz=0.10,               # heavy stock wheels (most rotational inertia)
    drag_coefficient=_CD_BLOCK,  # blunt block body (worst aero)
    friction_coefficient=0.35,   # unprepared axles (worst friction)
    alignment="STRAIGHT",        # ping-ponging off the rail (worst alignment)
)


def _make_car(
    *,
    mass_oz: float,
    com_ahead_of_rear_axle_in: float,
    count_touching: int,
    wheel_oz: float,
    drag_coefficient: float,
    friction_coefficient: float,
    alignment: str,
    frontal_area: float,
    wheelbase_in: float = 4.375,
    outer_radius_in: float = 0.595,
    inner_radius_in: float = 0.37,
    axle_radius_in: float = 0.045,
) -> CarDesign:
    """Build a valid CarDesign from plain numbers via the value objects.

    Mirrors the WI-12 construction helper so the baseline and every variant differ only
    in the named field(s); ``frontal_area`` is an explicit parameter here so the lever
    ordering can be measured at a spec-conformant larger front profile (PRD A5).
    """
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


def _time(*, frontal_area: float, **overrides: object) -> RaceResult:
    """Simulate the baseline car at ``frontal_area`` with single-lever overrides.

    ``dt`` and ``seed`` are fixed so the whole comparison is deterministic.
    """
    from pinewood_derby.engine import simulate

    params = dict(_BASE)
    params.update(overrides)
    params["frontal_area"] = frontal_area
    return simulate(_make_car(**params), dt=1e-3, seed=0)  # type: ignore[arg-type]


def _finished(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.FINISHED


def _aero_and_wheels_improvements(frontal_area: float) -> tuple[float, float]:
    """Return ``(aero_improvement, wheels_improvement)`` in seconds at ``frontal_area``.

    The aero improvement is the BLOCK→WEDGE body swap; the wheels improvement is
    lifting a wheel (4→3 touching) AND lightening the wheels ~50% (0.10→0.05 oz).
    Asserts the baseline and both variants FINISH (AC-ED1 precondition) so the
    ``race_time_s`` comparison is meaningful.
    """
    baseline = _time(frontal_area=frontal_area)
    assert _finished(baseline), (
        "the all-levers-worst baseline must FINISH so its race_time_s is a comparable "
        f"reference at frontal_area={frontal_area}; got outcome={baseline.outcome}"
    )
    assert baseline.race_time_s is not None
    base_t = baseline.race_time_s

    aero = _time(frontal_area=frontal_area, drag_coefficient=_CD_WEDGE)
    wheels = _time(frontal_area=frontal_area, count_touching=3, wheel_oz=0.05)
    assert _finished(aero), (
        f"the aero-optimized variant must FINISH; got outcome={aero.outcome}"
    )
    assert _finished(wheels), (
        f"the wheels-optimized variant must FINISH; got outcome={wheels.outcome}"
    )
    assert aero.race_time_s is not None
    assert wheels.race_time_s is not None
    return base_t - aero.race_time_s, base_t - wheels.race_time_s


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-001 — at a spec-conformant larger frontal area, the aero body swap must
# still buy a STRICTLY SMALLER race_time_s improvement than the wheels lever.
# This is the direct repro: it FAILS on the current engine (aero ≥ wheels at 0.0036).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_001_aero_stays_smaller_than_wheels_at_conformant_larger_front() -> None:
    """The smallest-lever invariant (AC-ED1) must hold at a spec-conformant body front,
    not only at the A5 default. At ``frontal_area = 0.0036`` m² (within A5's tunable
    range, ~25% over the default) the BLOCK→WEDGE aero improvement must remain strictly
    smaller than the 3-wheel + lighter-wheels improvement; otherwise the engine teaches
    that body shape outranks wheel choice (WI12-ADV-001 / AC-ED1)."""
    aero, wheels = _aero_and_wheels_improvements(_CONFORMANT_LARGER_FRONTAL_AREA)
    assert aero < wheels, (
        "aerodynamics must remain the smaller lever vs wheels at a spec-conformant "
        f"larger frontal area ({_CONFORMANT_LARGER_FRONTAL_AREA} m², within PRD A5): the "
        f"BLOCK->WEDGE body swap improved race_time_s by {aero:.6f}s but the 3-wheel + "
        f"lighter-wheels change only improved it by {wheels:.6f}s. The engine ranks body "
        f"shape at or above wheel choice, contradicting the taught priority order that "
        f"aero is the smallest lever (WI12-ADV-001 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-001 — the aero<wheels ordering must hold ACROSS the documented A5 band,
# not just at the single calibration point. Asserts at several conformant areas so a
# fix cannot simply re-tune the knob to pass one new point and re-invert elsewhere.
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize(
    "frontal_area",
    [0.0028, 0.0032, 0.0035, 0.0036, 0.0040],
)
def test_wi12_adv_001_aero_smaller_than_wheels_across_a5_band(
    frontal_area: float,
) -> None:
    """Across the documented PRD A5 frontal-area band, optimizing the body must never
    out-buy optimizing the wheels. The drag loss scales linearly with A while the wheels
    improvement is area-independent, so a single-point calibration leaves the ordering
    correct at the default and inverted above it. Aero must stay the smaller lever for
    every reasonable body front (WI12-ADV-001 / AC-ED1 / profile aero-is-minor)."""
    aero, wheels = _aero_and_wheels_improvements(frontal_area)
    assert aero < wheels, (
        f"at frontal_area={frontal_area} m² (within PRD A5's range) the aero body swap "
        f"improved race_time_s by {aero:.6f}s but the wheels change only by "
        f"{wheels:.6f}s — aero must be strictly the smaller lever across the whole A5 "
        f"band, not only at the calibration default (WI12-ADV-001 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-001 — guard against a regression-masking re-tune: increasing the frontal
# area must NOT increase the aero improvement past the (area-independent) wheels lever.
# Encodes the root cause — aero's linear-in-A scaling vs the area-independent wheels —
# so the fix must keep the ordering as A grows, not merely shift the crossover point.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_001_aero_improvement_does_not_overtake_wheels_as_area_grows() -> None:
    """As the frontal area grows from the A5 default to a conformant larger front, the
    aero improvement (linear in A) climbs while the wheels improvement (area-independent)
    barely moves. The invariant the engine must preserve is that aero never overtakes
    wheels within the documented band: the larger-area aero improvement must still be
    strictly below the larger-area wheels improvement (WI12-ADV-001 / AC-ED1)."""
    aero_default, wheels_default = _aero_and_wheels_improvements(_A5_DEFAULT_FRONTAL_AREA)
    aero_large, wheels_large = _aero_and_wheels_improvements(
        _CONFORMANT_LARGER_FRONTAL_AREA
    )

    # Sanity on the mechanism: at the default area aero is already the smaller lever
    # (this is the only point the existing WI-12 suite checks), and growing A raises the
    # aero improvement while the wheels improvement is essentially area-independent.
    assert aero_default < wheels_default, (
        "precondition: at the A5 default frontal area the aero lever is already the "
        f"smaller one (aero={aero_default:.6f}s, wheels={wheels_default:.6f}s)"
    )
    assert aero_large > aero_default, (
        "the aero improvement must grow with frontal area (drag loss is linear in A): "
        f"aero(default)={aero_default:.6f}s, aero(larger)={aero_large:.6f}s"
    )

    # The defect: at the larger conformant area aero overtakes the area-independent
    # wheels lever. The engine must keep aero strictly the smaller lever there.
    assert aero_large < wheels_large, (
        "growing the frontal area within PRD A5's range must NOT let the aero lever "
        f"overtake the wheels lever: at {_CONFORMANT_LARGER_FRONTAL_AREA} m² aero "
        f"improved race_time_s by {aero_large:.6f}s vs wheels' {wheels_large:.6f}s. The "
        f"single-point drag calibration inverts the taught priority order for any caller "
        f"above the crossover (WI12-ADV-001 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-001 — determinism: the inversion measurement is reproducible for a fixed
# dt + seed (gate: deterministic, seeded — not a flaky finding).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_001_measurement_is_deterministic() -> None:
    """Re-measuring the aero and wheels improvements at the conformant larger frontal
    area with the same fixed ``dt`` and ``seed`` must yield bit-identical numbers — the
    finding is a stable invariant violation, not RNG noise (gate: deterministic)."""
    first = _aero_and_wheels_improvements(_CONFORMANT_LARGER_FRONTAL_AREA)
    second = _aero_and_wheels_improvements(_CONFORMANT_LARGER_FRONTAL_AREA)
    assert first == second, (
        "the aero/wheels improvement measurement must be deterministic for a fixed "
        f"dt+seed; got {first} then {second}"
    )
