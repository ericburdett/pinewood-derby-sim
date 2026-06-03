"""WI03-PRESENT-WHY-PRIORITY — RED edge tests for the round-2 adversarial findings
WI03-ADV-R1-001 and WI03-ADV-R1-002 (both critical, domain-correctness, reproducible).

These cover ``pinewood_derby.present``'s ``why`` / ``tips`` (PRD AC-X2 / AC-X4) on two
non-finish paths the existing suite blessed wrong or left uncovered. All physics comes
from the **real** ``simulate()`` (no hand-built ``RaceResult`` fixtures, TRD §12); every
run pins ``dt = 1e-3`` and ``seed = FIXED_SEED`` so the assertions are deterministic.


WI03-ADV-R1-001 — the tipped "why"/tip coach the EXACT OPPOSITE physical fix
----------------------------------------------------------------------------
The engine rules a car unstable when its front-load fraction ``d_COM/L`` is **SMALL**
(the COM is too far **REARWARD**, so the front normal force collapses): the cliff is
``d_COM < 0.625 in`` on the standard 4.375 in wheelbase (``engine._COM_UNSTABLE_FRONT_FRACTION``;
physics-spec §4.2). Verified directly below:

    d_COM = 0.3 / 0.5 in  ⇒ DNF (tip)
    d_COM = 0.625 / 0.85 in ⇒ FINISHED

So the **correct fix is to move weight FORWARD** — *increasing* ``d_COM`` toward the
optimal zone. But ``present._WHY_TIPPED`` / the tipped tip currently tell the kid the
weight is "too far **forward** to stay stable" and to "move the weight **back** toward the
rear axle." Moving toward the rear axle **decreases** ``d_COM`` and makes the tip strictly
worse — the profile's worst-possible bug (teaching wrong physics). These tests assert the
**physically correct direction**: name the *rearward* COM and coach moving the weight
**forward**, never "too far forward" / "move it back."


WI03-ADV-R1-002 — a near-stationary STALLED legal car is falsely praised "ran clean"
------------------------------------------------------------------------------------
A light, legal, under-energised car (e.g. 1.0 oz, STRAIGHT, unprepared axle, block body)
creeps a few microns and stalls effectively at the start line: ``outcome=DNF``,
``finished=False``, but ``len(trajectory) > 1`` (so it is **not** the engine's pre-run
instability short-circuit — ``_is_tipped()`` is False). Its degenerate ledger
(``w_gravity ≈ 6e-7 J``) is correctly suppressed by ``_breakdown()`` to an empty tuple, so
``_dominant_loss_key`` is ``None``; the 1.0 oz car is ``legal_weight is True``; so ``_why``
falls through its final ``else`` to the **finisher praise**:

    "Your car ran clean — keep polishing your axles, lightening your wheels, and rolling
     straight to find a little more speed."

The car did **not** run (last position ≈ 0). It must not be **praised** ("ran clean") nor
handed friction/wheels red herrings; the real problem is that it is **too light /
under-energised** (PRD AC-X2 — name the dominant factor; profile: teaching wrong physics is
the worst possible bug). These tests assert that a stalled, never-really-moved car is told
the truth (it ran out of speed / needs more weight) instead of being congratulated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
from pinewood_derby.engine import simulate
from pinewood_derby.present import present
from pinewood_derby.result import Outcome
from pinewood_derby.track import STANDARD_TRACK
from pinewood_derby.units import Length, Mass

if TYPE_CHECKING:
    from pinewood_derby.present import RaceView
    from pinewood_derby.result import RaceResult

# The fixed seed the UI pins so a design's why / tips is reproducible (PRD A6).
FIXED_SEED = 0


# ── R1-001: direction of the tipped fix ─────────────────────────────────────── #
# The INVERTED (physically wrong) phrases the bug emits: tell the kid the weight is "too
# far forward" or to move it BACK / toward the rear axle. Moving weight rearward *lowers*
# d_COM and worsens the tip, so NONE of these may appear in a tipped car's coaching.
WRONG_DIRECTION_PHRASES = (
    "too far forward",
    "weight back",
    "move the weight back",
    "back toward the rear axle",
    "toward the rear axle",
    "toward the back",
    "to the back",
)
# At least one explicit FORWARD-direction phrase must appear — the real, correct fix
# (move weight forward / toward the front axle to raise d_COM above the cliff).
#
# NOTE on token choice: the bare substring "forward" is deliberately EXCLUDED — it is a
# substring of the buggy copy's "too far forward", so accepting it would let the inverted
# advice spuriously satisfy a forward-fix assertion. Each phrase here names the FRONT as
# the destination, which the inverted "move it back toward the rear axle" copy never does.
FORWARD_FIX_PHRASES = (
    "toward the front",
    "move it forward",
    "move the weight forward",
    "shift the weight forward",
    "weight forward",
    "front axle",
    "to the front",
    "closer to the front",
)

# ── R1-002: a stalled, never-really-moved legal car must not be praised ───────── #
# Phrases that, on a car that did NOT run, are actively misleading finisher praise.
MISLEADING_RAN_CLEAN_PHRASES = (
    "ran clean",
    "keep polishing",
    "find a little more speed",
)
# Plain-language tokens that name the REAL problem for an under-energised stall: the car
# ran out of speed / stopped short, and (being well under the cap) wants more weight.
STALL_TRUTH_TOKENS = (
    "ran out of speed",
    "stopped short",
    "stopped just short",
    "didn't make it",
    "did not make it",
    "out of speed",
    "more weight",
    "heavier",
    "add weight",
    "too light",
    "not enough speed",
    "ran out of energy",
)

# Jargon that must never appear in any kid-facing coaching string (PRD AC-X3).
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
    "stability cliff",
    "front-load fraction",
)


# ───────────────────────────────────────────────────────────────────────────── #
# Fixtures — real value objects, real engine (TRD §12).
# ───────────────────────────────────────────────────────────────────────────── #
def _wheels(*, count_touching: int = 4) -> Wheels:
    return Wheels(
        count_touching=count_touching,
        wheel_mass=Mass.from_ounces(0.09),
        outer_radius=Length.from_inches(0.595),
        inner_radius=Length.from_inches(0.37),
        axle_radius=Length.from_inches(0.045),
    )


def _car(
    *,
    mass_oz: float,
    com_in: float,
    mu: float = 0.20,
    cd: float = 0.30,
    alignment: str = "STRAIGHT",
) -> CarDesign:
    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_in),
        wheelbase=Length.from_inches(4.375),
        wheels=_wheels(),
        body=BodyShape(drag_coefficient=cd, frontal_area=0.0028),
        axle=Axle(friction_coefficient=mu),
        alignment=Alignment[alignment],
    )


def _tipped_car() -> CarDesign:
    """The R1-001 repro: COM too far REARWARD (0.3 in ⇒ d_COM/L ≈ 0.069 < cliff). The
    engine short-circuits it as unstable before the run (single at-rest point, all-zero
    ledger). The correct fix is to move weight FORWARD (raise d_COM)."""
    return _car(mass_oz=5.0, com_in=0.15)


def _forward_fixed_car() -> CarDesign:
    """Same car with the weight moved FORWARD (d_COM 0.3 → 0.85 in) — the real fix; it
    FINISHES. Used only to pin the engine truth of the fix direction, not the SUT."""
    return _car(mass_oz=5.0, com_in=0.85)


def _stalled_light_legal_car() -> CarDesign:
    """The R1-002 repro: a light (1.0 oz ≤ 5.0 oz, so LEGAL), high-friction, blunt car that
    creeps a few microns and stalls effectively at the line — a multi-point trajectory (so
    NOT a tip) with a degenerate near-zero ledger (so an empty breakdown)."""
    return _car(mass_oz=1.0, com_in=0.85, mu=0.35, cd=0.85)


def _simulate(car: CarDesign) -> RaceResult:
    return simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)


def _present(car: CarDesign) -> RaceView:
    return present(_simulate(car), car)


def _all_coaching_text(view: RaceView) -> list[str]:
    return [view.why, *view.tips]


# ───────────────────────────────────────────────────────────────────────────── #
# Sanity guards — confirm the fixtures reproduce the finding's engine state, pinning
# the TEST INPUTS (not the SUT). A later engine change that moved the cliff would trip
# these rather than silently hollow the edge tests.
# ───────────────────────────────────────────────────────────────────────────── #
def test_fixture_tipped_car_is_rearward_tip_and_forward_shift_finishes() -> None:
    """The engine truth behind R1-001: the 0.3 in (too-rearward COM) car tips (DNF, single
    at-rest point, all-zero ledger), and moving the SAME car's weight FORWARD to 0.85 in
    makes it FINISH — so the correct fix is forward, not back."""
    tipped = _simulate(_tipped_car())
    assert tipped.outcome is Outcome.DNF, "fixture must be a tip (DNF)"
    assert len(tipped.trajectory) == 1, "a tipped car never moves: one trajectory point"
    assert tipped.trajectory[0].position == 0.0
    assert tipped.energy.w_gravity == 0.0, "tipped: all-zero ledger"

    fixed = _simulate(_forward_fixed_car())
    assert fixed.outcome is Outcome.FINISHED, (
        "moving the weight FORWARD (d_COM 0.3 → 0.85 in) must FINISH — proving the correct "
        "fix direction is forward, not back (WI03-ADV-R1-001)"
    )


def test_fixture_stalled_light_legal_car_is_a_nonfinish_not_a_tip() -> None:
    """The engine truth behind R1-002: the light legal car is a DNF that did NOT tip —
    a multi-point trajectory (so ``_is_tipped`` is False) whose last position is at/near the
    start line, a degenerate near-zero ledger (so an empty breakdown), and ``legal_weight``
    True (so the over-limit branch does not catch it). Exactly the state under which
    ``_why`` wrongly falls through to the 'ran clean' praise."""
    r = _simulate(_stalled_light_legal_car())
    assert r.outcome is Outcome.DNF, "fixture must be a non-finish (DNF)"
    assert len(r.trajectory) > 1, (
        "the stall path must produce a multi-point trajectory (NOT the single-point tip "
        "short-circuit) so it reaches the buggy 'ran clean' fall-through"
    )
    assert r.trajectory[-1].position < 1.0, (
        "the car barely moved — it stalled effectively at the start line, not a real run"
    )
    assert r.legal_weight is True, (
        "the 1.0 oz car is legal — so the over-limit branch does not catch it and _why "
        "falls through to the 'ran clean' finisher default"
    )
    view = present(r, _stalled_light_legal_car())
    assert view.finished is False, "a stalled DNF must not be presented as finished"
    assert view.breakdown == (), (
        "the degenerate near-zero ledger must yield an empty breakdown (dominant loss None), "
        "so the bug is reached through the empty-breakdown legal path"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI03-ADV-R1-001 — the tipped fix must point FORWARD (the physically correct direction).
# ───────────────────────────────────────────────────────────────────────────── #
def test_tipped_why_does_not_give_the_inverted_backward_fix() -> None:
    """The ``why`` for a too-rearward tipped car must **never** say the weight is "too far
    forward" or coach moving it "back / toward the rear axle". That inverted advice lowers
    d_COM and makes the tip strictly worse — teaching wrong physics (WI03-ADV-R1-001;
    profile worst-possible bug)."""
    view = _present(_tipped_car())
    low = view.why.lower()
    for phrase in WRONG_DIRECTION_PHRASES:
        assert phrase not in low, (
            f"tipped 'why' {view.why!r} gives the INVERTED fix {phrase!r} — the car tips "
            "because its COM is too far BACK; the correct fix is to move weight FORWARD "
            "(WI03-ADV-R1-001)"
        )


def test_tipped_why_coaches_moving_weight_forward() -> None:
    """The ``why`` must coach the **real** fix: move the weight **forward** (toward the front
    axle, raising d_COM above the cliff). Verified that the same car FINISHES once the weight
    is forward (WI03-ADV-R1-001; PRD AC-X2)."""
    view = _present(_tipped_car())
    low = view.why.lower()
    assert any(phrase in low for phrase in FORWARD_FIX_PHRASES), (
        f"tipped 'why' {view.why!r} must coach moving the weight FORWARD (one of "
        f"{FORWARD_FIX_PHRASES}) — the correct fix for a too-rearward COM (WI03-ADV-R1-001)"
    )


def test_tipped_coaching_surface_nowhere_gives_the_inverted_fix() -> None:
    """The inverted "move it back" advice must not leak into any surfaced *tip* either —
    the whole coaching surface (``why`` + ``tips``) must be free of the wrong-direction
    phrases (WI03-ADV-R1-001)."""
    view = _present(_tipped_car())
    for text in _all_coaching_text(view):
        low = text.lower()
        for phrase in WRONG_DIRECTION_PHRASES:
            assert phrase not in low, (
                f"tipped coaching {text!r} gives the inverted fix {phrase!r} — correct fix "
                "is FORWARD (WI03-ADV-R1-001)"
            )


def test_tipped_top_tip_coaches_weight_forward() -> None:
    """Priority order (PRD AC-X4): a tipped car's #1 lever is weight placement, in the
    correct direction. The leading tip (or the ``why`` if it carries the fix) must coach
    moving the weight forward, not an axle/aero red herring and not the inverted back move."""
    view = _present(_tipped_car())
    leading = (view.tips[0] if view.tips else view.why).lower()
    assert any(phrase in leading for phrase in FORWARD_FIX_PHRASES), (
        f"the leading tipped coaching {leading!r} must foreground moving weight FORWARD "
        f"(one of {FORWARD_FIX_PHRASES}); got tips={view.tips!r} why={view.why!r}"
    )
    for phrase in WRONG_DIRECTION_PHRASES:
        assert phrase not in leading, (
            f"the leading tipped coaching {leading!r} gives the inverted fix {phrase!r}"
        )


def test_tipped_coaching_has_no_jargon_after_correction() -> None:
    """Whatever corrected (forward-direction) tipped coaching replaces the buggy copy must
    still leak no jargon (PRD AC-X3)."""
    view = _present(_tipped_car())
    for text in _all_coaching_text(view):
        low = text.lower()
        for token in BANNED_TOKENS:
            assert token not in low, f"tipped coaching {text!r} leaks jargon {token!r}"


# ───────────────────────────────────────────────────────────────────────────── #
# WI03-ADV-R1-002 — a stalled legal car (empty breakdown) must NOT be praised "ran clean".
# ───────────────────────────────────────────────────────────────────────────── #
def test_stalled_legal_car_why_does_not_falsely_praise_ran_clean() -> None:
    """A light legal car that creeps microns and stalls did **not** run; telling it "ran
    clean" and to "keep polishing your axles" is the finding's bug — praise plus the wrong
    fix for a car whose real problem is being under-energised. The ``why`` must contain none
    of the misleading praise phrases (WI03-ADV-R1-002; PRD AC-X2)."""
    view = _present(_stalled_light_legal_car())
    low = view.why.lower()
    for phrase in MISLEADING_RAN_CLEAN_PHRASES:
        assert phrase not in low, (
            f"a stalled legal car was told {phrase!r} in its 'why' {view.why!r} — it never "
            "really ran; this praises a non-run and prescribes the wrong fix (WI03-ADV-R1-002)"
        )


def test_stalled_legal_car_coaching_surface_nowhere_praises_ran_clean() -> None:
    """The misleading praise must not leak into a surfaced *tip* either — the whole coaching
    surface (``why`` + ``tips``) for the stalled legal car must be free of the 'ran clean'
    praise (WI03-ADV-R1-002)."""
    view = _present(_stalled_light_legal_car())
    for text in _all_coaching_text(view):
        low = text.lower()
        for phrase in MISLEADING_RAN_CLEAN_PHRASES:
            assert phrase not in low, (
                f"stalled legal car coaching {text!r} contains misleading praise {phrase!r} "
                "— it never really ran (WI03-ADV-R1-002)"
            )


def test_stalled_legal_car_why_names_the_real_under_energised_problem() -> None:
    """The ``why`` must name the **real** dominant factor for an under-energised stall: the
    car ran out of speed / stopped short and (being well under the 5.0 oz cap) wants more
    weight — not friction/wheels red herrings (WI03-ADV-R1-002; PRD AC-X2 — name the dominant
    factor in plain language tied to a real principle)."""
    view = _present(_stalled_light_legal_car())
    low = view.why.lower()
    assert any(tok in low for tok in STALL_TRUTH_TOKENS), (
        f"a stalled, under-energised legal car's 'why' {view.why!r} must name the real "
        f"problem (ran out of speed / needs more weight; one of {STALL_TRUTH_TOKENS}), not "
        "praise it or hand it a friction/wheels red herring (WI03-ADV-R1-002)"
    )


def test_stalled_legal_car_coaching_has_no_jargon() -> None:
    """The corrected stalled-car coaching must still leak no jargon (PRD AC-X3)."""
    view = _present(_stalled_light_legal_car())
    for text in _all_coaching_text(view):
        low = text.lower()
        for token in BANNED_TOKENS:
            assert token not in low, f"stalled coaching {text!r} leaks jargon {token!r}"


# ───────────────────────────────────────────────────────────────────────────── #
# Determinism (gate) — the corrected coaching must be a stable function of the seeded
# design for both fixtures.
# ───────────────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize("car_factory", [_tipped_car, _stalled_light_legal_car])
def test_coaching_is_deterministic(car_factory: object) -> None:
    """Re-presenting each fixture yields identical why and tips — the corrected coaching is
    reproducible, not flaky (gate: deterministic)."""
    car = car_factory()  # type: ignore[operator]
    v1 = present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car)
    v2 = present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car)
    assert v1.why == v2.why
    assert v1.tips == v2.tips
