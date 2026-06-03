"""WI15-ENGINE-PURITY-GUARD — the presentation layer adds no physics and consumes the
engine's public API unchanged (PRD AC-G1; TRD §10/§12).

These are durable, structural guards (not brittle string scans of behaviour):

- ``present.py`` imports only the engine's **data/result types** + the stdlib — never a
  third-party package and never the ``engine`` integrator itself, so it cannot run or
  re-derive physics; it only *translates a RaceResult it is handed* (AC-G1).
- The engine's public API the front-end depends on (``simulate``, ``CarDesign``,
  ``Track``/``STANDARD_TRACK``, ``RaceResult``) is importable and unchanged in shape
  (TRD §5 — the bridge consumes it as-is).
- ``pinewood_derby`` stays dependency-free (``pyproject`` ``dependencies = []``), so no
  physics/runtime dependency creeps in behind the boundary (TRD §10).

Machine-checked alongside these: ``uv run pytest`` / ``ruff check`` / ``mypy`` (strict)
all pass for the Python side including ``present.py`` (profile commands; AC-G1 last bullet).
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent.parent / "src" / "pinewood_derby"
_PRESENT = _PKG_DIR / "present.py"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


def _imports(source: str) -> tuple[set[str], set[str]]:
    """Return (absolute top-level modules, intra-package relative module names) imported
    by ``source``. Relative imports (``from . import x`` / ``from .x import y``) are the
    engine's own submodules; absolute ones must all be stdlib."""
    tree = ast.parse(source)
    absolute: set[str] = set()
    relative: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # `from . import car` -> names are submodules; `from .units import X`
                # -> module is the submodule. Capture the submodule name either way.
                if node.module:
                    relative.add(node.module.split(".")[0])
                else:
                    for alias in node.names:
                        relative.add(alias.name.split(".")[0])
            elif node.module:
                absolute.add(node.module.split(".")[0])
    return absolute, relative


def test_present_imports_only_stdlib_and_engine_submodules() -> None:
    """present.py imports nothing outside the stdlib + its own package — it adds no
    third-party dependency and computes only presentation (PRD AC-G1)."""
    absolute, _relative = _imports(_PRESENT.read_text(encoding="utf-8"))
    allowed = set(sys.stdlib_module_names) | {"__future__"}
    leaked = sorted(m for m in absolute if m not in allowed)
    assert not leaked, (
        f"present.py imports non-stdlib top-level modules {leaked!r}; the presentation "
        "layer must stay dependency-free and add no physics (AC-G1)"
    )


def test_present_does_not_run_or_import_the_engine_integrator() -> None:
    """present.py translates a ``RaceResult`` it is *given*; it must not import the
    ``engine`` integrator or call ``simulate`` (that would be running physics in the
    presentation layer, violating AC-G1). It depends only on the data/result types."""
    source = _PRESENT.read_text(encoding="utf-8")
    _absolute, relative = _imports(source)
    assert "engine" not in relative, (
        "present.py imports pinewood_derby.engine — the presentation layer must not run "
        "the simulation; it only translates the RaceResult it receives (AC-G1)"
    )
    # No call to simulate(...) anywhere in the module body.
    tree = ast.parse(source)
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } | {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "simulate" not in calls, (
        "present.py calls simulate(...) — it must consume engine output, not produce it "
        "(AC-G1)"
    )


def test_engine_public_api_is_importable_unchanged() -> None:
    """The exact public surface the front-end/bridge consumes (TRD §5) imports cleanly
    and unchanged — proof the presentation layer rides the engine's API, not a fork."""
    from pinewood_derby.car import CarDesign
    from pinewood_derby.engine import simulate
    from pinewood_derby.result import RaceResult
    from pinewood_derby.track import STANDARD_TRACK, Track

    assert callable(simulate)
    assert isinstance(STANDARD_TRACK, Track)
    # The types the bridge passes across the boundary exist and are classes.
    assert isinstance(CarDesign, type)
    assert isinstance(RaceResult, type)


def test_engine_package_declares_no_runtime_dependencies() -> None:
    """``pinewood_derby`` stays dependency-free (TRD §10): no physics/runtime dependency
    may creep in behind the engine boundary."""
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    deps = data.get("project", {}).get("dependencies", None)
    assert deps == [], f"engine package must declare no runtime dependencies, got {deps!r}"
