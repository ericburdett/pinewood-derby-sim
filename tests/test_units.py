"""WI-01 — Units & boundary value objects (Mass, Length, Angle).

Behavior-driven RED tests, written before implementation. The module
`pinewood_derby.units` does not exist yet, so each test imports it inside the test
body: a missing module then fails each criterion *independently* (true per-criterion
RED) instead of aborting whole-file collection with one import error.

Traceability to the WI-01 acceptance criteria (TRD §2, PRD NFR Typing):
- AC-1  Constructors + accessor surface:
        Mass.from_ounces/from_grams + .kg/.ounces;
        Length.from_inches/from_feet + .m/.inches/.feet;
        Angle.from_degrees + .radians/.degrees.
- AC-2  Round-trip conversions exact within float tolerance
        (oz->kg->oz, inches->m->inches, ...).
- AC-3  Conversion factors centralized in units.py (OZ_TO_KG=0.0283495, IN_TO_M=0.0254)
        AND SI NewType aliases (Meters, MetersPerSecond, Newtons, Joules, Kilograms,
        Radians) are defined as genuine typing.NewType over float.
- AC-4  Value objects are frozen/immutable dataclasses.
- AC-5  `uv run mypy .` passes under strict for these types (tooling gate, machine-checked
        by the typecheck command — exercised here by the typed surface these tests assert on).
"""

from __future__ import annotations

import dataclasses
import math
import typing

import pytest

# Centralized factors the implementation must expose (TRD §2). Mirrored here so the
# round-trip assertions are anchored to the spec'd constants, not to whatever the impl picks.
OZ_TO_KG = 0.0283495
IN_TO_M = 0.0254
GRAMS_PER_KG = 1000.0
INCHES_PER_FOOT = 12.0

REL_TOL = 1e-12
ABS_TOL = 1e-12

_SI_ALIASES = ("Meters", "MetersPerSecond", "Newtons", "Joules", "Kilograms", "Radians")


# ───────────────────────────────────────────────────────────────────────────── #
# AC-1 — constructors and accessors exist with the TRD §2 surface
# ───────────────────────────────────────────────────────────────────────────── #
def test_ac1_mass_constructors_and_accessors() -> None:
    from pinewood_derby.units import Mass

    m = Mass.from_ounces(5.0)
    assert m.kg == pytest.approx(5.0 * OZ_TO_KG, rel=REL_TOL, abs=ABS_TOL)
    assert m.ounces == pytest.approx(5.0, rel=REL_TOL, abs=ABS_TOL)

    g = Mass.from_grams(141.748)
    assert isinstance(g, Mass)
    assert g.kg == pytest.approx(141.748 / GRAMS_PER_KG, rel=REL_TOL, abs=ABS_TOL)


def test_ac1_length_constructors_and_accessors() -> None:
    from pinewood_derby.units import Length

    ln = Length.from_inches(10.0)
    assert ln.m == pytest.approx(10.0 * IN_TO_M, rel=REL_TOL, abs=ABS_TOL)
    assert ln.inches == pytest.approx(10.0, rel=REL_TOL, abs=ABS_TOL)
    assert ln.feet == pytest.approx(10.0 / INCHES_PER_FOOT, rel=REL_TOL, abs=ABS_TOL)

    ft = Length.from_feet(10.0)
    assert isinstance(ft, Length)
    assert ft.feet == pytest.approx(10.0, rel=REL_TOL, abs=ABS_TOL)
    assert ft.inches == pytest.approx(120.0, rel=REL_TOL, abs=ABS_TOL)
    assert ft.m == pytest.approx(10.0 * INCHES_PER_FOOT * IN_TO_M, rel=REL_TOL, abs=ABS_TOL)


def test_ac1_angle_constructors_and_accessors() -> None:
    from pinewood_derby.units import Angle

    a = Angle.from_degrees(30.0)
    assert a.radians == pytest.approx(math.radians(30.0), rel=REL_TOL, abs=ABS_TOL)
    assert a.degrees == pytest.approx(30.0, rel=REL_TOL, abs=ABS_TOL)

    right = Angle.from_degrees(90.0)
    assert right.radians == pytest.approx(math.pi / 2.0, rel=REL_TOL, abs=ABS_TOL)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-2 — round-trip conversions exact within float tolerance
# ───────────────────────────────────────────────────────────────────────────── #
def test_ac2_mass_round_trip_ounces() -> None:
    from pinewood_derby.units import Mass

    for oz in (0.0, 0.09, 1.0, 5.0, 7.3):
        assert Mass.from_ounces(oz).ounces == pytest.approx(oz, rel=REL_TOL, abs=ABS_TOL)


def test_ac2_mass_round_trip_grams() -> None:
    from pinewood_derby.units import Mass

    for grams in (2.55, 141.748, 200.0):
        assert Mass.from_grams(grams).kg * GRAMS_PER_KG == pytest.approx(
            grams, rel=REL_TOL, abs=ABS_TOL
        )


def test_ac2_length_round_trip_inches() -> None:
    from pinewood_derby.units import Length

    for inches in (0.045, 0.595, 4.375, 120.0):
        assert Length.from_inches(inches).inches == pytest.approx(inches, rel=REL_TOL, abs=ABS_TOL)


def test_ac2_length_round_trip_feet() -> None:
    from pinewood_derby.units import Length

    for feet in (0.5, 10.0, 32.0):
        assert Length.from_feet(feet).feet == pytest.approx(feet, rel=REL_TOL, abs=ABS_TOL)


def test_ac2_angle_round_trip_degrees() -> None:
    from pinewood_derby.units import Angle

    for deg in (0.0, 30.0, 45.0, 89.9, 180.0):
        assert Angle.from_degrees(deg).degrees == pytest.approx(deg, rel=REL_TOL, abs=ABS_TOL)


def test_ac2_length_inches_via_si_round_trip() -> None:
    """inches -> m -> inches stays exact (PRD round-trip example)."""
    from pinewood_derby.units import Length

    src = Length.from_inches(4.375)
    reconstructed = Length.from_inches(src.m / IN_TO_M)
    assert reconstructed.inches == pytest.approx(4.375, rel=REL_TOL, abs=ABS_TOL)


def test_ac2_length_feet_and_inches_describe_same_length() -> None:
    from pinewood_derby.units import Length

    assert Length.from_feet(1.0).inches == pytest.approx(12.0, rel=REL_TOL, abs=ABS_TOL)
    assert Length.from_feet(1.0).m == pytest.approx(
        Length.from_inches(12.0).m, rel=REL_TOL, abs=ABS_TOL
    )


# ───────────────────────────────────────────────────────────────────────────── #
# AC-3 — centralized conversion factors + SI NewType aliases
# ───────────────────────────────────────────────────────────────────────────── #
def test_ac3_conversion_factors_centralized_and_exact() -> None:
    from pinewood_derby import units

    assert units.OZ_TO_KG == 0.0283495
    assert units.IN_TO_M == 0.0254


def test_ac3_si_aliases_are_genuine_newtypes_over_float() -> None:
    """Aliases must be real typing.NewType(name, float), not bare `X = float`.

    A plain `Meters = float` would still satisfy a naive hasattr check while giving
    zero unit safety, so assert the NewType structure explicitly.
    """
    from pinewood_derby import units

    for name in _SI_ALIASES:
        alias = getattr(units, name, None)
        assert alias is not None, f"missing SI NewType alias: {name}"
        # typing.NewType objects carry __supertype__ and are callable identity wrappers.
        assert getattr(alias, "__supertype__", None) is float, (
            f"{name} must be typing.NewType over float"
        )
        assert isinstance(alias, typing.NewType)
        assert alias(1.5) == 1.5  # runtime identity


# ───────────────────────────────────────────────────────────────────────────── #
# AC-4 — value objects are frozen / immutable dataclasses
# ───────────────────────────────────────────────────────────────────────────── #
def test_ac4_mass_is_frozen_dataclass() -> None:
    from pinewood_derby.units import Mass

    m = Mass.from_ounces(5.0)
    assert dataclasses.is_dataclass(Mass)
    assert m.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.kg = 0.0  # type: ignore[misc]


def test_ac4_length_is_frozen_dataclass() -> None:
    from pinewood_derby.units import Length

    ln = Length.from_inches(1.0)
    assert dataclasses.is_dataclass(Length)
    assert ln.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    with pytest.raises(dataclasses.FrozenInstanceError):
        ln.m = 0.0  # type: ignore[misc]


def test_ac4_angle_is_frozen_dataclass() -> None:
    from pinewood_derby.units import Angle

    a = Angle.from_degrees(30.0)
    assert dataclasses.is_dataclass(Angle)
    assert a.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.radians = 0.0  # type: ignore[misc]


def test_ac4_value_objects_equal_by_value() -> None:
    """Frozen dataclasses compare by value — needed for use as validated inputs."""
    from pinewood_derby.units import Angle, Length, Mass

    assert Mass.from_ounces(5.0) == Mass.from_ounces(5.0)
    assert Length.from_inches(2.0) == Length.from_feet(2.0 / INCHES_PER_FOOT)
    assert Angle.from_degrees(30.0) == Angle.from_degrees(30.0)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-1/AC-5 — accessor outputs are finite floats (typed boundary; supports strict mypy)
# ───────────────────────────────────────────────────────────────────────────── #
def test_ac5_accessor_outputs_are_finite_floats() -> None:
    from pinewood_derby.units import Angle, Length, Mass

    m = Mass.from_ounces(5.0)
    for value in (m.kg, m.ounces):
        assert isinstance(value, float) and math.isfinite(value)

    ln = Length.from_inches(0.85)
    for value in (ln.m, ln.inches, ln.feet):
        assert isinstance(value, float) and math.isfinite(value)

    a = Angle.from_degrees(30.0)
    for value in (a.radians, a.degrees):
        assert isinstance(value, float) and math.isfinite(value)
