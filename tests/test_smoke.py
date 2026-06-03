"""Environment smoke test — verifies the toolchain runs.

The build loop's QA agent replaces this with real, behavior-driven physics tests.
"""

import pinewood_derby


def test_package_imports() -> None:
    assert pinewood_derby.__version__ == "0.0.0"
