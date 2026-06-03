"""WI03-ADV-P2-001 — RED edge tests: placement coaching must gate on the front-load
FRACTION ``d_COM/L``, never a RAW INCH threshold.

Confirmed adversarial finding (high, domain-correctness, reproducible)
----------------------------------------------------------------------
``present._tips()`` (and ``_why``'s placement branch) fire the rearward-shift placement
tip ``_TIP_PLACEMENT_FORWARD`` ("Move some weight toward the back, about an inch ahead
of the rear axle …") whenever ``car.com_ahead_of_rear_axle.inches >= 1.0`` — a **raw
inch** threshold. But the engine's placement advantage *and* its stability cliff are
governed by the **dimensionless fraction** ``d_COM/L`` (``engine._COM_UNSTABLE_FRONT_FRACTION
≈ 0.143``), exactly the distance-vs-fraction inversion the engine already remediated in
WI6-ADV-001. The raw-inch gate inverts on **non-standard wheelbases** (valid CarDesigns:
``car.py`` only requires ``wheelbase > 0`` and ``0 < d_COM < wheelbase``).

This produces the profile's **worst-possible bug — teaching wrong physics — in BOTH
directions**:

1. **Inverted (false) coaching.** A 5.0 oz STRAIGHT car with ``wheelbase=8.0 in`` and
   ``com=1.2 in`` has ``d_COM/L = 0.150`` — already strongly **REAR-biased** (the
   physically optimal direction) and only just above the cliff (``d_COM/L = 0.143``).
   The engine **FINISHES** this car, yet ``present`` tells the kid to "move some weight
   toward the back." Literally following that tip (``com ≈ 1.0 in`` → ``d_COM/L = 0.125``,
   **below** the cliff) makes ``simulate`` return ``Outcome.DNF`` — the advice converts a
   **finishing** car into a **tipping** one (verified live: 1.2 in FINISHED → 1.0 in DNF).
   Violates AC-X2 (placement "why"/tip tied to a real principle in the **correct
   direction**) and AC-X4 (the UI must **never invert** the engine's real priority order).

2. **Suppressed (missing) coaching, opposite direction.** A short-wheelbase nose-heavy
   finisher (``wheelbase=2.0 in``, ``com=0.85 in`` → ``d_COM/L = 0.425``, genuinely too
   far FORWARD) gets **no** rearward coaching at all, because ``0.85 < 1.0 in``. Yet here
   moving weight rearward is the real, correct improvement (verified live: this exact car
   speeds up 3.90 s → 3.29 s as ``com`` drops 0.85 → 0.40 in, staying above the cliff).

Both faults are the *same* root cause and the *same* fix: ``present`` must compute and gate
the placement coaching on the fraction ``car.com_ahead_of_rear_axle.m / car.wheelbase.m``,
not absolute inches. Standard 4.375 in wheelbase behaviour is unaffected (the existing
matrix tests only use the standard wheelbase, which is why this slipped through).

Scope of THESE tests (the boundary)
-----------------------------------
These assert only on the **coaching this WI owns** — the ``why`` and ``tips`` placement
strings (PRD AC-X2 / AC-X4) — and on the engine-truth invariant that following the
surfaced advice must not invert the engine's outcome. They do **not** assert on
``view.outcome`` / ``view.headline`` (the tipped/stalled classifier is a separate WI),
and they do **not** prescribe an implementation (no reference to private gating
constants) — only the observable, physically-correct behaviour.

Why RED now
-----------
``present`` exists and populates ``why`` / ``tips``, but the placement branch gates on raw
inches, so the inverted tip is surfaced for the long-wheelbase rear-biased finisher and the
correct rearward tip is withheld from the short-wheelbase nose-heavy finisher. These tests
assert the *corrected*, fraction-gated behaviour that does not exist yet — so they fail
**for the right reason** (wrong/missing placement coaching content, not an import or fixture
error).

Determinism (gate): every run fixes ``dt = 1e-3`` and ``seed = FIXED_SEED``; the STRAIGHT
fixtures still seed the engine, so each run is reproducible. No clock / network / unseeded
RNG. All physics comes from the **real** ``simulate()`` — no hand-built ``RaceResult``
fixtures (TRD §12).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
from pinewood_derby.engine import simulate
from pinewood_derby.present import present
from pinewood_derby.result import Outcome
from pinewood_derby.track import STANDARD_TRACK
from pinewood_derby.units import Length, Mass

if TYPE_CHECKING:
    from pinewood_derby.present import RaceView
    from pinewood_derby.result import RaceResult

# The fixed seed the UI pins so a design's time / why / tips is reproducible (PRD A6).
FIXED_SEED = 0

# Phrases that tell the kid to move weight REARWARD (toward the back / the rear axle). For a
# car that is *already* rear-biased (low d_COM/L, near the cliff) this is the inverted, wrong
# advice that can push it over the stability cliff (the finding's bug). Matched as lowercase
# substrings.
REARWARD_SHIFT_PHRASES = (
    "toward the back",
    "toward the rear axle",
    "to the back",
    "ahead of the rear axle",
    "weight back",
    "move it back",
)

# Jargon that must never reach the kid (PRD AC-X3) — the corrected, fraction-aware coaching
# must still be plain language and must not leak the engine's fraction/cliff terms.
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
    "fraction",
    "d_com",
    "stability cliff",
    "front-load",
    "wheelbase",
)


def _car(com_in: float, wheelbase_in: float, *, mass_oz: float = 5.0) -> CarDesign:
    """The finding's car family: a 5.0 oz STRAIGHT car parameterised by COM and
    wheelbase (both non-standard wheelbases are valid CarDesigns — ``car.py`` requires
    only ``wheelbase > 0`` and ``0 < d_COM < wheelbase``)."""
    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_in),
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
        alignment=Alignment.STRAIGHT,
    )


def _simulate(car: CarDesign) -> RaceResult:
    return simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)


def _present(car: CarDesign) -> RaceView:
    return present(_simulate(car), car)


def _all_coaching_text(view: RaceView) -> list[str]:
    """Every kid-facing placement-coaching surface — the ``why`` plus each ``tip``."""
    return [view.why, *view.tips]


# The finding's repro designs, by their physically meaningful fraction d_COM/L.
# Long wheelbase, REAR-biased finisher near the front-load collapse: d_COM/L = 0.075, just
# above the ~0.06 collapse fraction — it still FINISHES (tippy), so coaching it further back
# is unambiguously wrong (graded placement model).
_LONG_WB_REAR_BIASED = _car(com_in=0.6, wheelbase_in=8.0)
# A further-rearward shift on the same long-wheelbase car: d_COM/L = 0.05, BELOW the collapse
# fraction — the front load is gone and the engine then tips it (DNF).
_LONG_WB_FOLLOWED_ADVICE = _car(com_in=0.4, wheelbase_in=8.0)
# Short wheelbase, genuinely NOSE-heavy finisher: d_COM/L = 0.425, far above the cliff —
# moving weight rearward is the real improvement, but com=0.85 in < 1.0 in suppresses it.
_SHORT_WB_NOSE_HEAVY = _car(com_in=0.85, wheelbase_in=2.0)


# ───────────────────────────────────────────────────────────────────────────── #
# Sanity guards — pin the TEST INPUTS (not the SUT). Confirm the fixtures reproduce
# the finding's engine states; if a later engine change moves the cliff these catch it
# rather than silently hollowing the edge tests.
# ───────────────────────────────────────────────────────────────────────────── #
def test_fixture_long_wb_rear_biased_is_a_finisher() -> None:
    """The long-wheelbase rear-biased car (d_COM/L = 0.150, just above the cliff) really
    **finishes** — so coaching it to move weight further back is unambiguously wrong."""
    car = _LONG_WB_REAR_BIASED
    assert car.com_ahead_of_rear_axle.m / car.wheelbase.m < 0.16, (
        "fixture must be near the cliff (rear-biased), not a generic forward car"
    )
    assert _simulate(car).outcome is Outcome.FINISHED, (
        "the long-wheelbase rear-biased car must FINISH for the inversion bug to bite"
    )


def test_fixture_following_the_placement_tip_makes_engine_tip_the_car() -> None:
    """A further-rearward shift on this near-collapse long-wheelbase car (``com=0.4 in`` ⇒
    d_COM/L = 0.05) drops the front-load fraction below the collapse threshold, so the
    **engine** returns a DNF. This pins the engine-truth that a rearward shift here is
    physically destructive (a property of ``simulate``, independent of ``present``)."""
    assert _simulate(_LONG_WB_FOLLOWED_ADVICE).outcome is Outcome.DNF, (
        "shifting weight further back on this near-collapse long-wheelbase car must tip it — "
        "the engine truth a rearward placement tip would violate"
    )


def test_fixture_short_wb_nose_heavy_is_a_finisher_genuinely_forward() -> None:
    """The short-wheelbase nose-heavy car (d_COM/L = 0.425) finishes and is genuinely too
    far **forward** — rearward coaching is the correct improvement here, yet com=0.85 in
    is below the buggy 1.0 in gate."""
    car = _SHORT_WB_NOSE_HEAVY
    assert car.com_ahead_of_rear_axle.m / car.wheelbase.m > 0.30, (
        "fixture must be genuinely forward-biased (high d_COM/L)"
    )
    assert car.com_ahead_of_rear_axle.inches < 1.0, (
        "and below the buggy raw-inch gate, so the correct coaching is wrongly suppressed"
    )
    assert _simulate(car).outcome is Outcome.FINISHED


# ───────────────────────────────────────────────────────────────────────────── #
# Direction 1 — the INVERTED coaching: a rear-biased finisher must NOT be told to move
# weight further back. This is the direct assertion against the finding's repro.
# ───────────────────────────────────────────────────────────────────────────── #
def test_rear_biased_finisher_top_tip_is_not_a_rearward_shift() -> None:
    """The finding's exact assertion #1: ``tips[0]`` for the long-wheelbase rear-biased
    finisher must **not** be the rearward-shift placement tip. The car is already optimally
    rear-biased and near the cliff; coaching it further back inverts the engine's physics
    (PRD AC-X2 / AC-X4)."""
    view = _present(_LONG_WB_REAR_BIASED)
    assert view.tips, "a finisher should still surface some next-step tips"
    top = view.tips[0].lower()
    for phrase in REARWARD_SHIFT_PHRASES:
        assert phrase not in top, (
            f"the top tip {view.tips[0]!r} for an already rear-biased finisher tells the "
            f"kid to move weight back ({phrase!r}) — that inverts the engine's physics and "
            "can push the car over the stability cliff (WI03-ADV-P2-001)"
        )


def test_rear_biased_finisher_no_coaching_string_says_move_weight_back() -> None:
    """The inverted advice must not appear **anywhere** in the coaching surface (the
    ``why`` or any ``tip``) for the rear-biased finisher — not just at position 0. A
    fraction-gated placement branch never fires the rearward tip for a low-``d_COM/L`` car."""
    view = _present(_LONG_WB_REAR_BIASED)
    for text in _all_coaching_text(view):
        low = text.lower()
        for phrase in REARWARD_SHIFT_PHRASES:
            assert phrase not in low, (
                f"coaching string {text!r} tells an already rear-biased finisher to move "
                f"weight back ({phrase!r}) — physically wrong, can tip the car "
                "(WI03-ADV-P2-001)"
            )


def test_following_surfaced_placement_advice_never_inverts_engine_outcome() -> None:
    """The worst-possible-bug guard (profile: teaching wrong physics). If the surfaced
    coaching for the near-collapse rear-biased finisher told the kid to move weight further
    back, *literally following it* would turn a finishing car into a tipping one. We encode
    "the kid followed the rearward tip" as the engine-true outcome of the further-rearward
    design (``com=0.4 in`` ⇒ DNF): a correct, fraction-aware ``present`` simply never emits
    rearward advice for this car, so the antecedent is false and the car stays a finisher —
    either way the surfaced advice must be outcome-safe (PRD AC-X2 / AC-X4)."""
    view = _present(_LONG_WB_REAR_BIASED)
    surfaced = " ".join(_all_coaching_text(view)).lower()
    advises_rearward = any(phrase in surfaced for phrase in REARWARD_SHIFT_PHRASES)
    followed_outcome = _simulate(_LONG_WB_FOLLOWED_ADVICE).outcome
    # The engine truth: following the rearward placement tip tips this car.
    assert followed_outcome is Outcome.DNF
    assert not advises_rearward, (
        "present surfaced rearward placement advice for an already rear-biased finisher; "
        "following it (com → ~1 in ahead of the rear axle) makes the engine DNF the car — "
        "a finisher turned into a tip by the UI's own advice (WI03-ADV-P2-001)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# Direction 2 — the SUPPRESSED coaching: a genuinely nose-heavy (high d_COM/L) finisher
# on a short wheelbase MUST receive the rearward placement coaching, even though its COM
# is below the buggy 1.0 in raw-inch gate.
# ───────────────────────────────────────────────────────────────────────────── #
def test_nose_heavy_short_wb_finisher_receives_rearward_placement_coaching() -> None:
    """The opposite face of the same root cause: a short-wheelbase car genuinely too far
    **forward** (d_COM/L = 0.425) is faster with weight moved rearward (engine-verified),
    so it must receive the rearward placement coaching. The raw-inch gate withholds it
    because com=0.85 in < 1.0 in; a fraction-aware gate surfaces it (PRD AC-X2 / AC-X4)."""
    view = _present(_SHORT_WB_NOSE_HEAVY)
    surfaced = " ".join(_all_coaching_text(view)).lower()
    assert any(phrase in surfaced for phrase in REARWARD_SHIFT_PHRASES), (
        f"a genuinely nose-heavy finisher (d_COM/L = 0.425) got NO rearward placement "
        f"coaching — its placement advantage is suppressed by the raw-inch gate; coaching "
        f"surface was {_all_coaching_text(view)!r} (WI03-ADV-P2-001)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# The corrected, fraction-aware placement coaching must still leak no jargon (AC-X3).
# ───────────────────────────────────────────────────────────────────────────── #
def test_fraction_aware_placement_coaching_has_no_jargon() -> None:
    """Whatever corrected, fraction-gated placement coaching replaces the raw-inch gate, it
    must remain plain language — no technical units and, critically, no exposure of the
    engine's internal "fraction"/"wheelbase"/"front-load" terms (PRD AC-X3)."""
    for car in (_LONG_WB_REAR_BIASED, _SHORT_WB_NOSE_HEAVY):
        view = _present(car)
        for text in _all_coaching_text(view):
            low = text.lower()
            for token in BANNED_TOKENS:
                assert token not in low, (
                    f"placement coaching {text!r} leaks jargon token {token!r} "
                    "(WI03-ADV-P2-001 / AC-X3)"
                )
