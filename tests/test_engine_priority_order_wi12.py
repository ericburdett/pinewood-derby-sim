"""WI-12 — Educational priority-order invariant (AC-ED1).

The simulator's whole reason to exist is teaching the *right priority order* of derby
build techniques. AC-ED1 (PRD §6 l.169; assumption A6; profile "Constraints" /
"Domain & glossary") pins that order as a behavioral invariant of the engine:

  Starting from an *all-levers-worst* baseline car, optimize each lever category
  individually (all else held at the baseline) and measure the ``race_time_s``
  improvement each single-lever-category change buys. Then:

    * the **weight + placement** improvement is the **LARGEST** single-lever-category
      improvement, and
    * the **aerodynamic-body** improvement is the **SMALLEST**, and
    * **friction** is a dominant lever — its improvement is strictly larger than the
      aerodynamic improvement (per A6, friction is "the biggest lever after weight").

Per A6 only the TOP (weight+placement dominant) and BOTTOM (aero smallest) of the
ordering, plus friction-dominant-over-aero, are asserted; the *exact* relative order
among the middle levers (wheels / alignment) is deliberately NOT over-constrained, so a
faithful re-tuning of the middle levers cannot make this suite flap.

Behavior-driven, against the PUBLIC contract (``simulate`` + frozen ``RaceResult``)
only — never engine internals. Imports live inside each test body so a missing/renamed
symbol fails *that* test independently rather than aborting whole-file collection.

Integrity / determinism: every run fixes ``dt = 1e-3`` and ``seed = 0`` (no clock /
network / unseeded RNG). The lever endpoints are spec-anchored — the legal weight cap
(5.0 oz) and a forward-but-stable placement for "worst" weight+placement; the WEDGE
(C_d 0.20) vs wood-BLOCK (C_d 0.85) body presets for aero (physics-spec §3.1); the
polished+graphite (μ 0.10) vs unprepared (μ 0.35) axle presets for friction
(physics-spec §3.2); 4 heavy vs 3 light wheels for the wheel lever (physics-spec
§2.1/§2.2); STRAIGHT vs RAIL_RIDER for alignment (physics-spec §3.3). The baseline and
every single-lever-optimized variant must be FINISHED so ``race_time_s`` is comparable
(AC-ED1's stated precondition). This file is NEW; it modifies, skips, or deletes no
existing test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult

# ── Spec-anchored lever endpoints (physics-spec §2/§3; PRD §6). Pinned here so the
# comparison references the documented contract, not the engine's private constants. ──
_LEGAL_WEIGHT_LIMIT_OZ = 5.0          # BSA cap — the "best" (heaviest legal) weight
_CD_WEDGE = 0.20                      # streamlined wedge body (best aero)
_CD_BLOCK = 0.85                      # blunt wood-block body (worst aero)
_MU_POLISHED_GRAPHITE = 0.10          # polished + graphite axles (best friction)
_MU_UNPREPARED = 0.35                 # unprepared / no-lube axles (worst friction)

# ── The all-levers-worst baseline (every lever set to its poor end, yet still a
# FINISHED, stable, legal-mass run so race_time_s exists and is comparable). Each
# single-lever-category variant below changes exactly ONE category off this baseline. ──
_BASE = dict(
    mass_oz=4.0,                 # under the cap (weight headroom to optimize toward 5.0)
    com_ahead_of_rear_axle_in=1.0,   # forward-but-stable placement (room to shift rearward)
    count_touching=4,            # all four wheels touching (most rotational inertia)
    wheel_oz=0.10,               # heavy stock wheels (most rotational inertia)
    drag_coefficient=_CD_BLOCK,  # blunt block body (worst aero)
    friction_coefficient=_MU_UNPREPARED,  # unprepared axles (worst friction)
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
    wheelbase_in: float = 4.375,
    outer_radius_in: float = 0.595,
    inner_radius_in: float = 0.37,
    axle_radius_in: float = 0.045,
    frontal_area: float = 0.0028,
) -> CarDesign:
    """Build a valid CarDesign from plain numbers via the value objects.

    Mirrors the construction helper in the sibling WI test files so the baseline and
    every variant are built identically and differ only in the named field(s).
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


def _time(**overrides: object) -> RaceResult:
    """Simulate the baseline car with the given single-lever-category overrides.

    ``dt`` and ``seed`` are fixed so the whole comparison is deterministic.
    """
    from pinewood_derby.engine import simulate

    params = dict(_BASE)
    params.update(overrides)
    return simulate(_make_car(**params), dt=1e-3, seed=0)  # type: ignore[arg-type]


def _finished(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.FINISHED


# The five single-lever-category optimizations applied to the all-levers-worst baseline.
# Each maps to a category name and the field overrides that optimize *only* that category.
_OPTIMIZATIONS: dict[str, dict[str, object]] = {
    # Weight + placement: go to the legal cap AND shift the COM rearward into the
    # optimal zone (one combined category per AC-ED1 / spec §1.1 + §4).
    "weight+placement": {
        "mass_oz": _LEGAL_WEIGHT_LIMIT_OZ,
        "com_ahead_of_rear_axle_in": 0.85,
    },
    # Wheels: lift one wheel (4 -> 3 touching) and lighten the wheels (~50%), lowering
    # rotational inertia (spec §2.1/§2.2).
    "wheels": {"count_touching": 3, "wheel_oz": 0.05},
    # Aerodynamics: swap the blunt block body for the streamlined wedge (spec §3.1).
    "aero": {"drag_coefficient": _CD_WEDGE},
    # Friction: polished + graphite axles in place of unprepared ones (spec §3.2).
    "friction": {"friction_coefficient": _MU_POLISHED_GRAPHITE},
    # Alignment: a rail-rider instead of a ping-ponging straight car (spec §3.3).
    "alignment": {"alignment": "RAIL_RIDER"},
}


def _improvements() -> dict[str, float]:
    """``race_time_s`` improvement (baseline_time - variant_time) per lever category.

    Asserts the baseline and every single-lever variant FINISH (AC-ED1 precondition:
    race_time_s must exist and be comparable), then returns the per-category time
    saved. A positive improvement means the optimization made the car faster.
    """
    baseline = _time()
    assert _finished(baseline), (
        "the all-levers-worst baseline must FINISH so its race_time_s is a comparable "
        f"reference; got outcome={baseline.outcome}"
    )
    assert baseline.race_time_s is not None
    base_t = baseline.race_time_s

    improvements: dict[str, float] = {}
    for category, overrides in _OPTIMIZATIONS.items():
        variant = _time(**overrides)
        assert _finished(variant), (
            f"the '{category}'-optimized variant must FINISH so its race_time_s is "
            f"comparable to the baseline; got outcome={variant.outcome}"
        )
        assert variant.race_time_s is not None
        # Every single-lever optimization must make the car at least as fast as the
        # worst baseline — none of these documented "better build" moves may hurt.
        assert variant.race_time_s <= base_t, (
            f"optimizing '{category}' must not make the car slower than the "
            f"all-levers-worst baseline: variant={variant.race_time_s:.6f}s vs "
            f"baseline={base_t:.6f}s"
        )
        improvements[category] = base_t - variant.race_time_s
    return improvements


# ───────────────────────────────────────────────────────────────────────────── #
# AC-ED1 — weight + placement is the LARGEST single-lever-category improvement.
# ───────────────────────────────────────────────────────────────────────────── #
def test_aced1_weight_placement_is_the_largest_single_lever_improvement() -> None:
    """From the all-levers-worst baseline, optimizing weight + placement must buy the
    biggest ``race_time_s`` improvement of any single lever category — the dominant
    lever the simulator is meant to teach first (spec §1.1/§4; PRD A6)."""
    improvements = _improvements()
    wp = improvements["weight+placement"]
    others = {k: v for k, v in improvements.items() if k != "weight+placement"}
    for category, value in others.items():
        assert wp > value, (
            "weight+placement must be the LARGEST single-lever improvement, but "
            f"'{category}' improved race_time_s by {value:.6f}s vs weight+placement's "
            f"{wp:.6f}s — the engine's lever ordering contradicts the taught priority "
            f"(AC-ED1)"
        )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-ED1 — the aerodynamic-body improvement is the SMALLEST.
# ───────────────────────────────────────────────────────────────────────────── #
def test_aced1_aero_is_the_smallest_single_lever_improvement() -> None:
    """The aerodynamic body change must buy the *smallest* improvement of any single
    lever category. Aero is minor at derby speeds by design (profile: "Keep this
    appropriately small so kids learn the real priority order"); if optimizing the body
    shape beats any other lever, the engine teaches the wrong priority order (AC-ED1)."""
    improvements = _improvements()
    aero = improvements["aero"]
    others = {k: v for k, v in improvements.items() if k != "aero"}
    for category, value in others.items():
        assert aero < value, (
            "aerodynamics must be the SMALLEST single-lever improvement, but the aero "
            f"body change improved race_time_s by {aero:.6f}s — at least as much as "
            f"'{category}' ({value:.6f}s). Aero is overweighted relative to the real "
            f"derby priority order (AC-ED1 / profile aero-is-minor constraint)"
        )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-ED1 — friction is a dominant lever: strictly larger improvement than aero.
# ───────────────────────────────────────────────────────────────────────────── #
def test_aced1_friction_improvement_strictly_exceeds_aero() -> None:
    """Per A6 friction is "the biggest lever after weight" — its single-lever
    improvement must strictly exceed the aerodynamic one. Polished + graphite axles
    must matter more than body streamlining (spec §3.2 vs §3.1; AC-ED1)."""
    improvements = _improvements()
    friction = improvements["friction"]
    aero = improvements["aero"]
    assert friction > aero, (
        f"friction (a dominant lever) improved race_time_s by {friction:.6f}s but must "
        f"strictly exceed the aero improvement ({aero:.6f}s); the engine ranks aero at "
        f"or above friction, contradicting the taught priority order (AC-ED1)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-ED1 — determinism: the whole priority-order comparison is reproducible.
# (Fixed dt + seed ⇒ identical improvements across repeated runs.)
# ───────────────────────────────────────────────────────────────────────────── #
def test_aced1_priority_order_comparison_is_deterministic() -> None:
    """Re-running the entire baseline-vs-variants comparison with the same fixed
    ``dt`` and ``seed`` must yield bit-identical improvements — the ordering claim is a
    stable invariant, not a flaky one (gate: deterministic, seeded)."""
    first = _improvements()
    second = _improvements()
    assert first == second, (
        f"the priority-order comparison must be deterministic for a fixed dt+seed; got "
        f"{first} then {second}"
    )
