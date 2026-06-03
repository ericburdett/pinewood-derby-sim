"""Test suite for the pinewood derby physics engine.

Marks ``tests`` as a package so the QA-owned test modules resolve as
``tests.<module>`` — letting the ``[[tool.mypy.overrides]] module = ["tests.*"]``
section apply to the whole test tree under the ``uv run mypy .`` gate command.
"""
