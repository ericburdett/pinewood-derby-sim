---
# ── Machine-readable fields (parsed by the workflow) ──────────────────────────
app: pinewood-derby-sim
archetype: web-app                   # 0006 (2026-06-03): desktop/pygame path DROPPED; this is now a static web app
repo: ./
description: An interactive web simulator that teaches kids the physics of building a fast pinewood derby car.

language: [python, typescript]       # pure-Python engine + present.py; TypeScript front-end (web/)
framework: [vite]                    # UI = TypeScript + Vite + HTML <canvas>, Pyodide vendored same-origin (no CDN). The pinewood_derby ENGINE stays pure, dependency-free Python (pyproject dependencies=[]).
runtime: "python 3.12 (engine; runs in-browser via Pyodide/WASM) + node (web build/test tooling)"
package_manager: uv                  # Python: uv-managed venv + 3.12. Web: npm (web/ workspace).

# DUAL TEST STACK (0006): the pure Python layer (engine + present.py) is tested with
# pytest; the browser UI is tested with Playwright headless. Each work item uses the
# command matching its stack — pure-logic WIs run the bare commands, UI WIs run the
# `*_web` commands (run from the web/ workspace).
commands:                            # exact commands agents run (the contract for tooling)
  install: "uv sync"
  install_web: "npm --prefix web install"
  test: "uv run pytest"              # Python engine + present.py (pure logic) — pytest GREEN bar
  test_one: "uv run pytest {path}"
  test_web: "npm --prefix web test"  # Playwright headless UI specs — the UI GREEN bar
  lint: "uv run ruff check ."
  lint_web: "npm --prefix web run lint"
  typecheck: "uv run mypy ."
  typecheck_web: "npm --prefix web run typecheck"   # tsc --noEmit
  build: "npm --prefix web run build"  # Vite static bundle for GitHub Pages (vendors engine + Pyodide)
  run: "npm --prefix web run dev"      # Vite dev server — the interactive app
  run_engine: "uv run python -m pinewood_derby"  # engine-only entry point (no UI)

quality_bars:
  coverage: ">= 90% on the simulation engine + present.py (pure logic); >= 70% overall"
  performance: "a single race simulation computes in < 5ms; after warm-up a race renders within ~100ms and the animation runs >= 30fps"
  security: "no PII collected; no network calls at runtime; all assets same-origin (no CDN); offline-capable; safe for children"
  web_testing: "browser/UI behavior verified with Playwright headless specs (one per UI acceptance criterion)"

product_plane:
  skills: ./.claude/skills           # app-specific skills (override system plane)
  hooks: ./.claude/settings.json     # app-specific hooks
  agents: []                         # rare app/archetype specialist agents

archetype_plane: []                  # web-app-plane artifacts (e.g. a Pyodide-bridge or Playwright-harness skill) will emerge from the loop
---

# Pinewood Derby Simulator — Profile

> Teaches kids the *best way* to build a pinewood derby car by letting them adjust a car's design
> and watch the physics play out on a simulated track. The learning goal is as important as the
> simulation: every result should reinforce a real, correct building principle.

## Overview
A simulator where a child configures a pinewood derby car — weight and where it's placed, axle and
wheel prep, alignment, lubrication, body shape — and races it on a standard sloped track. The sim
shows the run, the time, and *why* the car performed as it did, building intuition for the
real-world principles. Audience: kids **12–17, tuned to the younger end (~12)** (and their
parents/leaders/den leaders running a projector demo) — reading level and tone aimed at ~12 yet
legible for 17 — so the UI must be simple, visual, and encouraging. *(0006: reconciled from the
former ~7–12 to match the 0001 spec and 0003 PRD.)*

## Domain & glossary
The simulation must be **physically grounded** — teaching wrong physics is the worst possible bug.
Core established principles to model:

- **Weight limit** — Standard max is **5.0 oz (141.7 g)**. Build up to, not over, the limit. More
  mass = more potential energy on the slope.
- **Weight placement** — Mass toward the **rear** (commonly ~1 inch ahead of the rear axle) sits
  higher on the slope longer, converting more potential energy to kinetic energy. Too far back =
  unstable / can pop a wheel; this is a real tradeoff to model.
- **Friction (the biggest lever after weight)** — Polished axles, removed burrs/crimp marks, and
  dry graphite lubrication reduce rolling and bore friction. Less wheel-to-body and
  wheel-to-axle-head contact = faster.
- **Alignment** — A car that drifts into the rails or wanders loses energy. "Rail-riding" (a tiny
  consistent steer) and reducing the number of wheels in contact reduce friction losses.
- **Wheels** — Lighter, true (round, balanced) wheels with smooth bores have lower rotational
  inertia and friction.
- **Aerodynamics** — Minor at derby speeds but non-zero; lower, smoother bodies help slightly. Keep
  this appropriately small so kids learn the *real* priority order (weight & friction first).

> **Glossary**
> - **PE/KE** — potential / kinetic energy; the core of why placement and weight matter.
> - **Rail-riding** — deliberately steering a car to glide along one rail consistently.
> - **DNF** — a car that derails or stalls; the sim should make failure modes legible.

## Conventions
Rules the **developer** follows and the **auditor** checks:

- **Architecture:** strict separation of a **pure simulation engine** (`pinewood_derby` package, no
  UI / no I/O) from the **web UI layer** (`web/`: TypeScript + Vite + HTML `<canvas>`, with the
  engine run in-browser via Pyodide). The engine is where the physics lives and where TDD is
  richest; the UI adds **no physics** (consumes the engine's public API + the `present.py`
  translation layer). *(0006: was "pygame, deferred"; the desktop path is dropped.)*
- **Engine style:** pure functions / immutable dataclasses, no hidden state, deterministic given
  inputs (a fixed seed for any randomness) so tests are reproducible.
- **Typing:** full type hints; **mypy `strict`** must pass. Model domain quantities explicitly
  (don't pass bare floats where grams vs ounces could be confused — use named types/units).
- **Testing:** `pytest`, behavior-driven against the engine's physics (e.g. "more rear weight,
  within the stable range, yields a faster time"); test principles and tradeoffs, not
  implementation details.
- **Lint:** `ruff` clean.
- **Dependencies:** keep the **engine** (`pinewood_derby`, incl. `present.py`) **dependency-free**
  (`pyproject` `dependencies = []`, stdlib only); web/UI dev dependencies (Vite, Playwright,
  Pyodide) live in the **`web/`** workspace and never leak into the Python engine.

## Constraints
- **Educational accuracy is a hard requirement** — simulated outcomes must reflect real derby
  physics and the correct priority order of techniques. A "fun but wrong" result is a bug.
- **Rich physics, simple presentation** — the simulation stays physically deep, but nothing
  technical (Joules, Newtons, coefficients, integration) ever reaches the kid. Anything *shown* to a
  ~12-year-old (or a group/demo) must be plain-language, visual, and immediately legible: "where did
  your speed go?", not an energy ledger. Complexity lives behind the engine boundary; the
  presentation layer translates it. A result a kid can't make sense of is a usability bug.
- **No network, no accounts, no data collection at runtime** — safe for children; all assets
  same-origin (no CDN); offline-capable after first load.
- **Deployment target:** a **static web app** (TypeScript + Vite, engine in-browser via Pyodide)
  **hosted on GitHub Pages** — no server. *(0006: replaces the former local-desktop/pygame target,
  which is dropped.)*
- **Accessibility:** age-appropriate, readable, keyboard-navigable, WCAG-AA, never color-only;
  legible on a projector and a Chromebook.

## Out of scope / known limitations
- No real-hardware integration, no multiplayer. A **leaderboard is now planned (`0004`)** — opt-in
  and networked, with its own COPPA-safe design; still no accounts/PII in the core simulator.
- Not a CAD/3D modeling tool — it teaches principles, it doesn't design a physical cut file.
- Aerodynamics is modeled at low fidelity by design.

## Product-plane notes
_(empty — the synthesizer will populate app-specific skills/hooks/learnings here as it discovers
them, e.g. a "physics-validation" skill if engine accuracy becomes a recurring friction point.)_
