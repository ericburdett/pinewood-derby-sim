"""WI-8 — Aerodynamics lever: a lower-drag body is faster, and the energy lost to
drag scales with C_d, frontal area, and the length of the high-speed flat run.

Behavior-driven tests written against the engine's public contract (``simulate`` +
the frozen ``RaceResult``). Imports live inside each test body so a missing/renamed
symbol fails *that criterion* independently (true per-criterion isolation) rather
than aborting whole-file collection.

Traceability to the WI-8 acceptance criteria (PRD §6; physics-spec §3.1; TRD §4
force model / §11):

- AC-A1 (PRD l.118): a WEDGE body (C_d = 0.20) finishes with a strictly smaller
  race_time_s than a wood-BLOCK body (C_d = 0.85), all else equal.
- AC-A2 (PRD l.120): energy.w_drag strictly INCREASES with C_d, strictly INCREASES
  with frontal_area, and strictly INCREASES with flat-section length (drag bites
  more at higher speed on a longer flat). Each tested all-else-equal on FINISHED
  runs.

Aerodynamics is intentionally the SMALLEST lever (that holistic ordering is
cross-checked in WI-12 / AC-ED1); these tests assert only the within-lever
*direction / monotonicity*, never an absolute magnitude.

Integrity / determinism: every test fixes dt and seed (no clock / network / unseeded
RNG) and uses RAIL_RIDER alignment so the seeded ping-pong rail draw never confounds
a directional aero claim. Drag is the only force that depends on C_d / frontal area
(F_drag = ½·ρ·v²·C_d·A, spec §3.1), so holding everything else equal isolates the
lever cleanly. This file is NEW; it modifies, skips, or deletes no existing test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult
    from pinewood_derby.track import Track

# Spec-anchored body-shape drag coefficients (physics-spec §3.1; TRD §5 / §3 presets),
# pinned here so the AC-A1 comparison references the contract, not the engine.
CD_WEDGE = 0.20
CD_BLOCK = 0.85


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — build valid inputs from plain numbers via the value objects.
# Mirrors tests/test_engine_wheels_wi7.py so construction stays consistent.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_car(
    *,
    mass_oz: float = 5.0,
    com_ahead_of_rear_axle_in: float = 0.85,
    wheelbase_in: float = 4.375,
    alignment: str = "RAIL_RIDER",
    count_touching: int = 4,
    wheel_oz: float = 0.09,
    outer_radius_in: float = 0.595,
    inner_radius_in: float = 0.37,
    axle_radius_in: float = 0.045,
    drag_coefficient: float = 0.30,
    frontal_area: float = 0.0028,
    friction_coefficient: float = 0.20,
) -> CarDesign:
    """A valid, FINISHED-capable baseline car. ``alignment`` is the enum member name.

    Only the aerodynamic fields (``drag_coefficient``, ``frontal_area``) are varied
    across the WI-8 comparisons; everything else is held identical so each test
    isolates exactly one lever ("all else equal").
    """
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(wheelbase_in),
        wheels=Wheels(
            count_touching=count_touching,
            wheel_mass=Mass.from_ounces(wheel_oz),
            outer_radius=Length.from_inches(outer_radius_in),
            inner_radius=Length.from_inches(inner_radius_in),
            axle_radius=Length.from_inches(axle_radius_in),
        ),
        body=BodyShape(drag_coefficient=drag_coefficient, frontal_area=frontal_area),
        axle=Axle(friction_coefficient=friction_coefficient),
        alignment=Alignment[alignment],
    )


def _make_track(*, flat_feet: float = 32.0) -> Track:
    """A STANDARD-geometry track with a configurable flat-section length.

    The ramp (10 ft @ 30°) and transition arc (6 in radius) are held identical so the
    flat-length comparison (AC-A2) varies only the high-speed runout, not the energy
    the car arrives with. ``flat_feet`` defaults to the STANDARD_TRACK flat (32 ft).
    """
    from pinewood_derby.track import Track
    from pinewood_derby.units import Angle, Length

    return Track(
        ramp_length=Length.from_feet(10.0),
        ramp_angle=Angle.from_degrees(30.0),
        transition_radius=Length.from_inches(6.0),
        flat_length=Length.from_feet(flat_feet),
    )


def _simulate(
    car: CarDesign,
    track: Track | None = None,
    *,
    dt: float = 1e-3,
    seed: int = 0,
) -> RaceResult:
    from pinewood_derby.engine import simulate

    if track is None:
        return simulate(car, dt=dt, seed=seed)
    return simulate(car, track, dt=dt, seed=seed)


def _finished(result: RaceResult) -> bool:
    from pinewood_derby.result import Outcome

    return result.outcome is Outcome.FINISHED


# ───────────────────────────────────────────────────────────────────────────── #
# AC-A1 — a wedge body (C_d = 0.20) finishes strictly faster than a wood-block body
# (C_d = 0.85), all else equal. (spec §3.1)
# ───────────────────────────────────────────────────────────────────────────── #
def test_aca1_wedge_finishes_strictly_faster_than_block() -> None:
    """Two cars identical except the drag coefficient (wedge 0.20 vs block 0.85),
    both FINISHED: the lower-drag wedge must finish strictly sooner. Less drag force
    (F_drag = ½·ρ·v²·C_d·A) means more of the car's energy stays kinetic."""
    from pinewood_derby.track import STANDARD_TRACK

    wedge = _simulate(
        _make_car(drag_coefficient=CD_WEDGE), STANDARD_TRACK, seed=0
    )
    block = _simulate(
        _make_car(drag_coefficient=CD_BLOCK), STANDARD_TRACK, seed=0
    )

    assert _finished(wedge), "wedge car should FINISH for a valid comparison"
    assert _finished(block), "block car should FINISH for a valid comparison"
    assert wedge.race_time_s is not None and block.race_time_s is not None
    assert wedge.race_time_s < block.race_time_s, (
        f"wedge car ({wedge.race_time_s:.6f}s) must beat the block car "
        f"({block.race_time_s:.6f}s) — a lower drag coefficient is faster, all else equal"
    )


def test_aca1_wedge_loses_strictly_less_energy_to_drag_than_block() -> None:
    """The mechanism behind the faster wedge time: the lower-C_d body sheds strictly
    less energy to drag over the run, so it keeps more speed."""
    from pinewood_derby.track import STANDARD_TRACK

    wedge = _simulate(
        _make_car(drag_coefficient=CD_WEDGE), STANDARD_TRACK, seed=0
    )
    block = _simulate(
        _make_car(drag_coefficient=CD_BLOCK), STANDARD_TRACK, seed=0
    )

    assert _finished(wedge) and _finished(block)
    assert wedge.energy.w_drag < block.energy.w_drag, (
        f"wedge drag loss ({wedge.energy.w_drag:.6f} J) must be strictly less than the "
        f"block's ({block.energy.w_drag:.6f} J)"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-A2 (i) — energy.w_drag strictly INCREASES with C_d, all else equal, on FINISHED
# runs. (spec §3.1)
# ───────────────────────────────────────────────────────────────────────────── #
def test_aca2_wdrag_strictly_increases_with_drag_coefficient() -> None:
    """Sweeping C_d upward (all else identical) must strictly increase the energy lost
    to drag. Tested across an increasing sequence so the relationship is monotone, not
    just true at the endpoints."""
    from pinewood_derby.track import STANDARD_TRACK

    cds = [0.20, 0.40, 0.60, 0.85]
    results = [
        _simulate(_make_car(drag_coefficient=cd), STANDARD_TRACK, seed=0) for cd in cds
    ]
    for cd, r in zip(cds, results, strict=True):
        assert _finished(r), f"car with C_d={cd} should FINISH for a valid comparison"

    w_drags = [r.energy.w_drag for r in results]
    for cd_lo, cd_hi, w_lo, w_hi in zip(
        cds[:-1], cds[1:], w_drags[:-1], w_drags[1:], strict=True
    ):
        assert w_hi > w_lo, (
            f"w_drag must strictly increase with C_d: C_d={cd_lo}->{w_lo:.6f} J but "
            f"C_d={cd_hi}->{w_hi:.6f} J (not strictly greater)"
        )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-A2 (ii) — energy.w_drag strictly INCREASES with frontal area, all else equal,
# on FINISHED runs. (spec §3.1)
# ───────────────────────────────────────────────────────────────────────────── #
def test_aca2_wdrag_strictly_increases_with_frontal_area() -> None:
    """A larger frontal area presents more body to the air, so (all else identical) the
    energy lost to drag must strictly increase. Tested across an increasing sequence so
    the relationship is monotone."""
    from pinewood_derby.track import STANDARD_TRACK

    areas = [0.0021, 0.0028, 0.0042, 0.0056]
    results = [
        _simulate(_make_car(frontal_area=a), STANDARD_TRACK, seed=0) for a in areas
    ]
    for a, r in zip(areas, results, strict=True):
        assert _finished(r), f"car with area={a} should FINISH for a valid comparison"

    w_drags = [r.energy.w_drag for r in results]
    for a_lo, a_hi, w_lo, w_hi in zip(
        areas[:-1], areas[1:], w_drags[:-1], w_drags[1:], strict=True
    ):
        assert w_hi > w_lo, (
            f"w_drag must strictly increase with frontal area: A={a_lo}->{w_lo:.6f} J "
            f"but A={a_hi}->{w_hi:.6f} J (not strictly greater)"
        )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-A2 (iii) — energy.w_drag strictly INCREASES with flat-section length: drag bites
# more at higher speed over a longer high-speed runout, all else equal, on FINISHED
# runs. (spec §3.1)
# ───────────────────────────────────────────────────────────────────────────── #
def test_aca2_wdrag_strictly_increases_with_flat_length() -> None:
    """The same car, released identically down the same ramp, run on tracks whose flat
    runout grows: each extra metre of flat is travelled near top speed, where F_drag
    (∝ v²) is largest, so the cumulative drag loss must strictly increase with the flat
    length. The ramp and transition arc are held identical so only the high-speed flat
    varies (the car arrives at the flat with the same energy each time)."""
    flats = [20.0, 28.0, 36.0, 44.0]
    results = [
        _simulate(_make_car(), _make_track(flat_feet=f), seed=0) for f in flats
    ]
    for f, r in zip(flats, results, strict=True):
        assert _finished(r), (
            f"car on a {f} ft flat should FINISH for a valid comparison"
        )

    w_drags = [r.energy.w_drag for r in results]
    for f_lo, f_hi, w_lo, w_hi in zip(
        flats[:-1], flats[1:], w_drags[:-1], w_drags[1:], strict=True
    ):
        assert w_hi > w_lo, (
            f"w_drag must strictly increase with flat length: {f_lo} ft->{w_lo:.6f} J "
            f"but {f_hi} ft->{w_hi:.6f} J (not strictly greater)"
        )


def test_aca2_zero_baseline_wdrag_is_positive_on_a_finished_run() -> None:
    """Sanity floor for the monotonicity claims: a FINISHED run actually loses some
    energy to drag (w_drag > 0 and finite), so the 'strictly increases' comparisons are
    measuring a real, non-degenerate quantity rather than a flat zero."""
    import math

    from pinewood_derby.track import STANDARD_TRACK

    r = _simulate(_make_car(), STANDARD_TRACK, seed=0)
    assert _finished(r)
    assert math.isfinite(r.energy.w_drag)
    assert r.energy.w_drag > 0.0, (
        f"a moving FINISHED car must lose some energy to drag, got w_drag="
        f"{r.energy.w_drag}"
    )
