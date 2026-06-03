"""Pure translation layer — engine ``RaceResult`` → kid-facing ``RaceView`` (the
folded ``0002``; TRD §4).

This module is the single place where the engine's raw, technical output is turned
into a plain-language, JSON-serializable view-model the web front-end renders. It is
**pure**: frozen dataclasses, deterministic, no DOM / I/O / network, and — critically
— **no physics**. It only *consumes* the engine's output; it never re-derives a force,
re-integrates a trajectory, or surfaces a technical unit (PRD AC-G1, AC-X3, A7).

Scope (WI01-PRESENT-VIEWMODEL): the **core view-model for a FINISHED run** — the
``finished`` flag, ``outcome="finished"``, the race time in *seconds* (the one allowed
numeric unit, PRD A7), the trajectory passed through 1:1 for the animator, and a
``to_json`` projection for the JS bridge. The view-model carries the fields the later
non-finish / "where did your speed go?" work items fill in, but this work item only
populates the finished-run path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from . import car as _car
from . import result as _result
from . import track as _track
from . import units as _units

CarDesign = _car.CarDesign
Outcome = _result.Outcome
RaceResult = _result.RaceResult

# Outcome labels the UI tells apart: a finisher, a wobble/tip, and a stable car that
# ran out of speed (PRD AC-R4). WI01 only produces "finished"; the later non-finish
# work item populates "tipped" / "stalled".
ViewOutcome = Literal["finished", "tipped", "stalled"]

# The "where did your speed go?" channels (PRD A8 / TRD §4): each kid-facing bar key
# maps to the engine ledger field it is derived from and a plain-language label that
# leaks no jargon (PRD AC-X3). ``is_kept`` marks the lone "speed you kept" bar — the
# final *linear* KE — apart from the four loss bars.
_BREAKDOWN_CHANNELS: tuple[tuple[str, str, str, bool], ...] = (
    ("air", "w_drag", "Pushing air", False),
    ("axle", "w_axle", "Axle friction", False),
    ("rails", "w_rail", "Bumping the rails", False),
    ("wheels", "ke_rotational_final", "Spinning the wheels", False),
    ("kept", "ke_linear_final", "Speed you kept", True),
)


@dataclass(frozen=True)
class FramePoint:
    """One down-sampled snapshot the animator replays — a verbatim copy of the
    engine's ``TrajectoryPoint`` (no physics recomputed, PRD AC-R1/AC-G1)."""

    t: float            # seconds since release
    position: float     # arc-position along the track [m]
    velocity: float     # linear speed [m/s]
    angle: float        # track angle at this position [rad]


@dataclass(frozen=True)
class LossBar:
    """One bar of the "where did your speed go?" breakdown — a plain-language share
    of the run's energy story, never a raw number (PRD AC-X1, A8)."""

    key: str            # "air" | "axle" | "rails" | "wheels" | "kept"
    label: str          # plain language, e.g. "Axle friction"
    proportion: float   # 0..1 share of the energy story (for bar length); NOT joules
    is_kept: bool       # the "speed you kept" bar vs a loss


@dataclass(frozen=True)
class RaceView:
    """The kid-facing, JSON-serializable view-model of a single race (TRD §4)."""

    finished: bool
    outcome: ViewOutcome
    time_seconds: float | None              # None for any non-finish (PRD AC-R2)
    stopped_distance_frac: float | None     # for "stalled"; None otherwise
    legal_weight: bool
    headline: str                           # plain-language one-liner
    breakdown: tuple[LossBar, ...]          # ranked largest-first (AC-X1)
    why: str                                # dominant-factor coaching (AC-X2)
    tips: tuple[str, ...]                    # next-step suggestions, priority-ordered
    trajectory: tuple[FramePoint, ...]      # frames the animator replays


# The legal weight cap (BSA standard, profile / PRD AC-C3); over this is "over-limit".
_LEGAL_WEIGHT_CAP_OZ = 5.0

# Placement coaching gates on the dimensionless front-load fraction ``d_COM/L`` (the
# physically meaningful quantity the engine itself uses for both the placement advantage
# and the stability cliff), NEVER a raw inch threshold — a raw inch gate inverts on
# non-standard wheelbases (WI03-ADV-P2-001; mirrors the engine's WI6-ADV-001 fix). A car
# whose COM sits forward of this fraction is genuinely nose-heavy and is coached to shift
# weight rearward. The value is the standard-wheelbase equivalent of the legacy 1.0 in
# gate (1.0 / 4.375 in) so standard 4.375 in cars are unaffected, and it sits comfortably
# above the engine's instability cliff (≈ 0.143) so the rearward tip never pushes a car
# over the cliff.
_COM_FORWARD_FRACTION_GATE = 1.0 / 4.375

# Dominant-loss → plain-language "why" coaching, tied to a real building principle
# (PRD AC-X2; TRD §4). The reviewed, table-driven lookup: each loss key names its fix
# in kid language, leaking no jargon (PRD AC-X3). "kept" is never a dominant *factor*.
_WHY_BY_LOSS: dict[str, str] = {
    "axle": (
        "Your biggest slowdown was axle friction — polish your axles smooth and "
        "add graphite so the wheels spin freely."
    ),
    "rails": (
        "Your biggest slowdown was bumping the rails — fix your car's alignment so "
        "it rolls straight instead of steering into the walls."
    ),
    "air": (
        "Your biggest slowdown was pushing air — give your car a lower, smoother "
        "wedge shape so it slips through the air."
    ),
    "wheels": (
        "Your biggest slowdown was spinning the wheels — use lighter, truer wheels "
        "so less of your speed gets used up turning them."
    ),
}

# Priority-ordered coaching levers (PRD AC-X4 / engine AC-ED1): weight & placement and
# friction dominate; wheels next; aerodynamics is the *smallest* lever and is therefore
# always emitted last so a tip never out-ranks weight or friction. Each entry pairs a
# loss key (or a synthetic weight/placement key) with its plain-language next step.
_TIP_WEIGHT_OVER_LIMIT = (
    "Your car is over the 5.0 oz limit — trim it down to the legal cap so it still "
    "passes inspection."
)
_TIP_PLACEMENT_FORWARD = (
    "Move some weight toward the back, about an inch ahead of the rear axle, so it "
    "rides higher on the ramp longer."
)
_TIP_BY_LOSS: dict[str, str] = {
    "axle": "Polish your axles and add a little graphite so the wheels spin freely.",
    "rails": "Tune your alignment so the car rolls straight and stops bumping the rails.",
    "wheels": "Switch to lighter, truer wheels so less speed is spent spinning them.",
    "air": "Give the body a lower, smoother wedge shape so it slips through the air.",
}


# ───────────────────────────────────────────────────────────────────────────── #
# Banned-terms guard (PRD AC-X3; TRD §4 / §11). A single shared list + checker so the
# SAME source of truth backs both this module's pytest guard and the later UI text scan.
# Nothing technical may ever reach a kid: energy/force units, velocity/acceleration
# units (spelled-out *and* symbol forms), named coefficients, the Greek/symbol jargon,
# physics terms, and the engine's raw ledger field names / internal physics phrasing.
# Matching is pure, case-insensitive, and substring-based ("measured in Joules." is
# caught), so a stray capitalisation or surrounding copy can't smuggle jargon past it.
# ───────────────────────────────────────────────────────────────────────────── #
BANNED_TERMS: tuple[str, ...] = (
    # Energy / force / power / mass units (spelled out and symbol forms).
    "joule",
    "joules",
    "newton",
    "newtons",
    "watt",
    "watts",
    "kilogram",
    "kilograms",
    # Velocity / acceleration units (symbol and spelled-out).
    "m/s",
    "m/s2",
    "m/s²",
    "meters per second",
    "metres per second",
    # The generic "coefficient" plus the named coefficients.
    "coefficient",
    "c_d",
    "drag coefficient",
    "friction coefficient",
    # Greek / symbol jargon for the friction coefficient.
    "μ",
    "mu_axle",
    # Physics terms that must never reach a kid.
    "moment of inertia",
    "rotational inertia",
    "normal force",
    "kinetic energy",
    "potential energy",
    "integration",
    "trajectory",
    # Raw engine ledger field names must never surface as copy.
    "w_drag",
    "w_axle",
    "w_rail",
    "w_gravity",
    "ke_linear",
    "ke_rotational",
    "pe_initial",
    "d_com",
    "proportion",
    # Internal physics phrasing the engine / present modules use behind the boundary.
    "front-load fraction",
    "stability cliff",
)

_BANNED_TERMS_LOWER: tuple[str, ...] = tuple(term.lower() for term in BANNED_TERMS)


def find_banned_terms(text: str) -> list[str]:
    """Return the banned terms (PRD AC-X3) that appear in ``text``, case-insensitively
    and as substrings. Pure and deterministic — the single reusable checker shared by
    this module's pytest guard and the UI text scan (TRD §11). Clean copy returns ``[]``."""
    haystack = text.lower()
    return [term for term in _BANNED_TERMS_LOWER if term in haystack]


def _format_seconds(seconds: float) -> str:
    """Plain-language time string — seconds is the only allowed surfaced unit (A7).
    Thousandths, like a real derby timer, so small design changes are visible."""
    return f"{seconds:.3f} seconds"


def _dominant_loss_key(breakdown: tuple[LossBar, ...]) -> str | None:
    """The key of the largest *loss* bar, excluding the "speed you kept" bar (TRD §4).

    ``None`` when there is no loss bar to be dominant over (e.g. a tip's empty
    breakdown), so the caller can fall back to outcome-driven coaching.
    """
    losses = [bar for bar in breakdown if not bar.is_kept]
    if not losses:
        return None
    return max(losses, key=lambda bar: bar.proportion).key


# A tipped car never ran (PRD AC-R4 / TRD §4): praising it or prescribing axle/wheel
# polishing is the worst-possible bug (teaching wrong physics). Its real, priority-first
# fix is weight placement / stability. The engine rules a car unstable when its weight
# sits too far **rearward** (front-load fraction d_COM/L below the stability cliff), so the
# correct, physically verified fix is to move the weight **FORWARD** (toward the front axle)
# — never backward, which lowers d_COM and makes the tip worse (WI03-ADV-R1-001). Stated in
# plain language with no engine jargon (AC-X3).
_WHY_TIPPED = (
    "Your car's weight is so far back that the front wheels barely touch the track — with "
    "almost no weight on them the car can't steer straight, so it wobbles off course instead "
    "of rolling. Move some weight forward so the front wheels stay planted and it tracks straight."
)

# A stalled, near-stationary car that never really moved (a non-finish with an empty
# breakdown that is *not* a tip) and is well under the weight cap. It did NOT run, so the
# "ran clean" finisher praise is wrong; its real problem is being under-energised — too
# light to carry enough speed down the ramp. The fix is more weight (up to the legal cap),
# stated in plain language with no jargon (PRD AC-X2 / AC-X3; WI03-ADV-R1-002).
_WHY_STALLED_UNDERPOWERED = (
    "Your car ran out of speed and stopped just short — it's too light to carry enough "
    "speed down the ramp. Add weight, up to the 5.0 oz limit, so it builds more speed."
)

# Kid-facing non-finish headlines (PRD AC-R2 / AC-R4) — encouraging, never a "crash", and
# distinct for the two stories the engine collapses into one DNF: a *tipped* (unstable) car
# that never left the line, vs a *stalled* car that ran but lost its speed. No jargon (AC-X3).
_HEADLINE_TIPPED = "Too much weight in the back — the front went light and your car wobbled off course."


def _stalled_headline(stopped_distance_frac: float) -> str:
    """An encouraging "ran out of speed" headline scaled to how far the car got — never a
    crash story (a stalled car was stable; it just didn't carry enough speed to finish)."""
    if stopped_distance_frac >= 0.85:
        return "So close! Your car ran out of speed just short of the finish line."
    if stopped_distance_frac > 0.0:
        return "Your car ran out of speed and rolled to a stop partway down the track."
    return "Your car ran out of speed and barely left the starting line."


# A car whose friction / aero / wheel / alignment levers are already at their best — coaching
# it to "fix" them is exactly the bug a kid sees (told to polish axles that are already
# polished, or fix alignment that's already straight-tracking). We treat a lever as
# already-optimal at/near the engine's best setting, so the coach stops nagging a tuned build
# and instead celebrates it (or points to the one lever with real headroom left). Thresholds
# sit just above the best presets so a continuous slider's "good" end counts as optimal too.
_AXLE_OPTIMAL_MU = 0.12          # polished + graphite ≈ 0.10
_WHEEL_OPTIMAL_OZ = 0.10         # light wheels ≈ 0.09 oz
_BODY_OPTIMAL_CD = 0.25          # smooth wedge ≈ 0.20
_WEIGHT_AT_CAP_OZ = 4.9          # at/above this (and legal) there's no real weight left to add

_WHY_OVER_LIMIT = (
    "Your car is over the 5.0 oz limit — trim it down to the legal cap so it still "
    "passes inspection."
)
_WHY_DIALED_IN = (
    "Your car is really well tuned — the axles are slick, the wheels are light, the body is "
    "smooth, and it rolls straight. This is about as fast as this design gets. Nice work!"
)
_WHY_ADD_WEIGHT = (
    "Your car runs clean — the one thing left is weight. Add a little more, up to the 5.0 oz "
    "limit, so it carries more speed down the ramp."
)
_TIP_DIALED_IN = (
    "You've tuned every part of this car — try a different design to see if you can beat this "
    "time, or race it against a friend's car."
)
_TIP_ADD_WEIGHT = (
    "Add a little weight, up to the 5.0 oz limit, so your car carries more speed all the way "
    "down the track."
)


def _optimal_levers(car: CarDesign) -> frozenset[str]:
    """The loss levers already at (or past) their best setting on this car, so the coach
    won't tell a kid to 'fix' something they've already optimized (the keys match the loss
    bars: ``axle`` / ``wheels`` / ``air`` / ``rails``). Reads only design settings — no
    physics (AC-G1)."""
    optimal: set[str] = set()
    if car.axle.friction_coefficient <= _AXLE_OPTIMAL_MU:
        optimal.add("axle")
    if car.wheels.wheel_mass.ounces <= _WHEEL_OPTIMAL_OZ:
        optimal.add("wheels")
    if car.body.drag_coefficient <= _BODY_OPTIMAL_CD:
        optimal.add("air")
    if car.alignment is _car.Alignment.RAIL_RIDER:
        optimal.add("rails")
    return frozenset(optimal)


def _best_fixable_loss(breakdown: tuple[LossBar, ...], optimal: frozenset[str]) -> str | None:
    """The largest loss whose lever is NOT already optimal — the genuinely worthwhile fix.
    Breakdown is ranked largest-first, so the first non-optimal lever is the most impactful
    one to coach. ``None`` when every surfaced loss lever is already dialed in."""
    for bar in breakdown:
        if not bar.is_kept and bar.key not in optimal:
            return bar.key
    return None


def _why(
    breakdown: tuple[LossBar, ...],
    legal_weight: bool,
    *,
    tipped: bool,
    finished: bool,
    optimal: frozenset[str],
    weight_at_cap: bool,
) -> str:
    """The dominant-factor "why" (PRD AC-X2): name the largest *loss* in plain
    language and tie it to its real building principle. A tipped car (never moved) is
    coached to move its weight forward (its real placement/stability fix), never the "ran
    clean" praise; a stalled near-stationary car that didn't finish and has no real loss
    story is told it ran out of speed (and, being legal, wants more weight), never praised;
    an over-limit car with no loss story falls back to legal-cap weight coaching."""
    if tipped:
        return _WHY_TIPPED

    if finished:
        # Coach the biggest loss whose lever still has room to improve — NOT a lever the kid
        # has already optimized (the bug: telling a polished-axle car to polish its axles).
        fixable = _best_fixable_loss(breakdown, optimal)
        if fixable is not None and fixable in _WHY_BY_LOSS:
            return _WHY_BY_LOSS[fixable]
        if not legal_weight:
            return _WHY_OVER_LIMIT
        # Every friction/aero/wheel/alignment lever is already optimal:
        if not weight_at_cap:
            return _WHY_ADD_WEIGHT  # the one real lever left is more weight
        return _WHY_DIALED_IN  # nothing left to improve — celebrate it

    # Non-finish (stalled): unchanged — name the dominant loss, else coach weight / under-power.
    dominant = _dominant_loss_key(breakdown)
    if dominant is not None and dominant in _WHY_BY_LOSS:
        return _WHY_BY_LOSS[dominant]
    if not legal_weight:
        return _WHY_OVER_LIMIT
    # A legal, non-tipped car with no honest loss story that still didn't finish stalled near
    # the line — it never really ran, so it must not be praised; the real problem is being
    # under-energised (too light), per WI03-ADV-R1-002.
    return _WHY_STALLED_UNDERPOWERED


_TIP_TIPPED_FORWARD = (
    "Move the weight forward so the front wheels keep their grip — then the car tracks "
    "straight down the ramp instead of wobbling off course."
)
_TIP_STALLED_ADD_WEIGHT = (
    "Add weight, up to the 5.0 oz limit, so your car builds more speed and doesn't run "
    "out before the finish line."
)


def _tips(
    breakdown: tuple[LossBar, ...],
    legal_weight: bool,
    com_front_fraction: float,
    *,
    tipped: bool,
    finished: bool,
    optimal: frozenset[str],
    weight_at_cap: bool,
) -> tuple[str, ...]:
    """1–3 next-step suggestions in the engine's real priority order (PRD AC-X4 /
    AC-ED1): weight & placement and friction first, wheels next, aerodynamics last — so
    an aero tip can never out-rank a weight/friction tip. Built largest-fix-first within
    that fixed lever ordering, capped at three.

    A tipped car (never ran) is coached only to its real placement/stability fix — its
    weight is too far *back* and must move *forward* toward the front axle (raising the
    front-load fraction above the stability cliff) — never the friction/aero red herrings
    that assume a run happened, and never the inverted "move it back" advice that worsens
    the tip (PRD AC-X4; WI03-ADV-R1-001). A stalled, near-stationary legal car that didn't
    finish is coached to add weight — it ran out of speed, not "ran clean" (WI03-ADV-R1-002).
    """
    if tipped:
        return (_TIP_TIPPED_FORWARD,)

    dominant = _dominant_loss_key(breakdown)
    if not finished and not breakdown and legal_weight:
        # Stalled near the line with no honest loss story: the dominant fix is more weight.
        return (_TIP_STALLED_ADD_WEIGHT,)
    # (priority_rank, tip) — lower rank surfaces first; weight/placement = 0, friction = 1,
    # wheels = 2, aero = 3. The dominant loss's own tip is boosted to the front of its
    # lever bucket so the top tip addresses this run's biggest fixable loss.
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()

    def add(rank: int, tip: str, *, boost: bool = False) -> None:
        if tip in seen:
            return
        seen.add(tip)
        candidates.append((rank, 0 if boost else 1, tip))

    # Weight / placement — the dominant lever (rank 0). An over-limit car is coached to the
    # legal cap first; a legal finisher with room under the cap is coached to add weight; a
    # far-forward COM is coached toward the rear axle.
    if not legal_weight:
        add(0, _TIP_WEIGHT_OVER_LIMIT, boost=True)
    elif finished and not weight_at_cap:
        add(0, _TIP_ADD_WEIGHT, boost=True)
    if com_front_fraction >= _COM_FORWARD_FRACTION_GATE:
        add(0, _TIP_PLACEMENT_FORWARD, boost=legal_weight)

    # Friction / wheels / aero — only suggest a lever that ISN'T already optimal, so a kid is
    # never told to "fix" a part they've already tuned (the bug this addresses). Priority
    # order is preserved: friction (rank 1) before wheels (2) before aerodynamics (3).
    if "axle" not in optimal:
        add(1, _TIP_BY_LOSS["axle"], boost=dominant == "axle")
    if "rails" not in optimal:
        add(1, _TIP_BY_LOSS["rails"], boost=dominant == "rails")
    if "wheels" not in optimal:
        add(2, _TIP_BY_LOSS["wheels"], boost=dominant == "wheels")
    if "air" not in optimal:
        add(3, _TIP_BY_LOSS["air"], boost=dominant == "air")

    candidates.sort(key=lambda c: (c[0], c[1]))
    tips = tuple(tip for _, _, tip in candidates[:3])
    if tips:
        return tips
    # Nothing actionable surfaced: a fully-tuned finisher is congratulated and nudged toward a
    # new challenge rather than handed an empty list; a no-loss-story stall wants more weight.
    return (_TIP_DIALED_IN,) if finished else (_TIP_STALLED_ADD_WEIGHT,)


def _is_tipped(result: RaceResult) -> bool:
    """A *tipped* (unstable) run, per the engine's own evidence (TRD §4 / PRD AC-R4):
    the engine short-circuits an unstable car **before** the run, so the result is a
    non-finish with a single at-rest trajectory point at position 0 (and an all-zero
    ledger). Reads only ``outcome`` + ``trajectory`` — no physics (AC-G1)."""
    return (
        result.outcome is not Outcome.FINISHED
        and len(result.trajectory) == 1
        and result.trajectory[0].position == 0.0
    )


def _trajectory_view(result: RaceResult) -> tuple[FramePoint, ...]:
    """Copy the engine's down-sampled trajectory 1:1 into FramePoints (no physics)."""
    return tuple(
        FramePoint(t=tp.t, position=tp.position, velocity=tp.velocity, angle=tp.angle)
        for tp in result.trajectory
    )


def _breakdown(result: RaceResult) -> tuple[LossBar, ...]:
    """Build the ranked "where did your speed go?" bars (PRD AC-X1, A8; TRD §4).

    Each channel's share is its mapped ledger field divided by the **integrated
    gravity work** ``w_gravity`` — the energy actually delivered on *this* run, which
    the per-force ledger closes against — so the bars sum to ~1.0 for a finisher *and*
    a stalled car alike (not ``pe_initial``, which a stalled car never fully realizes).

    A tipped run has an all-zero ledger (``w_gravity == 0``): there is no speed story
    to chart, so the breakdown is empty — which also guards the divisor against zero.

    The ledger only closes against ``w_gravity`` once the car has actually descended:
    ``w_gravity == w_drag + w_axle + w_rail + ke_linear_final + ke_rotational_final``.
    A car that creeps a few microns off the line and stalls leaves a *degenerate*
    near-stationary ledger where integration noise on a microscopic ``w_gravity`` lets a
    loss channel exceed the delivered work (e.g. ``w_rail > w_gravity``). Normalizing
    against that explodes a bar past 1 and the bars stop summing to ~1 — a chart claiming
    a >100% loss, which a kid can't make sense of (TRD §4; PRD AC-X1). When the channels
    do **not** partition the delivered work, there is no honest speed story to chart, so —
    as with a tip — the breakdown is suppressed.

    Bars are ranked **largest proportion first**.
    """
    energy = result.energy
    delivered = energy.w_gravity
    if delivered <= 0.0:
        return ()

    bars = tuple(
        LossBar(
            key=key,
            label=label,
            proportion=getattr(energy, field) / delivered,
            is_kept=is_kept,
        )
        for key, field, label, is_kept in _BREAKDOWN_CHANNELS
    )

    # Only surface the breakdown when the channels truly partition the delivered work:
    # each share within [0, 1] and the whole summing to ~1. Otherwise the ledger is the
    # degenerate near-stationary case (losses exceed a microscopic w_gravity) and any
    # chart would mislead, so suppress it like a tip.
    total = sum(bar.proportion for bar in bars)
    if any(not 0.0 <= bar.proportion <= 1.0 + 1e-9 for bar in bars) or abs(total - 1.0) > 1e-6:
        return ()

    return tuple(sorted(bars, key=lambda bar: bar.proportion, reverse=True))


def present(
    result: RaceResult, car: CarDesign, track: _track.Track = _track.STANDARD_TRACK
) -> RaceView:
    """Translate an engine ``RaceResult`` (+ its ``CarDesign``) into a ``RaceView``.

    A **finisher** maps to ``finished=True``, ``outcome="finished"``,
    ``time_seconds == result.race_time_s`` (the only numeric unit surfaced is seconds, A7).
    A **non-finish** is classified into the two kid-facing stories the engine collapses
    into one DNF (PRD AC-R4): ``"tipped"`` (unstable — never left the line) vs ``"stalled"``
    (ran but lost its speed), from the trajectory + ledger alone — no new physics (AC-G1).
    ``stopped_distance_frac`` (a stalled car's fraction of the way to the finish) is measured
    against ``track`` (the standard track by default — the only track the app races on). The
    trajectory is passed through verbatim for the animator; ``present`` mutates no argument.
    """
    trajectory = _trajectory_view(result)
    breakdown = _breakdown(result)
    # Placement coaching gates on the dimensionless front-load fraction d_COM/L (the
    # quantity the engine uses), never raw inches — so it never inverts on a non-standard
    # wheelbase (WI03-ADV-P2-001).
    com_front_fraction = car.com_ahead_of_rear_axle.m / car.wheelbase.m
    tipped = _is_tipped(result)
    finished = result.outcome is Outcome.FINISHED and result.race_time_s is not None
    # State-aware coaching: which levers are already optimal, and whether weight is at the cap,
    # so we never advise "fixing" a lever the kid has already tuned (PRD AC-X2/AC-X4).
    optimal = _optimal_levers(car)
    weight_at_cap = result.legal_weight and car.mass.ounces >= _WEIGHT_AT_CAP_OZ
    why = _why(
        breakdown,
        result.legal_weight,
        tipped=tipped,
        finished=finished,
        optimal=optimal,
        weight_at_cap=weight_at_cap,
    )
    tips = _tips(
        breakdown,
        result.legal_weight,
        com_front_fraction,
        tipped=tipped,
        finished=finished,
        optimal=optimal,
        weight_at_cap=weight_at_cap,
    )

    if result.outcome is Outcome.FINISHED and result.race_time_s is not None:
        return RaceView(
            finished=True,
            outcome="finished",
            time_seconds=result.race_time_s,
            stopped_distance_frac=None,
            legal_weight=result.legal_weight,
            headline=f"Nice! Your car finished in {_format_seconds(result.race_time_s)}.",
            breakdown=breakdown,
            why=why,
            tips=tips,
            trajectory=trajectory,
        )

    # Non-finish (PRD AC-R2 / AC-R4): a non-finisher carries no invented time. The engine
    # short-circuits an *unstable* car before it moves (single at-rest point at position 0,
    # all-zero ledger) — that is a "tipped" wobble, never a crash, and has no speed story to
    # chart (``_breakdown`` already returns no bars). Anything else ran but lost its speed —
    # a "stalled" car — and we report how far it got toward the finish.
    if tipped:
        return RaceView(
            finished=False,
            outcome="tipped",
            time_seconds=None,
            stopped_distance_frac=0.0,
            legal_weight=result.legal_weight,
            headline=_HEADLINE_TIPPED,
            breakdown=breakdown,
            why=why,
            tips=tips,
            trajectory=trajectory,
        )

    track_length = track.ramp_length.m + track.flat_length.m
    last_position = result.trajectory[-1].position if result.trajectory else 0.0
    frac = last_position / track_length if track_length > 0.0 else 0.0
    frac = 0.0 if frac < 0.0 else 1.0 if frac > 1.0 else frac
    return RaceView(
        finished=False,
        outcome="stalled",
        time_seconds=None,
        stopped_distance_frac=frac,
        legal_weight=result.legal_weight,
        headline=_stalled_headline(frac),
        breakdown=breakdown,
        why=why,
        tips=tips,
        trajectory=trajectory,
    )


def to_json(view: RaceView) -> dict[str, object]:
    """Project a ``RaceView`` to a plain dict for the JS bridge — no lingering
    dataclass instances or proxies, every value JSON-serializable.

    PRD AC-X3 (no jargon) governs the **strings rendered to the kid** — headline, why,
    tips, bar labels — and the no-jargon guard scans exactly those *values*. The dict
    **keys** are structural identifiers the JS bridge/animator address by name, never
    shown to the user, so they carry the view-model's own field names. In particular the
    animator replays the run from the ``trajectory`` key (PRD AC-R1), so that data key
    keeps its plain field name rather than being renamed to dodge a guard that only
    applies to rendered copy. (Adjudicated 2026-06-03: an earlier draft renamed
    ``trajectory``→``frames`` to satisfy a key-level jargon scan, which contradicted the
    AC-R1 test requiring the ``trajectory`` key; the guard was re-scoped to values.)
    """
    return {
        "finished": view.finished,
        "outcome": view.outcome,
        "time_seconds": view.time_seconds,
        "stopped_distance_frac": view.stopped_distance_frac,
        "legal_weight": view.legal_weight,
        "headline": view.headline,
        "breakdown": [
            {
                "key": bar.key,
                "label": bar.label,
                "share": bar.proportion,
                "is_kept": bar.is_kept,
            }
            for bar in view.breakdown
        ],
        "why": view.why,
        "tips": list(view.tips),
        "trajectory": [
            {"t": fp.t, "position": fp.position, "velocity": fp.velocity, "angle": fp.angle}
            for fp in view.trajectory
        ],
    }


# ───────────────────────────────────────────────────────────────────────────── #
# Garage serialization (WI06-PRESENT-GARAGE-SERDE; PRD AC-S2, TRD §5/§7)
#
# CarDesign <-> a plain, JSON-serializable dict for the browser garage (localStorage).
# Values are stored in the engine's *canonical SI* units (kg, m) read straight off the
# value objects, so a round-trip is lossless (no lossy oz/inch reconversion). Each
# entry carries a schemaVersion so a later CarDesign change can be migrated. This is
# pure presentation-boundary plumbing: no physics, no I/O (PRD AC-G1).
# ───────────────────────────────────────────────────────────────────────────── #

#: Bump when the on-disk CarDesign garage shape changes (TRD §7, PRD A4 migration).
GARAGE_SCHEMA_VERSION = 1


def to_dict(car: CarDesign) -> dict[str, object]:
    """Serialize a ``CarDesign`` to a plain, JSON-serializable dict for the garage.

    Stores canonical SI values (kg, m) verbatim off the unit value objects so
    ``from_dict(to_dict(car)) == car`` exactly, and tags the entry with
    ``schemaVersion`` for forward migration (TRD §7)."""
    return {
        "schemaVersion": GARAGE_SCHEMA_VERSION,
        "design": {
            "mass_kg": car.mass.kg,
            "com_ahead_of_rear_axle_m": car.com_ahead_of_rear_axle.m,
            "wheelbase_m": car.wheelbase.m,
            "wheels": {
                "count_touching": car.wheels.count_touching,
                "wheel_mass_kg": car.wheels.wheel_mass.kg,
                "outer_radius_m": car.wheels.outer_radius.m,
                "inner_radius_m": car.wheels.inner_radius.m,
                "axle_radius_m": car.wheels.axle_radius.m,
            },
            "body": {
                "drag_coefficient": car.body.drag_coefficient,
                "frontal_area": car.body.frontal_area,
            },
            "axle": {"friction_coefficient": car.axle.friction_coefficient},
            "alignment": car.alignment.value,
        },
    }


def _sub(d: dict[str, object], key: str) -> dict[str, object]:
    """Pull a nested mapping by key, raising ValueError if it is absent or not a dict."""
    value = d[key]
    if not isinstance(value, dict):
        raise ValueError(f"garage entry {key!r} must be a mapping, got {value!r}")
    return value


def _num(d: dict[str, object], key: str) -> float:
    """Pull a real number by key (rejecting bool, which is an int subclass)."""
    value = d[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"garage field {key!r} must be a number, got {value!r}")
    return float(value)


def _int(d: dict[str, object], key: str) -> int:
    value = d[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"garage field {key!r} must be an int, got {value!r}")
    return value


def _str(d: dict[str, object], key: str) -> str:
    value = d[key]
    if not isinstance(value, str):
        raise ValueError(f"garage field {key!r} must be a string, got {value!r}")
    return value


def from_dict(data: dict[str, object]) -> CarDesign:
    """Reconstruct a ``CarDesign`` from :func:`to_dict` output, re-validating through
    the engine's own constructors — the single source of truth (TRD §5).

    Raises ``ValueError`` for an unsupported ``schemaVersion``, a malformed/incomplete
    entry (missing key, wrong type), or any value that violates a CarDesign invariant
    (the sub-object and ``CarDesign`` constructors raise ``ValueError`` themselves), so
    a corrupt stored design surfaces gracefully upstream rather than yielding an invalid
    object."""
    if not isinstance(data, dict):
        raise ValueError(f"garage entry must be a mapping, got {type(data).__name__}")
    if data.get("schemaVersion") != GARAGE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported garage schemaVersion {data.get('schemaVersion')!r}; expected "
            f"{GARAGE_SCHEMA_VERSION}"
        )
    try:
        design = _sub(data, "design")
        wheels_d = _sub(design, "wheels")
        body_d = _sub(design, "body")
        axle_d = _sub(design, "axle")
        wheels = _car.Wheels(
            count_touching=_int(wheels_d, "count_touching"),
            wheel_mass=_units.Mass(_num(wheels_d, "wheel_mass_kg")),
            outer_radius=_units.Length(_num(wheels_d, "outer_radius_m")),
            inner_radius=_units.Length(_num(wheels_d, "inner_radius_m")),
            axle_radius=_units.Length(_num(wheels_d, "axle_radius_m")),
        )
        body = _car.BodyShape(
            drag_coefficient=_num(body_d, "drag_coefficient"),
            frontal_area=_num(body_d, "frontal_area"),
        )
        axle = _car.Axle(friction_coefficient=_num(axle_d, "friction_coefficient"))
        alignment = _car.Alignment(_str(design, "alignment"))
        return CarDesign(
            mass=_units.Mass(_num(design, "mass_kg")),
            com_ahead_of_rear_axle=_units.Length(_num(design, "com_ahead_of_rear_axle_m")),
            wheelbase=_units.Length(_num(design, "wheelbase_m")),
            wheels=wheels,
            body=body,
            axle=axle,
            alignment=alignment,
        )
    except KeyError as exc:
        raise ValueError(f"malformed garage entry: missing key {exc}") from exc


# ───────────────────────────────────────────────────────────────────────────── #
# Legality inspection (feature 0008). Pure rule checks for the UI's "inspection" panel.
# Weight is the one UNIVERSAL hard rule (≤ 5.0 oz). The dimensional limits are the common
# BSA-style values but VARY BY LEAGUE, so the UI presents them with a "check your pack's
# rules" disclaimer. No physics here — these are build-rule checks on plain dimensions.
# ───────────────────────────────────────────────────────────────────────────── #
LEGAL_LIMITS: dict[str, float] = {
    "weight_oz_max": 5.0,
    "width_in_max": 2.75,
    "length_in_max": 7.0,
    "height_in_max": 3.5,
    "ground_clearance_in_min": 0.375,
}

_EPS = 1e-9


def _rule(name: str, ok: bool, value: str, requirement: str) -> dict[str, object]:
    return {"rule": name, "ok": ok, "value": value, "requirement": requirement}


def legality_report(
    *,
    mass_oz: float,
    width_in: float,
    height_in: float,
    length_in: float,
    ground_clearance_in: float,
) -> list[dict[str, object]]:
    """A per-rule legality checklist for the inspection panel. Each entry carries the rule
    name, whether it passes, the car's value, and the plain-language requirement. Pure and
    deterministic. Weight is universal; the rest are typical-but-league-dependent (the UI
    says so) — no rule is asserted here as the one true rulebook."""
    return [
        _rule("Weight", mass_oz <= LEGAL_LIMITS["weight_oz_max"] + _EPS,
              f"{mass_oz:.1f} oz", "at most 5.0 oz"),
        _rule("Width", width_in <= LEGAL_LIMITS["width_in_max"] + _EPS,
              f"{width_in:.2f} in", "at most 2.75 in wide"),
        _rule("Length", length_in <= LEGAL_LIMITS["length_in_max"] + _EPS,
              f"{length_in:.2f} in", "at most 7.0 in long"),
        _rule("Height", height_in <= LEGAL_LIMITS["height_in_max"] + _EPS,
              f"{height_in:.2f} in", "at most 3.5 in tall"),
        _rule("Ground clearance", ground_clearance_in >= LEGAL_LIMITS["ground_clearance_in_min"] - _EPS,
              f"{ground_clearance_in:.2f} in", "at least 3/8 in to clear the rail"),
    ]
