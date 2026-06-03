"""WI-13 — Non-functional requirements: performance, lint, strict typing,
coverage thresholds, and a stdlib-only engine.

Behavior-driven verification tests for the PRD §7 NFR table. These assert the
*system-level* properties the feature must hold, not engine physics. Each test
traces to one NFR acceptance criterion:

- Performance (PRD §7, l.182 / profile ``quality_bars.performance``): a single
  ``simulate()`` on STANDARD_TRACK completes in < 5 ms, with fixed ``dt`` and ``seed``
  (deterministic inputs) and a best-of-N measurement to remove scheduler jitter.
- Lint (PRD §7, l.185): ``uv run ruff check .`` is clean (exit 0) with all test
  files — including this one — included.
- Typing (PRD §7, l.184): ``uv run mypy .`` passes under ``strict`` with the test
  tree included (no new type errors).
- Coverage (PRD §7, l.186): ``pytest --cov`` reports engine coverage >= 90% and
  overall >= 70%.
- Dependencies / safety (PRD §7, l.187/188; AC-PU1): every module of the
  ``pinewood_derby`` engine package imports stdlib only (plus its own sub-modules) —
  no third-party imports, no network/file I/O — and ``pyproject`` runtime
  ``dependencies`` stays empty.

Determinism: the perf test pins ``dt`` and ``seed`` and uses RAIL_RIDER (seed-free)
inputs; the tool-driven tests are pure functions of the repository state. No clock
assertions beyond a generous best-of-N budget, no network, no unseeded randomness.

The tool-driven tests (ruff / mypy / coverage) intentionally run the *exact* profile
commands as subprocesses so a regression in lint, typing, or coverage fails the suite
rather than silently passing. They are guarded to skip cleanly only if ``uv`` is not
on PATH (never to mask a real failure).
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

import pytest

# ── Repository / package layout (resolved from this file, no CWD assumptions) ──
_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_PKG_DIR = _REPO_ROOT / "src" / "pinewood_derby"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# NFR thresholds, mirrored from PRD §7 / profile (not from the implementation).
_PERF_BUDGET_S = 5e-3          # < 5 ms per simulate() on STANDARD_TRACK
_ENGINE_COVERAGE_MIN = 90.0    # >= 90% on the engine package
_OVERALL_COVERAGE_MIN = 70.0   # >= 70% overall

# The stdlib modules the engine is permitted to use (PRD §7 l.187 / TRD §7).
_ALLOWED_STDLIB = {"math", "dataclasses", "enum", "random", "typing"}
# Tokens that would indicate file I/O or network access in engine source.
_FORBIDDEN_TOKENS = (
    "open(",
    "import socket",
    "import urllib",
    "import requests",
    "import http",
    "import os",
    "import sys",
    "import pathlib",
    "import subprocess",
)


def _uv_available() -> bool:
    return shutil.which("uv") is not None


# ───────────────────────────────────────────────────────────────────────────── #
# Helpers — build a valid, seed-independent (RAIL_RIDER) car for the perf test.
# ───────────────────────────────────────────────────────────────────────────── #
def _make_perf_car() -> Any:
    from pinewood_derby.car import Alignment, Axle, BodyShape, CarDesign, Wheels
    from pinewood_derby.units import Length, Mass

    return CarDesign(
        mass=Mass.from_ounces(5.0),
        com_ahead_of_rear_axle=Length.from_inches(0.85),
        wheelbase=Length.from_inches(4.375),
        wheels=Wheels(
            count_touching=4,
            wheel_mass=Mass.from_ounces(0.09),
            outer_radius=Length.from_inches(0.595),
            inner_radius=Length.from_inches(0.37),
            axle_radius=Length.from_inches(0.045),
        ),
        body=BodyShape(drag_coefficient=0.30, frontal_area=0.0028),
        axle=Axle(friction_coefficient=0.20),
        alignment=Alignment.RAIL_RIDER,
    )


# ───────────────────────────────────────────────────────────────────────────── #
# NFR: Performance — a single simulate() on STANDARD_TRACK is < 5 ms.
# ───────────────────────────────────────────────────────────────────────────── #
def test_nfr_perf_single_simulate_under_5ms_on_standard_track() -> None:
    """A single ``simulate()`` on the STANDARD_TRACK with fixed dt/seed completes in
    under the 5 ms budget. Deterministic inputs (RAIL_RIDER, seed=0, dt=1e-3) and a
    best-of-N measurement remove scheduler jitter while keeping the assertion honest
    (best-case is the cleanest lower bound on the engine's intrinsic cost)."""
    from pinewood_derby.engine import simulate
    from pinewood_derby.track import STANDARD_TRACK

    car = _make_perf_car()

    # Warm up imports / branch prediction so we time steady-state, not first-call cost.
    simulate(car, STANDARD_TRACK, dt=1e-3, seed=0)

    best = float("inf")
    for _ in range(50):
        start = time.perf_counter()
        simulate(car, STANDARD_TRACK, dt=1e-3, seed=0)
        best = min(best, time.perf_counter() - start)

    assert best < _PERF_BUDGET_S, (
        f"simulate() took {best * 1000:.3f} ms (best of 50); "
        f"budget is {_PERF_BUDGET_S * 1000:.1f} ms"
    )


def test_nfr_perf_uses_documented_default_dt_and_seed() -> None:
    """The perf budget is asserted against the engine's documented defaults: a
    bare ``simulate(car)`` (dt=1e-3, seed=0, STANDARD_TRACK by default) is the call
    the budget protects, and it returns a real result, not an early bail-out."""
    from pinewood_derby.engine import simulate

    car = _make_perf_car()
    simulate(car)  # warmup with all defaults

    best = float("inf")
    for _ in range(50):
        start = time.perf_counter()
        result = simulate(car)
        best = min(best, time.perf_counter() - start)

    assert result.trajectory, "simulate() must return a populated trajectory"
    assert best < _PERF_BUDGET_S, (
        f"default simulate(car) took {best * 1000:.3f} ms; budget {_PERF_BUDGET_S * 1000:.1f} ms"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# NFR: Lint — `uv run ruff check .` is clean (exit 0) with tests included.
# ───────────────────────────────────────────────────────────────────────────── #
def test_nfr_lint_ruff_clean() -> None:
    """The exact profile lint command exits 0 over the whole repo (src + tests),
    so this new test file is itself lint-clean."""
    if not _uv_available():
        pytest.skip("uv not on PATH; lint NFR verified by the gate's own command")
    proc = subprocess.run(
        ["uv", "run", "ruff", "check", "."],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"`ruff check .` failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# NFR: Typing — `uv run mypy .` passes under strict with tests included.
# ───────────────────────────────────────────────────────────────────────────── #
def test_nfr_typecheck_mypy_strict_clean() -> None:
    """The exact profile typecheck command exits 0 under strict mode over the repo,
    so this new test file introduces no type errors."""
    if not _uv_available():
        pytest.skip("uv not on PATH; typing NFR verified by the gate's own command")
    proc = subprocess.run(
        ["uv", "run", "mypy", "."],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"`mypy .` failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    )


# ───────────────────────────────────────────────────────────────────────────── #
# NFR: Coverage — engine >= 90%, overall >= 70%.
# ───────────────────────────────────────────────────────────────────────────── #
def _parse_total_coverage(report: str) -> float:
    """Extract the overall TOTAL coverage percentage from a coverage term report."""
    match = re.search(r"^TOTAL\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)%", report, re.MULTILINE)
    assert match is not None, f"could not find TOTAL line in coverage report:\n{report}"
    return float(match.group(1))


def _parse_module_coverage(report: str, module_suffix: str) -> float:
    """Extract a single module's coverage percentage by path suffix (e.g. engine.py)."""
    pattern = rf"^\S*{re.escape(module_suffix)}\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)%"
    match = re.search(pattern, report, re.MULTILINE)
    assert match is not None, (
        f"could not find {module_suffix} line in coverage report:\n{report}"
    )
    return float(match.group(1))


# Re-entrancy guard env var: any pytest spawned *by this coverage test* sets it, so a
# nested invocation of this same test self-skips instead of forking again. This makes the
# measurement robust even though some pre-existing tests (the WI-7 adversarial suite)
# themselves shell out to ``pytest tests/`` — without the guard those could mutually
# re-trigger this full-suite run and fork-bomb the runner.
_COVERAGE_REENTRY_FLAG = "PD_NFR_COVERAGE_RUNNING"

# Test modules that *themselves* spawn a full ``pytest tests/`` subprocess. Running them
# inside this coverage child would re-enter the suite recursively; their own in-process
# engine coverage is negligible (they mostly shell out), so ignoring them does not
# understate the engine numbers the gate cares about. (test_nfr_wi13.py is this file.)
_SUITE_SPAWNING_MODULES = (
    "tests/test_nfr_wi13.py",
    "tests/test_engine_adversarial_wi7_adv_p2_001.py",
)


def test_nfr_coverage_engine_and_overall_meet_bar() -> None:
    """Running the suite under coverage reports engine package coverage >= 90% and
    overall >= 70%.

    The measurement spawns a single inner ``pytest --cov`` over the ``tests/`` tree with
    the project's default ``addopts`` cleared (we set our own ``--cov`` explicitly) and
    every *full-suite-spawning* module ignored (this file and the WI-7 adversarial test
    that itself runs ``pytest tests/``). Ignoring those is both correct and necessary:
    they exercise **no** additional engine lines in-process (they shell out), so dropping
    them does not understate engine coverage — and it breaks a pathological mutual
    recursion (this coverage test ↔ the WI-7 suite-spawner) that would otherwise fork the
    full suite without bound. A re-entrancy env guard self-skips any deeper nesting as a
    belt-and-suspenders. Every other test module still runs, so the engine/overall numbers
    are faithful to the real coverage the gate cares about."""
    if os.environ.get(_COVERAGE_REENTRY_FLAG) == "1":
        pytest.skip("nested coverage measurement; outer run already asserts the bar")
    if not _uv_available():
        pytest.skip("uv not on PATH; coverage NFR verified by the gate's own command")

    ignore_args: list[str] = []
    for module in _SUITE_SPAWNING_MODULES:
        ignore_args.append(f"--ignore={module}")

    env = dict(os.environ)
    env[_COVERAGE_REENTRY_FLAG] = "1"

    proc = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            "tests",
            "-o",
            "addopts=",  # drop the project's default --cov so we control instrumentation
            "-p",
            "no:cacheprovider",
            "--cov=pinewood_derby",
            "--cov-report=term-missing",
            *ignore_args,
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    report = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"inner pytest run failed:\n{report}"

    overall = _parse_total_coverage(report)
    assert overall >= _OVERALL_COVERAGE_MIN, (
        f"overall coverage {overall}% < {_OVERALL_COVERAGE_MIN}% bar\n{report}"
    )

    # Engine package coverage: every src/pinewood_derby/*.py except the deferred
    # __main__ entry-point placeholder (UI not built) must clear the 90% engine bar.
    engine_modules = ("car.py", "engine.py", "result.py", "track.py", "units.py")
    for module in engine_modules:
        cov = _parse_module_coverage(report, module)
        assert cov >= _ENGINE_COVERAGE_MIN, (
            f"engine module {module} coverage {cov}% < {_ENGINE_COVERAGE_MIN}% bar\n{report}"
        )


# ───────────────────────────────────────────────────────────────────────────── #
# NFR: Dependencies / safety — engine imports stdlib only; pyproject deps empty.
# ───────────────────────────────────────────────────────────────────────────── #
def _engine_source_files() -> list[Path]:
    files = sorted(_PKG_DIR.glob("*.py"))
    assert files, f"no engine source files found under {_PKG_DIR}"
    return files


def _imported_top_modules(source: str) -> set[str]:
    """Top-level module names imported by a source file (absolute imports only;
    intra-package relative imports like ``from .units import ...`` are skipped)."""
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import within pinewood_derby; not an external dep
            if node.module:
                modules.add(node.module.split(".")[0])
    return modules


def test_nfr_engine_imports_stdlib_only() -> None:
    """Every module in the engine package imports only the stdlib modules the spec
    allows (math, dataclasses, enum, random, typing) plus ``__future__`` — never a
    third-party package. Verified statically across the whole package surface."""
    allowed = _ALLOWED_STDLIB | {"__future__"}
    stdlib = set(sys.stdlib_module_names)
    for path in _engine_source_files():
        modules = _imported_top_modules(path.read_text(encoding="utf-8"))
        for module in modules:
            assert module in allowed, (
                f"{path.name} imports {module!r}, outside the allowed engine stdlib "
                f"set {sorted(allowed)}"
            )
            # Belt-and-suspenders: the allowed name is genuinely stdlib (or __future__),
            # never a vendored third-party shadow.
            assert module == "__future__" or module in stdlib, (
                f"{path.name} imports {module!r} which is not a stdlib module"
            )


def test_nfr_engine_has_no_io_or_network_tokens() -> None:
    """No engine module performs file I/O or network access: scan each source file for
    forbidden tokens (open(, socket/urllib/http/requests, os/sys/pathlib/subprocess)."""
    for path in _engine_source_files():
        source = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN_TOKENS:
            assert token not in source, (
                f"{path.name} must not perform I/O / network / process access: "
                f"found forbidden token {token!r}"
            )


def test_nfr_engine_uses_local_seeded_rng_not_module_global() -> None:
    """Randomness flows through a per-call ``random.Random(seed)`` — never the module
    global ``random.random``/``random.seed`` — keeping the engine deterministic and
    free of hidden process-global state."""
    engine_src = (_PKG_DIR / "engine.py").read_text(encoding="utf-8")
    assert "random.Random(" in engine_src, "engine must construct a local random.Random(seed)"
    for global_call in ("random.seed(", "random.uniform(", "random.random("):
        assert global_call not in engine_src, (
            f"engine must not call the module-global RNG: found {global_call!r}"
        )


def test_nfr_pyproject_runtime_dependencies_are_empty() -> None:
    """The runtime dependency list stays empty (engine is dependency-free, PRD §7
    l.187 / TRD §7): ``[project].dependencies == []``."""
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert deps == [], f"engine must be dependency-free; pyproject dependencies = {deps}"
