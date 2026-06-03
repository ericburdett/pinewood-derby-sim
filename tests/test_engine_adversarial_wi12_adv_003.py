"""WI12-ADV-003 — the weight+placement-vs-friction priority order inverts for any
heavier-but-still-legal all-levers-worst baseline (domain-correctness, high).

AC-ED1 (PRD §6 l.169; assumption A6; profile "Constraints" / "Domain & glossary")
pins weight + placement as the *largest* single-lever-category improvement: "weight &
placement are the dominant levers ... matching the spec's documented teaching
priorities." The engine must teach that weight + placement outranks every other lever,
friction included, from any reasonable all-levers-worst starting car.

The existing WI-12 suite only probes this at a baseline mass of **4.0 oz** — a brittle,
cherry-picked point. The weight+placement improvement is dominated by *mass headroom*
(going from the baseline mass up to the 5.0 oz legal cap), so its magnitude COLLAPSES as
the baseline mass rises toward the cap, while the friction (μ 0.35 → 0.10) improvement is
roughly mass-independent. The crossover sits at baseline ≈ 4.07 oz: at 4.0 oz
weight+placement (barely) wins, but for any baseline in ≈ 4.1–5.0 oz — a wide, fully
legal, all-other-levers-worst car — friction's ``race_time_s`` improvement STRICTLY
exceeds weight+placement's. A child whose starting car is already, say, 4.25 oz would be
taught that polishing axles matters more than weight & placement, inverting the very
priority order the simulator exists to teach (profile: teaching wrong physics is "the
worst possible bug").

Repro (mirrors the WI-12 helper exactly, all-levers-worst baseline EXCEPT the baseline
mass: com 1.0 in, 4 wheels @ 0.10 oz, C_d 0.85, μ 0.35, STRAIGHT, frontal_area 0.0028,
dt 1e-3, seed 0):
  * baseline mass 4.25 oz: baseline ≈ 4.135953 s; weight+placement improvement
    (→ 5.0 oz, com 0.85 in) ≈ 0.304599 s; friction improvement (→ μ 0.10) ≈ 0.373931 s
    → friction (0.373931) > weight+placement (0.304599): AC-ED1 inverted.

The fix is in the ENGINE (the weight/placement coupling must keep weight+placement the
dominant lever across the legal mass band — e.g. placement's contribution must not be so
small that the lever's whole magnitude rides on mass headroom that vanishes near the
cap), NOT in the tests.

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

# ── Spec-anchored lever endpoints (physics-spec §1.1/§3.2/§4; PRD §6). ────────────
_LEGAL_WEIGHT_LIMIT_OZ = 5.0          # BSA cap — the "best" (heaviest legal) weight
_MU_POLISHED_GRAPHITE = 0.10          # polished + graphite axles (best friction)
_MU_UNPREPARED = 0.35                 # unprepared / no-lube axles (worst friction)

# The WI-12 weight+placement recipe: go to the legal cap AND shift the COM rearward into
# the optimal zone. Probed across the whole optimal placement band so a fix cannot pass
# by re-tuning one placement endpoint (the finding holds for com 0.75 / 0.85 / 1.0).
_WP_OPTIMAL_COM_IN = (0.75, 0.85, 1.0)

# ── The all-levers-worst baseline, mirroring the WI-12 helper exactly, with the baseline
# MASS parameterized so the weight+placement-vs-friction ordering can be probed across the
# legal mass band (not only the cherry-picked 4.0 oz calibration point). ──
_BASE = dict(
    com_ahead_of_rear_axle_in=1.0,   # forward-but-stable placement (room to shift rearward)
    count_touching=4,                # all four wheels touching (most rotational inertia)
    wheel_oz=0.10,                   # heavy stock wheels (most rotational inertia)
    drag_coefficient=0.85,           # blunt block body (worst aero)
    friction_coefficient=_MU_UNPREPARED,  # unprepared axles (worst friction)
    alignment="STRAIGHT",            # ping-ponging off the rail (worst alignment)
    frontal_area=0.0028,             # PRD A5 documented default (≈1.75"×2.5")
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
    in the named field(s).
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


def _time(*, baseline_mass_oz: float, **overrides: object) -> RaceResult:
    """Simulate the baseline at a given baseline mass with single-lever overrides.

    ``mass_oz`` defaults to the baseline mass (so the baseline and the friction variant
    share the same mass); the weight+placement override supplies the legal-cap mass.
    ``dt`` and ``seed`` are fixed so the comparison is deterministic.
    """
    from pinewood_derby.engine import simulate

    params = dict(_BASE)
    params["mass_oz"] = baseline_mass_oz
    params.update(overrides)
    return simulate(_make_car(**params), dt=1e-3, seed=0)  # type: ignore[arg-type]


def _finished(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.FINISHED


def _wp_and_friction_improvements(
    *, baseline_mass_oz: float, wp_com_in: float
) -> tuple[float, float]:
    """Return ``(weight_placement_improvement, friction_improvement)`` in seconds at this
    baseline mass. weight+placement = go to the 5.0 oz legal cap AND shift the COM to
    ``wp_com_in`` (optimal zone); friction = polished+graphite axles (μ 0.10). Both off
    the same all-levers-worst baseline (the WI-12 recipe).

    Asserts the baseline and both variants FINISH (AC-ED1 precondition) so the
    ``race_time_s`` comparison is meaningful.
    """
    baseline = _time(baseline_mass_oz=baseline_mass_oz)
    assert _finished(baseline), (
        "the all-levers-worst baseline must FINISH so its race_time_s is a comparable "
        f"reference at baseline_mass_oz={baseline_mass_oz}; got outcome={baseline.outcome}"
    )
    assert baseline.race_time_s is not None
    base_t = baseline.race_time_s

    weight_placement = _time(
        baseline_mass_oz=baseline_mass_oz,
        mass_oz=_LEGAL_WEIGHT_LIMIT_OZ,
        com_ahead_of_rear_axle_in=wp_com_in,
    )
    friction = _time(
        baseline_mass_oz=baseline_mass_oz,
        friction_coefficient=_MU_POLISHED_GRAPHITE,
    )
    assert _finished(weight_placement), (
        "the weight+placement-optimized variant must FINISH; got "
        f"outcome={weight_placement.outcome}"
    )
    assert _finished(friction), (
        f"the friction-optimized variant must FINISH; got outcome={friction.outcome}"
    )
    assert weight_placement.race_time_s is not None
    assert friction.race_time_s is not None
    return base_t - weight_placement.race_time_s, base_t - friction.race_time_s


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-003 — at the exact finding repro (baseline 4.25 oz, com 0.85 in), the
# weight+placement lever must remain STRICTLY LARGER than the friction lever.
# Direct repro: FAILS on the current engine (wp ≈ 0.304599 s, friction ≈ 0.373931 s).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_003_weight_placement_beats_friction_at_4_25oz_baseline() -> None:
    """The largest-lever invariant (AC-ED1) must hold for a heavier-but-still-legal
    all-levers-worst baseline, not only the 4.0 oz point the WI-12 suite probes. At a
    baseline mass of 4.25 oz the weight+placement improvement (→ 5.0 oz cap, COM 0.85 in)
    must remain STRICTLY LARGER than the friction improvement (μ 0.35 → 0.10); otherwise a
    child whose car is already 4.25 oz is taught that polishing axles outranks weight &
    placement, inverting the taught priority order (WI12-ADV-003 / AC-ED1)."""
    wp, friction = _wp_and_friction_improvements(
        baseline_mass_oz=4.25, wp_com_in=0.85
    )
    assert wp > friction, (
        "weight+placement must remain the LARGER lever vs friction for a heavier-but-"
        "still-legal all-levers-worst baseline (4.25 oz): going to the 5.0 oz cap + "
        f"COM 0.85 in improved race_time_s by {wp:.6f}s but polishing axles improved it "
        f"by {friction:.6f}s. The engine ranks friction above weight+placement, "
        f"contradicting the taught priority order that weight & placement is the dominant "
        f"lever (WI12-ADV-003 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-003 — the ordering must hold for EVERY optimal placement endpoint at the
# heavier baseline, so a fix cannot pass by re-tuning one COM value. The finding holds
# for com 0.75 / 0.85 / 1.0 in (the whole optimal-zone band, spec §4.2).
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("wp_com_in", _WP_OPTIMAL_COM_IN)
def test_wi12_adv_003_weight_placement_beats_friction_across_optimal_com(
    wp_com_in: float,
) -> None:
    """At the 4.25 oz baseline, weight+placement must out-buy friction for every optimal
    placement endpoint (COM 0.75 / 0.85 / 1.0 in). The lever's collapse near the legal cap
    is driven by vanishing mass headroom, not the placement choice, so no single COM value
    rescues the ordering — the engine must keep weight+placement dominant across the band
    (WI12-ADV-003 / AC-ED1)."""
    wp, friction = _wp_and_friction_improvements(
        baseline_mass_oz=4.25, wp_com_in=wp_com_in
    )
    assert wp > friction, (
        f"at the 4.25 oz baseline with weight+placement COM={wp_com_in} in, "
        f"weight+placement improved race_time_s by {wp:.6f}s but friction improved it by "
        f"{friction:.6f}s — weight+placement must stay strictly the larger lever across "
        f"the optimal placement band (WI12-ADV-003 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-003 — the ordering must hold ACROSS the heavier-but-legal baseline-mass
# band, not just at one point. Asserts at several baseline masses in 4.1–5.0 oz so a fix
# cannot simply nudge the crossover and re-invert elsewhere.
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("baseline_mass_oz", [4.1, 4.25, 4.5, 4.75, 5.0])
def test_wi12_adv_003_weight_placement_beats_friction_across_legal_mass_band(
    baseline_mass_oz: float,
) -> None:
    """Across the heavier-but-still-legal baseline-mass band (4.1–5.0 oz), optimizing
    weight + placement must never be out-bought by optimizing friction. The
    weight+placement improvement shrinks as the baseline mass approaches the legal cap
    (vanishing mass headroom) while the friction improvement is roughly mass-independent,
    so a 4.0 oz calibration leaves the ordering correct at 4.0 oz and inverted for any
    heavier legal baseline. weight+placement must stay strictly the larger lever across
    the whole legal mass band (WI12-ADV-003 / AC-ED1 / profile weight-is-dominant)."""
    wp, friction = _wp_and_friction_improvements(
        baseline_mass_oz=baseline_mass_oz, wp_com_in=0.85
    )
    assert wp > friction, (
        f"at baseline_mass_oz={baseline_mass_oz} (fully legal) the weight+placement lever "
        f"improved race_time_s by {wp:.6f}s but friction improved it by {friction:.6f}s — "
        f"weight+placement must be strictly the larger lever across the whole legal "
        f"baseline-mass band, not only at the 4.0 oz calibration point "
        f"(WI12-ADV-003 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-003 — guard against a regression-masking re-tune: raising the baseline mass
# toward the legal cap must NOT let the (roughly mass-independent) friction improvement
# overtake the weight+placement lever. Encodes the root cause — weight+placement's
# magnitude rides on mass headroom that vanishes near the cap while friction does not — so
# the fix must keep the ordering as the baseline mass rises, not merely shift the
# crossover point past 4.25 oz.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_003_friction_does_not_overtake_weight_placement_as_baseline_heavier() -> None:
    """As the all-levers-worst baseline goes from the calibration mass (4.0 oz) toward a
    heavier-but-still-legal one (4.25 oz), the weight+placement improvement shrinks (less
    mass headroom to recover before the 5.0 oz cap) while the friction improvement is
    essentially unchanged (it is decoupled from baseline mass). The invariant the engine
    must preserve is that friction never overtakes weight+placement across this band: at
    the heavier baseline the friction improvement must still be strictly below the
    weight+placement improvement (WI12-ADV-003 / AC-ED1)."""
    wp_light, fr_light = _wp_and_friction_improvements(
        baseline_mass_oz=4.0, wp_com_in=0.85
    )
    wp_heavy, fr_heavy = _wp_and_friction_improvements(
        baseline_mass_oz=4.25, wp_com_in=0.85
    )

    # Sanity on the mechanism: at the light calibration baseline weight+placement is
    # already the larger lever (the point the existing WI-12 suite checks), and raising
    # the baseline mass shrinks the weight+placement improvement while leaving friction
    # essentially unchanged.
    assert wp_light > fr_light, (
        "precondition: at the calibration baseline (4.0 oz) weight+placement is already "
        f"the larger lever (wp={wp_light:.6f}s, friction={fr_light:.6f}s)"
    )
    assert wp_heavy < wp_light, (
        "the weight+placement improvement must shrink as the baseline mass rises toward "
        f"the legal cap (less headroom to recover): wp(4.0oz)={wp_light:.6f}s, "
        f"wp(4.25oz)={wp_heavy:.6f}s"
    )

    # The defect: at the heavier legal baseline friction overtakes the shrinking
    # weight+placement lever. The engine must keep weight+placement strictly the larger
    # lever there.
    assert wp_heavy > fr_heavy, (
        "raising the all-levers-worst baseline mass within the legal band must NOT let "
        f"the friction lever overtake weight+placement: at baseline 4.25 oz "
        f"weight+placement improved race_time_s by {wp_heavy:.6f}s vs friction's "
        f"{fr_heavy:.6f}s. The mass-headroom-dependent weight+placement coupling inverts "
        f"the taught priority order for any caller whose starting car is already heavier "
        f"(WI12-ADV-003 / AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI12-ADV-003 — determinism: the inversion measurement is reproducible for a fixed
# dt + seed (gate: deterministic, seeded — not a flaky finding).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi12_adv_003_measurement_is_deterministic() -> None:
    """Re-measuring the weight+placement and friction improvements at the heavier baseline
    with the same fixed ``dt`` and ``seed`` must yield bit-identical numbers — the finding
    is a stable invariant violation, not RNG noise (gate: deterministic)."""
    first = _wp_and_friction_improvements(baseline_mass_oz=4.25, wp_com_in=0.85)
    second = _wp_and_friction_improvements(baseline_mass_oz=4.25, wp_com_in=0.85)
    assert first == second, (
        "the weight+placement/friction improvement measurement must be deterministic for "
        f"a fixed dt+seed; got {first} then {second}"
    )
