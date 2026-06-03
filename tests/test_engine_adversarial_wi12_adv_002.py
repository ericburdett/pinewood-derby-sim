"""WI12-ADV-002 — the aero-vs-wheels priority order inverts along the wheel-inertia
axis at a spec-conformant lighter stock wheel / thinner bore (domain-correctness, high).

AC-ED1 (PRD §6 l.169; assumption A6; profile "Constraints" / "Domain & glossary")
pins aerodynamics as the *smallest* lever: "Minor at derby speeds … Keep this
appropriately small so kids learn the real priority order (weight & friction first)."
The engine must teach that wheel choice (3-vs-4 + lighter wheels) outranks body shape.

WI12-ADV-001 fixed the area axis (drag loss scales linearly with frontal area while the
wheels lever is area-independent). This finding is the *same root cause on a different,
still-uncovered axis*: the wheels lever's improvement shrinks as the **stock wheel
rotational inertia** shrinks, while the aero (BLOCK→WEDGE) improvement is independent of
wheel inertia. Both the existing WI-12 suite and WI12-ADV-001 only probe the ordering at
the heavy stock wheel mass (0.10 oz) and the default bore radius (R_inner = 0.37 in).

For spec-conformant lighter stock wheels — spec §1.1 gives m_w ≈ 0.09 oz as a *nominal*,
not a floor, and 0.07 oz is a perfectly buildable lighter stock wheel — or a thinner bore
(R_inner = 0.20 in; PRD A4 explicitly flags R_inner as a tunable placeholder), the
BLOCK→WEDGE body swap buys a STRICTLY LARGER ``race_time_s`` improvement than the wheels
lever (3-touching + 50%-lighter wheels, the WI-12 recipe). Aero is then no longer the
smallest lever, teaching the wrong derby priority order (AC-ED1 violated).

Repro (mirrors the WI-12 helper, all-levers-worst baseline: mass 4.0 oz, COM 1.0 in,
4 wheels, C_d 0.85, μ 0.35, STRAIGHT, frontal_area 0.0028, dt 1e-3, seed 0):
  * Lighter stock wheels (m_w = 0.07 oz): baseline ≈ 4.281160 s; aero improvement
    ≈ 0.068078 s; wheels improvement (3-touching + m_w 0.035 oz) ≈ 0.059836 s
    → aero (0.068078) ≥ wheels (0.059836): AC-ED1 inverted.
  * Thinner bore (R_inner = 0.20 in, m_w default 0.09 oz): aero improvement ≈ 0.068004 s
    ≥ wheels improvement (3-touching + m_w 0.045 oz) ≈ 0.061786 s: AC-ED1 inverted.

The fix is in the engine (the drag calibration ``_DRAG_EFFECTIVE_AREA_FRACTION`` /
``_DRAG_AREA_EXPONENT`` and the wheels inertia coupling were tuned/verified only at the
heavy-wheel / wide-bore calibration point) — aero must remain the smallest lever across
the spec-conformant wheel-inertia band — NOT in the tests.

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

# ── Spec-anchored lever endpoints (physics-spec §2/§3; PRD §6). ──────────────────
_CD_WEDGE = 0.20            # streamlined wedge body (best aero)
_CD_BLOCK = 0.85            # blunt wood-block body (worst aero)

# ── Spec-conformant wheel-inertia points (NOT engine internals). ─────────────────
# Spec §1.1 gives m_w ≈ 0.09 oz as a *nominal* stock wheel, not a floor; 0.07 oz is a
# perfectly buildable lighter stock wheel. PRD A4 flags R_inner (default 0.37 in) as an
# explicitly tunable placeholder; 0.20 in is a realistic thinner bore. Both lower the
# stock wheel rotational inertia and so shrink the wheels lever's improvement.
_STOCK_WHEEL_OZ_DEFAULT = 0.10        # the heavy stock wheel the WI-12 suite probes at
_STOCK_WHEEL_OZ_LIGHTER = 0.07        # spec-conformant lighter stock wheel (§1.1 nominal)
_R_INNER_DEFAULT_IN = 0.37            # PRD A4 default (placeholder) bore-wall radius
_R_INNER_THINNER_IN = 0.20            # PRD A4 tunable: a realistic thinner bore

# The WI-12 wheels recipe: lift one wheel (4→3 touching) AND lighten the wheels ~50%.
_LIGHTEN_FRACTION = 0.50

# ── The all-levers-worst baseline, mirroring the WI-12 helper exactly, with the stock
# wheel mass and bore radius parameterized so the lever ordering can be probed along the
# wheel-inertia axis (not just the heavy-wheel / wide-bore calibration point). ──
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
    here so the lever ordering can be measured along the spec-conformant wheel-inertia
    axis (PRD A4 R_inner placeholder; spec §1.1 nominal m_w).
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
# WI12-ADV-002 — at a spec-conformant lighter stock wheel (m_w = 0.07 oz; §1.1
# nominal, not a floor), the aero body swap must still buy a STRICTLY SMALLER
# race_time_s improvement than the wheels lever. Direct repro #1: FAILS on the
# current engine (aero ≈ 0.068078 s ≥ wheels ≈ 0.059836 s).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_002_aero_stays_smaller_than_wheels_at_lighter_stock_wheel() -> None:
    """The smallest-lever invariant (AC-ED1) must hold for a spec-conformant lighter
    stock wheel, not only the heavy 0.10 oz wheel the WI-12 suite probes. At
    ``m_w = 0.07 oz`` the BLOCK→WEDGE aero improvement must remain strictly smaller than
    the 3-wheel + 50%-lighter-wheels improvement; otherwise the engine teaches that body
    shape outranks wheel choice (WI12-ADV-002 / AC-ED1)."""
    aero, wheels = _aero_and_wheels_improvements(
        stock_wheel_oz=_STOCK_WHEEL_OZ_LIGHTER,
        inner_radius_in=_R_INNER_DEFAULT_IN,
    )
    assert aero < wheels, (
        "aerodynamics must remain the smaller lever vs wheels at a spec-conformant "
        f"lighter stock wheel (m_w={_STOCK_WHEEL_OZ_LIGHTER} oz, §1.1 nominal): the "
        f"BLOCK->WEDGE body swap improved race_time_s by {aero:.6f}s but the 3-wheel + "
        f"lighter-wheels change only improved it by {wheels:.6f}s. The engine ranks body "
        f"shape at or above wheel choice, contradicting the taught priority order that "
        f"aero is the smallest lever (WI12-ADV-002 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-002 — at a spec-conformant thinner bore (R_inner = 0.20 in; PRD A4
# explicitly tunable placeholder), the aero body swap must still buy a STRICTLY
# SMALLER improvement than the wheels lever. Direct repro #2: FAILS on the current
# engine (aero ≈ 0.068004 s ≥ wheels ≈ 0.061786 s at default 0.09 oz wheels).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_002_aero_stays_smaller_than_wheels_at_thinner_bore() -> None:
    """The smallest-lever invariant (AC-ED1) must hold for a spec-conformant thinner
    bore. PRD A4 flags ``R_inner`` (default 0.37 in) as a tunable placeholder; at
    ``R_inner = 0.20 in`` (with default 0.09 oz stock wheels) the lower rotational
    inertia shrinks the wheels lever until the BLOCK→WEDGE aero improvement overtakes it.
    Aero must remain strictly the smaller lever (WI12-ADV-002 / AC-ED1)."""
    aero, wheels = _aero_and_wheels_improvements(
        stock_wheel_oz=0.09,
        inner_radius_in=_R_INNER_THINNER_IN,
    )
    assert aero < wheels, (
        "aerodynamics must remain the smaller lever vs wheels at a spec-conformant "
        f"thinner bore (R_inner={_R_INNER_THINNER_IN} in, PRD A4 tunable placeholder): "
        f"the BLOCK->WEDGE body swap improved race_time_s by {aero:.6f}s but the 3-wheel "
        f"+ lighter-wheels change only improved it by {wheels:.6f}s. The engine ranks "
        f"body shape at or above wheel choice, contradicting the taught priority order "
        f"that aero is the smallest lever (WI12-ADV-002 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-002 — the aero<wheels ordering must hold ACROSS the spec-conformant
# wheel-mass band, not just at the heavy calibration point. Asserts at several stock
# wheel masses so a fix cannot simply re-tune to pass one point and re-invert elsewhere.
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize(
    "stock_wheel_oz",
    [0.10, 0.09, 0.08, 0.07, 0.06],
)
def test_wi12_adv_002_aero_smaller_than_wheels_across_stock_wheel_band(
    stock_wheel_oz: float,
) -> None:
    """Across the spec-conformant stock wheel-mass band, optimizing the body must never
    out-buy optimizing the wheels. The wheels improvement shrinks as stock wheel inertia
    shrinks while the aero improvement is wheel-inertia-independent, so a heavy-wheel
    calibration leaves the ordering correct at 0.10 oz and inverted for lighter (still
    spec-conformant) stock wheels. Aero must stay the smaller lever across the band
    (WI12-ADV-002 / AC-ED1 / profile aero-is-minor)."""
    aero, wheels = _aero_and_wheels_improvements(
        stock_wheel_oz=stock_wheel_oz,
        inner_radius_in=_R_INNER_DEFAULT_IN,
    )
    assert aero < wheels, (
        f"at stock_wheel_oz={stock_wheel_oz} (spec-conformant) the aero body swap "
        f"improved race_time_s by {aero:.6f}s but the wheels change only by "
        f"{wheels:.6f}s — aero must be strictly the smaller lever across the whole "
        f"spec-conformant wheel-mass band, not only at the heavy calibration point "
        f"(WI12-ADV-002 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-002 — guard against a regression-masking re-tune: lightening the stock
# wheels must NOT let the (wheel-inertia-independent) aero improvement overtake the
# wheels lever. Encodes the root cause — aero is decoupled from wheel inertia while the
# wheels improvement shrinks with it — so the fix must keep the ordering as stock wheel
# inertia drops, not merely shift the crossover point.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_002_aero_does_not_overtake_wheels_as_stock_wheel_lightens() -> None:
    """As the stock wheel goes from the heavy calibration mass (0.10 oz) to a
    spec-conformant lighter one (0.07 oz), the wheels improvement shrinks (less
    rotational inertia to recover) while the aero improvement is essentially unchanged
    (it is decoupled from wheel inertia). The invariant the engine must preserve is that
    aero never overtakes wheels across this band: at the lighter stock wheel the aero
    improvement must still be strictly below the wheels improvement (WI12-ADV-002 /
    AC-ED1)."""
    aero_heavy, wheels_heavy = _aero_and_wheels_improvements(
        stock_wheel_oz=_STOCK_WHEEL_OZ_DEFAULT,
        inner_radius_in=_R_INNER_DEFAULT_IN,
    )
    aero_light, wheels_light = _aero_and_wheels_improvements(
        stock_wheel_oz=_STOCK_WHEEL_OZ_LIGHTER,
        inner_radius_in=_R_INNER_DEFAULT_IN,
    )

    # Sanity on the mechanism: at the heavy stock wheel aero is already the smaller lever
    # (the only point the existing WI-12 suite checks), and lightening the stock wheel
    # shrinks the wheels improvement while leaving aero essentially unchanged.
    assert aero_heavy < wheels_heavy, (
        "precondition: at the heavy stock wheel (0.10 oz) the aero lever is already the "
        f"smaller one (aero={aero_heavy:.6f}s, wheels={wheels_heavy:.6f}s)"
    )
    assert wheels_light < wheels_heavy, (
        "the wheels improvement must shrink as the stock wheel lightens (less rotational "
        f"inertia to recover): wheels(0.10oz)={wheels_heavy:.6f}s, "
        f"wheels(0.07oz)={wheels_light:.6f}s"
    )

    # The defect: at the lighter conformant stock wheel aero overtakes the shrinking
    # wheels lever. The engine must keep aero strictly the smaller lever there.
    assert aero_light < wheels_light, (
        "lightening the stock wheel within the spec-conformant band must NOT let the "
        f"aero lever overtake the wheels lever: at m_w={_STOCK_WHEEL_OZ_LIGHTER} oz aero "
        f"improved race_time_s by {aero_light:.6f}s vs wheels' {wheels_light:.6f}s. The "
        f"wheel-inertia-decoupled drag calibration inverts the taught priority order for "
        f"any caller with lighter stock wheels (WI12-ADV-002 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-002 — determinism: the inversion measurement is reproducible for a fixed
# dt + seed (gate: deterministic, seeded — not a flaky finding).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_002_measurement_is_deterministic() -> None:
    """Re-measuring the aero and wheels improvements at the lighter stock wheel with the
    same fixed ``dt`` and ``seed`` must yield bit-identical numbers — the finding is a
    stable invariant violation, not RNG noise (gate: deterministic)."""
    first = _aero_and_wheels_improvements(
        stock_wheel_oz=_STOCK_WHEEL_OZ_LIGHTER, inner_radius_in=_R_INNER_DEFAULT_IN
    )
    second = _aero_and_wheels_improvements(
        stock_wheel_oz=_STOCK_WHEEL_OZ_LIGHTER, inner_radius_in=_R_INNER_DEFAULT_IN
    )
    assert first == second, (
        "the aero/wheels improvement measurement must be deterministic for a fixed "
        f"dt+seed; got {first} then {second}"
    )
