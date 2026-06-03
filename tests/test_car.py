"""WI-3 — CarDesign + sub-objects (Wheels, BodyShape, Axle, Alignment).

Behavior-driven RED tests, written before implementation. The module
``pinewood_derby.car`` does not exist yet, so each test imports it inside the test
body: a missing module then fails each criterion *independently* (true per-criterion
RED) instead of aborting whole-file collection with a single import error.

Traceability to the WI-3 acceptance criteria (PRD §6; TRD §3 data model, §6
validation; physics-spec §2.1/§2.2/§3.1/§3.2):

- AC-W3: CarDesign with mass <= 0 raises ValueError; mass > limit does NOT raise.
- AC-P5: com_ahead_of_rear_axle outside (0, wheelbase) raises ValueError.
- AC-WH3: I = ½·m_w·(R_outer² + R_inner²); invalid wheel geometry
  (R_inner >= R_outer, r_axle >= R_outer, any radius/mass <= 0) and
  count_touching not in {3, 4} raise ValueError.
- AC-A3: BodyShape drag_coefficient <= 0 or frontal_area <= 0 raises ValueError;
  WEDGE (C_d=0.20) and BLOCK (C_d=0.85) presets exist.
- AC-F2 (validation portion): Axle friction_coefficient < 0 raises ValueError;
  POLISHED_GRAPHITE (0.10) and UNPREPARED (0.35) presets exist.
- Immutability: all CarDesign sub-objects are frozen and validate once in
  __post_init__.

All tests are deterministic: no clock, network, or RNG. The car model is pure.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels

# Spec-anchored preset values (physics-spec §3.1/§3.2). Mirrored here so assertions
# are anchored to the spec, not to whatever the implementation happens to pick.
CD_WEDGE = 0.20
CD_BLOCK = 0.85
MU_POLISHED_GRAPHITE = 0.10
MU_UNPREPARED = 0.35

# A nominal, valid frontal area (m²) and drag coefficient for happy-path construction.
VALID_FRONTAL_AREA = 0.0028
VALID_CD = 0.30

ABS_TOL = 1e-12


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — construct valid sub-objects from plain numbers via unit value objects.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_wheels(
    *,
    count_touching: int = 4,
    wheel_mass_oz: float = 0.09,
    outer_radius_in: float = 0.595,
    inner_radius_in: float = 0.37,
    axle_radius_in: float = 0.045,
) -> Wheels:
    from pinewood_derby.car import Wheels
    from pinewood_derby.units import Length, Mass

    return Wheels(
        count_touching=count_touching,
        wheel_mass=Mass.from_ounces(wheel_mass_oz),
        outer_radius=Length.from_inches(outer_radius_in),
        inner_radius=Length.from_inches(inner_radius_in),
        axle_radius=Length.from_inches(axle_radius_in),
    )


def _make_body(
    *,
    drag_coefficient: float = VALID_CD,
    frontal_area: float = VALID_FRONTAL_AREA,
) -> BodyShape:
    from pinewood_derby.car import BodyShape

    return BodyShape(drag_coefficient=drag_coefficient, frontal_area=frontal_area)


def _make_axle(*, friction_coefficient: float = 0.20) -> Axle:
    from pinewood_derby.car import Axle

    return Axle(friction_coefficient=friction_coefficient)


def _make_car(
    *,
    mass_oz: float = 5.0,
    com_ahead_of_rear_axle_in: float = 0.85,
    wheelbase_in: float = 4.375,
    wheels: Wheels | None = None,
    body: BodyShape | None = None,
    axle: Axle | None = None,
    alignment: Alignment | None = None,
) -> CarDesign:
    from pinewood_derby.car import Alignment, CarDesign
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(wheelbase_in),
        wheels=wheels if wheels is not None else _make_wheels(),
        body=body if body is not None else _make_body(),
        axle=axle if axle is not None else _make_axle(),
        alignment=alignment if alignment is not None else Alignment.STRAIGHT,
    )


# ───────────────────────────────────────────────────────────────────────────── #
# Happy path — valid construction (the positive cases the validators must allow).
# ───────────────────────────────────────────────────────────────────────────── #
def test_valid_cardesign_constructs_successfully() -> None:
    from pinewood_derby.car import CarDesign

    car = _make_car()
    assert isinstance(car, CarDesign)


def test_valid_subobjects_construct_successfully() -> None:
    from pinewood_derby.car import Axle, BodyShape, Wheels

    assert isinstance(_make_wheels(), Wheels)
    assert isinstance(_make_body(), BodyShape)
    assert isinstance(_make_axle(), Axle)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-W3 — CarDesign with mass <= 0 raises ValueError; over-weight does NOT raise.
# ───────────────────────────────────────────────────────────────────────────── #
def test_acw3_zero_mass_raises() -> None:
    with pytest.raises(ValueError):
        _make_car(mass_oz=0.0)


def test_acw3_negative_mass_raises() -> None:
    with pytest.raises(ValueError):
        _make_car(mass_oz=-1.0)


def test_acw3_overweight_mass_does_not_raise() -> None:
    """Over the 5.0 oz limit is reported later (legal_weight=False, AC-W2/A1), not a
    construction error. This pins the rule that physics does not enforce the weight cap."""
    from pinewood_derby.car import CarDesign

    car = _make_car(mass_oz=7.5)  # well over the 5.0 oz limit
    assert isinstance(car, CarDesign)


def test_acw3_mass_at_limit_does_not_raise() -> None:
    from pinewood_derby.car import CarDesign

    car = _make_car(mass_oz=5.0)
    assert isinstance(car, CarDesign)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-P5 — com_ahead_of_rear_axle outside (0, wheelbase) raises ValueError.
# ───────────────────────────────────────────────────────────────────────────── #
def test_acp5_zero_com_raises() -> None:
    """The interval is open at 0: d_COM == 0 is invalid."""
    with pytest.raises(ValueError):
        _make_car(com_ahead_of_rear_axle_in=0.0)


def test_acp5_negative_com_raises() -> None:
    with pytest.raises(ValueError):
        _make_car(com_ahead_of_rear_axle_in=-0.5)


def test_acp5_com_equal_to_wheelbase_raises() -> None:
    """The interval is open at the wheelbase: d_COM == wheelbase is invalid."""
    with pytest.raises(ValueError):
        _make_car(com_ahead_of_rear_axle_in=4.375, wheelbase_in=4.375)


def test_acp5_com_greater_than_wheelbase_raises() -> None:
    with pytest.raises(ValueError):
        _make_car(com_ahead_of_rear_axle_in=5.0, wheelbase_in=4.375)


def test_acp5_com_strictly_inside_interval_is_valid() -> None:
    """Interior values of (0, wheelbase) must construct — pins the open interval so the
    validator cannot over-reject valid placements."""
    from pinewood_derby.car import CarDesign

    for d_in in (0.001, 1.0, 2.1875, 4.374):
        car = _make_car(com_ahead_of_rear_axle_in=d_in, wheelbase_in=4.375)
        assert isinstance(car, CarDesign)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-WH3 — moment of inertia formula I = ½·m_w·(R_outer² + R_inner²).
# ───────────────────────────────────────────────────────────────────────────── #
def test_acwh3_moment_of_inertia_matches_formula() -> None:
    """I = ½·m_w·(R_outer² + R_inner²), in SI (kg·m²), independent of magic constants:
    computed directly from the wheel's own m_w, R_outer, R_inner."""
    wheels = _make_wheels(
        wheel_mass_oz=0.09,
        outer_radius_in=0.595,
        inner_radius_in=0.37,
    )
    from pinewood_derby.units import Length, Mass

    m_w = Mass.from_ounces(0.09).kg
    r_o = Length.from_inches(0.595).m
    r_i = Length.from_inches(0.37).m
    expected = 0.5 * m_w * (r_o**2 + r_i**2)

    assert wheels.moment_of_inertia() == pytest.approx(expected, rel=1e-12, abs=ABS_TOL)


def test_acwh3_moment_of_inertia_scales_linearly_with_mass() -> None:
    """Doubling wheel mass doubles I (½·m_w·(...) is linear in m_w) — behavioral check
    of the formula independent of absolute geometry constants."""
    light = _make_wheels(wheel_mass_oz=0.09)
    heavy = _make_wheels(wheel_mass_oz=0.18)
    assert heavy.moment_of_inertia() == pytest.approx(
        2.0 * light.moment_of_inertia(), rel=1e-12
    )


def test_acwh3_moment_of_inertia_uses_sum_of_squared_radii() -> None:
    """I depends on (R_outer² + R_inner²): a wheel with a larger inner radius (more mass
    distributed outward) has a strictly larger I, all else equal."""
    thin_hub = _make_wheels(outer_radius_in=0.595, inner_radius_in=0.20)
    thick_hub = _make_wheels(outer_radius_in=0.595, inner_radius_in=0.50)
    assert thick_hub.moment_of_inertia() > thin_hub.moment_of_inertia()


# AC-WH3 — invalid wheel geometry raises ValueError.
def test_acwh3_inner_radius_equal_to_outer_raises() -> None:
    """R_inner >= R_outer is invalid (the rule's boundary: equal is rejected)."""
    with pytest.raises(ValueError):
        _make_wheels(outer_radius_in=0.595, inner_radius_in=0.595)


def test_acwh3_inner_radius_greater_than_outer_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(outer_radius_in=0.595, inner_radius_in=0.70)


def test_acwh3_axle_radius_equal_to_outer_raises() -> None:
    """r_axle >= R_outer is invalid (boundary: equal is rejected)."""
    with pytest.raises(ValueError):
        _make_wheels(outer_radius_in=0.595, axle_radius_in=0.595)


def test_acwh3_axle_radius_greater_than_outer_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(outer_radius_in=0.595, axle_radius_in=0.80)


def test_acwh3_zero_outer_radius_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(outer_radius_in=0.0, inner_radius_in=0.0, axle_radius_in=0.0)


def test_acwh3_negative_outer_radius_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(outer_radius_in=-0.5)


def test_acwh3_zero_inner_radius_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(inner_radius_in=0.0)


def test_acwh3_negative_inner_radius_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(inner_radius_in=-0.1)


def test_acwh3_zero_axle_radius_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(axle_radius_in=0.0)


def test_acwh3_negative_axle_radius_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(axle_radius_in=-0.01)


def test_acwh3_zero_wheel_mass_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(wheel_mass_oz=0.0)


def test_acwh3_negative_wheel_mass_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(wheel_mass_oz=-0.09)


# AC-WH3 — count_touching not in {3, 4} raises ValueError.
def test_acwh3_count_three_is_valid() -> None:
    from pinewood_derby.car import Wheels

    assert isinstance(_make_wheels(count_touching=3), Wheels)


def test_acwh3_count_four_is_valid() -> None:
    from pinewood_derby.car import Wheels

    assert isinstance(_make_wheels(count_touching=4), Wheels)


def test_acwh3_count_two_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(count_touching=2)


def test_acwh3_count_five_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(count_touching=5)


def test_acwh3_count_zero_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(count_touching=0)


def test_acwh3_count_negative_raises() -> None:
    with pytest.raises(ValueError):
        _make_wheels(count_touching=-3)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-A3 — BodyShape validation + WEDGE/BLOCK presets.
# ───────────────────────────────────────────────────────────────────────────── #
def test_aca3_zero_drag_coefficient_raises() -> None:
    with pytest.raises(ValueError):
        _make_body(drag_coefficient=0.0)


def test_aca3_negative_drag_coefficient_raises() -> None:
    with pytest.raises(ValueError):
        _make_body(drag_coefficient=-0.20)


def test_aca3_zero_frontal_area_raises() -> None:
    with pytest.raises(ValueError):
        _make_body(frontal_area=0.0)


def test_aca3_negative_frontal_area_raises() -> None:
    with pytest.raises(ValueError):
        _make_body(frontal_area=-0.0028)


def test_aca3_positive_values_construct_successfully() -> None:
    from pinewood_derby.car import BodyShape

    assert isinstance(_make_body(drag_coefficient=0.01, frontal_area=1e-6), BodyShape)


def test_aca3_wedge_preset_exists_with_cd_020() -> None:
    from pinewood_derby.car import BodyShape

    assert isinstance(BodyShape.WEDGE, BodyShape)
    assert BodyShape.WEDGE.drag_coefficient == pytest.approx(CD_WEDGE, abs=1e-12)


def test_aca3_block_preset_exists_with_cd_085() -> None:
    from pinewood_derby.car import BodyShape

    assert isinstance(BodyShape.BLOCK, BodyShape)
    assert BodyShape.BLOCK.drag_coefficient == pytest.approx(CD_BLOCK, abs=1e-12)


def test_aca3_wedge_is_more_aerodynamic_than_block() -> None:
    """The presets encode the spec's ordering: a wedge has a strictly lower drag
    coefficient than a wood block (§3.1)."""
    from pinewood_derby.car import BodyShape

    assert BodyShape.WEDGE.drag_coefficient < BodyShape.BLOCK.drag_coefficient


def test_aca3_presets_have_positive_frontal_area() -> None:
    from pinewood_derby.car import BodyShape

    assert BodyShape.WEDGE.frontal_area > 0.0
    assert BodyShape.BLOCK.frontal_area > 0.0


# ───────────────────────────────────────────────────────────────────────────── #
# AC-F2 (validation portion) — Axle validation + POLISHED_GRAPHITE/UNPREPARED presets.
# ───────────────────────────────────────────────────────────────────────────── #
def test_acf2_negative_friction_coefficient_raises() -> None:
    with pytest.raises(ValueError):
        _make_axle(friction_coefficient=-0.01)


def test_acf2_zero_friction_coefficient_is_valid() -> None:
    """The rule is μ < 0 raises; μ == 0 (idealized frictionless) must NOT raise. This
    pins the inclusive lower boundary so the validator cannot over-reject."""
    from pinewood_derby.car import Axle

    assert isinstance(_make_axle(friction_coefficient=0.0), Axle)


def test_acf2_positive_friction_coefficient_is_valid() -> None:
    from pinewood_derby.car import Axle

    assert isinstance(_make_axle(friction_coefficient=0.50), Axle)


def test_acf2_polished_graphite_preset_exists_with_mu_010() -> None:
    from pinewood_derby.car import Axle

    assert isinstance(Axle.POLISHED_GRAPHITE, Axle)
    assert Axle.POLISHED_GRAPHITE.friction_coefficient == pytest.approx(
        MU_POLISHED_GRAPHITE, abs=1e-12
    )


def test_acf2_unprepared_preset_exists_with_mu_035() -> None:
    from pinewood_derby.car import Axle

    assert isinstance(Axle.UNPREPARED, Axle)
    assert Axle.UNPREPARED.friction_coefficient == pytest.approx(MU_UNPREPARED, abs=1e-12)


def test_acf2_polished_is_lower_friction_than_unprepared() -> None:
    """Presets encode the spec ordering: polished+graphite has strictly lower friction
    than an unprepared axle (§3.2)."""
    from pinewood_derby.car import Axle

    assert Axle.POLISHED_GRAPHITE.friction_coefficient < Axle.UNPREPARED.friction_coefficient


# ───────────────────────────────────────────────────────────────────────────── #
# Immutability — all CarDesign sub-objects are frozen, validated-once dataclasses.
# ───────────────────────────────────────────────────────────────────────────── #
def test_cardesign_is_frozen_dataclass() -> None:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.units import Mass

    car = _make_car()
    assert dataclasses.is_dataclass(CarDesign)
    assert car.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    with pytest.raises(dataclasses.FrozenInstanceError):
        car.mass = Mass.from_ounces(4.0)  # type: ignore[misc]


def test_wheels_is_frozen_dataclass() -> None:
    from pinewood_derby.car import Wheels

    wheels = _make_wheels()
    assert dataclasses.is_dataclass(Wheels)
    assert wheels.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    with pytest.raises(dataclasses.FrozenInstanceError):
        wheels.count_touching = 3  # type: ignore[misc]


def test_bodyshape_is_frozen_dataclass() -> None:
    from pinewood_derby.car import BodyShape

    body = _make_body()
    assert dataclasses.is_dataclass(BodyShape)
    assert body.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    with pytest.raises(dataclasses.FrozenInstanceError):
        body.drag_coefficient = 0.5  # type: ignore[misc]


def test_axle_is_frozen_dataclass() -> None:
    from pinewood_derby.car import Axle

    axle = _make_axle()
    assert dataclasses.is_dataclass(Axle)
    assert axle.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    with pytest.raises(dataclasses.FrozenInstanceError):
        axle.friction_coefficient = 0.5  # type: ignore[misc]


def test_cardesign_equal_by_value() -> None:
    """Frozen dataclasses compare by value — needed for use as a validated input and for
    'all else equal' behavioral comparisons downstream."""
    assert _make_car() == _make_car()


def test_alignment_enum_has_straight_and_rail_rider() -> None:
    from pinewood_derby.car import Alignment

    # The two members are distinct (kept as a set-membership check so the intent
    # holds without a non-overlapping `!=` between two distinct enum literals).
    assert len({Alignment.STRAIGHT, Alignment.RAIL_RIDER}) == 2
