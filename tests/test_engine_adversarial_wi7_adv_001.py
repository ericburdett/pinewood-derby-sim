"""WI7-ADV-001 — axle bore friction must use the per-wheel NORMAL FORCE, so total
axle friction is INDEPENDENT of the wheel count (it must not be multiplied by N).

Confirmed adversarial finding (domain correctness, high):

The authoritative physics-spec.md §3.2 defines

    F_axle = N_wheel · μ_axle · (r_axle / R_outer)

where ``N_wheel`` is explicitly the NORMAL FORCE on the wheel ("derived from weight
distribution, see Section 4"), NOT the *count* of wheels. The TRD §4 is even more
explicit: "use per-wheel normal load; total F_axle = μ·(r_axle/R_outer)·F_normal summed
over the N touching wheels (load shared by count)" — i.e. each wheel carries the share
``F_normal / N`` of the car's total normal load ``F_normal = M·g·cos θ``, so summing the
per-wheel friction over the N wheels CANCELS the count:

    Σ_{i=1..N} μ·(r_axle/R_outer)·(F_normal / N) = μ·(r_axle/R_outer)·F_normal

The total axle friction is therefore the same whether 3 or 4 wheels touch.

The engine (engine.py) instead computes
``axle_factor = n_wheels · μ · (r_axle / R_outer)`` and multiplies it by the FULL car
normal load ``f_normal = M·g·cos θ`` — it omitted the per-wheel ``/N`` division, leaving
an uncancelled count multiplier. The reported total axle loss is then
``N · μ · (r_axle/R_outer) · M·g·cos θ`` — 4× the spec value for a 4-wheel car and 3×
for a 3-wheel car, and it scales LINEARLY with wheel count. On a flat-only track
(θ = 0) the reported ``energy.w_axle`` ratio 4-wheel : 3-wheel is exactly 4/3 ≈ 1.3333,
the count dependence the spec/TRD forbid.

Why this matters (and why the existing WI-7 / F-lever tests don't catch it): AC-WH1's
"3-wheel faster than 4-wheel" is correct in DIRECTION (it still holds with μ = 0 purely
from rotational inertia), and the F-lever tests only assert that ``w_axle`` rises with μ
and with wheel count — they never assert the count-INDEPENDENCE the spec mandates. So
the bulk of the measured 3-vs-4 time gap is produced by this non-physical 4/3 friction
inflation rather than the legitimate single-axle + rotational-inertia mechanism AC-WH1
describes. The profile makes educational accuracy a HARD requirement and the spec calls
friction "the biggest lever after weight"; teaching a 3–4× wrong axle-friction magnitude
is a domain-correctness defect.

These tests pin the *contract* the spec §3.2 / TRD §4 state — the total axle friction
is the per-wheel normal load summed over the wheels, hence count-independent — not the
uncancelled count multiplier the engine currently applies. They are derived from the
spec/TRD, not from the engine's internals: they exercise only the public ``simulate``
contract and assert relationships/identities the spec names.

Determinism: every test fixes dt and seed and uses RAIL_RIDER alignment (constant,
RNG-free rail force) so the seeded ping-pong draw never confounds the axle-friction
comparison. This file is NEW; it modifies, skips, or deletes no existing test.

Traceability: physics-spec §3.2 / §4.1; PRD §6 AC-F2 (F_axle = N_wheel·μ·(r_axle/R_outer));
TRD §4 ("load shared by count"); adversarial finding WI7-ADV-001.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult
    from pinewood_derby.track import Track

# Spec/TRD-anchored geometry (PRD A4 BSA-typical defaults), pinned here so the
# count-independence contract references the spec, not the engine's internals.
MU = 0.20
R_AXLE_IN = 0.045
R_OUTER_IN = 0.595


def _flat_track() -> Track:
    """A track whose running section is essentially flat (θ → 0 on the flat) — the
    cleanest place to expose the count multiplier, because there ``F_normal = M·g``
    is constant and the per-wheel-load cancellation makes total axle friction exactly
    count-independent. Matches the finding's repro track."""
    from pinewood_derby.track import Track
    from pinewood_derby.units import Angle, Length

    return Track(
        ramp_length=Length.from_feet(10),
        ramp_angle=Angle.from_degrees(30),
        transition_radius=Length.from_inches(12),
        flat_length=Length.from_feet(32),
    )


def _make_car(*, count_touching: int) -> CarDesign:
    """A valid, FINISHED-capable baseline car parameterized only by wheel count.

    Everything else is held identical so the only thing under test is whether total
    axle friction depends on the number of wheels (it must not, per spec §3.2 / TRD §4).
    """
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(5.0),
        com_ahead_of_rear_axle=Length.from_inches(0.85),
        wheelbase=Length.from_inches(4.375),
        wheels=Wheels(
            count_touching=count_touching,
            wheel_mass=Mass.from_ounces(0.09),
            outer_radius=Length.from_inches(R_OUTER_IN),
            inner_radius=Length.from_inches(0.37),
            axle_radius=Length.from_inches(R_AXLE_IN),
        ),
        body=BodyShape(drag_coefficient=0.30, frontal_area=0.0028),
        axle=Axle(friction_coefficient=MU),
        alignment=Alignment.RAIL_RIDER,
    )


def _simulate(car: CarDesign) -> RaceResult:
    from pinewood_derby.engine import simulate

    return simulate(car, _flat_track(), dt=1e-3, seed=0)


def _finished(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.FINISHED


# ───────────────────────────────────────────────────────────────────────────── #
# WI7-ADV-001 — the core defect: the reported axle-friction loss must NOT scale with
# the wheel count. Per spec §3.2 / TRD §4 the per-wheel normal load is F_normal/N and
# summing over N wheels cancels the count, so w_axle(4-wheel) ≈ w_axle(3-wheel).
# The engine reports the 4/3 ratio (count multiplier), which this test rejects.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi7_adv_001_axle_friction_work_is_count_independent() -> None:
    """Two cars identical except the touching-wheel count (3 vs 4). On a flat-running
    track the total axle-friction work ``energy.w_axle`` must be (very nearly) equal:
    each wheel carries ``F_normal / N`` so the sum over N wheels is count-independent.

    The engine multiplies by N instead, reporting w_axle(4w) ≈ (4/3)·w_axle(3w). The
    small residual difference allowed here comes only from the slightly different
    trajectories (the 4-wheel car has marginally more rotational inertia), NOT from a
    1/3 friction inflation, so a generous 5% relative tolerance still fails the engine's
    33% count multiplier while admitting the legitimate trajectory difference."""
    three = _simulate(_make_car(count_touching=3))
    four = _simulate(_make_car(count_touching=4))

    assert _finished(three) and _finished(four), (
        "both cars must FINISH on the flat-running track for a valid w_axle comparison"
    )
    assert three.energy.w_axle > 0.0, "axle friction must do real (positive) work"

    ratio = four.energy.w_axle / three.energy.w_axle
    assert abs(ratio - 1.0) < 0.05, (
        f"total axle friction must be count-INDEPENDENT (spec §3.2 / TRD §4: each wheel "
        f"carries F_normal/N, the sum over N wheels cancels the count), so "
        f"w_axle(4-wheel)/w_axle(3-wheel) must be ≈ 1.0, got {ratio:.4f}. A ratio near "
        f"4/3 ≈ 1.333 means the engine multiplied the friction by the wheel COUNT "
        f"instead of dividing the load by it — a 3–4× wrong axle-friction magnitude."
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI7-ADV-001 — pin the spec MAGNITUDE, not just the ratio: on the flat the per-step
# axle friction force is μ·(r_axle/R_outer)·F_normal with F_normal = M·g (θ = 0),
# count-independent. We check it via the energy ledger over the flat section.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi7_adv_001_axle_friction_matches_count_independent_spec_magnitude() -> None:
    """The reported axle-friction work must match the spec's count-INDEPENDENT formula
    in magnitude, not 3–4× it. We bound it: total axle work over the whole run must be
    LESS than the friction of a single full-load axle integrated over the track length,
    because the genuine spec force ``μ·(r_axle/R_outer)·M·g·cos θ`` is at most
    ``μ·(r_axle/R_outer)·M·g`` (cos θ ≤ 1) per unit distance — with NO wheel-count
    multiplier. The engine's N× force makes a 4-wheel car's w_axle ~4× this single-axle
    bound, which this test rejects.

    This pins that AC-F2's ``F_axle = N_wheel·μ·(r_axle/R_outer)`` uses N_wheel = the
    per-wheel NORMAL FORCE (a force in Newtons), not the integer wheel count."""
    car = _make_car(count_touching=4)
    r = _simulate(car)
    assert _finished(r), "car must FINISH for a valid axle-work magnitude check"

    mass_kg = car.mass.kg
    r_axle = car.wheels.axle_radius.m
    r_outer = car.wheels.outer_radius.m
    track = _flat_track()
    track_length = track.ramp_length.m + track.flat_length.m

    # Upper bound on the spec-correct total axle work: the count-independent force
    # μ·(r_axle/R_outer)·M·g (cos θ ≤ 1) integrated over the full track length. The
    # real value is strictly smaller (cos θ < 1 on the ramp, and a stable rear bias
    # unloads the front wheels), so this is a safe ceiling for the SINGLE-axle-load
    # spec model with no wheel-count multiplier.
    g = 9.81
    single_axle_force = MU * (r_axle / r_outer) * mass_kg * g
    spec_upper_bound = single_axle_force * track_length

    assert r.energy.w_axle <= spec_upper_bound, (
        f"reported axle-friction work {r.energy.w_axle:.6f} J exceeds the spec's "
        f"count-independent ceiling {spec_upper_bound:.6f} J (= μ·(r_axle/R_outer)·M·g "
        f"× track_length, cos θ ≤ 1). Exceeding it means the engine applied a wheel-"
        f"COUNT multiplier to the friction (spec §3.2 / TRD §4 use the per-wheel normal "
        f"load F_normal/N, which makes the total count-independent)."
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI7-ADV-001 — guard the WI-7 claim's MECHANISM: AC-WH1 (3-wheel faster) must hold
# from the legitimate rotational-inertia / single-axle physics, not be dominated by
# the non-physical 4/3 friction inflation. With axle friction REMOVED (μ = 0), the
# 3-wheel car must still be strictly faster (pure rotational-inertia mechanism), and
# with friction present the axle term must not be count-inflated (covered above).
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi7_adv_001_three_wheel_advantage_survives_without_friction_inflation() -> None:
    """With axle friction zeroed (μ = 0) there is NO axle-count term at all, so any
    3-vs-4 time gap is the legitimate rotational-inertia mechanism AC-WH1 names. The
    3-wheel car must still finish strictly faster. This guards that AC-WH1's pass does
    not RELY on the count-inflated friction — the educational claim must rest on real
    physics. (Deterministic: μ = 0 removes the rail/seed-free axle term; RAIL_RIDER
    keeps rail force constant.)"""
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
    from pinewood_derby.engine import simulate
    from pinewood_derby.units import Length, Mass

    def frictionless(count: int) -> CarDesign:
        return CarDesign(
            mass=Mass.from_ounces(5.0),
            com_ahead_of_rear_axle=Length.from_inches(0.85),
            wheelbase=Length.from_inches(4.375),
            wheels=Wheels(
                count_touching=count,
                wheel_mass=Mass.from_ounces(0.09),
                outer_radius=Length.from_inches(R_OUTER_IN),
                inner_radius=Length.from_inches(0.37),
                axle_radius=Length.from_inches(R_AXLE_IN),
            ),
            body=BodyShape(drag_coefficient=0.30, frontal_area=0.0028),
            axle=Axle(friction_coefficient=0.0),
            alignment=Alignment.RAIL_RIDER,
        )

    track = _flat_track()
    three = simulate(frictionless(3), track, dt=1e-3, seed=0)
    four = simulate(frictionless(4), track, dt=1e-3, seed=0)

    assert _finished(three) and _finished(four)
    assert three.energy.w_axle == 0.0 and four.energy.w_axle == 0.0, (
        "with μ = 0 there must be no axle-friction work at all, so the 3-vs-4 gap is "
        "purely the rotational-inertia mechanism"
    )
    assert three.race_time_s is not None and four.race_time_s is not None
    assert three.race_time_s < four.race_time_s, (
        f"with axle friction removed, the 3-wheel car ({three.race_time_s:.6f}s) must "
        f"still beat the 4-wheel car ({four.race_time_s:.6f}s) from rotational inertia "
        f"alone — AC-WH1's advantage must not depend on the count-inflated friction"
    )
