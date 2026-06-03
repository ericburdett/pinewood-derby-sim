"""WI03-ADV-001 — RED edge tests: a TIPPED car must not be told it "ran clean".

Confirmed adversarial finding (high, domain-correctness, reproducible)
----------------------------------------------------------------------
A car whose weight sits too far **rearward** — its front-load fraction ``d_COM/L``
*below* the engine's *stability cliff* (small ``d_COM``) — is ruled unstable by the
engine **before the run starts**: the result is ``outcome=DNF`` with a **single at-rest
trajectory point at position 0** and an **all-zero energy ledger** (the car never moved).
The engine's own evidence for "this car tipped / wobbled off the line" (TRD §4, PRD AC-R4).

Direction correction (WI03-ADV-R1-001)
--------------------------------------
The engine rules a car unstable when the front-load fraction ``d_COM/L`` is **SMALL**
(the COM is too far **REARWARD**, so the front normal force collapses): the cliff is at
``d_COM < 0.625 in`` on the standard 4.375 in wheelbase (``engine._COM_UNSTABLE_FRONT_FRACTION``;
physics-spec §4.2). The **correct fix is to move weight FORWARD** — *increasing* ``d_COM``
toward the optimal zone — verified: ``d_COM = 0.3/0.5 in`` ⇒ DNF (tip), ``d_COM = 0.625/0.85 in``
⇒ FINISHED. The earlier revision of this test (and the ``present.py`` copy it blessed) had the
direction **exactly backwards** — it told the kid the weight was "too far forward" and to "move
the weight back toward the rear axle," which *decreases* ``d_COM`` and makes the tip strictly
worse: the profile's worst-possible bug (teaching wrong physics). These tests now assert the
**physically correct** coaching: name the rearward COM and coach moving the weight **forward**.

Because this WI's ``present()._why()`` runs **unconditionally on every path**, a tipped
run flows through it like any other:

- ``_breakdown()`` correctly emits **no** loss bars (an all-zero ``w_gravity`` ledger
  has no honest speed story), so ``_dominant_loss_key()`` is ``None``;
- the 5.0 oz car is ``legal_weight is True``;
- so ``_why`` falls through its final ``else`` and emits the **encouraging finisher**
  default:

    "Your car ran clean — keep polishing your axles, lightening your wheels, and
     rolling straight to find a little more speed."

This is **pedagogically and physically WRONG** and the profile's worst-possible bug
("teaching wrong physics"): the car **did not run at all**, the kid is **praised**, and
is told to polish axles / lighten wheels when the **real, correct fix is the opposite** —
its weight is too far forward / over the stability cliff and must be moved **back** toward
(about an inch ahead of) the rear axle so it rides stably down the ramp.

Scope of THIS work item (the boundary)
--------------------------------------
The *tipped-vs-stalled classifier itself* (``view.outcome == "tipped"``, the
``stopped_distance_frac`` semantics, the wobble headline) is a **later** WI / AC-R4, so
these tests deliberately do **not** assert on ``view.outcome`` or ``view.headline``. They
assert only on the **coaching strings this WI's ``_why``/``_tips`` produce** — the field
this work item owns (PRD AC-X2 / AC-X4): a tipped run's ``why`` (and its surfaced
coaching) must

  1. **never** falsely tell the kid the car "ran clean" / "keep polishing your axles",
     and
  2. address the **real** problem — weight placement / stability: the COM is too far
     **rearward** and the weight must move **FORWARD** (toward the front axle) to clear the
     cliff — i.e. the correct priority-ordered lever in the **physically correct direction**,
     not an aero/axle red herring and not the inverted "move it back" advice (WI03-ADV-R1-001).

Why RED now
-----------
``present()`` exists and the breakdown/why/tips are populated (WI01–WI03), but ``_why``
emits the "ran clean" finisher default on the tipped non-finish path. These tests assert
the *corrected* coaching, which does not exist yet — so they fail **for the right reason**
(a wrong/misleading ``why`` string, not an import or fixture error).

Determinism (gate): the run fixes ``dt = 1e-3`` and ``seed = FIXED_SEED``. The tipped car
is short-circuited by the engine before the (seeded) RNG matters, so the result is
reproducible regardless. No clock / network / unseeded RNG.

All physics comes from the **real** ``simulate()`` — no hand-built ``RaceResult`` fixtures
(TRD §12), so the misleading ``why`` is exercised against a genuine tipped ledger.
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

# Phrases that, on a TIPPED (never-moved) run, are an actively MISLEADING "ran clean"
# praise — the bug. None of these may appear in a tipped car's coaching (it did not run,
# and polishing/lightening is the wrong fix).
MISLEADING_RAN_CLEAN_PHRASES = (
    "ran clean",
    "keep polishing",
    "find a little more speed",
)

# Plain-language tokens that anchor the CORRECT fix for a tipped car. The engine truth
# (WI03-ADV-R1-001): the car tips because its COM is too far **REARWARD** (front-load
# fraction d_COM/L below the cliff), so the correct fix is to move the weight **FORWARD**
# (toward the front axle) — *increasing* d_COM. These tokens describe a placement/stability
# message in that physically correct direction; the test additionally requires at least one
# explicit forward-direction phrase (FORWARD_FIX_PHRASES below).
#
# NOTE on token choice: these are matched as substrings, so every token is chosen to be
# free of false-positive traps in *unrelated* coaching copy — e.g. "lean" is excluded
# because it is a substring of "clean" ("ran clean"), which would spuriously match the very
# buggy default these tests reject. The wrong-direction tokens the prior revision accepted
# ("rear axle", "weight back", "toward the back", "too far forward") are intentionally
# REMOVED — accepting them blessed the inverted advice that makes a tip worse.
PLACEMENT_FIX_TOKENS = (
    "tipped",
    "wobble",
    "unstable",
    "stable",
    "stability",
    "balance",
    "too far back",
    "too far rearward",
    "forward",
    "front axle",
    "toward the front",
)

# At least one of these explicit FORWARD-direction phrases must appear in a tipped car's
# coaching — the real, physically correct fix (move weight forward / toward the front axle
# to raise d_COM above the cliff). A message that only says "stable"/"wobble" without a
# direction is insufficient; a kid needs the actionable, correct direction (WI03-ADV-R1-001).
#
# NOTE: the bare substring "forward" is deliberately EXCLUDED — it is a substring of the
# buggy "too far forward", so accepting it would let the inverted advice spuriously satisfy
# a forward-fix assertion. Each phrase names the FRONT as the destination.
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

# Phrases that encode the INVERTED (physically WRONG) fix the bug emits — telling the kid to
# move the weight BACKWARD / toward the rear axle, or that the weight is "too far forward".
# Moving weight back *decreases* d_COM and makes the tip strictly worse, so NONE of these may
# appear in a tipped car's coaching (WI03-ADV-R1-001; profile: teaching wrong physics is the
# worst possible bug).
WRONG_DIRECTION_PHRASES = (
    "too far forward",
    "weight back",
    "move the weight back",
    "back toward the rear axle",
    "toward the rear axle",
    "toward the back",
    "to the back",
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
    "stability cliff",  # "cliff" is engine jargon; the kid hears "too far forward"
    "front-load fraction",
)


# ───────────────────────────────────────────────────────────────────────────── #
# The tipped fixture — the EXACT repro design from the finding. Weight sits too far
# REARWARD (COM only 0.15 in ahead of the rear axle on a 4.375 in wheelbase ⇒ front-load
# fraction d_COM/L ≈ 0.034, well *below* the engine's front-load collapse threshold), so the
# front normal force has essentially vanished and the engine rules it unstable before the
# run: a single at-rest point at position 0 and an all-zero ledger. The correct fix is to
# move the weight FORWARD (raise d_COM), verified: d_COM = 0.85 in for this car FINISHES.
# ───────────────────────────────────────────────────────────────────────────── #
def _tipped_car() -> CarDesign:
    return CarDesign(
        mass=Mass.from_ounces(5.0),
        com_ahead_of_rear_axle=Length.from_inches(0.15),
        wheelbase=Length.from_inches(4.375),
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
    """Every kid-facing coaching string on the view (the ``why`` plus each tip)."""
    return [view.why, *view.tips]


# ───────────────────────────────────────────────────────────────────────────── #
# Sanity guard — confirm the fixture really IS a tipped, never-moved run (pins the
# TEST INPUT, not the SUT). If a later engine change moved the stability cliff this
# would catch it rather than silently hollow the edge tests.
# ───────────────────────────────────────────────────────────────────────────── #
def test_fixture_is_a_tipped_never_moved_dnf() -> None:
    """The repro design must reproduce the finding's engine state: ``outcome=DNF``, a
    single at-rest trajectory point at position 0, an all-zero ledger, and a legal
    (5.0 oz) weight — exactly the conditions under which ``_why`` wrongly falls through
    to the 'ran clean' default."""
    result = _simulate(_tipped_car())
    assert result.outcome is Outcome.DNF, "fixture must be a non-finish (DNF)"
    assert len(result.trajectory) == 1, "a tipped car never moves: one trajectory point"
    assert result.trajectory[0].position == 0.0, "tipped: the lone point sits at the line"
    energy = result.energy
    assert energy.w_gravity == 0.0, "tipped: all-zero ledger (the car never descended)"
    assert energy.w_drag == 0.0
    assert energy.w_axle == 0.0
    assert energy.w_rail == 0.0
    assert energy.ke_linear_final == 0.0
    assert energy.ke_rotational_final == 0.0
    assert result.legal_weight is True, (
        "the 5.0 oz car is legal — so the bug is NOT masked by the over-limit branch; "
        "_why falls through to its 'ran clean' finisher default"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI03-ADV-001 — the misleading "ran clean" praise must NOT be shown to a car that
# never ran. This is the direct assertion against the finding's repro.
# ───────────────────────────────────────────────────────────────────────────── #
def test_tipped_car_why_does_not_falsely_say_it_ran_clean() -> None:
    """A tipped car (single at-rest point, all-zero ledger) **did not run** — telling the
    kid it "ran clean" and to "keep polishing your axles" is the finding's bug: praise +
    the wrong fix for a car whose real problem is its weight placement. The ``why`` must
    not contain any 'ran clean' praise phrase (PRD AC-X2; profile: teaching wrong physics
    is the worst possible bug)."""
    view = _present(_tipped_car())
    low = view.why.lower()
    for phrase in MISLEADING_RAN_CLEAN_PHRASES:
        assert phrase not in low, (
            f"a tipped car was told {phrase!r} in its 'why' {view.why!r} — it never ran; "
            "this praises a non-run and prescribes the wrong fix (WI03-ADV-001)"
        )


def test_tipped_car_coaching_nowhere_says_it_ran_clean() -> None:
    """The misleading praise must not leak into a surfaced *tip* either — the whole
    coaching surface (``why`` + ``tips``) for a tipped run must be free of 'ran clean'
    praise, since the car never moved."""
    view = _present(_tipped_car())
    for text in _all_coaching_text(view):
        low = text.lower()
        for phrase in MISLEADING_RAN_CLEAN_PHRASES:
            assert phrase not in low, (
                f"tipped car coaching string {text!r} contains misleading praise "
                f"{phrase!r} — it never ran (WI03-ADV-001)"
            )


def test_tipped_car_why_addresses_the_real_placement_stability_fix() -> None:
    """The correct coaching for a tipped car is the **opposite** of "polish axles": its
    weight is too far **rearward** (front-load fraction below the cliff) and must move
    **forward** (toward the front axle, raising d_COM) so it rides stably (PRD AC-X2
    weight/placement coaching; TRD §4). The ``why`` must name that real fix — not a
    friction/aero red herring."""
    view = _present(_tipped_car())
    low = view.why.lower()
    assert any(tok in low for tok in PLACEMENT_FIX_TOKENS), (
        f"a tipped car's 'why' {view.why!r} must address the real fix — its weight is too "
        f"far back and must move forward — not generic polishing; expected one of "
        f"{PLACEMENT_FIX_TOKENS}"
    )


def test_tipped_car_why_coaches_moving_weight_forward_not_backward() -> None:
    """WI03-ADV-R1-001 — the physically correct DIRECTION. The engine tips a car whose COM
    is too far **rearward** (small d_COM, front-load fraction below the cliff); the fix is to
    move weight **FORWARD** (raise d_COM toward the optimal zone), verified: this exact car at
    d_COM = 0.85 in FINISHES while at 0.3 in it tips. The ``why`` must coach that forward
    move and must **never** tell the kid the weight is "too far forward" or to "move it back
    toward the rear axle" — that inverted advice *decreases* d_COM and makes the tip strictly
    worse (the profile's worst-possible bug: teaching wrong physics, PRD AC-X2 / AC-X4)."""
    view = _present(_tipped_car())
    low = view.why.lower()
    for phrase in WRONG_DIRECTION_PHRASES:
        assert phrase not in low, (
            f"a tipped car's 'why' {view.why!r} gives the INVERTED fix {phrase!r} — moving "
            "weight back makes the tip strictly worse; the correct fix is to move it FORWARD "
            "(WI03-ADV-R1-001)"
        )
    assert any(phrase in low for phrase in FORWARD_FIX_PHRASES), (
        f"a tipped car's 'why' {view.why!r} must coach moving the weight FORWARD (one of "
        f"{FORWARD_FIX_PHRASES}) — that is the real fix for a too-rearward COM (WI03-ADV-R1-001)"
    )


def test_tipped_car_coaching_nowhere_gives_the_inverted_backward_fix() -> None:
    """The inverted "move it back" advice must not leak into a surfaced *tip* either — the
    whole coaching surface (``why`` + ``tips``) for a tipped run must be free of the
    wrong-direction phrases, since moving weight rearward worsens the tip (WI03-ADV-R1-001)."""
    view = _present(_tipped_car())
    for text in _all_coaching_text(view):
        low = text.lower()
        for phrase in WRONG_DIRECTION_PHRASES:
            assert phrase not in low, (
                f"tipped car coaching string {text!r} gives the inverted fix {phrase!r} — "
                "the correct fix is to move weight FORWARD (WI03-ADV-R1-001)"
            )


def test_tipped_car_top_coaching_targets_placement_not_axle_polishing() -> None:
    """Priority order (PRD AC-X4 / AC-ED1): for a car that **tipped off the line**, the
    dominant, correct lever is **weight placement / stability**, not axle polishing. The
    surfaced coaching must therefore foreground the placement/stability fix — the leading
    coaching string (the ``why``, or the first tip if the ``why`` defers to tips) must
    speak to placement/stability rather than only friction prep."""
    view = _present(_tipped_car())
    leading = view.why.lower()
    assert any(tok in leading for tok in PLACEMENT_FIX_TOKENS), (
        "the leading 'why' for a tipped car must foreground the weight-placement / "
        f"stability fix (one of {PLACEMENT_FIX_TOKENS}); got {view.why!r}"
    )


def test_tipped_car_coaching_has_no_jargon() -> None:
    """Whatever corrected tipped-car coaching replaces the buggy default, it must still
    leak no jargon (PRD AC-X3) — including not exposing the engine's 'stability cliff' /
    'front-load fraction' terms to the kid."""
    view = _present(_tipped_car())
    for text in _all_coaching_text(view):
        low = text.lower()
        for token in BANNED_TOKENS:
            assert token not in low, (
                f"tipped car coaching {text!r} leaks jargon token {token!r}"
            )
