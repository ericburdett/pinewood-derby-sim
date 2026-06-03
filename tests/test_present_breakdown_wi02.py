"""WI02-PRESENT-BREAKDOWN — RED tests for the "Where did your speed go?" ranked
energy breakdown of ``pinewood_derby.present`` (PRD AC-X1, A8; TRD §4).

This work item fills in ``RaceView.breakdown`` — the ranked ``LossBar`` chart that
turns the engine's raw energy ledger into a kid-facing "where did your speed go?"
story. Scope (the five acceptance criteria for WI02):

- **AC-X1 mapping (A8):** for a FINISHED run, the breakdown maps the engine ledger to
  ``LossBar``s — ``w_drag``→``"air"``, ``w_axle``→``"axle"``, ``w_rail``→``"rails"``,
  ``ke_rotational_final``→``"wheels"``, and the final **linear** KE
  (``ke_linear_final``)→``"kept"`` (the "speed you kept" bar, ``is_kept=True``). Each
  bar carries a plain-language ``label`` (no jargon).
- **Normalization (TRD §4):** bars are proportions of the energy **actually delivered
  on the run** — the integrated gravity work ``w_gravity`` (which the per-force ledger
  closes against), **not** ``pe_initial`` — so the proportions sum to ~1.0 for **both**
  a finisher *and* a stalled car. The divisor is pinned to ``w_gravity`` by exact
  equality (``field / w_gravity``); see ``test_normalization_denominator_is_exactly_w_gravity``
  for why a sum-to-1 check alone cannot tell ``w_gravity`` from ``pe_initial`` on the
  ``STANDARD_TRACK`` (the engine reports them equal there).
- **Ranking (AC-X1):** the bars are ordered **largest proportion first**.
- **Tip guard (TRD §4):** a ``tipped`` run has an **all-zero ledger** (``w_gravity ==
  0``); the breakdown emits **no bars** at all — its story is the wobble headline, not
  a loss chart — which also guards the normalization against divide-by-zero.
- **Coverage (PRD NFR):** these tests are driven by **real ``simulate()`` output**
  across multiple designs and contribute to the ≥ 90% ``present.py`` coverage bar.

The view-model contract (``present``/``RaceView``/``LossBar``) already exists from
WI01, so imports here are top-level; the breakdown *population* is what does not exist
yet (WI01 sets ``breakdown=()`` everywhere) — that is the true RED these tests assert.

All tests are deterministic: a single fixed seed, no clock / network / unseeded RNG.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest

from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
from pinewood_derby.engine import simulate
from pinewood_derby.present import LossBar, present
from pinewood_derby.result import Outcome
from pinewood_derby.track import STANDARD_TRACK
from pinewood_derby.units import Length, Mass

if TYPE_CHECKING:
    from pinewood_derby.result import RaceResult

# The fixed seed the UI pins so a design's time/breakdown is reproducible (PRD A6).
FIXED_SEED = 0

# The five expected breakdown keys (PRD A8). Four are losses, one ("kept") is the
# "speed you kept" bar.
EXPECTED_KEYS = {"air", "axle", "rails", "wheels", "kept"}

# The engine ledger field each key is derived from (PRD A8 / TRD §4). Used to assert
# the mapping is exact, not merely "five bars with the right names".
KEY_TO_LEDGER_FIELD = {
    "air": "w_drag",
    "axle": "w_axle",
    "rails": "w_rail",
    "wheels": "ke_rotational_final",
    "kept": "ke_linear_final",
}

# Jargon that must never appear in a kid-facing bar label (PRD AC-X3). Scoped to the
# terms a breakdown label could plausibly leak; the broader AC-X3 scan lives elsewhere.
BANNED_LABEL_TOKENS = (
    "joule",
    "newton",
    "coefficient",
    "m/s",
    "moment of inertia",
    "normal force",
    "kinetic",
    "rotational",
    "w_drag",
    "w_axle",
    "w_rail",
    "ke_",
    "μ",
    "c_d",
)


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — build real value objects and run the *real* engine. No hand-built
# RaceResult fixtures (PRD NFR / TRD §12): the breakdown must hold against genuine
# simulate() ledgers, not a fabricated one that happens to sum to 1.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_wheels(*, count_touching: int = 4) -> Wheels:
    return Wheels(
        count_touching=count_touching,
        wheel_mass=Mass.from_ounces(0.09),
        outer_radius=Length.from_inches(0.595),
        inner_radius=Length.from_inches(0.37),
        axle_radius=Length.from_inches(0.045),
    )


def _make_car(
    *,
    mass_oz: float = 5.0,
    com_ahead_of_rear_axle_in: float = 0.85,
    friction_coefficient: float = 0.20,
    drag_coefficient: float = 0.30,
    alignment: str = "STRAIGHT",
) -> CarDesign:
    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(4.375),
        wheels=_make_wheels(),
        body=BodyShape(drag_coefficient=drag_coefficient, frontal_area=0.0028),
        axle=Axle(friction_coefficient=friction_coefficient),
        alignment=Alignment[alignment],
    )


def _simulate(car: CarDesign) -> RaceResult:
    return simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)


def _finished_car() -> CarDesign:
    """A well-built car that finishes (verified: outcome FINISHED, full ledger)."""
    return _make_car()


def _stalled_car() -> CarDesign:
    """A *stable* (d_COM in the optimal zone) but over-frictioned car that runs down
    the ramp, clears the descent, and **stops short** on the flat — a real multi-point
    ``stalled`` DNF whose ledger still closes against ``w_gravity`` (verified empirically:
    mu=5.0 → last_position ≈ 4.24 m, 0 < pos < track_length ≈ 12.80 m, w_gravity ≈ 2.15 J,
    final linear KE ≈ 0).

    NOT the unstable-d_COM tip path (d_COM stays at 0.85 in, well above the cliff) and
    NOT a no-progress at-rest stall (which would have an all-zero ledger like a tip);
    this car genuinely runs part of the track before stopping (RAIL_RIDER ⇒ RNG-free).
    Its breakdown bars therefore still close to ~1.0 against w_gravity (TRD §4)."""
    return _make_car(friction_coefficient=5.0, alignment="RAIL_RIDER")


def _tipped_car() -> CarDesign:
    """An unstable car (d_COM = 0.5 in < the 0.625 in stability cliff) the engine rules
    a DNF **before the run** — single at-rest trajectory point and an all-zero ledger
    (``w_gravity == 0``). Its breakdown must be empty (TRD §4)."""
    return _make_car(com_ahead_of_rear_axle_in=0.15)


def _track_length_m() -> float:
    return STANDARD_TRACK.ramp_length.m + STANDARD_TRACK.flat_length.m


def _bars_by_key(bars: tuple[LossBar, ...]) -> dict[str, LossBar]:
    return {bar.key: bar for bar in bars}


# ───────────────────────────────────────────────────────────────────────────── #
# Sanity guards — confirm each design really is the engine outcome it claims, so a
# later engine change can never silently turn (e.g.) the "stalled" fixture into a
# finisher and hollow out these tests. These pin the test inputs, not the SUT.
# ───────────────────────────────────────────────────────────────────────────── #
def test_fixture_finished_car_is_a_real_finisher_with_a_full_ledger() -> None:
    r = _simulate(_finished_car())
    assert r.outcome is Outcome.FINISHED
    e = r.energy
    assert e.w_gravity > 0.0
    assert e.w_drag > 0.0 and e.w_axle > 0.0 and e.w_rail > 0.0
    assert e.ke_rotational_final > 0.0 and e.ke_linear_final > 0.0


def test_fixture_stalled_car_runs_and_stops_short_with_a_closing_ledger() -> None:
    r = _simulate(_stalled_car())
    assert r.outcome is Outcome.DNF
    assert len(r.trajectory) > 1, "a stalled car has a real multi-point trajectory"
    last = r.trajectory[-1].position
    assert 0.0 < last < _track_length_m(), "stops short, between start and finish"
    assert r.energy.w_gravity > 0.0, "descended part of the ramp, so gravity did work"


def test_fixture_tipped_car_has_single_point_and_all_zero_ledger() -> None:
    r = _simulate(_tipped_car())
    assert r.outcome is Outcome.DNF
    assert len(r.trajectory) == 1 and r.trajectory[0].position == 0.0
    e = r.energy
    assert e.w_gravity == 0.0
    assert e.w_drag == 0.0 and e.w_axle == 0.0 and e.w_rail == 0.0
    assert e.ke_rotational_final == 0.0 and e.ke_linear_final == 0.0


# ───────────────────────────────────────────────────────────────────────────── #
# AC-X1 / A8 — Mapping: the FINISHED breakdown maps the ledger to the five LossBars
# with the documented keys, including "kept" for the final linear KE.
# ───────────────────────────────────────────────────────────────────────────── #
def test_finished_breakdown_has_exactly_the_five_documented_keys() -> None:
    """A finisher emits exactly the five A8 bars — air, axle, rails, wheels, kept."""
    view = present(_simulate(_finished_car()), _finished_car())
    keys = {bar.key for bar in view.breakdown}
    assert keys == EXPECTED_KEYS, f"breakdown keys {keys} != {EXPECTED_KEYS}"
    assert len(view.breakdown) == 5, "exactly one bar per ledger channel, no dupes"


def test_finished_breakdown_keys_map_to_their_ledger_fields() -> None:
    """Each bar's proportion derives from its mapped ledger field (A8): the relative
    ordering of the raw ledger values must match the relative ordering of the bars'
    proportions, proving the wiring ``w_drag→air`` / ``w_axle→axle`` / ``w_rail→rails``
    / ``ke_rotational_final→wheels`` / ``ke_linear_final→kept`` — not a shuffle."""
    result = _simulate(_finished_car())
    view = present(result, _finished_car())
    bars = _bars_by_key(view.breakdown)
    energy = result.energy
    for key, field in KEY_TO_LEDGER_FIELD.items():
        assert key in bars, f"missing bar for key {key!r}"
        raw = getattr(energy, field)
        # proportion is raw / w_gravity; assert that exact relationship.
        expected = raw / energy.w_gravity
        assert bars[key].proportion == pytest.approx(expected, abs=1e-9), (
            f"bar {key!r} should be {field}/w_gravity = {expected:.6f}, "
            f"got {bars[key].proportion:.6f}"
        )


def test_finished_kept_bar_is_linear_ke_and_flagged_is_kept() -> None:
    """The "speed you kept" bar is the final **linear** KE (ke_linear_final, NOT the
    rotational share) and is the only bar with ``is_kept=True``; the four loss bars are
    ``is_kept=False`` (PRD A8 / TRD §4)."""
    result = _simulate(_finished_car())
    view = present(result, _finished_car())
    bars = _bars_by_key(view.breakdown)
    assert "kept" in bars, "a finisher must produce a 'kept' (speed you kept) bar"
    kept = bars["kept"]
    assert kept.is_kept is True
    assert kept.proportion == pytest.approx(
        result.energy.ke_linear_final / result.energy.w_gravity, abs=1e-9
    )
    for key in ("air", "axle", "rails", "wheels"):
        assert bars[key].is_kept is False, f"loss bar {key!r} must not be is_kept"
    assert sum(1 for b in view.breakdown if b.is_kept) == 1, "exactly one kept bar"


def test_finished_each_bar_has_a_plain_language_label_without_jargon() -> None:
    """Every bar carries a non-empty plain-language label and no technical jargon /
    raw ledger field name leaks into it (PRD AC-X1 'plain-language label', AC-X3)."""
    view = present(_simulate(_finished_car()), _finished_car())
    assert len(view.breakdown) == 5, "a finisher must produce all five labelled bars"
    for bar in view.breakdown:
        assert isinstance(bar.label, str) and bar.label.strip(), (
            f"bar {bar.key!r} needs a non-empty plain-language label"
        )
        # The label must be human text, not the bar key echoed back (e.g. not "air").
        assert bar.label.strip().lower() != bar.key.lower(), (
            f"bar {bar.key!r} label {bar.label!r} is just the key, not plain language"
        )
        low = bar.label.lower()
        for token in BANNED_LABEL_TOKENS:
            assert token not in low, (
                f"bar {bar.key!r} label {bar.label!r} leaks jargon token {token!r}"
            )


# ───────────────────────────────────────────────────────────────────────────── #
# Normalization (TRD §4) — proportions are shares of w_gravity (energy delivered on
# THIS run), not pe_initial, so they sum to ~1.0 for BOTH a finisher and a stalled car.
# ───────────────────────────────────────────────────────────────────────────── #
def test_finished_breakdown_proportions_sum_to_one() -> None:
    """A finisher's five bars partition the delivered energy: they sum to ~1.0."""
    view = present(_simulate(_finished_car()), _finished_car())
    total = sum(bar.proportion for bar in view.breakdown)
    assert total == pytest.approx(1.0, abs=1e-6), f"finisher bars sum {total} != 1.0"


def test_stalled_breakdown_proportions_sum_to_one() -> None:
    """A stalled car descends only part of the ramp, so w_gravity < pe_initial.
    Because the bars normalize against **w_gravity** (not pe_initial), they STILL sum
    to ~1.0 — the key TRD §4 invariant that distinguishes the correct denominator."""
    view = present(_simulate(_stalled_car()), _stalled_car())
    assert len(view.breakdown) > 0, "a stalled car still gets a breakdown"
    total = sum(bar.proportion for bar in view.breakdown)
    assert total == pytest.approx(1.0, abs=1e-6), f"stalled bars sum {total} != 1.0"


def test_normalization_denominator_is_exactly_w_gravity() -> None:
    """Pin the denominator to ``w_gravity`` for a STALLED car (TRD §4). Each bar's
    proportion must equal its mapped ledger field divided by **``w_gravity``** exactly —
    not by ``pe_initial`` and not by the sum of the bars or any other quantity. This is
    the criterion's load-bearing wording ("integrated ``w_gravity``, not ``pe_initial``").

    *Note for the validate/sign-off phase:* on the ``STANDARD_TRACK`` the engine reports
    ``pe_initial == w_gravity`` for any car that clears the ramp's full vertical drop
    (``pe_initial`` is the fixed total geometric drop ``M·g·Δh_com``; a car either
    descends it fully or no-progress-stalls at position 0 with an all-zero ledger). So
    the two denominators are *numerically equal* here and a sum-to-1 check alone cannot
    tell them apart. Pinning each proportion to the **exact** ``field / w_gravity`` value
    is therefore the discriminating assertion: it fails if the code divides by any other
    quantity, and it is the only formulation that survives the engine's actual geometry.
    (The TRD §4 example "stalled ⇒ ``w_gravity < pe_initial``" does not arise on the
    standard track — flagged for the developer/PO; the *invariant* "divide by ``w_gravity``"
    still holds and is what is enforced here.)"""
    result = _simulate(_stalled_car())
    energy = result.energy
    assert energy.w_gravity > 0.0
    view = present(result, _stalled_car())
    bars = _bars_by_key(view.breakdown)
    assert set(bars) == EXPECTED_KEYS, "stalled car must still produce all five bars"
    for key, field in KEY_TO_LEDGER_FIELD.items():
        expected = getattr(energy, field) / energy.w_gravity
        assert bars[key].proportion == pytest.approx(expected, abs=1e-9), (
            f"stalled bar {key!r} = {bars[key].proportion:.6f} but {field}/w_gravity = "
            f"{expected:.6f}; the denominator must be w_gravity (TRD §4)"
        )
    total = sum(bar.proportion for bar in view.breakdown)
    assert total == pytest.approx(1.0, abs=1e-6)


def test_all_proportions_are_finite_nonnegative_fractions() -> None:
    """Every bar proportion is a finite number in [0, 1] (a share, never a raw Joule
    value and never negative or > 1) for both a finisher and a stalled car."""
    for car in (_finished_car(), _stalled_car()):
        view = present(_simulate(car), car)
        assert len(view.breakdown) > 0, "this run should produce breakdown bars"
        for bar in view.breakdown:
            assert math.isfinite(bar.proportion), f"{bar.key} proportion not finite"
            assert 0.0 <= bar.proportion <= 1.0 + 1e-9, (
                f"{bar.key} proportion {bar.proportion} outside [0, 1]"
            )


# ───────────────────────────────────────────────────────────────────────────── #
# Ranking (AC-X1) — the breakdown is ordered largest proportion first.
# ───────────────────────────────────────────────────────────────────────────── #
def test_finished_breakdown_is_ranked_largest_first() -> None:
    """The finisher's bars are in non-increasing proportion order (AC-X1)."""
    view = present(_simulate(_finished_car()), _finished_car())
    assert len(view.breakdown) == 5, "ranking is only meaningful once the bars exist"
    props = [bar.proportion for bar in view.breakdown]
    assert props == sorted(props, reverse=True), (
        f"breakdown not ranked largest-first: {[(b.key, round(b.proportion, 4)) for b in view.breakdown]}"
    )


def test_stalled_breakdown_is_ranked_largest_first() -> None:
    """Ranking holds for a stalled car too — and its dominant bar is a *loss*, not the
    (≈0) kept bar, so the ordering is genuinely exercised, not trivially sorted."""
    view = present(_simulate(_stalled_car()), _stalled_car())
    assert len(view.breakdown) > 0, "a stalled car still produces breakdown bars to rank"
    props = [bar.proportion for bar in view.breakdown]
    assert props == sorted(props, reverse=True), "stalled breakdown not ranked largest-first"
    # A stalled car kept ~no speed, so 'kept' must not lead the ranking.
    assert view.breakdown[0].key != "kept", "a stalled car did not keep its speed"


def test_ranking_reflects_the_actual_ledger_order() -> None:
    """The ranked bar order equals the order obtained by sorting the mapped ledger
    values directly — proving the rank is computed from the data, not hard-coded."""
    result = _simulate(_finished_car())
    view = present(result, _finished_car())
    energy = result.energy
    expected_order = [
        key
        for key, _ in sorted(
            KEY_TO_LEDGER_FIELD.items(),
            key=lambda kv: getattr(energy, kv[1]),
            reverse=True,
        )
    ]
    actual_order = [bar.key for bar in view.breakdown]
    assert actual_order == expected_order, (
        f"ranked order {actual_order} != ledger-sorted order {expected_order}"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# Tip guard (TRD §4) — an all-zero-ledger tip (w_gravity == 0) emits NO bars; this
# also guards the normalization against divide-by-zero.
# ───────────────────────────────────────────────────────────────────────────── #
def test_tipped_run_emits_no_breakdown_bars() -> None:
    """A tipped run (all-zero ledger, w_gravity == 0) has an EMPTY breakdown — its
    story is the wobble headline, not a loss chart (TRD §4). Asserted alongside the
    finisher getting five bars so this is a deliberate exclusion, not the WI01 state
    where *no* run yet produces bars."""
    result = _simulate(_tipped_car())
    assert result.energy.w_gravity == 0.0, "fixture must be the all-zero-ledger tip"
    tipped_view = present(result, _tipped_car())
    assert tipped_view.breakdown == (), "a tipped run must emit no breakdown bars"
    # Contrast: a finisher on the same code path DOES get the five bars, proving the
    # empty breakdown above is the guard firing, not breakdown being unimplemented.
    finished_view = present(_simulate(_finished_car()), _finished_car())
    assert len(finished_view.breakdown) == 5


def test_tip_does_not_raise_zero_division() -> None:
    """Building the view for the all-zero-ledger tip must not raise (the w_gravity == 0
    denominator is guarded, not divided into) (TRD §4 'guarding against divide-by-zero')."""
    try:
        view = present(_simulate(_tipped_car()), _tipped_car())
    except ZeroDivisionError as exc:  # pragma: no cover - the failure we guard against
        pytest.fail(f"tipped run raised ZeroDivisionError instead of guarding it: {exc}")
    assert view.breakdown == ()


# ───────────────────────────────────────────────────────────────────────────── #
# Determinism (PRD A6 / NFR) — the breakdown is a stable function of the seeded design.
# ───────────────────────────────────────────────────────────────────────────── #
def test_breakdown_is_deterministic_across_repeated_calls() -> None:
    """Same seeded design ⇒ an identical breakdown tuple (keys, labels, proportions,
    order) across repeated present(simulate(...)) calls."""
    car = _finished_car()
    v1 = present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car)
    v2 = present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car)
    assert len(v1.breakdown) == 5, "determinism is over a real, populated breakdown"
    assert v1.breakdown == v2.breakdown
