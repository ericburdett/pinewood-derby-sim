# PRD — Pinewood Derby Physics Simulation Engine

- **App:** pinewood-derby-sim
- **Feature:** `0001-physics-engine`
- **Status:** approved (open questions resolved and user-approved 2026-06-02)
- **Author:** Planner
- **Last updated:** 2026-06-02
- **Grounding docs:** [`profile.md`](../../profile.md) · [`docs/physics-spec.md`](../../docs/physics-spec.md)
  (authoritative domain reference)

> **Scope note.** This feature began as "weight + placement" but, per the product owner's decisions
> on 2026-06-02, now covers the **full single-car physics engine** from the engineering spec:
> weight, center-of-mass, wheels/rotational inertia, aerodynamic drag, axle friction, and
> alignment/rail behavior. The UI remains deferred. The directory/id was renamed
> `0001-weight-placement-engine` → `0001-physics-engine` on 2026-06-02 to match this scope.

---

## 1. Problem statement

The simulator's entire value rests on a **physically correct engine**: it teaches young men
(12–17) the *right* way to build a fast pinewood derby car, in the *right priority order*. A
"fun but wrong" result is the worst possible bug — it teaches bad engineering. Before any UI
exists, we need a pure, deterministic, dependency-free engine that takes a car design and a track
and predicts the run: the time, the outcome, the speeds, and a transparent energy breakdown that
explains *why* the car performed as it did.

This is also the first end-to-end exercise of the SDLC factory's TDD build loop, so the engine's
contract must be precise enough that QA can write a failing test from every acceptance criterion.

## 2. Target users

- **Immediate consumer:** the SDLC build loop (QA, developer, adversarial reviewer, PO) — the
  engine is validated entirely through tests in this feature.
- **Downstream consumer:** the deferred pygame UI, which will drive `simulate(...)` from slider
  toggles (spec §5) and animate the returned trajectory.
- **Ultimate audience:** kids 12–17 (and parents/leaders) learning derby physics.

## 3. Goals

- A pure function `simulate(car, track, *, dt, seed) -> RaceResult` that models all six levers from
  the spec with **directionally correct, real-world physics**.
- **Educational priority order preserved:** weight & placement are the dominant levers; aerodynamics
  is the smallest — the engine's numbers must reflect this ordering.
- Every result is **explainable**: a per-force energy ledger that closes (work-energy theorem).
- **Deterministic & reproducible**: fixed `dt` + seeded RNG → bit-identical results.
- Strictly typed (mypy `strict`), lint-clean (ruff), dependency-free (stdlib only), no I/O / no
  network — safe for children and trivially testable.

## 4. Non-goals / out of scope

- No UI, rendering, animation, or input widgets (pygame deferred to a later feature).
- **No translation, ranking, plain-language explanation, or "insights" in the engine.** Per the
  profile's *rich physics, simple presentation* constraint, all kid-facing framing — ranking the
  losses ("where did your speed go?"), wording, coaching, visuals — is owned by the future
  UI/explanation feature, not feature 0001. The engine emits **raw, neutral physics data** (energy
  ledger, speeds, normal forces, trajectory) structured so that layer can derive those answers
  trivially, but it does not compute or word them. (Decision 2026-06-02.)
- No persistence, accounts, leaderboards, networking, or telemetry.
- No multi-car / head-to-head racing in one call (single-car simulation; a heat is N calls).
- No CAD / cut-file / 3D-geometry modeling — principles, not part design.
- No real-hardware integration.
- Aerodynamics is modeled at the spec's fidelity (single `C_d`·`A` drag term), not CFD.

## 5. Functional requirements

The engine accepts an immutable **CarDesign** with all six levers and an immutable validated
**Track**, and returns an immutable **RaceResult**. Levers, per the spec:

| Lever | Input | Spec ref |
| --- | --- | --- |
| Total weight | `mass` (M) | §1.1 |
| Weight placement | `com_distance_ahead_of_rear_axle` (d_COM) | §4 |
| Wheels | count `N` (3/4), per-wheel mass `m_w`, radii → moment of inertia `I` | §2.1, §2.2 |
| Aerodynamics | drag coefficient `C_d`, frontal area `A` | §3.1 |
| Axle friction | coefficient `μ_axle`, `r_axle`, `R_outer` | §3.2 |
| Alignment | `STRAIGHT` (seeded ping-pong) or `RAIL_RIDER` (constant) | §3.3 |

The run is computed by **time-step Euler integration** of `F_net = F_gravity − F_drag − F_axle −
F_rail` over the track's piecewise geometry (ramp → smooth transition arc → flat), tracking linear
and rotational kinetic energy.

## 6. Acceptance criteria (testable)

Each criterion is behavioral and machine-checkable; QA writes ≥1 failing test per criterion.
"All else equal" means two `CarDesign`s identical except the named field, same track/dt/seed.

### Weight (M)
- **AC-W1** Within the stable placement zone, the **heavier** car finishes with a strictly smaller
  `race_time_s` (more mass → more PE → faster).
- **AC-W2** `mass ≤ 5.0 oz (141.748 g)` → `legal_weight = True`; `mass > limit` → `legal_weight =
  False` but the run is still simulated normally (the weight rule is reported, not enforced by
  physics). [assumption A1]
- **AC-W3** `mass ≤ 0` raises `ValueError`.

### Placement (d_COM) & stability tradeoff
- **AC-P1** Within the stable range, **decreasing d_COM** (shifting mass toward the rear) strictly
  decreases `race_time_s` (rear bias sits higher on the ramp / pushes longer).
- **AC-P2** A car with d_COM in the optimal zone **[0.75 in, 1.0 in]** finishes and is strictly
  faster than the same car at d_COM = 1.25 in (forward = stable but slow). (spec §4.2)
- **AC-P3** A car with **d_COM < 0.625 in** returns `outcome = DNF` with `race_time_s = None`
  (front normal force collapses → wobble/crash). This is the tradeoff: "more rear" stops helping
  and becomes a failure. [assumption A2]
- **AC-P4** On the flat, reported normal forces satisfy `N_f = M·g·(d_COM/L)` and
  `N_r = M·g·(1 − d_COM/L)` within tolerance, with `N_f + N_r ≈ M·g`; `N_f → 0` as `d_COM → 0`.
- **AC-P5** `d_COM` outside `(0, wheelbase)` raises `ValueError`.

### Wheels (N, I, m_w)
- **AC-WH1** A **3-wheels-touching** car is strictly faster than the otherwise-identical 4-wheel
  car (less rotational inertia + one less axle's friction). (spec §5)
- **AC-WH2** **Lightweight wheels** (reduced `m_w`, up to 60%) yield a strictly smaller
  `race_time_s` than standard wheels (lower `I` → more energy in linear KE). (spec §2.2)
- **AC-WH3** Moment of inertia is computed as `I = ½·m_w·(R_outer² + R_inner²)`. Invalid wheel
  geometry (`R_inner ≥ R_outer`, `r_axle ≥ R_outer`, any radius/mass ≤ 0) and `N ∉ {3, 4}` raise
  `ValueError`.

### Aerodynamics (C_d, A)
- **AC-A1** A **wedge** body (`C_d = 0.20`) is strictly faster than a **wood-block** body
  (`C_d = 0.85`), all else equal. (spec §3.1)
- **AC-A2** The energy lost to drag (`energy.w_drag`) increases with `C_d`, with frontal area `A`,
  and with flat-section length (drag bites more at higher speed on the flat).
- **AC-A3** `C_d ≤ 0` or `frontal_area ≤ 0` raises `ValueError`.

### Axle friction (μ)
- **AC-F1** **Polished + graphite** axles (`μ = 0.10`) yield a strictly smaller `race_time_s` than
  unpolished/no-lube (`μ = 0.35`), all else equal. (spec §3.2)
- **AC-F2** `F_axle = N_wheel·μ·(r_axle / R_outer)`; reported `energy.w_axle` increases with `μ`.
  `μ < 0` raises `ValueError`.

### Alignment / rail (seeded)
- **AC-AL1** A **RAIL_RIDER** car (constant `F_rail = 0.05 N`) is strictly faster than the
  otherwise-identical **STRAIGHT** (ping-ponging) car, for a fixed seed. (spec §3.3, §5)
- **AC-AL2** STRAIGHT-alignment rail friction is drawn from the seeded RNG within `[1.5, 3.0] N`;
  reported `energy.w_rail` reflects it. An **unstable** d_COM amplifies rail friction (wobble
  multiplier) per spec §4.2.
- **AC-AL3** **Determinism:** identical `(car, track, dt, seed)` → a **bit-identical** `RaceResult`
  across repeated calls (including the random ping-pong path). RAIL_RIDER results are
  seed-independent.

### Track
- **AC-T1** `Track` is an explicit validated input. A **longer** total track → longer
  `race_time_s` for the same car; a **steeper** ramp angle (within `(0°, 90°)`) → faster time.
- **AC-T2** `Track.angle_at(position)` returns the ramp angle on the ramp, `0` on the flat, and a
  **continuous, monotonic** interpolation through the transition arc (no discontinuous jump). (spec
  §1.2)
- **AC-T3** Invalid track (any length ≤ 0, ramp angle ∉ `(0°, 90°)`, transition radius < 0) raises
  `ValueError`. A `STANDARD_TRACK` constant matching the spec (10 ft ramp @ 30°, ~32 ft flat) is
  provided.

### Energy / physics integrity (invariants)
- **AC-E1** **Ledger closes:** for a FINISHED run, `KE_total_final ≈ W_gravity − (W_drag + W_axle +
  W_rail)` within relative tolerance `1e-6` (discrete work-energy theorem holds by construction).
- **AC-E2** `KE_total = ½·M·v² + Σ ½·I·ω²` with `ω = v / R_outer`; the rotational fraction is `> 0`
  for massive wheels and **decreases** when wheels are lightened or a wheel is lifted (3-wheel).
- **AC-E3** **Convergence / numerical stability:** halving `dt` changes `race_time_s` by `< 1%`.
- **AC-E4** Reported `W_gravity` equals the analytic PE drop `M·g·Δh_com` within a tolerance that
  shrinks as `dt → 0`.

### Output contract
- **AC-O1** `simulate(...)` returns an **immutable** `RaceResult` with: `outcome`, `race_time_s`
  (`None` iff not FINISHED), `exit_velocity` (end of ramp), `top_speed`, `finish_velocity`,
  `energy` breakdown, `normal_forces` (`N_f`, `N_r`), `legal_weight`, and a sampled `trajectory`.
  All numeric outputs are finite; velocities ≥ 0. [assumption A7 covers trajectory]
- **AC-O2** FINISHED ⇒ `race_time_s > 0` and finite; DNF ⇒ `race_time_s is None` and
  `outcome = DNF`.

### Educational correctness (domain)
- **AC-ED1** **Priority order holds:** starting from an all-levers-worst baseline car, the
  `race_time_s` improvement from optimizing **weight + placement** is the **largest** of any single
  lever category, and the improvement from the **aerodynamic** body change is the **smallest** —
  matching the spec's documented teaching priorities. [assumption A6]

### Purity
- **AC-PU1** The engine performs **no file I/O and no network access**, holds no module-level
  mutable state, and is composed of pure functions / frozen dataclasses (deterministic given
  inputs).

## 7. Non-functional requirements

| NFR | Requirement | Evidence |
| --- | --- | --- |
| Performance | A single `simulate(...)` completes in **< 5 ms** | timed test with margin (profile `quality_bars`) |
| Determinism | Fixed `dt` + seed ⇒ reproducible | AC-AL3, AC-PU1 |
| Typing | `uv run mypy .` passes under `strict`; unit-typed boundary (no bare floats where grams/oz/inches could be confused) | typecheck gate |
| Lint | `uv run ruff check .` clean | lint gate |
| Coverage | **≥ 90%** on the engine; **≥ 70%** overall | `pytest --cov` |
| Dependencies | Engine uses **stdlib only** (`math`, `dataclasses`, `enum`, `random`, `typing`) | pyproject `dependencies = []` |
| Safety | No PII, no network, offline — safe for children | AC-PU1 |
| Educational accuracy | All directional relationships and the priority order are physically correct | AC-W*/P*/WH*/A*/F*/AL*/ED1 |

## 8. Assumptions & decisions

Decisions the Planner made where the spec was silent or open. Items marked **[confirmed
2026-06-02]** were resolved by the user at the approval gate; the rest are documented defaults the
user did not object to and may revisit.

- **A1 — Over-weight handling:** `M > 5.0 oz` is **reported** (`legal_weight = False`) and still
  simulated, *not* an error or auto-DNF. (Teaches "heavier is faster, but the rules cap you.")
- **A2 — DNF semantics [confirmed 2026-06-02]:** an unstable car (`d_COM < 0.625 in`) is a **DNF
  with `race_time_s = None`** ("crash"), returning the partial trajectory and the energy ledger up
  to the failure — *not* a finite heavy-penalty time. The spec allowed either; the user chose the
  legible-cliff model.
- **A3 — Time step:** default `dt = 1e-3 s` (spec showed `0.01`) with **linear finish-line
  interpolation** so `race_time_s` isn't quantized to `dt`. Tunable per call.
- **A4 — Geometry constants [confirmed 2026-06-02]:** the spec gives `M_max`, `m_w`, `g`, `ρ`,
  `C_d`, `μ`, angles and lengths, but **not** wheel `R_outer`/`R_inner`, axle `r_axle`, or
  **wheelbase L**. The user accepted the Planner's **BSA-typical documented defaults**: `R_outer ≈
  0.595 in`, a bore-based `R_inner` (flagged placeholder, tunable), `r_axle ≈ 0.045 in` nail shank,
  wheelbase `L ≈ 4.375 in`. Each lands in `constants.py` with a sourced comment.
- **A5 — Frontal area `A` [confirmed 2026-06-02]:** the spec gives `C_d` but `A = height × width`
  needs default body dimensions; the user accepted a documented default frontal area (≈ `1.75 in ×
  2.5 in`) with body-shape presets.
- **A6 — Priority-order invariant (AC-ED1):** the engine asserts weight+placement is the dominant
  lever and aerodynamics the smallest. Matches spec §5 takeaways (friction/axle is "biggest lever
  after weight"); the middle levers' exact ordering among themselves is *not* asserted, only the top
  and bottom.
- **A7 — Trajectory output [confirmed 2026-06-02]:** `RaceResult` includes a **down-sampled
  trajectory** (≤ ~500 points of `t, position, velocity, angle`) now, so the deferred pygame UI can
  animate the run without re-simulating.

> **Note on educational realism vs. correctness.** Because A4/A5 absolute magnitudes are not pinned
> by the spec, every behavioral acceptance criterion is written **directionally** (orderings,
> bounds, ledger closure) and holds under any reasonable constants. The confirmed defaults set the
> *realism* of absolute numbers; they cannot make a directional AC pass or fail.

## 9. Open questions for the user

**All open questions are resolved (2026-06-02).** The approval gate is clear.

1. **Geometry constants (A4) and frontal-area defaults (A5)** → *Resolved:* accept the Planner's
   BSA-typical documented defaults.
2. **DNF-vs-penalty choice (A2)** → *Resolved:* DNF with `race_time_s = None`.
3. **Feature id** (rename vs. keep `0001-weight-placement-engine`) → *Resolved:* renamed to
   **`0001-physics-engine`** to match the broadened scope.
