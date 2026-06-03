"""WI05-PRESENT-DNF-CLASSIFIER — non-finish disambiguation: tipped vs stalled.

Acceptance criteria (PRD AC-R4, AC-R2 data side; TRD §4):
- Any engine ``outcome=DNF`` => ``finished=False`` and ``time_seconds=None``, classified
  into ``outcome="tipped"`` or ``"stalled"`` from the trajectory + ledger only (no new
  physics, AC-G1).
- A single at-rest trajectory point at position 0 with an all-zero ledger => ``"tipped"``,
  ``stopped_distance_frac == 0.0`` (an unstable car the engine short-circuits before it runs).
- A real multi-point run that stops between the start and the finish
  (``0 < position < track_length``) => ``"stalled"``,
  ``stopped_distance_frac == last_position / track_length`` in (0, 1).
- Each gets a distinct, encouraging, jargon-free message; a slow/stable car is never a crash.
- A finisher is classified neither tipped nor stalled.

Driven by REAL ``simulate()`` output, not hand-built fixtures (TRD §12).
"""

from __future__ import annotations

import pytest

from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
from pinewood_derby.engine import simulate
from pinewood_derby.present import RaceView, present, to_json
from pinewood_derby.result import Outcome
from pinewood_derby.track import STANDARD_TRACK
from pinewood_derby.units import Length, Mass

FIXED_SEED = 0
TRACK_LENGTH_M = STANDARD_TRACK.ramp_length.m + STANDARD_TRACK.flat_length.m
_CRASH_WORDS = ("crash", "crashed", "tip", "tipped", "wobble", "wobbled", "flip")


def _wheels(*, light: bool = True, count: int = 4) -> Wheels:
    return Wheels(
        count_touching=count,
        wheel_mass=Mass.from_ounces(0.09 if light else 0.13),
        outer_radius=Length.from_inches(0.595),
        inner_radius=Length.from_inches(0.37),
        axle_radius=Length.from_inches(0.045),
    )


def _build(
    *, mass_oz: float, com_in: float, mu: float, light: bool = True, wedge: bool = True
) -> CarDesign:
    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_in),
        wheelbase=Length.from_inches(4.375),
        wheels=_wheels(light=light),
        body=BodyShape.WEDGE if wedge else BodyShape.BLOCK,
        axle=Axle(friction_coefficient=mu),
        alignment=Alignment.RAIL_RIDER,  # RNG-free => deterministic
    )


def _present(car: CarDesign) -> RaceView:
    return present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car)


# Designs chosen against the live engine (verified): a stable finisher, an unstable car the
# engine short-circuits (tipped), and a stable-but-underpowered car that runs partway then
# stalls (mu=1.5, ~1.5 oz => stops ~34% down the track).
_FINISHER = _build(mass_oz=5.0, com_in=0.85, mu=0.10)
_TIPPED = _build(mass_oz=5.0, com_in=0.1, mu=0.10)
_PARTWAY_STALL = _build(mass_oz=1.5, com_in=0.85, mu=1.5, light=False, wedge=False)


def test_engine_states_are_as_expected() -> None:
    """Pin the fixtures' engine states so a later engine change can't silently hollow the
    classifier tests (pins the INPUTS, not the SUT)."""
    fin = simulate(_FINISHER, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)
    tip = simulate(_TIPPED, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)
    stall = simulate(_PARTWAY_STALL, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)
    assert fin.outcome is Outcome.FINISHED
    assert tip.outcome is Outcome.DNF and len(tip.trajectory) == 1
    assert tip.trajectory[0].position == 0.0
    assert stall.outcome is Outcome.DNF and len(stall.trajectory) > 1
    assert 0.0 < stall.trajectory[-1].position < TRACK_LENGTH_M


def test_finisher_is_neither_tipped_nor_stalled() -> None:
    view = _present(_FINISHER)
    assert view.finished is True
    assert view.outcome == "finished"
    assert view.stopped_distance_frac is None
    assert view.time_seconds is not None


def test_tipped_run_is_classified_tipped() -> None:
    view = _present(_TIPPED)
    assert view.finished is False
    assert view.outcome == "tipped"
    assert view.time_seconds is None
    assert view.stopped_distance_frac == 0.0
    assert view.breakdown == ()  # all-zero ledger => no speed story
    assert any(word in view.headline.lower() for word in ("tip", "wobble"))


def test_stalled_run_is_classified_stalled_with_distance() -> None:
    car = _PARTWAY_STALL
    result = simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)
    view = present(result, car)
    assert view.finished is False
    assert view.outcome == "stalled"
    assert view.time_seconds is None
    assert view.stopped_distance_frac is not None
    assert 0.0 < view.stopped_distance_frac < 1.0
    expected = result.trajectory[-1].position / TRACK_LENGTH_M
    assert view.stopped_distance_frac == pytest.approx(expected)


def test_stalled_message_is_never_a_crash_story() -> None:
    """A stable car that ran out of speed must NEVER be told it crashed/tipped (AC-R4)."""
    view = _present(_PARTWAY_STALL)
    lowered = view.headline.lower()
    assert not any(word in lowered for word in _CRASH_WORDS), (
        f"stalled headline reads as a crash: {view.headline!r}"
    )


def test_tipped_and_stalled_never_collapse_into_one_outcome() -> None:
    assert _present(_TIPPED).outcome != _present(_PARTWAY_STALL).outcome


def test_to_json_carries_outcome_and_stopped_distance_frac() -> None:
    for car in (_FINISHER, _TIPPED, _PARTWAY_STALL):
        view = present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car)
        payload = to_json(view)
        assert payload["outcome"] == view.outcome
        assert payload["stopped_distance_frac"] == view.stopped_distance_frac


def test_classification_is_deterministic() -> None:
    a = _present(_PARTWAY_STALL)
    b = _present(_PARTWAY_STALL)
    assert (a.outcome, a.stopped_distance_frac) == (b.outcome, b.stopped_distance_frac)
