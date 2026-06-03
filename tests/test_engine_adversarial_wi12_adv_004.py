"""WI12-ADV-004 — the aero-vs-wheels priority order STILL inverts one notch beyond the
WI12-ADV-002 calibration, for a spec-conformant lighter stock wheel + thinner bore
(domain-correctness, high).

AC-ED1 (PRD §6 l.169; assumption A6; profile "Constraints" / "Domain & glossary")
pins aerodynamics as the *smallest* lever: "Minor at derby speeds … Keep this
appropriately small so kids learn the real priority order (weight & friction first)."
The engine must teach that wheel choice (3-vs-4 + lighter wheels) outranks body shape.

WI12-ADV-002 re-tuned the drag knobs to keep aero smaller than the wheels lever down to
0.07 oz stock wheels / 0.20 in bore. This finding is the SAME root cause one notch
further out: the wheels-lever improvement keeps shrinking with stock-wheel rotational
inertia while the BLOCK→WEDGE aero improvement is inertia-independent, so the inversion
reappears for a spec-conformant lighter stock wheel WITH a thinner bore taken together.

Spec §2.2 allows reducing m_w "by up to 60%" from the ≈ 0.09 oz nominal → a floor of
≈ 0.036 oz; a 0.06 oz stock wheel is well within that. PRD A4 flags ``R_inner`` (default
0.37 in) as a tunable placeholder; 0.20 in is a realistic thinner bore. At stock wheel
mass 0.06 oz with R_inner ≤ 0.25 in the BLOCK→WEDGE aero improvement STRICTLY EXCEEDS the
wheels-lever improvement, so aero is no longer the smallest lever — the engine again
teaches that body shape outranks wheel choice for a buildable light-wheel car
(AC-ED1 violated).

Repro (mirrors the WI-12 helper, all-levers-worst baseline: mass 4.0 oz, COM 1.0 in,
4 wheels, C_d 0.85, μ 0.35, STRAIGHT, frontal_area 0.0028, dt 1e-3, seed 0) with the
stock wheel at m_w = 0.06 oz and R_inner = 0.20 in:
  * aero improvement (BLOCK→WEDGE) ≈ 0.044898 s; wheels improvement (3-touching +
    m_w 0.03 oz, the WI-12 50%-lighter recipe) ≈ 0.041739 s
    → aero (0.044898) ≥ wheels (0.041739): AC-ED1 inverted.

The fix is in the ENGINE (the drag calibration must keep aero the smallest lever across
the full spec-conformant wheel-inertia band — light stock wheels AND thin bores together,
not only down to the WI12-ADV-002 calibration point), NOT in the tests.

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

# ── Spec-anchored lever endpoints (physics-spec §3.1; PRD §6). ───────────────────
_CD_WEDGE = 0.20            # streamlined wedge body (best aero)
_CD_BLOCK = 0.85            # blunt wood-block body (worst aero)

# ── Spec-conformant light-wheel / thin-bore points (NOT engine internals). ───────
# Spec §2.2 allows reducing m_w "by up to 60%" from the ≈0.09 oz nominal → floor ≈0.036
# oz; 0.06 oz is well within. PRD A4 flags R_inner (default 0.37 in) as an explicitly
# tunable placeholder; 0.20–0.25 in are realistic thinner bores. Light wheel + thin bore
# together lower the stock wheel rotational inertia far enough to shrink the wheels lever
# below the (inertia-independent) aero lever one notch past the WI12-ADV-002 calibration.
_STOCK_WHEEL_OZ_LIGHT = 0.06          # spec-conformant light stock wheel (§2.2 within 60%)
_R_INNER_THIN_IN = 0.20               # PRD A4 tunable: a realistic thin bore

# The WI-12 wheels recipe: lift one wheel (4→3 touching) AND lighten the wheels ~50%.
_LIGHTEN_FRACTION = 0.50

# ── The all-levers-worst baseline, mirroring the WI-12 helper exactly, with the stock
# wheel mass and bore radius parameterized so the lever ordering can be probed along the
# light-wheel / thin-bore axis (one notch beyond the WI12-ADV-002 calibration point). ──
_BASE = dict(
    mass_oz=4.0,                 # under the cap, FINISHED, stable
    com_ahead_of_rear_axle_in=1.0,
    count_touching=4,            # all four wheels touching (most rotational inertia)
    drag_coefficient=_CD_BLOCK,  # blunt block body (worst aero)
    friction_coefficient=0.35,   # unprepared axles (worst friction)
    alignment="STRAIGHT",        # ping-ponging off the rail (worst alignment)
    frontal_area=0.0028,         # PRD A5 documented default (≈1.75"×2.5")
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
    inner_radius_in: float,
    wheelbase_in: float = 4.375,
    outer_radius_in: float = 0.595,
    axle_radius_in: float = 0.045,
) -> CarDesign:
    """Build a valid CarDesign from plain numbers via the value objects.

    Mirrors the WI-12 construction helper so the baseline and every variant differ only
    in the named field(s); ``wheel_oz`` and ``inner_radius_in`` are explicit parameters
    here so the lever ordering can be measured along the spec-conformant light-wheel /
    thin-bore axis (spec §2.2 60% reduction; PRD A4 R_inner placeholder).
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


def _time(
    *, stock_wheel_oz: float, inner_radius_in: float, **overrides: object
) -> RaceResult:
    """Simulate the baseline at a given stock wheel mass / bore with single-lever
    overrides. ``dt`` and ``seed`` are fixed so the comparison is deterministic.

    ``wheel_oz`` defaults to the *stock* wheel mass (so the baseline and the aero variant
    share the same stock wheels); a wheels-lever override supplies the lightened mass.
    """
    from pinewood_derby.engine import simulate

    params = dict(_BASE)
    params["wheel_oz"] = stock_wheel_oz
    params["inner_radius_in"] = inner_radius_in
    params.update(overrides)
    return simulate(_make_car(**params), dt=1e-3, seed=0)  # type: ignore[arg-type]


def _finished(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.FINISHED


def _aero_and_wheels_improvements(
    *, stock_wheel_oz: float, inner_radius_in: float
) -> tuple[float, float]:
    """Return ``(aero_improvement, wheels_improvement)`` in seconds at this wheel-inertia
    point. The aero improvement is the BLOCK→WEDGE body swap; the wheels improvement is
    lifting a wheel (4→3 touching) AND lightening the wheels ~50% (the WI-12 recipe).

    Asserts the baseline and both variants FINISH (AC-ED1 precondition) so the
    ``race_time_s`` comparison is meaningful.
    """
    baseline = _time(stock_wheel_oz=stock_wheel_oz, inner_radius_in=inner_radius_in)
    assert _finished(baseline), (
        "the all-levers-worst baseline must FINISH so its race_time_s is a comparable "
        f"reference at stock_wheel_oz={stock_wheel_oz}, R_inner={inner_radius_in}in; got "
        f"outcome={baseline.outcome}"
    )
    assert baseline.race_time_s is not None
    base_t = baseline.race_time_s

    aero = _time(
        stock_wheel_oz=stock_wheel_oz,
        inner_radius_in=inner_radius_in,
        drag_coefficient=_CD_WEDGE,
    )
    wheels = _time(
        stock_wheel_oz=stock_wheel_oz,
        inner_radius_in=inner_radius_in,
        count_touching=3,
        wheel_oz=stock_wheel_oz * _LIGHTEN_FRACTION,
    )
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
# WI12-ADV-004 — at the exact finding repro (stock wheel 0.06 oz, R_inner 0.20 in),
# the aero body swap must still buy a STRICTLY SMALLER race_time_s improvement than the
# wheels lever. Direct repro: FAILS on the current engine (aero ≈ 0.044898 s ≥
# wheels ≈ 0.041739 s).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_004_aero_stays_smaller_than_wheels_at_light_wheel_thin_bore() -> None:
    """The smallest-lever invariant (AC-ED1) must hold one notch beyond the WI12-ADV-002
    calibration: at a spec-conformant light stock wheel (m_w = 0.06 oz, within spec §2.2's
    60% reduction) WITH a thin bore (R_inner = 0.20 in, PRD A4 tunable placeholder) the
    BLOCK→WEDGE aero improvement must remain strictly smaller than the 3-wheel +
    50%-lighter-wheels improvement; otherwise the engine teaches that body shape outranks
    wheel choice for a buildable light-wheel car (WI12-ADV-004 / AC-ED1)."""
    aero, wheels = _aero_and_wheels_improvements(
        stock_wheel_oz=_STOCK_WHEEL_OZ_LIGHT,
        inner_radius_in=_R_INNER_THIN_IN,
    )
    assert aero < wheels, (
        "aerodynamics must remain the smaller lever vs wheels at a spec-conformant light "
        f"stock wheel + thin bore (m_w={_STOCK_WHEEL_OZ_LIGHT} oz within §2.2's 60%, "
        f"R_inner={_R_INNER_THIN_IN} in per PRD A4): the BLOCK->WEDGE body swap improved "
        f"race_time_s by {aero:.6f}s but the 3-wheel + lighter-wheels change only improved "
        f"it by {wheels:.6f}s. The engine ranks body shape at or above wheel choice, "
        f"contradicting the taught priority order that aero is the smallest lever "
        f"(WI12-ADV-004 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-004 — the aero<wheels ordering must hold across the thin-bore band at the
# light stock wheel, not just at R_inner 0.20. The finding states the inversion is
# present for R_inner ≤ ~0.25 in at 0.06 oz stock wheels.
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("inner_radius_in", [0.15, 0.20, 0.25])
def test_wi12_adv_004_aero_smaller_than_wheels_across_thin_bore_band(
    inner_radius_in: float,
) -> None:
    """At the light 0.06 oz stock wheel, optimizing the body must never out-buy
    optimizing the wheels across the thin-bore band (R_inner ≤ ~0.25 in). A thinner bore
    lowers stock wheel rotational inertia and so shrinks the wheels lever while the aero
    lever is bore-independent; the engine must keep aero strictly the smaller lever across
    this spec-conformant band, not only at the WI12-ADV-002 calibration point
    (WI12-ADV-004 / AC-ED1 / profile aero-is-minor)."""
    aero, wheels = _aero_and_wheels_improvements(
        stock_wheel_oz=_STOCK_WHEEL_OZ_LIGHT,
        inner_radius_in=inner_radius_in,
    )
    assert aero < wheels, (
        f"at stock_wheel_oz={_STOCK_WHEEL_OZ_LIGHT}, R_inner={inner_radius_in} in "
        f"(spec-conformant) the aero body swap improved race_time_s by {aero:.6f}s but "
        f"the wheels change only by {wheels:.6f}s — aero must be strictly the smaller "
        f"lever across the whole spec-conformant light-wheel/thin-bore band, not only at "
        f"the WI12-ADV-002 calibration point (WI12-ADV-004 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-004 — guard against a regression-masking re-tune: combining a spec-conformant
# light stock wheel with a thin bore must NOT let the (inertia-independent) aero
# improvement overtake the wheels lever. Encodes the root cause — aero is decoupled from
# wheel inertia while the wheels improvement shrinks with both lighter wheels and thinner
# bores — so the fix must keep the ordering as wheel inertia drops on BOTH axes together,
# not merely shift the crossover.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_004_aero_does_not_overtake_wheels_when_lighter_and_thinner() -> None:
    """Moving from the WI12-ADV-002 calibration corner (0.07 oz stock / 0.20 in bore) to a
    lighter stock wheel (0.06 oz) at the same thin bore further shrinks the wheels
    improvement (less rotational inertia to recover) while leaving the aero improvement
    essentially unchanged (it is decoupled from wheel inertia). The invariant the engine
    must preserve is that aero never overtakes wheels across this band: at the lighter
    stock wheel + thin bore the aero improvement must still be strictly below the wheels
    improvement (WI12-ADV-004 / AC-ED1)."""
    aero_calib, wheels_calib = _aero_and_wheels_improvements(
        stock_wheel_oz=0.07, inner_radius_in=_R_INNER_THIN_IN
    )
    aero_light, wheels_light = _aero_and_wheels_improvements(
        stock_wheel_oz=_STOCK_WHEEL_OZ_LIGHT, inner_radius_in=_R_INNER_THIN_IN
    )

    # Sanity on the mechanism: lightening the stock wheel from 0.07 → 0.06 oz at the thin
    # bore shrinks the wheels improvement further while leaving aero essentially unchanged.
    assert wheels_light < wheels_calib, (
        "the wheels improvement must shrink further as the stock wheel lightens at the "
        f"thin bore (less rotational inertia to recover): wheels(0.07oz)={wheels_calib:.6f}s, "
        f"wheels(0.06oz)={wheels_light:.6f}s"
    )

    # The defect: at the lighter conformant stock wheel + thin bore aero overtakes the
    # shrinking wheels lever. The engine must keep aero strictly the smaller lever there.
    assert aero_light < wheels_light, (
        "combining a spec-conformant light stock wheel (0.06 oz) with a thin bore "
        f"(R_inner {_R_INNER_THIN_IN} in) must NOT let the aero lever overtake the wheels "
        f"lever: aero improved race_time_s by {aero_light:.6f}s vs wheels' "
        f"{wheels_light:.6f}s. The wheel-inertia-decoupled drag calibration inverts the "
        f"taught priority order one notch past the WI12-ADV-002 fix for any caller with "
        f"lighter, thinner-bored stock wheels (WI12-ADV-004 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-004 — determinism: the inversion measurement is reproducible for a fixed
# dt + seed (gate: deterministic, seeded — not a flaky finding).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_004_measurement_is_deterministic() -> None:
    """Re-measuring the aero and wheels improvements at the light stock wheel + thin bore
    with the same fixed ``dt`` and ``seed`` must yield bit-identical numbers — the finding
    is a stable invariant violation, not RNG noise (gate: deterministic)."""
    first = _aero_and_wheels_improvements(
        stock_wheel_oz=_STOCK_WHEEL_OZ_LIGHT, inner_radius_in=_R_INNER_THIN_IN
    )
    second = _aero_and_wheels_improvements(
        stock_wheel_oz=_STOCK_WHEEL_OZ_LIGHT, inner_radius_in=_R_INNER_THIN_IN
    )
    assert first == second, (
        "the aero/wheels improvement measurement must be deterministic for a fixed "
        f"dt+seed; got {first} then {second}"
    )
