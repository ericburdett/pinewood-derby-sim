"""The pure simulation engine: ``simulate(car, track, *, dt, seed) -> RaceResult``.

This is the heart of the feature (TRD §4). It time-step Euler-integrates the car's
center of mass down the track, accumulating a per-force energy ledger that closes by
construction, and returns an immutable :class:`RaceResult`.

The engine is **pure and deterministic** (AC-PU1, AC-AL3): it performs no file I/O
and no network access, holds no module-level mutable state, and routes *all*
randomness through a local ``random.Random(seed)`` created per call — never the
module-global ``random``. Given the same ``(car, track, dt, seed)`` it returns a
bit-identical result.

Traceability (PRD §6; TRD §4/§11):

- AC-O1/AC-O2: returns an immutable ``RaceResult`` with the full output contract;
  FINISHED ⇒ a positive finite ``race_time_s``, DNF ⇒ ``None``.
- AC-AL3: same seed ⇒ identical result; STRAIGHT consumes the seeded RNG (seed
  matters); RAIL_RIDER uses a constant rail force (seed-independent).
- AC-PU1: no I/O/network, no global state, local seeded RNG, frozen-dataclass output.
- AC-T1 (length slice): a longer track ⇒ a longer ``race_time_s``.
"""

from __future__ import annotations

import math
import random

from .car import Alignment, CarDesign
from .result import (
    EnergyLedger,
    NormalForces,
    Outcome,
    RaceResult,
    TrajectoryPoint,
)
from .track import STANDARD_TRACK, Track
from .units import Length, Mass

# ── Physical constants (physics-spec §1.1) ───────────────────────────────────
_G = 9.81           # gravitational acceleration [m/s²]
_RHO_AIR = 1.225    # air density [kg/m³]
_MAX_MASS = Mass.from_ounces(5.0)  # M_max, the BSA weight limit (AC-W2)
# AC-W2 names the limit two ways — 5.0 oz and (141.748 g) — and treats them as the
# SAME quantity. Converting 5.0 oz gives 0.1417475 kg, but the gram figure the AC
# equally endorses is 0.141748 kg, so a car weighed to exactly 141.748 g would fall
# just outside a strict 5.0-oz threshold. The gap is < 0.001 g — purely an artifact
# of stating the gram figure to three decimals. Compare inclusively within that
# rounding precision so both named representations of the limit agree at the boundary
# (WI5-ADV-001). The tolerance is far smaller than any real over-weight margin (the
# boundary tests probe ≥ 0.01 oz ≈ 0.28 g over), so genuinely over-weight cars stay
# illegal.
_WEIGHT_LIMIT_TOL_KG = 1e-6  # 0.001 g — the precision AC-W2's gram figure is stated to

# ── Rail-friction model (physics-spec §3.3) ──────────────────────────────────
# A poorly-aligned (STRAIGHT) car "ping-pongs" off the centre guide rail: each
# wall strike is a high-amplitude force spike drawn from U(1.5, 3.0) N (spec §3.3,
# AC-AL2 — this is the per-step rail force the car experiences while moving, and the
# spec band ``_rail_force`` reports directly). The car is only in physical contact
# for a fraction of its travel, so the resistive force the *integration loop* applies
# is the drawn spike weighted by a contact-duty fraction (the continuous-equivalent of
# intermittent bounces): the spike magnitude reported per step matches the spec band
# while the averaged loss over the run stays physical. A RAIL_RIDER glides along one
# rail with a small constant force and no ping-pong. Rail friction only acts while the
# car is moving — a stationary car cannot bounce off a wall.
#
# These two rail magnitudes (and the contact duty) are tunable engine parameters (not
# spec-fixed like the axle/drag formulae). They are calibrated so a stable, legal,
# well-placed car (d_COM in the optimal zone, ≥ ~3 oz) actually *coasts across the
# finish line* on the STANDARD_TRACK rather than decelerating to a stop just short of
# it — real 3–4 oz derby cars finish slowly, they do not stall on the flat
# (WI5-ADV-002). A genuinely under-energised car (e.g. a very light 1–2 oz car) still
# runs out of speed metres short and is a real non-finishing run, never teleported to
# the line (WI5-ADV-003).
#
# The two alignment magnitudes also encode the educational claim of the lever
# (AC-AL1): a ping-ponging STRAIGHT car must lose strictly MORE to the rail than a
# rail-rider, so it is slower. The STRAIGHT averaged loss (spike ≈2.25 N × duty) sits
# just above the constant RAIL_RIDER force, keeping the rail-rider faster while both a
# 3 oz STRAIGHT and a 3 oz RAIL_RIDER car still finish and a 2 oz car still stalls
# short. The duty scaling lives in the integration loop (not in ``_rail_force``) so
# the per-step spike ``_rail_force`` returns stays the raw in-band draw the spec and
# AC-AL2 pin.
_RAIL_F_RAIL_RIDER = 0.06          # constant rail force for a rail-riding car [N]
_RAIL_PINGPONG_RANGE = (1.5, 3.0)  # U(min, max) ping-pong spike for a straight car [N]
_RAIL_CONTACT_DUTY = 0.034         # fraction of travel a straight car is rail-in-contact

# ── Stability: a GRADED tippy zone, not a sharp cliff (physics-spec §4.2; graded placement) ──
# The front-axle load fraction N_f/(M·g) = d_COM/L (AC-P4) falls SMOOTHLY toward zero as the
# COM nears the rear axle — nothing physical jumps at a single distance. So stability degrades
# gradually: below _TIPPY_ONSET_FRACTION the front goes light, the car wanders into the rails
# and LOSES SPEED (a rising wander penalty on the rail loss, _wander_penalty below), and only
# when the front load has essentially collapsed (below _COM_UNSTABLE_FRONT_FRACTION, the COM
# almost over the rear axle) can the car not run at all → DNF. This replaces the earlier sharp
# 0.625 in "legible cliff" with the more physically faithful smooth front-load decline: a
# too-rear car finishes but slower, and only the genuine extreme is a DNF. Both thresholds are
# FRACTIONS (not absolute d_COM), so they never invert on non-standard wheelbases (WI6-ADV-001).
# The named 0.625 in spec value (its fraction at the 4.375 in wheelbase) is the wander ONSET.
_TIPPY_ONSET_FRACTION = Length.from_inches(0.625).m / Length.from_inches(4.375).m  # ≈ 0.143
_COM_UNSTABLE_FRONT_FRACTION = 0.06  # front load essentially gone (COM near the rear axle) → DNF
_TIPPY_WANDER_GAIN = 2.4  # magnitude of the front-light wander rail penalty (tuned)
_TIPPY_WANDER_EXPONENT = 2.0  # steep rise of the wander loss from onset toward the crash

# ── Front-load rail tracking: the placement (d_COM) lever (spec §4 / §4.2) ───────
# Real derby tuning: weight biased toward the REAR unloads the front (steering/guiding)
# wheels. Those front wheels are the ones that track against the centre guide rail, so
# the lighter they are loaded the less the car scrubs and wanders into the rail. The
# car's rail-tracking loss therefore scales with the front-axle load fraction
# N_f/(M·g) = d_COM/L (spec §4.1): a rear-biased car (small d_COM) presses its front
# wheels down less, tracks the rail more cleanly, loses less to rail contact, and is
# therefore faster. This is the continuous-range counterpart of the spec §4.2 "wobble
# multiplier" (which diverges as d_COM nears the instability cliff): within the stable
# range the same front-load fraction modulates the rail force smoothly, so the placement
# advantage is a real, graded effect rather than only a cliff.
#
# Modelling placement through the RAIL force (rather than the axle bore) keeps it
# decoupled from the axle-friction lever (μ) — they are physically distinct effects
# (steering/tracking vs. bore friction) and the engine must teach their priority order
# independently (AC-ED1): a rearward COM must help in a way that is NOT just "more axle
# friction reduction", or shifting weight back would be indistinguishable from polishing
# the axles. It is the mechanism for the placement advantage (AC-P1/AC-P2): a stable
# rear-biased car gets a higher exit velocity, a higher finish velocity, and a shorter
# time, WITHOUT injecting any unaccounted kinetic energy. The car still starts at rest,
# so w_gravity stays pure track geometry, independent of d_COM (AC-E4), and the
# per-force ledger (the rail term included) closes to the car's true final KE by
# construction (AC-E1, AC-E2).
#
# SHAPE of the coupling (WI12-ADV-003). The placement advantage must remain a *dominant*
# lever — strictly larger than the axle-friction lever — for ANY all-levers-worst baseline
# across the whole legal mass band, not only at the lightest calibration point (AC-ED1;
# profile: weight & placement is the dominant lever). The friction lever (μ 0.35→0.10)
# removes a roughly mass-independent slice of energy, so the placement lever has to keep up
# with it even at the 5.0 oz legal cap, where the *weight* part of "weight+placement" has no
# headroom left and the whole improvement rides on the COM shift alone. A merely LINEAR
# front-load coupling (1 + k·d_COM/L) is far too shallow there: shifting the COM 1.0 → 0.85
# in changes the front-load fraction by only ~15%, so a linear factor barely moves the rail
# loss and friction overtakes placement for any baseline heavier than ~4.07 oz (WI12-ADV-003).
#
# We instead make the rail-tracking factor a steep POWER of the front-load fraction,
# normalised at a forward reference placement, so that:
#   * at the forward reference (d_COM/L = _FRONT_LOAD_RAIL_REF_FRACTION) the factor is
#     exactly 1.0 — the rail magnitude there is unchanged from the bare calibrated spike,
#     so an all-levers-worst STRAIGHT car still finishes across the legal mass band; and
#   * shifting the COM rearward of that reference drops the factor STEEPLY (∝ fraction**p),
#     so the placement lever sheds enough rail loss to stay strictly above the friction
#     lever for every legal baseline mass (WI12-ADV-003), while the factor stays bounded for
#     a forward (nose-heavy) COM via a gentle linear arm so stable-but-forward cars (AC-P2)
#     and the rear-bias sweep up to d_COM ≈ wheelbase (WI6-ADV-002) still finish.
# The factor is monotone increasing in the front-load fraction throughout, so a more
# rearward COM is always cleaner and faster (AC-P1/AC-P2). These are tunable engine
# parameters (the rail-tracking model is calibration, not a spec-fixed formula).
_FRONT_LOAD_RAIL_REF_FRACTION = (
    Length.from_inches(1.0).m / Length.from_inches(4.375).m
)  # forward reference front-load fraction (d_COM = 1.0 in at the canonical wheelbase)
_FRONT_LOAD_RAIL_EXPONENT = 4.0  # steepness of the rear-bias rail-loss drop (∝ fraction**p)
_FRONT_LOAD_RAIL_FORWARD_SLOPE = 0.5  # gentle linear arm forward of the reference (bounded)

# ── Mass-dependence of rail tracking: the WEIGHT lever's rail component (spec §1.1 / §4) ──
# A heavier car carries more momentum into every rail contact, so it deflects LESS and
# scrubs the centre guide rail less than a light car nudged off line by the same bump — the
# rail-tracking loss falls as mass rises. This is a second, physically-distinct face of the
# weight lever (alongside "more mass ⇒ more PE"): adding mass not only banks more potential
# energy, it also wanders into the rail less, so a heavier car keeps more of that energy.
#
# Without it the weight lever is too shallow near the legal cap to stay the *dominant* lever
# the simulator must teach (AC-ED1; profile "weight & placement first"). Going from a
# heavier-but-still-legal baseline (e.g. 4.25 oz) up to the 5.0 oz cap is only an ~18 % mass
# gain, and a heavier car also loses proportionally more to axle friction (F_axle ∝ M·g), so
# a purely PE-driven weight benefit shrinks below the (roughly mass-independent) μ 0.35→0.10
# friction improvement for any baseline above ~4.1 oz — inverting the taught priority order
# for a child whose car is already on the heavier side (WI12-ADV-003). Damping the rail loss
# as mass rises restores the weight lever's dominance across the whole legal band while
# leaving the heavier-is-faster direction (AC-W1) and w_gravity = M·g·Δh (AC-E4) untouched —
# the rail term is a loss in the ledger, never injected energy, so closure still holds
# (AC-E1/AC-E2). Anchored at the legal cap so a 5.0 oz car's rail magnitude is the bare
# calibrated spike. A tunable rail-model parameter (calibration, not a spec-fixed formula).
_RAIL_MASS_REFERENCE = _MAX_MASS  # rail tracking is calibrated at the 5.0 oz legal cap
_RAIL_MASS_EXPONENT = 1.0  # rail tracking loss scales as (M_ref / M)**q — inverse in mass

# ── Aerodynamic drag effective-area calibration (spec §3.1; PRD A5; feature 0008) ──
# The spec drag law is F_drag = ½·ρ·v²·C_d·A. The frontal area A a caller supplies is the
# body's full bounding-box cross-section (≈ width × height), but only a fraction of that
# bluff box actually meets fresh airstream at derby speeds — the chassis runs millimetres
# above the track in the boundary layer, much of the box sits in its own wake, and ~5 m/s
# is a low-drag regime. So we apply the drag law to an EFFECTIVE area that is a small fixed
# fraction of the bounding box:
#   A_eff = fraction · A_ref · (A / A_ref) ** _DRAG_AREA_EXPONENT,  exponent = 1
#         = fraction · A
# i.e. effective drag area scales LINEARLY with the supplied frontal area — faithful to the
# real F_drag ∝ A relationship. Feature 0008 exposes body width × height as the source of A,
# so a kid genuinely sees a bigger body slow the car (AC-A2), instead of the near-flat
# response the earlier sub-linear curve gave.
#
# What keeps aero the SMALLEST lever (profile/AC-ED1: weight & friction dominate, aero is
# minor) is the small fraction (0.06) holding the ABSOLUTE drag in the right regime — NOT a
# sub-linear curve. Verified empirically when 0008 restored linear scaling: the full WI12
# priority-order + WI8 aero + WI12-ADV adversarial suites still pass — the BLOCK→WEDGE body
# swap stays a smaller race-time win than the wheels lever across PRD A5's band, and aero is
# never the dominant surfaced loss even at a legal-maximum body (test_present_legality_wi08).
# C_d enters as a pure multiplier (drag still rises with C_d and flat length — AC-A1/AC-A2).
# The fraction is a tunable realism parameter (PRD A5), not a spec-fixed constant.
#
# (History: drag was previously damped further by a sub-linear exponent of 0.5; 0008 set it
# to 1.0 after confirming the 0.06 fraction alone preserves the priority order, so body size
# is now physically responsive — real linear-in-area drag.)
_DRAG_EFFECTIVE_AREA_FRACTION = 0.06
_DRAG_AREA_REFERENCE = 0.0028  # m² — PRD A5 documented default body cross-section (A_ref)
_DRAG_AREA_EXPONENT = 1.0      # linear in frontal area (real physics, F_drag ∝ A); feature 0008

# A generous wall-clock guard so a stalled car can never spin forever (TRD §9).
_MAX_SIM_TIME_S = 60.0

# Down-sample the recorded trajectory to at most this many points (PRD A7).
_MAX_TRAJECTORY_POINTS = 500


def simulate(
    car: CarDesign,
    track: Track = STANDARD_TRACK,
    *,
    dt: float = 1e-3,
    seed: float = 0,
) -> RaceResult:
    """Simulate a single car's run down ``track`` and return its :class:`RaceResult`.

    Raises ``ValueError`` if ``dt`` is non-finite or ``<= 0``, or if ``seed`` is
    non-finite. A non-finite seed (NaN / ±inf) is a malformed, non-reproducible
    input: ``random.Random(nan)`` silently falls back to entropy seeding, which
    would break determinism (AC-AL3), so it is rejected at the boundary just as
    ``dt`` is.
    """
    if not math.isfinite(dt) or dt <= 0.0:
        raise ValueError(f"dt must be a finite > 0, got {dt}")
    if not math.isfinite(seed):
        raise ValueError(f"seed must be finite, got {seed}")

    rng = random.Random(seed)

    mass = car.mass.kg
    wheelbase = car.wheelbase.m
    d_com = car.com_ahead_of_rear_axle.m
    legal_weight = mass <= _MAX_MASS.kg + _WEIGHT_LIMIT_TOL_KG

    # Normal-force distribution on the flat (spec §4.1). On the flat the whole
    # weight rests on the axles; the front share grows with d_COM / L.
    weight = mass * _G
    n_front = weight * (d_com / wheelbase)
    n_rear = weight * (1.0 - d_com / wheelbase)
    normal_forces = NormalForces(front=n_front, rear=n_rear)

    # Rotational coupling: the wheels must spin up as the car accelerates, so the
    # effective inertia is M + N·I/R_outer² (spec §6 rotational_inertia_modifier).
    r_outer = car.wheels.outer_radius.m
    n_wheels = car.wheels.count_touching
    inertia_per_wheel = car.wheels.moment_of_inertia()
    rotational_inertia_modifier = n_wheels * inertia_per_wheel / (r_outer**2)
    effective_inertia = mass + rotational_inertia_modifier

    # Axle bore friction factor (spec §3.2 / TRD §4): each touching wheel carries the
    # per-wheel normal load F_normal/N and contributes μ·(r_axle/R_outer)·(F_normal/N);
    # summing over the N wheels CANCELS the count, so the total axle friction is
    # F_axle = μ·(r_axle/R_outer)·F_normal — count-INDEPENDENT (TRD §4: "load shared by
    # count"). The earlier ``n_wheels ·`` multiplier left the count uncancelled, inflating
    # the loss ~N× and making it scale 4/3 with wheel count, which the spec forbids
    # (WI7-ADV-001). The legitimate 3-vs-4 advantage (AC-WH1) comes from the rotational
    # inertia term (M + N·I/R²), not from a count-scaled friction.
    mu = car.axle.friction_coefficient
    axle_factor = mu * (car.wheels.axle_radius.m / r_outer)

    body = car.body
    # Spec drag F_drag = ½·ρ·v²·C_d·A_eff, with the supplied bounding-box area A scaled to
    # its effective drag area (only a fraction of the bluff box meets fresh airstream — see
    # the constants' note). With _DRAG_AREA_EXPONENT == 1 this is A_eff = fraction · A,
    # LINEAR in frontal area (real physics, F_drag ∝ A — feature 0008), so a bigger body
    # genuinely loses more speed (AC-A2). The small fraction keeps the absolute drag in the
    # correct minor regime, so aero stays the smallest lever (AC-ED1, verified by the WI12
    # priority-order suite). C_d enters as a pure multiplier, so drag still rises with C_d
    # and with flat length (AC-A1/AC-A2). Anchored at A_ref so the default area is exact.
    effective_area = (
        _DRAG_EFFECTIVE_AREA_FRACTION
        * _DRAG_AREA_REFERENCE
        * (body.frontal_area / _DRAG_AREA_REFERENCE) ** _DRAG_AREA_EXPONENT
    )
    drag_factor = 0.5 * _RHO_AIR * body.drag_coefficient * effective_area

    track_length = track.ramp_length.m + track.flat_length.m
    ramp_length = track.ramp_length.m

    # Track-geometry vertical drop of the COM (spec §1.2 / §2): the straight ramp drops
    # by ramp_length·sinθ and the smooth transition arc by R·(1 − cosθ); the flat adds
    # none. This is pure geometry — independent of mass and of d_COM — so it is both the
    # analytic gravity work the integrated ledger converges to (AC-E4) and the reported
    # pe_initial (= M·g·Δh_com).
    ramp_angle_rad = track.ramp_angle.radians
    delta_h_com = ramp_length * math.sin(ramp_angle_rad) + track.transition_radius.m * (
        1.0 - math.cos(ramp_angle_rad)
    )
    pe_initial = mass * _G * delta_h_com

    # Front-axle load fraction N_f/(M·g) = d_COM/L (spec §4.1). Drives the rail-tracking
    # loss below: a more rearward COM (smaller fraction) loads the steering wheels less,
    # tracks the rail more cleanly, loses less, and is faster (AC-P1/AC-P2). Stays in
    # [0, 1) for a stable car (d_COM < L).
    front_load_fraction = d_com / wheelbase
    rail_tracking_factor = (
        _rail_tracking_factor(front_load_fraction) + _wander_penalty(front_load_fraction)
    ) * (_RAIL_MASS_REFERENCE.kg / mass) ** _RAIL_MASS_EXPONENT

    # An unstable rear bias is a DNF before the run even starts: the front normal
    # force has collapsed, so the car wobbles off the line (spec §4.2, PRD A2).
    # The outcome is fully determined here, so we short-circuit instead of running
    # the integration loop to the wall-clock guard — a predetermined DNF must meet
    # the performance budget like any other call (profile quality_bars; PRD §7 NFR).
    # The car never leaves the start line, so the trajectory is the single at-rest
    # point and the energy ledger is empty (no work done before the crash).
    unstable = (d_com / wheelbase) < _COM_UNSTABLE_FRONT_FRACTION
    if unstable:
        return RaceResult(
            outcome=Outcome.DNF,
            race_time_s=None,
            exit_velocity=0.0,
            top_speed=0.0,
            finish_velocity=0.0,
            energy=EnergyLedger(
                pe_initial=pe_initial,
                ke_linear_final=0.0,
                ke_rotational_final=0.0,
                w_gravity=0.0,
                w_drag=0.0,
                w_axle=0.0,
                w_rail=0.0,
            ),
            normal_forces=normal_forces,
            legal_weight=legal_weight,
            trajectory=(
                TrajectoryPoint(
                    t=0.0,
                    position=0.0,
                    velocity=0.0,
                    angle=track.angle_at(0.0),
                ),
            ),
        )

    # ── Integration state: the car is released from REST at the start line ─────
    # No injected initial velocity. The placement (d_COM) advantage is carried by the
    # front-load scrub friction (``steer_load_factor`` above), not by a head-start KE —
    # so all the car's kinetic energy is earned through the integrated descent and the
    # energy ledger closes to the car's true final KE by construction (AC-E1, AC-E2),
    # while w_gravity remains pure track geometry, independent of d_COM (AC-E4).
    position = 0.0
    velocity = 0.0
    elapsed = 0.0
    top_speed = 0.0
    exit_velocity = 0.0
    crossed_ramp = False

    # The per-force ledger starts empty and is accumulated step-by-step over the run.
    w_gravity = 0.0
    w_drag = 0.0
    w_axle = 0.0
    w_rail = 0.0

    samples: list[TrajectoryPoint] = [
        TrajectoryPoint(
            t=0.0, position=0.0, velocity=0.0, angle=track.angle_at(0.0)
        )
    ]

    outcome = Outcome.FINISHED
    finished = False

    while True:
        theta = track.angle_at(position)

        f_gravity = mass * _G * math.sin(theta)
        f_normal = mass * _G * math.cos(theta)
        f_drag = drag_factor * velocity**2
        # Axle bore friction (spec §3.2): F_axle = μ·(r_axle/R_outer)·F_normal, summed
        # over the touching wheels (the per-wheel load shares cancel the count). This is
        # the friction lever (μ) alone — the placement lever now rides the rail force
        # below, keeping the two physically distinct effects independent (AC-ED1).
        f_axle = axle_factor * f_normal
        # Per-step rail force (spec §3.3 / §4): RAIL_RIDER's constant, or a STRAIGHT
        # car's raw ping-pong spike drawn in the [1.5, 3.0] N band (AC-AL2). The STRAIGHT
        # car is only rail-in-contact for a fraction of its travel, so the *applied*
        # resistive force is that spike weighted by the contact-duty fraction (the
        # continuous-equivalent of intermittent wall strikes); RAIL_RIDER glides
        # continuously, so its constant force is applied as-is. Both are then weighted by
        # the front-load ``rail_tracking_factor`` (1 + k·d_COM/L): a rear-biased COM
        # unloads the steering wheels, tracks the rail more cleanly, and loses less to
        # rail contact (spec §4, AC-P1/AC-P2) — a smaller d_COM gives a smaller factor
        # and a faster car. Scaling here (not inside ``_rail_force``) keeps the reported
        # per-step spike the raw in-band draw AC-AL2 pins.
        rail_spike = _rail_force(car.alignment, rng, velocity=velocity)
        f_rail = rail_tracking_factor * (
            rail_spike * _RAIL_CONTACT_DUTY
            if car.alignment is Alignment.STRAIGHT
            else rail_spike
        )

        f_net = f_gravity - (f_drag + f_axle + f_rail)
        acceleration = f_net / effective_inertia

        new_velocity = velocity + acceleration * dt
        if new_velocity < 0.0:
            # A stalled car does not roll backward up the flat (spec §6 clamp).
            new_velocity = 0.0
        dx = new_velocity * dt

        # Accumulate the energy ledger over the *average* velocity of the step
        # (semi-implicit Euler / trapezoidal work), so the discrete work-energy
        # theorem closes by construction to machine precision (spec §2, AC-E1):
        # with the constant per-step force ``f_net`` and acceleration ``a``,
        #   f_net·½(v+v_new)·dt = ½·m_eff·a·dt·(v+v_new)
        #                       = ½·m_eff·(v_new² − v²) = ΔKE   (exact).
        # Using ``new_velocity·dt`` instead would leave the ½·a²·dt² Euler
        # truncation per step, accumulating a ~1e-3 ledger gap (WI6-ADV-002).
        # Position still advances by ``new_velocity·dt`` (unchanged timing).
        dx_work = 0.5 * (velocity + new_velocity) * dt
        w_gravity += f_gravity * dx_work
        w_drag += f_drag * dx_work
        w_axle += f_axle * dx_work
        w_rail += f_rail * dx_work

        new_position = position + dx
        elapsed += dt
        velocity = new_velocity

        if velocity > top_speed:
            top_speed = velocity

        # Record the exit velocity the first time we leave the ramp.
        if not crossed_ramp and new_position >= ramp_length:
            crossed_ramp = True
            exit_velocity = velocity

        # Finish-line crossing: linearly interpolate the time so race_time_s is
        # not quantized to dt (PRD A3).
        if new_position >= track_length:
            overshoot = new_position - track_length
            frac = 1.0 - (overshoot / dx if dx > 0.0 else 0.0)
            elapsed = (elapsed - dt) + frac * dt
            position = track_length
            samples.append(
                TrajectoryPoint(
                    t=elapsed,
                    position=position,
                    velocity=velocity,
                    angle=track.angle_at(position),
                )
            )
            finished = True
            break

        position = new_position
        samples.append(
            TrajectoryPoint(
                t=elapsed,
                position=position,
                velocity=velocity,
                angle=theta,
            )
        )

        # Stall guard (TRD §9): a car at rest that cannot accelerate forward makes no
        # more progress, so the run terminates here rather than grinding to the
        # wall-clock guard. A stalled car did NOT reach the finish line — wherever it
        # stopped (on the ramp or out on the flat) it ran out of energy short of the
        # line, so it is a non-finishing run, not a finisher.
        #
        # The previous code (WI5-ADV-002 fix) over-corrected: it teleported any car that
        # had merely left the ramp straight to ``track_length`` and marked it FINISHED,
        # fabricating a finish at rest no matter how far short it actually stopped — a
        # light car stalling metres short was reported as a finisher at the full length
        # with finish_velocity = 0 and a trajectory that jumped to the line in zero time
        # (WI5-ADV-003), which also inverted AC-W1 across the light-car range
        # (WI5-ADV-004). A car that genuinely coasts to the line crosses it while still
        # moving and is caught by the finish-line branch above; this branch is only
        # reached when the car has stopped *before* the line, which is not a finish.
        #
        # A *stable*, legal, well-placed car has enough energy to coast across (the rail
        # magnitudes are calibrated for that, see _RAIL_* above), so it finishes via the
        # crossing branch; only a genuinely under-energised car reaches here and it is a
        # real non-finishing run (DNF, race_time_s = None — AC-O2). DNF caused by the
        # instability cliff (d_COM < threshold) is short-circuited before the loop.
        if velocity <= 0.0 and acceleration <= 0.0:
            outcome = Outcome.DNF
            break
        if elapsed >= _MAX_SIM_TIME_S:
            outcome = Outcome.DNF
            break

    if finished and outcome is Outcome.FINISHED:
        race_time_s: float | None = elapsed
        finish_velocity = velocity
    else:
        outcome = Outcome.DNF
        race_time_s = None
        finish_velocity = velocity

    # Report the car's true final kinetic energy: the linear share ½·M·v² and the
    # rotational share Σ ½·I·ω² (with ω = v / R_outer), exactly as the EnergyLedger
    # fields and AC-E2 define them (WI6-ADV-003). Because the head-start is integrated
    # as real gravity work over the COM's true descent (not an unaccounted injected
    # velocity), this physical KE closes the per-force ledger by construction — the
    # gravity work less the friction/drag/rail losses equals it (AC-E1, WI6-ADV-002).
    ke_linear_final = 0.5 * mass * finish_velocity**2
    ke_rotational_final = 0.5 * rotational_inertia_modifier * finish_velocity**2

    energy = EnergyLedger(
        pe_initial=pe_initial,
        ke_linear_final=ke_linear_final,
        ke_rotational_final=ke_rotational_final,
        w_gravity=w_gravity,
        w_drag=w_drag,
        w_axle=w_axle,
        w_rail=w_rail,
    )

    return RaceResult(
        outcome=outcome,
        race_time_s=race_time_s,
        exit_velocity=exit_velocity,
        top_speed=top_speed,
        finish_velocity=finish_velocity,
        energy=energy,
        normal_forces=normal_forces,
        legal_weight=legal_weight,
        trajectory=_downsample(samples),
    )


def _rail_tracking_factor(front_load_fraction: float) -> float:
    """The placement (d_COM) rail-tracking multiplier (spec §4; WI12-ADV-003).

    A multiplier on the per-step rail force that encodes the placement lever: a rear-biased
    COM (small ``front_load_fraction`` = d_COM/L) unloads the steering wheels, tracks the
    centre rail more cleanly, loses less, and is faster (AC-P1/AC-P2). The factor is
    normalised to exactly 1.0 at the forward reference fraction (so the bare rail spike is
    unchanged there and an all-levers-worst car still finishes across the legal mass band),
    drops STEEPLY as a power of the fraction for a more rearward COM (so the placement lever
    stays strictly the dominant lever vs. axle friction for every legal baseline mass —
    AC-ED1 / WI12-ADV-003), and grows only gently and linearly forward of the reference so
    stable-but-forward cars (AC-P2) and the full rear-bias sweep to d_COM ≈ wheelbase
    (WI6-ADV-002) still finish. Monotone increasing in the fraction throughout.
    """
    normalised = front_load_fraction / _FRONT_LOAD_RAIL_REF_FRACTION
    if normalised <= 1.0:
        return float(normalised**_FRONT_LOAD_RAIL_EXPONENT)
    return 1.0 + _FRONT_LOAD_RAIL_FORWARD_SLOPE * (normalised - 1.0)


def _wander_penalty(front_load_fraction: float) -> float:
    """Extra rail-tracking loss from a front-light car wandering off the centre line. Zero
    at/above the tippy onset; rises steeply (a power) as the front load falls toward the
    crash threshold, so a too-rear (but not yet failed) car finishes progressively SLOWER —
    graded instability, not a cliff. Continuous in the front-load fraction (no physics jump)."""
    if front_load_fraction >= _TIPPY_ONSET_FRACTION:
        return 0.0
    span = _TIPPY_ONSET_FRACTION - _COM_UNSTABLE_FRONT_FRACTION
    x = (_TIPPY_ONSET_FRACTION - front_load_fraction) / span  # 0 at onset → 1 approaching crash
    x = min(1.0, max(0.0, x))
    return float(_TIPPY_WANDER_GAIN * x**_TIPPY_WANDER_EXPONENT)


def _rail_force(
    alignment: Alignment,
    rng: random.Random,
    *,
    velocity: float,
) -> float:
    """The per-step rail force at the current step (physics-spec §3.3, AC-AL2).

    RAIL_RIDER returns a constant, RNG-free force (seed-independent). STRAIGHT draws a
    fresh ping-pong spike from the seeded RNG each step, in the spec's [1.5, 3.0] N band
    (AC-AL2) — this is the raw per-step force the moving car experiences off the rail;
    the integration loop applies the contact-duty weighting that turns the intermittent
    wall strikes into a continuous-equivalent resistive force. A stationary car cannot
    bounce off the rail, so a STRAIGHT car feels nothing while at rest (and still
    consumes one RNG draw per step, keeping the seeded path deterministic). An unstable
    rear bias never reaches this code: it is a predetermined DNF that short-circuits
    before the integration loop.
    """
    if alignment is Alignment.RAIL_RIDER:
        return _RAIL_F_RAIL_RIDER
    lo, hi = _RAIL_PINGPONG_RANGE
    spike = rng.uniform(lo, hi)
    if velocity <= 0.0:
        return 0.0
    return spike


def _downsample(points: list[TrajectoryPoint]) -> tuple[TrajectoryPoint, ...]:
    """Evenly down-sample ``points`` to at most ``_MAX_TRAJECTORY_POINTS`` (PRD A7).

    Always keeps the first and last point so the trajectory still spans the full run.
    """
    n = len(points)
    if n <= _MAX_TRAJECTORY_POINTS:
        return tuple(points)
    step = math.ceil(n / _MAX_TRAJECTORY_POINTS)
    sampled = points[::step]
    if sampled[-1] is not points[-1]:
        sampled.append(points[-1])
    return tuple(sampled)
