"""WI-3 — Adversarial edge tests for the CarDesign work item.

Covering tests for confirmed adversarial-review findings (gates.md Step 4 -> Step 1).
These are RED tests: they fail against the current state of the work item and must
pass once the developer fixes the finding, WITHOUT weakening WI-3's existing
behavioral tests in ``tests/test_car.py``.

Finding under test:

- WI3-F3 (error_exception_paths, high): the profile's typecheck gate command is
  *exactly* ``uv run mypy .`` (profile ``commands.typecheck``). Although
  ``[tool.mypy]`` sets ``files = ["src"]``, the explicit CLI path ``.`` overrides
  that and mypy type-checks the WI-3 test file too. ``tests/test_car.py`` then
  produces 9 mypy errors under ``strict``:
    * ``no-untyped-def`` on the helper functions ``_make_wheels`` / ``_make_body``
      / ``_make_axle`` / ``_make_car`` (missing return / parameter annotations),
    * eight ``unused-ignore`` on the frozen-mutation ``# type: ignore`` comments,
    * one ``comparison-overlap`` on the ``Alignment.STRAIGHT != Alignment.RAIL_RIDER``
      check.
  ``src/pinewood_derby/`` is itself mypy-clean; the failure is entirely in WI-3 test
  code, but the gate command (TRD §11 / PRD NFR "mypy strict passes") still exits
  non-zero. AC trace: PRD NFR "Typing: ``uv run mypy .`` passes under strict".

These tests shell out to the *exact* profile gate command so they assert the real
contract (the gate as run), not a paraphrase of it. They are deterministic: mypy is
a pure static analysis with no clock / network / RNG dependence, run against a fixed
checkout.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

# Repository root for this app = two levels up from this test file
# (.../pinewood-derby-sim/tests/test_car_adversarial.py -> .../pinewood-derby-sim).
APP_ROOT = Path(__file__).resolve().parent.parent
WI3_TEST_FILE = APP_ROOT / "tests" / "test_car.py"


def _run_mypy(*args: str) -> subprocess.CompletedProcess[str]:
    """Run mypy via the project's ``uv`` runner from the app root.

    Mirrors the profile's typecheck gate invocation (``uv run mypy ...``) so the
    assertion is against the same toolchain the gate uses. Skips (rather than
    fails spuriously) only if ``uv`` is entirely unavailable on the runner.
    """
    if shutil.which("uv") is None:
        pytest.skip("uv is not available on this runner; cannot exercise the typecheck gate")
    return subprocess.run(
        ["uv", "run", "mypy", *args],
        cwd=APP_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


# ───────────────────────────────────────────────────────────────────────────── #
# WI3-F3 — the WI-3 test file must be clean under the typecheck gate command.
# ───────────────────────────────────────────────────────────────────────────── #
def test_wi3f3_typecheck_gate_command_passes() -> None:
    """The exact profile gate command ``uv run mypy .`` must exit zero.

    This is the finding stated directly: as run, the gate currently exits non-zero
    because the WI-3 test code is type-checked and is not strict-clean.
    """
    result = _run_mypy(".")
    assert result.returncode == 0, (
        "the profile typecheck gate `uv run mypy .` exited non-zero "
        f"(rc={result.returncode}). The WI-3 test code must be mypy-strict clean so it "
        "does not break the gate:\n" + result.stdout + result.stderr
    )


def test_wi3f3_wi3_test_file_is_mypy_strict_clean() -> None:
    """Scope the finding to WI-3: ``tests/test_car.py`` itself must produce no mypy
    errors under ``strict``.

    Asserts there is no ``error:`` line attributed to the WI-3 test file. This isolates
    the WI-3 fix from any unrelated errors elsewhere in the tree, so a green here means
    the WI-3 test code (and only it) was made strict-clean.
    """
    result = _run_mypy(str(WI3_TEST_FILE))
    offending = [
        line
        for line in result.stdout.splitlines()
        if "test_car.py" in line and ": error:" in line
    ]
    assert offending == [], (
        "tests/test_car.py is not mypy-strict clean; the WI-3 test code breaks the "
        "typecheck gate. Offending lines:\n" + "\n".join(offending)
    )


def test_wi3f3_no_unused_type_ignore_in_wi3_test_file() -> None:
    """No-regression on the specific defect: the WI-3 test file must contain no
    ``unused-ignore`` errors (the eight stray ``# type: ignore`` comments on the
    frozen-mutation assertions). A correct fix removes the dead ignores rather than
    blanket-silencing the file."""
    result = _run_mypy(str(WI3_TEST_FILE))
    unused = [
        line
        for line in result.stdout.splitlines()
        if "test_car.py" in line and "unused-ignore" in line
    ]
    assert unused == [], (
        "tests/test_car.py has unused `# type: ignore` comments (unused-ignore):\n"
        + "\n".join(unused)
    )


def test_wi3f3_no_untyped_def_in_wi3_test_file() -> None:
    """No-regression: the WI-3 helper functions (``_make_wheels`` / ``_make_body`` /
    ``_make_axle`` / ``_make_car``) must carry full annotations so mypy reports no
    ``no-untyped-def`` for the file."""
    result = _run_mypy(str(WI3_TEST_FILE))
    untyped = [
        line
        for line in result.stdout.splitlines()
        if "test_car.py" in line and "no-untyped-def" in line
    ]
    assert untyped == [], (
        "tests/test_car.py has functions missing type annotations (no-untyped-def):\n"
        + "\n".join(untyped)
    )


def test_wi3f3_no_comparison_overlap_in_wi3_test_file() -> None:
    """No-regression: the ``Alignment.STRAIGHT != Alignment.RAIL_RIDER`` check triggers
    a ``comparison-overlap`` under strict (two distinct enum literals). The fix must
    keep the behavioral intent (the two members are distinct) without leaving a
    mypy-flagged non-overlapping comparison in the WI-3 test code."""
    result = _run_mypy(str(WI3_TEST_FILE))
    overlap = [
        line
        for line in result.stdout.splitlines()
        if "test_car.py" in line and "comparison-overlap" in line
    ]
    assert overlap == [], (
        "tests/test_car.py has a non-overlapping equality check (comparison-overlap):\n"
        + "\n".join(overlap)
    )
