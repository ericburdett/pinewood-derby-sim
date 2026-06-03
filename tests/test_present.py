"""WI01-PRESENT-VIEWMODEL — RED tests for the pure translation layer ``present.py``.

The module ``pinewood_derby.present`` does not exist yet, so each test imports it
*inside the test body*: a missing module then fails each criterion **independently**
(true per-criterion RED) instead of aborting whole-file collection with one import
error.

These tests drive ``present()`` with **real ``simulate()`` output** (not hand-built
fixtures), per the PRD NFR "Translation purity & coverage" and TRD §12.

Traceability to the WI01 acceptance criteria (PRD AC-G1, AC-R1, AC-R3, A7; NFR
"Translation purity & coverage"; TRD §4):

- AC-1 (purity / contract): ``present(result, car) -> RaceView`` and
  ``to_json(view) -> dict`` are pure; ``RaceView``/``LossBar``/``FramePoint`` are
  frozen dataclasses; the module imports only ``pinewood_derby`` submodules + the
  stdlib, performs no DOM/I/O/network and computes no physics math (PRD AC-G1).
- AC-2 (finished mapping): a FINISHED run gives ``finished=True``,
  ``outcome="finished"``, ``time_seconds == result.race_time_s`` (display precision);
  seconds is the only numeric unit surfaced (PRD AC-R1 translation half, A7).
- AC-3 (trajectory passthrough): ``RaceView.trajectory`` is a tuple of ``FramePoint``
  snapshots (position/velocity/angle/t) derived 1:1 from ``result.trajectory``; no
  physics is recomputed (PRD AC-R1, AC-G1).
- AC-4 (determinism): ``present(simulate(car, seed=FIXED_SEED), car)`` returns an
  identical ``RaceView`` across repeated calls for the same design (PRD AC-R3 data
  side; NFR Determinism).

All tests are deterministic: a single fixed seed, no clock / network / unseeded RNG.
"""

from __future__ import annotations

import ast
import dataclasses
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pinewood_derby.car import CarDesign
    from pinewood_derby.result import RaceResult

# The fixed seed the UI pins so a design's time/animation is reproducible (PRD A6).
FIXED_SEED = 0

# Numeric jargon units that must NOT leak into the view-model's numeric story — only
# *seconds* is an allowed surfaced unit (PRD A7). Used by the "seconds is the only
# numeric unit" guard.
BANNED_NUMERIC_UNIT_TOKENS = (
    "joule",
    "newton",
    "m/s",
    "meters per second",
    "metres per second",
    "kg",
    "kilogram",
    "watt",
)


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — build a valid, FINISHED-capable car from real value objects, then run
# the *real* engine. No hand-built RaceResult fixtures (PRD NFR / TRD §12).
# ───────────────────────────────────────────────────────────────────────────── #
def _make_wheels(*, count_touching: int = 4) -> Any:
    from pinewood_derby.car import Wheels
    from pinewood_derby.units import Length, Mass

    return Wheels(
        count_touching=count_touching,
        wheel_mass=Mass.from_ounces(0.09),
        outer_radius=Length.from_inches(0.595),
        inner_radius=Length.from_inches(0.37),
        axle_radius=Length.from_inches(0.045),
    )


def _make_car(
    *,
    mass_oz: float = 5.0,
    com_ahead_of_rear_axle_in: float = 0.85,
    alignment: str = "STRAIGHT",
) -> CarDesign:
    """A valid, FINISHED-capable baseline car (mirrors tests/test_engine_e2e.py)."""
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(mass_oz),
        com_ahead_of_rear_axle=Length.from_inches(com_ahead_of_rear_axle_in),
        wheelbase=Length.from_inches(4.375),
        wheels=_make_wheels(),
        body=BodyShape(drag_coefficient=0.30, frontal_area=0.0028),
        axle=Axle(friction_coefficient=0.20),
        alignment=Alignment[alignment],
    )


def _finished_result(*, seed: int = FIXED_SEED) -> RaceResult:
    """Real ``simulate()`` output for a FINISHED run on the STANDARD_TRACK."""
    from pinewood_derby.engine import simulate
    from pinewood_derby.track import STANDARD_TRACK

    result = simulate(_make_car(), STANDARD_TRACK, dt=1e-3, seed=seed)
    return result


def _present_finished() -> Any:
    """Translate a real FINISHED run into a RaceView."""
    from pinewood_derby.present import present

    car = _make_car()
    return present(_finished_result(), car)


def _iter_strings(obj: Any) -> list[str]:
    """Flatten every string reachable from a view-model (for jargon scans)."""
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(_iter_strings(k))
            out.extend(_iter_strings(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_iter_strings(v))
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            out.extend(_iter_strings(getattr(obj, f.name)))
    return out


# ───────────────────────────────────────────────────────────────────────────── #
# AC-1 — Purity & contract: pure functions, frozen dataclasses, engine-only imports,
# no DOM/I/O/network, no physics math (PRD AC-G1).
# ───────────────────────────────────────────────────────────────────────────── #
def test_ac1_present_is_callable_and_returns_raceview() -> None:
    """present(result, car) returns a RaceView instance."""
    from pinewood_derby.present import RaceView, present

    view = present(_finished_result(), _make_car())
    assert isinstance(view, RaceView)


def test_ac1_to_json_returns_plain_dict() -> None:
    """to_json(view) returns a plain dict for the JS bridge (no lingering objects)."""
    from pinewood_derby.present import to_json

    payload = to_json(_present_finished())
    assert isinstance(payload, dict)


def test_ac1_view_model_types_are_frozen_dataclasses() -> None:
    """RaceView, LossBar, FramePoint are all frozen (immutable) dataclasses."""
    from pinewood_derby.present import FramePoint, LossBar, RaceView

    for cls in (RaceView, LossBar, FramePoint):
        assert dataclasses.is_dataclass(cls), f"{cls.__name__} must be a dataclass"
        assert cls.__dataclass_params__.frozen is True, f"{cls.__name__} must be frozen"


def test_ac1_raceview_instance_is_immutable() -> None:
    """A produced RaceView cannot be mutated (frozen at the instance level)."""
    view = _present_finished()
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.finished = False  # type: ignore[misc]


def test_ac1_framepoint_instances_are_immutable() -> None:
    """Each FramePoint snapshot is frozen so the whole view is immutable."""
    view = _present_finished()
    assert len(view.trajectory) > 0
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.trajectory[0].position = -1.0  # type: ignore[misc]


def test_ac1_module_imports_only_engine_submodules_and_stdlib() -> None:
    """AST-scan present.py: every import resolves to a pinewood_derby submodule
    (engine/car/result/track/units) or the stdlib — no DOM, no third-party, no
    network/UI package (PRD AC-G1, TRD §4)."""
    import sys

    import pinewood_derby.present as present_mod

    source = Path(present_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    allowed_engine = {
        "pinewood_derby",
        "pinewood_derby.engine",
        "pinewood_derby.car",
        "pinewood_derby.result",
        "pinewood_derby.track",
        "pinewood_derby.units",
    }
    stdlib = set(sys.stdlib_module_names)

    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # Ignore __future__ and relative imports (level > 0 -> same package).
            if node.level and not node.module:
                continue
            if node.module:
                roots.add(node.module)

    for mod in roots:
        if mod == "__future__":
            continue
        if mod in allowed_engine or mod.startswith("pinewood_derby"):
            continue
        top = mod.split(".")[0]
        assert top in stdlib, (
            f"present.py imports non-stdlib / non-engine module {mod!r} "
            "(no DOM/UI/network/third-party deps allowed — AC-G1)"
        )


def test_ac1_source_has_no_io_network_or_dom() -> None:
    """Static guardrail: present.py performs no file I/O, network access, or DOM/UI
    work — forbidden tokens must not appear (PRD AC-G1, TRD §4)."""
    import pinewood_derby.present as present_mod

    source = Path(present_mod.__file__).read_text(encoding="utf-8")
    forbidden = (
        "open(",
        "import socket",
        "import urllib",
        "import requests",
        "import http",
        "document.",
        "window.",
        "import js",
        "from js",
        "import pyodide",
    )
    for token in forbidden:
        assert token not in source, f"present.py must not do I/O/network/DOM: found {token!r}"


def test_ac1_source_computes_no_physics_math() -> None:
    """present.py adds NO physics: it must not re-import the engine's physical
    constants or re-derive forces. A direct ``from pinewood_derby.engine import
    simulate`` is fine (it consumes engine OUTPUT), but pulling the engine's private
    physics constants/integration helpers into the translation layer would be
    recomputing physics (PRD AC-G1, TRD §4 'computes no physics')."""
    import pinewood_derby.present as present_mod

    source = Path(present_mod.__file__).read_text(encoding="utf-8")
    physics_smells = ("9.81", "1.225", "_RHO_AIR", "_G ", "0.5 * mass", "math.sin(", "math.cos(")
    for token in physics_smells:
        assert token not in source, (
            f"present.py appears to recompute physics (found {token!r}) — the "
            "translation layer must consume engine output, not re-derive it (AC-G1)"
        )


def test_ac1_present_is_pure_does_not_mutate_inputs() -> None:
    """present() does not mutate its RaceResult/CarDesign inputs (pure translation)."""
    result = _finished_result()
    car = _make_car()
    before_result = repr(result)
    before_car = repr(car)
    from pinewood_derby.present import present

    present(result, car)
    assert repr(result) == before_result, "present() mutated the RaceResult input"
    assert repr(car) == before_car, "present() mutated the CarDesign input"


# ───────────────────────────────────────────────────────────────────────────── #
# AC-2 — FINISHED-run mapping: finished=True, outcome='finished',
# time_seconds == result.race_time_s; seconds is the only surfaced numeric unit
# (PRD AC-R1 translation half, A7).
# ───────────────────────────────────────────────────────────────────────────── #
def test_ac2_finished_flag_true_for_finished_run() -> None:
    """A FINISHED engine outcome maps to RaceView.finished == True."""
    view = _present_finished()
    assert view.finished is True


def test_ac2_outcome_is_finished_literal() -> None:
    """The view's outcome label for a finisher is exactly the string 'finished'."""
    view = _present_finished()
    assert view.outcome == "finished"


def test_ac2_time_seconds_equals_engine_race_time() -> None:
    """time_seconds carries the engine's race_time_s to display precision — the UI
    adds no physics and invents no number (PRD AC-R1)."""
    result = _finished_result()
    from pinewood_derby.present import present

    view = present(result, _make_car())
    assert result.race_time_s is not None
    assert view.time_seconds is not None
    assert view.time_seconds == pytest.approx(result.race_time_s, abs=5e-3)


def test_ac2_time_seconds_is_a_real_positive_number() -> None:
    """For a finisher the surfaced time is a finite, positive float (a real time)."""
    view = _present_finished()
    assert view.time_seconds is not None
    assert isinstance(view.time_seconds, float)
    assert math.isfinite(view.time_seconds)
    assert view.time_seconds > 0.0


def test_ac2_seconds_is_the_only_numeric_unit_surfaced() -> None:
    """No technical numeric unit (Joules, Newtons, m/s, kg, ...) appears in any
    kid-facing string of the view-model — only seconds is allowed (PRD A7)."""
    view = _present_finished()
    for text in _iter_strings(view):
        low = text.lower()
        for unit in BANNED_NUMERIC_UNIT_TOKENS:
            assert unit not in low, f"surfaced unit jargon {unit!r} found in: {text!r}"


# ───────────────────────────────────────────────────────────────────────────── #
# AC-3 — Trajectory passthrough: tuple of FramePoint(position/velocity/angle/t)
# derived 1:1 from result.trajectory; no physics recomputed (PRD AC-R1, AC-G1).
# ───────────────────────────────────────────────────────────────────────────── #
def test_ac3_trajectory_is_a_tuple_of_framepoints() -> None:
    from pinewood_derby.present import FramePoint

    view = _present_finished()
    assert isinstance(view.trajectory, tuple)
    assert len(view.trajectory) > 0
    for fp in view.trajectory:
        assert isinstance(fp, FramePoint)


def test_ac3_framepoint_exposes_position_velocity_angle_t() -> None:
    """Each FramePoint carries the four animator fields, all finite."""
    view = _present_finished()
    for fp in view.trajectory:
        for field in ("position", "velocity", "angle", "t"):
            assert hasattr(fp, field), f"FramePoint missing field: {field}"
            assert math.isfinite(getattr(fp, field)), f"FramePoint.{field} not finite"


def test_ac3_trajectory_length_matches_engine_trajectory() -> None:
    """The view replays the engine's down-sampled trajectory 1:1 — no points added,
    dropped, or re-integrated."""
    result = _finished_result()
    from pinewood_derby.present import present

    view = present(result, _make_car())
    assert len(view.trajectory) == len(result.trajectory)


def test_ac3_framepoints_copy_engine_values_verbatim() -> None:
    """Each FramePoint's fields equal the corresponding engine TrajectoryPoint's
    values exactly (verbatim copy — no physics recomputed, PRD AC-R1/AC-G1)."""
    result = _finished_result()
    from pinewood_derby.present import present

    view = present(result, _make_car())
    for fp, tp in zip(view.trajectory, result.trajectory):
        assert fp.t == tp.t
        assert fp.position == tp.position
        assert fp.velocity == tp.velocity
        assert fp.angle == tp.angle


def test_ac3_to_json_preserves_full_trajectory() -> None:
    """to_json carries every trajectory frame through to the JSON payload so the
    animator can replay the whole run from the plain dict."""
    result = _finished_result()
    from pinewood_derby.present import present, to_json

    payload = to_json(present(result, _make_car()))
    assert "trajectory" in payload
    frames = payload["trajectory"]
    assert isinstance(frames, (list, tuple))
    assert len(frames) == len(result.trajectory)


# ───────────────────────────────────────────────────────────────────────────── #
# AC-4 — Determinism: present(simulate(car, seed=FIXED_SEED), car) is identical
# across repeated calls for the same design (PRD AC-R3 data side; NFR Determinism).
# ───────────────────────────────────────────────────────────────────────────── #
def test_ac4_present_is_identical_across_repeated_calls() -> None:
    """Same design ⇒ the entire RaceView compares equal across repeated
    present(simulate(...)) calls (frozen dataclasses == by value)."""
    from pinewood_derby.engine import simulate
    from pinewood_derby.present import present
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car()
    v1 = present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car)
    v2 = present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car)
    assert v1 == v2


def test_ac4_present_trajectory_is_bit_identical_across_calls() -> None:
    """Stronger than ==: every FramePoint float is bit-for-bit identical across two
    independent present(simulate(...)) runs for the same seeded design."""
    from pinewood_derby.engine import simulate
    from pinewood_derby.present import present
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car()
    v1 = present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car)
    v2 = present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car)
    assert len(v1.trajectory) == len(v2.trajectory)
    for f1, f2 in zip(v1.trajectory, v2.trajectory):
        assert f1 == f2
    assert v1.time_seconds == v2.time_seconds


def test_ac4_to_json_payload_is_deterministic() -> None:
    """The JSON payload the bridge ships is also stable across repeated runs (a
    downstream leaderboard relies on identical designs producing identical data)."""
    from pinewood_derby.engine import simulate
    from pinewood_derby.present import present, to_json
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_car()
    p1 = to_json(present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car))
    p2 = to_json(present(simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED), car))
    assert p1 == p2
