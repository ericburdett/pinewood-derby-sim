"""WI-2 — Adversarial edge tests for the Track model.

Covering tests for confirmed adversarial-review findings (gates.md Step 4 → Step 1).
These are RED tests: they fail against the current vulnerable implementation and must
pass once the developer adds the corresponding guards, WITHOUT weakening WI-2's
existing happy-path tests.

Findings under test (each maps to PRD AC-T3 "invalid track raises ValueError" and the
spec §1.2 geometry contract that the flat zone is genuinely flat):

- ADV-1 (input_validation, high): ``Track.__post_init__`` uses ``length.m <= 0.0``
  guards. Since ``nan <= 0`` is False and ``inf > 0``, a ramp_length or flat_length of
  ``nan`` / ``inf`` passes validation and does NOT raise. A non-finite length then
  poisons ``angle_at`` (returns ``nan``), silently propagating into the engine's
  integration loop. AC-T3 requires an invalid track to raise. Fix: ``math.isfinite``
  guards on all lengths.

- ADV-2 (domain_correctness, high): the transition arc length is ``transition_radius *
  ramp_angle`` and is consumed *past* ``ramp_length`` inside ``angle_at``, but nothing
  validates that the arc fits within ``flat_length``. With a large ``transition_radius``
  relative to ``flat_length``, the geometric flat zone begins beyond the declared track
  end, so the car is still inclined at the declared end of the track — a physically
  inconsistent "flat that is still steep". A valid track must reach angle 0 by the
  declared total length.

All tests are deterministic: pure geometry, no clock / network / RNG. The module
``pinewood_derby.track`` is imported inside each test body so a missing symbol fails
each criterion independently (true per-criterion RED) rather than aborting collection.
"""

from __future__ import annotations

import math

import pytest

# Spec-anchored constants mirrored locally (physics-spec §1.2) so assertions are
# anchored to the spec, not to the implementation's chosen magic numbers.
RAMP_FEET = 10.0
RAMP_DEGREES = 30.0
FLAT_FEET_NOMINAL = 32.0


# ───────────────────────────────────────────────────────────────────────────── #
# ADV-1 — non-finite lengths must be rejected (input validation)
# ───────────────────────────────────────────────────────────────────────────── #
def _try_make_track(
    *,
    ramp_length_m: float,
    flat_length_m: float,
) -> None:
    """Construct a Track directly from SI metres for the named lengths.

    Built from raw ``Length(m=...)`` so a non-finite SI value reaches
    ``__post_init__`` unchanged (no conversion that could sanitize it).
    """
    from pinewood_derby.track import Track
    from pinewood_derby.units import Angle, Length

    Track(
        ramp_length=Length(ramp_length_m),
        ramp_angle=Angle.from_degrees(RAMP_DEGREES),
        transition_radius=Length.from_inches(6.0),
        flat_length=Length(flat_length_m),
    )


def test_adv1_nan_ramp_length_raises() -> None:
    """A NaN ramp_length is invalid and must raise (it currently slips past
    ``nan <= 0`` which is False)."""
    good_flat = FLAT_FEET_NOMINAL * 12.0 * 0.0254
    with pytest.raises(ValueError):
        _try_make_track(ramp_length_m=float("nan"), flat_length_m=good_flat)


def test_adv1_inf_ramp_length_raises() -> None:
    """An infinite ramp_length is invalid and must raise (``inf > 0`` is True, so the
    ``<= 0`` guard lets it through)."""
    good_flat = FLAT_FEET_NOMINAL * 12.0 * 0.0254
    with pytest.raises(ValueError):
        _try_make_track(ramp_length_m=float("inf"), flat_length_m=good_flat)


def test_adv1_nan_flat_length_raises() -> None:
    """A NaN flat_length is invalid and must raise."""
    good_ramp = RAMP_FEET * 12.0 * 0.0254
    with pytest.raises(ValueError):
        _try_make_track(ramp_length_m=good_ramp, flat_length_m=float("nan"))


def test_adv1_inf_flat_length_raises() -> None:
    """An infinite flat_length is invalid and must raise."""
    good_ramp = RAMP_FEET * 12.0 * 0.0254
    with pytest.raises(ValueError):
        _try_make_track(ramp_length_m=good_ramp, flat_length_m=float("inf"))


def test_adv1_nan_transition_radius_raises() -> None:
    """A NaN transition_radius is invalid and must raise (the ``< 0`` guard also lets
    NaN through, so a non-finite radius would poison the arc-length computation)."""
    from pinewood_derby.track import Track
    from pinewood_derby.units import Angle, Length

    with pytest.raises(ValueError):
        Track(
            ramp_length=Length.from_feet(RAMP_FEET),
            ramp_angle=Angle.from_degrees(RAMP_DEGREES),
            transition_radius=Length(float("nan")),
            flat_length=Length.from_feet(FLAT_FEET_NOMINAL),
        )


def test_adv1_angle_at_never_returns_nan_for_constructible_track() -> None:
    """Defence-in-depth on the propagation symptom: for any track that *constructs*,
    ``angle_at`` must return a finite angle everywhere.

    Today a NaN-length track both constructs AND poisons ``angle_at`` (returns nan),
    silently feeding nan into the engine's integration loop. After the fix the track
    no longer constructs, so this loop never runs on a poisoned track; the assertion
    guards that no constructible track yields a non-finite angle.
    """
    from pinewood_derby.track import Track
    from pinewood_derby.units import Angle, Length

    # Attempt the adversarial NaN-ramp track. If construction (correctly) raises, the
    # finding is fixed and there is no poisoned object to probe — treat as covered.
    try:
        track = Track(
            ramp_length=Length(float("nan")),
            ramp_angle=Angle.from_degrees(RAMP_DEGREES),
            transition_radius=Length.from_inches(6.0),
            flat_length=Length.from_feet(FLAT_FEET_NOMINAL),
        )
    except ValueError:
        return  # construction rejected the non-finite length — the desired behavior
    # If we reach here the track constructed (current buggy behavior); it must at least
    # not emit a non-finite angle.
    assert math.isfinite(track.angle_at(0.0)), (
        "angle_at returned a non-finite value for a constructible track "
        "(non-finite length leaked into the geometry)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# ADV-2 — transition arc must fit within the declared track (domain correctness)
# ───────────────────────────────────────────────────────────────────────────── #
def _arc_overrun_track_kwargs() -> dict[str, object]:
    """A track whose transition arc (R·θ) is far longer than its flat zone.

    arc_length = transition_radius * ramp_angle
               = 50 in * (89°) ≈ 50 in * 1.553 rad ≈ 77.6 in  (≈ 1.97 m)
    flat_length = 0.1 in ≈ 0.00254 m  → the arc dwarfs the flat by ~770x.
    """
    from pinewood_derby.units import Angle, Length

    return {
        "ramp_length": Length.from_inches(1.0),
        "ramp_angle": Angle.from_degrees(89.0),
        "transition_radius": Length.from_inches(50.0),
        "flat_length": Length.from_inches(0.1),
    }


def test_adv2_arc_overrunning_flat_is_rejected_at_construction() -> None:
    """A track whose transition arc cannot fit within the flat zone is geometrically
    inconsistent (the declared 'flat' is still inclined) and must raise ``ValueError``
    per AC-T3 (invalid track raises)."""
    from pinewood_derby.track import Track

    with pytest.raises(ValueError):
        Track(**_arc_overrun_track_kwargs())  # type: ignore[arg-type]


def test_adv2_angle_is_zero_at_declared_end_of_track() -> None:
    """Domain invariant (spec §1.2): the car must be on the genuine flat — angle 0 — by
    the declared end of the track (ramp_length + flat_length).

    With an oversized transition arc the current implementation reports a steep angle
    (~1.55 rad) at the declared end, meaning the 'flat' is still a steep incline. This
    asserts the symptom directly: if such a track is constructible at all, its angle at
    the declared end must be ~0.
    """
    from pinewood_derby.track import Track

    try:
        track = Track(**_arc_overrun_track_kwargs())  # type: ignore[arg-type]
    except ValueError:
        return  # construction rejected the inconsistent geometry — desired behavior
    declared_end = track.ramp_length.m + track.flat_length.m
    assert track.angle_at(declared_end) == pytest.approx(0.0, abs=1e-9), (
        "angle at the declared end of the track is not flat: the transition arc "
        "overran the flat zone (a 'flat' that is still inclined)"
    )


def test_adv2_standard_track_arc_fits_within_flat() -> None:
    """Regression guard: the spec-compliant STANDARD_TRACK must satisfy the same
    arc-fits-within-flat invariant (its small 6 in radius easily fits the 32 ft flat),
    so the new validation does not over-reject the canonical track."""
    from pinewood_derby.track import STANDARD_TRACK

    arc_length = STANDARD_TRACK.transition_radius.m * STANDARD_TRACK.ramp_angle.radians
    assert arc_length <= STANDARD_TRACK.flat_length.m
    declared_end = STANDARD_TRACK.ramp_length.m + STANDARD_TRACK.flat_length.m
    assert STANDARD_TRACK.angle_at(declared_end) == pytest.approx(0.0, abs=1e-9)
