"""WI06-PRESENT-GARAGE-SERDE — CarDesign <-> plain-dict serialization for the garage.

Acceptance criteria (PRD AC-S2; TRD §5/§7):
- A pure ``to_dict(CarDesign) -> dict`` and ``from_dict(dict) -> CarDesign`` round-trip
  every control field losslessly (mass, com_ahead_of_rear_axle, wheelbase, wheels,
  body, axle, alignment).
- Each serialized entry carries a ``schemaVersion`` so a later CarDesign change can be
  migrated (TRD §7, PRD A4).
- ``from_dict`` re-validates through CarDesign construction so a malformed / illegal
  stored design raises ``ValueError`` (caught upstream) rather than yielding an invalid
  object (TRD §5).
- Reconstructing a design from its serialized form and racing it reproduces the
  original design's time with the fixed seed (PRD AC-S2, AC-R3 data side).
- Pure, JSON-serializable, DOM-free (the localStorage payload is plain JSON).
"""

from __future__ import annotations

import json

import pytest

from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
from pinewood_derby.engine import simulate
from pinewood_derby.track import STANDARD_TRACK
from pinewood_derby.units import Length, Mass

FIXED_SEED = 0


def _wheels(*, count: int = 4) -> Wheels:
    return Wheels(
        count_touching=count,
        wheel_mass=Mass.from_ounces(0.09),
        outer_radius=Length.from_inches(0.595),
        inner_radius=Length.from_inches(0.37),
        axle_radius=Length.from_inches(0.045),
    )


def _car(
    *,
    mass_oz: float = 5.0,
    com_in: float = 0.85,
    alignment: str = "RAIL_RIDER",
    count: int = 4,
    mu: float = 0.10,
    cd: float = 0.30,
) -> CarDesign:
    """A valid, finish-capable baseline car; RAIL_RIDER => RNG-free => fully
    deterministic so the reproduce-time assertion is seed-independent."""
    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_in),
        wheelbase=Length.from_inches(4.375),
        wheels=_wheels(count=count),
        body=BodyShape(drag_coefficient=cd, frontal_area=0.0028),
        axle=Axle(friction_coefficient=mu),
        alignment=Alignment[alignment],
    )


# A matrix spanning the control surface: legal finisher, over-limit, both alignments,
# 3- and 4-wheel, prepped and unprepped axles.
_MATRIX = {
    "legal_finisher": _car(),
    "over_limit": _car(mass_oz=7.0),
    "straight": _car(alignment="STRAIGHT"),
    "three_wheel": _car(count=3),
    "unprepared_block": _car(mu=0.35, cd=0.85),
    "rear_biased": _car(com_in=1.5),
}


# ── schemaVersion + JSON-serializability ─────────────────────────────────────── #
@pytest.mark.parametrize("name", list(_MATRIX))
def test_to_dict_carries_schema_version_and_is_json_serializable(name: str) -> None:
    from pinewood_derby.present import GARAGE_SCHEMA_VERSION, to_dict

    payload = to_dict(_MATRIX[name])
    assert payload["schemaVersion"] == GARAGE_SCHEMA_VERSION
    # The localStorage entry must be plain JSON — no dataclasses, enums, or proxies.
    dumped = json.dumps(payload)
    assert isinstance(json.loads(dumped), dict)


# ── lossless round-trip ──────────────────────────────────────────────────────── #
@pytest.mark.parametrize("name", list(_MATRIX))
def test_round_trip_is_lossless(name: str) -> None:
    """``from_dict(to_dict(car)) == car`` for every design: frozen dataclasses compare
    by value, so equality proves every control field survived intact (PRD AC-S2)."""
    from pinewood_derby.present import from_dict, to_dict

    car = _MATRIX[name]
    assert from_dict(to_dict(car)) == car


@pytest.mark.parametrize("name", list(_MATRIX))
def test_round_trip_survives_a_json_text_hop(name: str) -> None:
    """The real garage path is dict -> JSON text -> dict; reconstructing through an
    actual ``json.dumps``/``loads`` round-trip still rebuilds the exact design."""
    from pinewood_derby.present import from_dict, to_dict

    car = _MATRIX[name]
    assert from_dict(json.loads(json.dumps(to_dict(car)))) == car


# ── reproduce-time (AC-S2 / AC-R3 data side) ─────────────────────────────────── #
@pytest.mark.parametrize("name", list(_MATRIX))
def test_reconstructed_design_reproduces_race_time(name: str) -> None:
    from pinewood_derby.present import from_dict, to_dict

    car = _MATRIX[name]
    restored = from_dict(to_dict(car))
    original = simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)
    again = simulate(restored, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)
    assert again.race_time_s == original.race_time_s
    assert again.outcome == original.outcome
    assert [p.position for p in again.trajectory] == [p.position for p in original.trajectory]


# ── from_dict re-validates (malformed / illegal -> ValueError) ───────────────── #
def test_from_dict_rejects_unknown_schema_version() -> None:
    from pinewood_derby.present import from_dict, to_dict

    payload = to_dict(_car())
    payload["schemaVersion"] = 999
    with pytest.raises(ValueError):
        from_dict(payload)


@pytest.mark.parametrize(
    "broken",
    [
        {},  # empty
        {"schemaVersion": 1},  # missing design
        "not-a-mapping",  # wrong type
        [1, 2, 3],  # wrong type
    ],
)
def test_from_dict_rejects_malformed_entry(broken: object) -> None:
    from pinewood_derby.present import from_dict

    with pytest.raises(ValueError):
        from_dict(broken)  # type: ignore[arg-type]


def test_from_dict_rejects_missing_nested_field() -> None:
    from pinewood_derby.present import from_dict, to_dict

    payload = to_dict(_car())
    del payload["design"]["wheels"]["outer_radius_m"]  # type: ignore[index]
    with pytest.raises(ValueError):
        from_dict(payload)


@pytest.mark.parametrize(
    ("field_path", "bad_value"),
    [
        (("mass_kg",), -1.0),  # AC-W3 mass <= 0
        (("wheelbase_m",), 0.0),  # wheelbase <= 0
        (("com_ahead_of_rear_axle_m",), 999.0),  # com outside (0, wheelbase) (AC-P5)
        (("wheels", "count_touching"), 5),  # AC-WH3 count not in {3,4}
        (("axle", "friction_coefficient"), -0.5),  # AC-F2 mu < 0
    ],
)
def test_from_dict_revalidates_illegal_design_through_constructors(
    field_path: tuple[str, ...], bad_value: object
) -> None:
    """A stored design whose values violate the engine's own invariants must raise
    ValueError on load (re-validated through CarDesign/sub-object construction), never
    yield an invalid object (TRD §5 — the engine validation is the single source of
    truth)."""
    from pinewood_derby.present import from_dict, to_dict

    payload = to_dict(_car())
    target: dict[str, object] = payload["design"]  # type: ignore[assignment]
    for key in field_path[:-1]:
        target = target[key]  # type: ignore[assignment]
    target[field_path[-1]] = bad_value
    with pytest.raises(ValueError):
        from_dict(payload)


def test_from_dict_rejects_unknown_alignment() -> None:
    from pinewood_derby.present import from_dict, to_dict

    payload = to_dict(_car())
    payload["design"]["alignment"] = "sideways"  # type: ignore[index]
    with pytest.raises(ValueError):
        from_dict(payload)


# ── purity ───────────────────────────────────────────────────────────────────── #
def test_serde_is_pure_and_non_mutating() -> None:
    from pinewood_derby.present import from_dict, to_dict

    car = _car()
    first = to_dict(car)
    second = to_dict(car)
    assert first == second  # same input => same output
    # to_dict output is independent across calls (no shared mutable state).
    first["design"]["mass_kg"] = 0.0  # type: ignore[index]
    assert second["design"]["mass_kg"] != 0.0  # type: ignore[index]
    # from_dict does not mutate its input.
    payload = to_dict(car)
    snapshot = json.dumps(payload)
    from_dict(payload)
    assert json.dumps(payload) == snapshot
