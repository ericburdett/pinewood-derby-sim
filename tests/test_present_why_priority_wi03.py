"""WI03-PRESENT-WHY-PRIORITY — RED tests for the dominant-factor ``why`` and the
priority-ordered ``tips`` of ``pinewood_derby.present`` (PRD AC-X2, AC-X4; TRD §4/§12).

This work item fills in two ``RaceView`` fields WI01 left empty (``why=""``, ``tips=()``):

- **``why`` (PRD AC-X2; TRD §4):** for a finished/stalled run with a real breakdown, the
  ``why`` names the **dominant factor for this run** — the **largest *loss* bar, excluding
  the "kept" bar** — in plain language, and ties it to a **real building principle** via a
  small reviewed, table-driven lookup:
    * ``axle``  → polish the axles & add graphite
    * ``rails`` → fix the alignment / rail-ride
    * ``air``   → smoother / lower body
    * ``wheels``→ lighter, truer wheels
  plus **weight/placement coaching** driven by ``legal_weight`` and
  ``car.com_ahead_of_rear_axle`` (e.g. an over-limit car is told to trim to the legal cap;
  a forward COM is told to shift weight toward the rear axle).

- **``tips`` (PRD AC-X4; rides engine AC-ED1):** 1–3 next-step suggestions ordered by the
  engine's **real priority order** (weight/placement & friction dominate; aerodynamics is
  smallest). Across sample designs the surfaced ranking / ``why`` must **never invert** the
  engine ordering — aero is **never** advised over weight or friction (TRD §11/§12 priority-
  order domain test).

Why these tests are RED now
---------------------------
``present``/``RaceView`` already exist (WI01) and the breakdown is populated (WI02), but
``why`` and ``tips`` are still the WI01 placeholders (``""`` / ``()``) on every path. These
tests assert the *populated, principle-tied, priority-ordered* behavior that does not exist
yet — so they fail **for the right reason** (an empty ``why`` / empty ``tips`` / wrong
content, not an import or fixture error).

Determinism (gate): every run fixes ``dt = 1e-3`` and ``seed = FIXED_SEED``; STRAIGHT-
aligned fixtures still seed the engine, so the comparison is reproducible. No clock /
network / unseeded RNG.

All physics comes from the **real** ``simulate()`` — no hand-built ``RaceResult`` fixtures
(TRD §12), so the ``why``/``tips`` are exercised against genuine ledgers and the engine's
own priority ordering, never a fabricated one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
from pinewood_derby.engine import simulate
from pinewood_derby.present import (
    _TIP_DIALED_IN,
    _WHY_DIALED_IN,
    _optimal_levers,
    present,
)
from pinewood_derby.result import Outcome
from pinewood_derby.track import STANDARD_TRACK
from pinewood_derby.units import Length, Mass

if TYPE_CHECKING:
    from pinewood_derby.present import RaceView
    from pinewood_derby.result import RaceResult

# The fixed seed the UI pins so a design's time / why / tips is reproducible (PRD A6).
FIXED_SEED = 0

# The legal weight cap (BSA standard, profile / PRD AC-C3); over this is "over-limit".
_LEGAL_WEIGHT_LIMIT_OZ = 5.0

# Jargon that must never appear in kid-facing ``why`` / ``tips`` text (PRD AC-X3). The
# broad AC-X3 scan lives elsewhere; this is the slice a coaching string could plausibly leak.
BANNED_TOKENS = (
    "joule",
    "newton",
    "coefficient",
    "m/s",
    "moment of inertia",
    "normal force",
    "kinetic energy",
    "rotational inertia",
    "w_drag",
    "w_axle",
    "w_rail",
    "ke_",
    "μ",
    "c_d",
    "proportion",
)

# Plain-language tokens that anchor each dominant-loss key to its real building principle
# (PRD AC-X2 lookup table; TRD §4). The ``why`` for a run whose dominant loss is ``key``
# must mention at least one of these — the principle, not just the bar name.
PRINCIPLE_TOKENS: dict[str, tuple[str, ...]] = {
    "axle": ("polish", "graphite"),
    "rails": ("align", "rail", "straight"),
    "air": ("smooth", "lower", "shape", "wedge", "air"),
    "wheels": ("wheel", "light", "true"),
}

# Tokens that mark a tip as advising the *weight/placement* or *friction* lever — the
# dominant levers that may never be out-ranked by an aero tip (PRD AC-X4 / AC-ED1).
WEIGHT_TOKENS = ("weight", "heavier", "rear", "back", "place", "cap", "limit", "trim")
FRICTION_TOKENS = ("polish", "graphite", "axle", "align", "rail", "friction")
# Tokens that mark a tip as advising the *aerodynamic* lever — the smallest lever.
AERO_TOKENS = ("air", "smooth", "wedge", "body shape", "streamline", "aero")


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — build real value objects and run the *real* engine (TRD §12). No hand-
# built RaceResult fixtures: the why/tips must hold against genuine simulate() ledgers
# and the engine's own priority ordering.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_wheels(
    *,
    count_touching: int = 4,
    wheel_oz: float = 0.09,
    outer_in: float = 0.595,
    inner_in: float = 0.37,
) -> Wheels:
    return Wheels(
        count_touching=count_touching,
        wheel_mass=Mass.from_ounces(wheel_oz),
        outer_radius=Length.from_inches(outer_in),
        inner_radius=Length.from_inches(inner_in),
        axle_radius=Length.from_inches(0.045),
    )


def _make_car(
    *,
    mass_oz: float = 5.0,
    com_ahead_of_rear_axle_in: float = 0.85,
    friction_coefficient: float = 0.20,
    drag_coefficient: float = 0.30,
    frontal_area: float = 0.0028,
    alignment: str = "STRAIGHT",
    count_touching: int = 4,
    wheel_oz: float = 0.09,
    outer_in: float = 0.595,
    inner_in: float = 0.37,
) -> CarDesign:
    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(4.375),
        wheels=_make_wheels(
            count_touching=count_touching,
            wheel_oz=wheel_oz,
            outer_in=outer_in,
            inner_in=inner_in,
        ),
        body=BodyShape(drag_coefficient=drag_coefficient, frontal_area=frontal_area),
        axle=Axle(friction_coefficient=friction_coefficient),
        alignment=Alignment[alignment],
    )


def _simulate(car: CarDesign) -> RaceResult:
    return simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)


def _present(car: CarDesign) -> RaceView:
    return present(_simulate(car), car)


def _dominant_loss_key(view: RaceView) -> str:
    """The key of the largest *loss* bar (excluding the 'kept' bar) — what the ``why``
    must name (TRD §4). Mirrors the engine truth, computed from the populated breakdown."""
    losses = [bar for bar in view.breakdown if not bar.is_kept]
    assert losses, "this run has no loss bars to be dominant over"
    return max(losses, key=lambda bar: bar.proportion).key


# ── Fixtures, each pinned to the dominant-loss key it is meant to surface. ──────── #
def _rails_dominant_car() -> CarDesign:
    """A STRAIGHT-aligned car ping-ponging off the rail: ``rails`` is the largest loss
    (verified: rails ≈ 0.24 leads). Tests the ``rails`` → fix-alignment principle."""
    return _make_car(alignment="STRAIGHT", friction_coefficient=0.10, drag_coefficient=0.20)


def _axle_dominant_car() -> CarDesign:
    """A RAIL_RIDER (tiny constant rail loss) with **unprepared** axles (μ=0.35): ``axle``
    is the largest loss (verified: axle ≈ 0.21 leads rails ≈ 0.19). Tests ``axle`` →
    polish & graphite. RAIL_RIDER ⇒ RNG-free, so deterministic without the seed mattering."""
    return _make_car(alignment="RAIL_RIDER", friction_coefficient=0.35, drag_coefficient=0.20)


def _wheels_dominant_car() -> CarDesign:
    """A RAIL_RIDER with **heavy, large** wheels (high rotational inertia) and otherwise
    slick prep: ``wheels`` is the largest loss (verified: wheels ≈ 0.23 leads rails ≈ 0.19).
    Tests ``wheels`` → lighter, truer wheels."""
    return _make_car(
        alignment="RAIL_RIDER",
        friction_coefficient=0.02,
        drag_coefficient=0.20,
        wheel_oz=0.5,
        outer_in=1.0,
        inner_in=0.99,
    )


def _overlimit_car() -> CarDesign:
    """A heavy (7.0 oz > 5.0 oz cap) but still-finishing car: ``legal_weight is False``
    (verified). Drives the weight/placement coaching path (trim to the legal cap)."""
    return _make_car(mass_oz=7.0)


def _forward_com_legal_car() -> CarDesign:
    """A legal car with its COM well **forward** (0.85 in ahead of the rear axle, far from
    the rear). Drives the placement coaching (shift weight toward the rear axle)."""
    return _make_car(mass_oz=5.0, com_ahead_of_rear_axle_in=0.85)


def _all_text(view: RaceView) -> list[str]:
    """Every kid-facing coaching string on the view (the ``why`` plus each tip)."""
    return [view.why, *view.tips]


# ───────────────────────────────────────────────────────────────────────────── #
# Sanity guards — confirm each fixture really is the engine outcome / dominant-loss it
# claims, so a later engine change can't silently hollow these tests out. These pin the
# TEST INPUTS, not the SUT (the ``why``/``tips`` themselves).
# ───────────────────────────────────────────────────────────────────────────── #
def test_fixture_rails_car_finishes_with_rails_the_dominant_loss() -> None:
    view = _present(_rails_dominant_car())
    assert _simulate(_rails_dominant_car()).outcome is Outcome.FINISHED
    assert _dominant_loss_key(view) == "rails", "fixture must surface rails as top loss"


def test_fixture_axle_car_finishes_with_axle_the_dominant_loss() -> None:
    view = _present(_axle_dominant_car())
    assert _simulate(_axle_dominant_car()).outcome is Outcome.FINISHED
    assert _dominant_loss_key(view) == "axle", "fixture must surface axle as top loss"


def test_fixture_wheels_car_finishes_with_wheels_the_dominant_loss() -> None:
    view = _present(_wheels_dominant_car())
    assert _simulate(_wheels_dominant_car()).outcome is Outcome.FINISHED
    assert _dominant_loss_key(view) == "wheels", "fixture must surface wheels as top loss"


def test_fixture_overlimit_car_is_illegal_weight_but_finishes() -> None:
    r = _simulate(_overlimit_car())
    assert r.outcome is Outcome.FINISHED
    assert r.legal_weight is False, "fixture must be an over-limit (illegal-weight) car"


# ───────────────────────────────────────────────────────────────────────────── #
# AC-X2 — ``why`` names the dominant factor in plain language and ties it to a real
# building principle via the reviewed, table-driven lookup.
# ───────────────────────────────────────────────────────────────────────────── #
def test_why_is_a_nonempty_plain_language_string_for_a_finisher() -> None:
    """A finisher with a real breakdown must surface a non-empty ``why`` — the WI01
    placeholder ``why=""`` is the RED state this asserts against (PRD AC-X2)."""
    view = _present(_rails_dominant_car())
    assert isinstance(view.why, str)
    assert view.why.strip(), "a finisher's 'why' must not be the empty WI01 placeholder"


@pytest.mark.parametrize(
    ("car_factory", "key"),
    [
        (_rails_dominant_car, "rails"),
        (_axle_dominant_car, "axle"),
        (_wheels_dominant_car, "wheels"),
    ],
)
def test_why_ties_dominant_loss_to_its_real_building_principle(
    car_factory: object, key: str
) -> None:
    """For each dominant-loss key the ``why`` must mention the **real building principle**
    from the reviewed lookup table (PRD AC-X2; TRD §4): ``axle`` → polish/graphite,
    ``rails`` → fix alignment / rail-ride, ``wheels`` → lighter/truer wheels. Asserting the
    *principle* tokens (not just the bar key echoed back) proves the table-driven tie, not a
    label restatement."""
    view = _present(car_factory())  # type: ignore[operator]
    assert _dominant_loss_key(view) == key, "fixture precondition: this key must dominate"
    low = view.why.lower()
    expected = PRINCIPLE_TOKENS[key]
    assert any(tok in low for tok in expected), (
        f"dominant loss {key!r}: 'why' {view.why!r} must tie to its real principle "
        f"(one of {expected}), not merely name the bar"
    )


def test_why_for_overlimit_car_coaches_to_the_legal_weight_cap() -> None:
    """The weight/placement coaching driven by ``legal_weight`` (PRD AC-X2): an over-limit
    car's ``why`` (or a surfaced tip) must coach trimming toward the legal cap — weight
    coaching the lookup table feeds from ``legal_weight``, not just a loss bar."""
    view = _present(_overlimit_car())
    assert view.legal_weight is False, "fixture must be the over-limit car"
    text = " ".join(_all_text(view)).lower()
    assert any(tok in text for tok in ("limit", "cap", "5.0", "5 oz", "over", "trim", "lighter than")), (
        f"over-limit car must surface legal-cap weight coaching; got why={view.why!r} "
        f"tips={view.tips!r}"
    )


def test_why_contains_no_jargon() -> None:
    """No technical unit / term leaks into the ``why`` across the dominant-loss fixtures
    (PRD AC-X3, the slice a coaching string could leak)."""
    for car in (_rails_dominant_car(), _axle_dominant_car(), _wheels_dominant_car()):
        view = _present(car)
        low = view.why.lower()
        for token in BANNED_TOKENS:
            assert token not in low, f"'why' {view.why!r} leaks jargon token {token!r}"


# ───────────────────────────────────────────────────────────────────────────── #
# TRD §4 — the 'why' selects the largest LOSS bar (EXCLUDING the 'kept' bar) as the
# dominant factor, even when 'kept' is the single largest bar overall.
# ───────────────────────────────────────────────────────────────────────────── #
def test_why_selects_largest_loss_excluding_the_kept_bar() -> None:
    """A good finisher *keeps* most of its energy, so the ``kept`` bar is the single
    largest bar overall. The ``why`` must still name the largest **loss** (the dominant
    *factor*), never "speed you kept" — TRD §4's "exclude the kept bar" rule. The principle
    tokens of the dominant-loss key must appear; the kept bar's label must not be the
    subject."""
    car = _rails_dominant_car()
    view = _present(car)
    # Precondition: 'kept' really is the biggest bar overall (so the exclusion is exercised).
    biggest = max(view.breakdown, key=lambda bar: bar.proportion)
    assert biggest.is_kept, (
        "this fixture must keep most of its speed so 'kept' is the largest bar overall, "
        "making the exclude-kept rule load-bearing"
    )
    dom = _dominant_loss_key(view)
    low = view.why.lower()
    assert any(tok in low for tok in PRINCIPLE_TOKENS[dom]), (
        f"'why' {view.why!r} must name the dominant LOSS {dom!r}, not the kept bar"
    )
    # And the why must not be framed around keeping speed (the kept bar is not a 'factor').
    assert "speed you kept" not in low, "'why' must target a loss, not the kept bar"


def test_why_tracks_the_dominant_loss_across_designs() -> None:
    """Across designs with *different* dominant losses, the ``why``'s principle follows the
    dominant loss bar — proving the selection is data-driven (the largest loss), not a
    hard-coded message. axle-dominant ⇒ polish/graphite; wheels-dominant ⇒ wheel coaching;
    and the two must differ."""
    axle_view = _present(_axle_dominant_car())
    wheels_view = _present(_wheels_dominant_car())
    assert _dominant_loss_key(axle_view) == "axle"
    assert _dominant_loss_key(wheels_view) == "wheels"
    assert any(t in axle_view.why.lower() for t in PRINCIPLE_TOKENS["axle"]), (
        f"axle-dominant 'why' {axle_view.why!r} must coach axle prep"
    )
    assert any(t in wheels_view.why.lower() for t in PRINCIPLE_TOKENS["wheels"]), (
        f"wheels-dominant 'why' {wheels_view.why!r} must coach wheels"
    )
    assert axle_view.why != wheels_view.why, (
        "different dominant losses must yield different 'why' messages (data-driven, "
        "not a single hard-coded string)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-X4 — ``tips`` holds 1–3 priority-ordered next-step suggestions; aero is never
# advised over weight/friction.
# ───────────────────────────────────────────────────────────────────────────── #
def test_tips_are_one_to_three_nonempty_suggestions() -> None:
    """``tips`` holds **1–3** non-empty next-step strings (PRD AC-X4 / TRD §4) — the WI01
    placeholder ``tips=()`` is the RED state this asserts against."""
    view = _present(_rails_dominant_car())
    assert 1 <= len(view.tips) <= 3, f"tips must be 1–3 suggestions, got {len(view.tips)}"
    for tip in view.tips:
        assert isinstance(tip, str) and tip.strip(), "each tip must be a non-empty string"


def test_tips_contain_no_jargon() -> None:
    """No jargon leaks into any tip across the fixtures (PRD AC-X3)."""
    for car in (_rails_dominant_car(), _axle_dominant_car(), _wheels_dominant_car(), _overlimit_car()):
        view = _present(car)
        for tip in view.tips:
            low = tip.lower()
            for token in BANNED_TOKENS:
                assert token not in low, f"tip {tip!r} leaks jargon token {token!r}"


def test_tips_never_advise_aero_above_weight_or_friction() -> None:
    """The load-bearing AC-X4 invariant: a tip advising **aerodynamics** must never be
    ranked **above** a tip advising **weight/placement** or **friction** (the dominant
    levers). If any tip mentions aero, no *later* tip may be the first weight/friction tip —
    i.e. the first aero tip cannot precede the first weight/friction tip. Checked across a
    matrix of sample designs so the ordering can't invert on any one of them."""
    cars = [
        _make_car(),
        _rails_dominant_car(),
        _axle_dominant_car(),
        _wheels_dominant_car(),
        _overlimit_car(),
        _forward_com_legal_car(),
        _make_car(drag_coefficient=0.85),  # blunt block body (most aero-relevant)
    ]
    for car in cars:
        view = _present(car)
        first_aero = None
        first_wf = None
        for i, tip in enumerate(view.tips):
            low = tip.lower()
            is_aero = any(t in low for t in AERO_TOKENS)
            is_wf = any(t in low for t in WEIGHT_TOKENS + FRICTION_TOKENS)
            # A weight/friction tip takes precedence in classification over an aero token,
            # since a single tip should advise one lever; but if a tip somehow reads as both
            # we treat it as weight/friction (the dominant lever) and do not count it as aero.
            if is_wf:
                if first_wf is None:
                    first_wf = i
            elif is_aero:
                if first_aero is None:
                    first_aero = i
        if first_aero is not None and first_wf is not None:
            assert first_wf < first_aero, (
                f"priority order inverted: an aero tip (#{first_aero}) precedes the first "
                f"weight/friction tip (#{first_wf}) for tips={view.tips!r} — aero must "
                f"never out-rank weight/friction (AC-X4 / AC-ED1)"
            )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-X4 / TRD §12 — priority-order DOMAIN test: across a matrix of sample designs, the
# surfaced ranking / why never inverts the engine's real ordering (weight/placement &
# friction dominate, aero smallest). This is the WI's flagship invariant test.
# ───────────────────────────────────────────────────────────────────────────── #
def _matrix_designs() -> dict[str, CarDesign]:
    """A small matrix spanning each lever's good/bad end, all FINISHED & legal-mass so the
    surfaced story is comparable. Built from the *same* helper as the engine's own AC-ED1
    priority-order suite so the UI is checked against the very ordering the engine asserts."""
    return {
        "default": _make_car(),
        "unprepared_axle": _make_car(friction_coefficient=0.35, alignment="RAIL_RIDER"),
        "straight_align": _make_car(alignment="STRAIGHT"),
        "block_body": _make_car(drag_coefficient=0.85, alignment="RAIL_RIDER", friction_coefficient=0.10),
        "heavy_wheels": _make_car(alignment="RAIL_RIDER", friction_coefficient=0.10, wheel_oz=0.18),
        "light_legal": _make_car(mass_oz=3.0),
    }


def test_priority_order_air_is_never_the_dominant_surfaced_loss() -> None:
    """The flagship priority-order domain invariant (PRD AC-X4; TRD §12): across the design
    matrix, **aerodynamics is never the dominant surfaced loss** — its bar is never the
    largest loss and the ``why`` never coaches body-shape as the #1 fix. Aero is minor by
    design (profile / engine AC-ED1); surfacing it as the dominant factor would teach the
    wrong priority order. (For a finisher whose dominant loss is a real lever, the surfaced
    ``why`` must not be an aero-first message.)"""
    for name, car in _matrix_designs().items():
        view = _present(car)
        if not view.breakdown:
            continue  # a degenerate/empty breakdown has no ranking to invert
        dom = _dominant_loss_key(view)
        assert dom != "air", (
            f"design {name!r}: aerodynamics surfaced as the DOMINANT loss ({dom!r}) — the "
            f"UI inverted the engine's priority order (aero must be the smallest, AC-X4)"
        )
        # The 'why' must coach the dominant loss's principle — UNLESS that lever is already
        # optimal, in which case the state-aware coach correctly targets a still-fixable lever
        # instead of nagging the tuned one (it must never be empty either way).
        low = view.why.lower()
        assert low.strip(), f"design {name!r}: 'why' must not be empty"
        if dom in PRINCIPLE_TOKENS and dom not in _optimal_levers(car):
            assert any(t in low for t in PRINCIPLE_TOKENS[dom]), (
                f"design {name!r}: dominant loss {dom!r} (not yet optimal) but 'why' "
                f"{view.why!r} does not coach it — the surfaced 'why' must follow the engine "
                f"ordering"
            )


def test_priority_order_surfaced_loss_ranking_matches_ledger_ranking() -> None:
    """Across the matrix, the surfaced **loss ranking** (the order of the loss bars in the
    breakdown) must equal the order obtained by ranking the raw engine ledger losses — the
    UI must **never re-order** what the engine reports (PRD AC-X4 "never inverts it"; TRD
    §12). This pins the no-inversion contract to the engine's own numbers, not a hard-coded
    expectation."""
    field_for_key = {
        "air": "w_drag",
        "axle": "w_axle",
        "rails": "w_rail",
        "wheels": "ke_rotational_final",
    }
    for name, car in _matrix_designs().items():
        result = _simulate(car)
        view = present(result, car)
        if not view.breakdown:
            continue
        surfaced = [bar.key for bar in view.breakdown if not bar.is_kept]
        energy = result.energy
        expected = sorted(
            surfaced, key=lambda k: getattr(energy, field_for_key[k]), reverse=True
        )
        assert surfaced == expected, (
            f"design {name!r}: surfaced loss ranking {surfaced} != engine-ledger ranking "
            f"{expected} — the UI inverted the engine's loss order (AC-X4 / TRD §12)"
        )


def test_priority_order_results_are_deterministic() -> None:
    """The whole why/tips/ranking surface is a stable function of the seeded design (gate:
    deterministic). Re-presenting each matrix design yields identical why, tips, and
    breakdown — the priority-order claim is a reproducible invariant, not a flaky one."""
    for name, car in _matrix_designs().items():
        v1 = present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car)
        v2 = present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car)
        assert v1.why == v2.why, f"design {name!r}: 'why' not deterministic"
        assert v1.tips == v2.tips, f"design {name!r}: 'tips' not deterministic"
        assert v1.breakdown == v2.breakdown, f"design {name!r}: breakdown not deterministic"


# ───────────────────────────────────────────────────────────────────────────── #
# State-aware coaching: a fully-tuned finisher must not be nagged to "fix" levers it has
# already optimized (the real-user report) — it is celebrated and nudged to a new challenge.
# ───────────────────────────────────────────────────────────────────────────── #
def _dialed_in_car() -> CarDesign:
    """Every lever at its best: slick axles, light wheels, smooth wedge, rail-riding, weight
    at the cap — the build a kid reaches after optimizing every control."""
    return _make_car(
        mass_oz=5.0,
        com_ahead_of_rear_axle_in=0.85,
        friction_coefficient=0.10,
        drag_coefficient=0.20,
        alignment="RAIL_RIDER",
        wheel_oz=0.09,
    )


def test_fully_tuned_finisher_is_celebrated_not_nagged() -> None:
    car = _dialed_in_car()
    assert _simulate(car).outcome is Outcome.FINISHED, "fixture must be a finisher"
    assert _optimal_levers(car) == frozenset({"axle", "wheels", "air", "rails"}), (
        "fixture precondition: every loss lever must already be optimal"
    )
    view = _present(car)
    # No 'fix an already-optimal lever' prescription — the bug this guards against.
    assert view.why == _WHY_DIALED_IN, f"a dialed-in car must be celebrated, got {view.why!r}"
    assert view.tips == (_TIP_DIALED_IN,), f"a dialed-in car must not be nagged, got {view.tips!r}"
    joined = (view.why + " " + " ".join(view.tips)).lower()
    for token in BANNED_TOKENS:
        assert token not in joined, f"dialed-in coaching leaks jargon {token!r}"
