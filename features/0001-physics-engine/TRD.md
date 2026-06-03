# TRD — Pinewood Derby Physics Simulation Engine

- **App:** pinewood-derby-sim · **Feature:** `0001-physics-engine`
- **Status:** approved (open questions resolved and user-approved 2026-06-02)
- **Companion:** [`PRD.md`](./PRD.md) · **Domain truth:** [`docs/physics-spec.md`](../../docs/physics-spec.md)
- **Last updated:** 2026-06-02

This TRD describes *how* to build the engine specified in the PRD. It is consistent with the app
profile's stack (Python 3.12, uv, pure dependency-free engine, mypy `strict`, ruff, pytest) and
grounds every model choice in `docs/physics-spec.md`.

---

## 1. Architecture & module layout

Pure simulation engine, no UI/I/O. New modules under the existing `pinewood_derby` package:

```
src/pinewood_derby/
  __init__.py            # re-export public API (simulate, CarDesign, Track, RaceResult, ...)
  units.py               # value objects: Mass, Length, Angle; SI NewType aliases
  constants.py           # BSA + spec constants (M_max, g, RHO, m_w, defaults, presets)
  car.py                 # CarDesign + sub-objects (Wheels, BodyShape, Axle, Alignment) + validation
  track.py               # Track (validated), angle_at(position), STANDARD_TRACK
  result.py              # RaceResult, Outcome, EnergyLedger, NormalForces (frozen)
  engine.py              # simulate(...): the Euler integration loop + force model
tests/                   # QA-owned behavior tests (one+ per acceptance criterion)
```

- **Strict separation:** physics lives in `engine.py`; domain types are dumb, validated, immutable
  data. No global mutable state.
- **Determinism:** all randomness flows through a `random.Random(seed)` instance created inside
  `simulate(...)`; never the module-global `random`.

## 2. Units strategy (mypy strict, no unit confusion)

Per the profile ("don't pass bare floats where grams vs ounces could be confused"):

- **Boundary value objects** (frozen dataclasses) carry units and convert explicitly:
  - `Mass` — `.kg`, `.ounces`; `Mass.from_ounces(5.0)`, `Mass.from_grams(141.748)`.
  - `Length` — `.m`, `.inches`, `.feet`; `Length.from_inches(0.85)`, `Length.from_feet(10)`.
  - `Angle` — `.radians`, `.degrees`; `Angle.from_degrees(30)`.
  - Round-trip conversions are exact within float tolerance (unit test).
- **Hot-loop internals** use plain SI `float`s with `NewType` aliases for readability:
  `Meters`, `MetersPerSecond`, `Newtons`, `Joules`, `Kilograms`, `Radians`. Conversion to SI
  happens once at the API boundary, keeping the integration loop allocation-free (perf NFR).
- Conversion factors centralized in `units.py` (`OZ_TO_KG = 0.0283495`, `IN_TO_M = 0.0254`, …).

## 3. Data model / contracts

```python
class Outcome(enum.Enum):
    FINISHED = "finished"
    DNF = "dnf"                 # unstable: front lifts / wobble crash (spec §4.2)

class Alignment(enum.Enum):
    STRAIGHT = "straight"       # seeded ping-pong, F_rail ~ U(1.5, 3.0) N
    RAIL_RIDER = "rail_rider"   # constant F_rail = 0.05 N

@dataclass(frozen=True)
class Wheels:
    count_touching: int         # 3 or 4
    wheel_mass: Mass            # m_w per wheel
    outer_radius: Length        # R_outer
    inner_radius: Length        # R_inner (bore-side wall)
    axle_radius: Length         # r_axle (nail shank)
    def moment_of_inertia(self) -> float:    # I = ½ m_w (R_o² + R_i²)  [kg·m²]

@dataclass(frozen=True)
class BodyShape:
    drag_coefficient: float     # C_d
    frontal_area: float         # A [m²]  (height × width)
    # presets: BodyShape.WEDGE (0.20), BodyShape.BLOCK (0.85)

@dataclass(frozen=True)
class Axle:
    friction_coefficient: float # μ_axle  (presets: POLISHED_GRAPHITE 0.10, UNPREPARED 0.35)

@dataclass(frozen=True)
class CarDesign:
    mass: Mass                              # M (chassis + wheels)
    com_ahead_of_rear_axle: Length          # d_COM
    wheelbase: Length                       # L
    wheels: Wheels
    body: BodyShape
    axle: Axle
    alignment: Alignment
    # __post_init__ runs validation (Section 6); frozen → validated-once, immutable

@dataclass(frozen=True)
class Track:
    ramp_length: Length
    ramp_angle: Angle
    transition_radius: Length   # circular-arc radius joining ramp→flat (0 = sharp)
    flat_length: Length
    def angle_at(self, position_m: float) -> float:   # radians; piecewise + arc blend
    # STANDARD_TRACK: 10 ft ramp @ 30°, transition arc, ~32 ft flat (spec §1.2)

@dataclass(frozen=True)
class NormalForces:
    front: float                # N_f  [N]
    rear: float                 # N_r  [N]

@dataclass(frozen=True)
class EnergyLedger:
    pe_initial: float           # M·g·Δh_com  [J]
    ke_linear_final: float      # ½ M v²
    ke_rotational_final: float  # Σ ½ I ω²
    w_gravity: float            # Σ F_grav·dx (discrete)
    w_drag: float               # Σ F_drag·dx
    w_axle: float               # Σ F_axle·dx
    w_rail: float               # Σ F_rail·dx

@dataclass(frozen=True)
class TrajectoryPoint:
    t: float; position: float; velocity: float; angle: float

@dataclass(frozen=True)
class RaceResult:
    outcome: Outcome
    race_time_s: float | None           # None iff not FINISHED
    exit_velocity: float                # v at end of ramp [m/s]
    top_speed: float
    finish_velocity: float
    energy: EnergyLedger
    normal_forces: NormalForces
    legal_weight: bool                  # M ≤ M_max
    trajectory: tuple[TrajectoryPoint, ...]   # down-sampled (≤ ~500 pts)
```

**Public entry point:**

```python
def simulate(
    car: CarDesign,
    track: Track = STANDARD_TRACK,
    *,
    dt: float = 1e-3,
    seed: int = 0,
) -> RaceResult: ...
```

## 4. Physics / integration approach

Time-step Euler integration of the COM along the track (spec §6), starting at rest.

**Per step** at COM arc-position `s`, velocity `v`:
1. `θ = track.angle_at(s)`  (ramp angle → arc blend → 0 on flat; continuous, AC-T2)
2. Forces (all in N):
   - `F_gravity = M·g·sin θ`
   - `F_normal  = M·g·cos θ`  (used for axle friction load)
   - `F_drag    = ½·ρ·v²·C_d·A`                              (spec §3.1)
   - `F_axle    = N·μ·(r_axle / R_outer)·(F_normal / N…)` → use per-wheel normal load; total
     `F_axle = μ·(r_axle/R_outer)·F_normal` summed over the `N` touching wheels (load shared by
     count). (spec §3.2)
   - `F_rail`: RAIL_RIDER → `0.05`; STRAIGHT → `rng.uniform(1.5, 3.0)` per step, times a **wobble
     multiplier** that grows as `N_f → 0` for unstable `d_COM` (spec §3.3/§4.2).
3. **Effective inertia** (rotational coupling): the wheels' rotation resists acceleration. Using
   `ω = v/R_outer`, the linear+rotational system accelerates as
   `a = F_net / (M + N·I/R_outer²)`  — i.e. `rotational_inertia_modifier = N·I/R_outer²` in the
   spec's pseudocode. This is the mechanism by which lighter wheels / fewer wheels → faster
   (AC-WH1, AC-WH2, AC-E2).
4. `F_net = F_gravity − F_drag − F_axle − F_rail`
5. Euler update: `v += a·dt`; `s += v·dt`; `t += dt`. Clamp `v ≥ 0` (a stalled car does not roll
   backward up the flat).
6. Accumulate the energy ledger: `w_gravity += F_gravity·dx`, etc. (so AC-E1 closes **by
   construction** regardless of Euler truncation error).

**Placement (d_COM) wiring — the two real mechanisms (spec §4, profile):**
- **Start height:** the COM's initial arc-position on the ramp depends on `d_COM`; mass biased
  rearward (smaller `d_COM`) starts **higher** → larger `pe_initial` → faster (AC-P1). Model the
  release as the front bumper at the start line; the COM sits `(L − d_COM)`-related distance up-ramp.
- **Normal-force distribution / stability:** on the flat, `N_f = M·g·(d_COM/L)`,
  `N_r = M·g·(1 − d_COM/L)` (AC-P4). As `d_COM → 0`, `N_f → 0` → front lifts. Below the spec's
  `0.625 in` threshold the wobble multiplier diverges and the run ends in `DNF` (AC-P3).

**Finish-line interpolation (A3, AC-E3/AC-O2):** when `s` crosses `track_length` between steps,
linearly interpolate `t` at the crossing so `race_time_s` is not quantized to `dt`.

**DNF detection:** if `N_f ≤ 0` (front lifts) at any point, or the wobble-amplified `F_rail` stalls
the car (`v → 0` before the finish on the flat), return `outcome = DNF`, `race_time_s = None`,
with the partial trajectory and the energy ledger up to the failure.

**Trajectory down-sampling:** record every step internally but emit ≤ ~500 evenly-spaced
`TrajectoryPoint`s (keeps `RaceResult` bounded for the future UI; A7).

## 5. Constants (`constants.py`)

From the spec (§1.1) plus geometry defaults from PRD A4/A5 — **confirmed by the user 2026-06-02**
(BSA-typical, each with a sourced comment; `R_inner` stays a flagged, tunable placeholder):

```python
G = 9.81                      # m/s²
RHO_AIR = 1.225               # kg/m³
MAX_MASS = Mass.from_ounces(5.0)          # 0.141748 kg
STD_WHEEL_MASS = Mass.from_ounces(0.09)   # 0.00255 kg
# --- geometry NOT in the spec; defaults pending confirmation (PRD A4/A5) ---
STD_WHEELBASE   = Length.from_inches(4.375)
STD_R_OUTER     = Length.from_inches(0.595)
STD_R_INNER     = Length.from_inches(0.37)    # placeholder bore-wall radius
STD_AXLE_RADIUS = Length.from_inches(0.045)
STD_FRONTAL_AREA = 0.0028     # m² placeholder (≈ 1.75" × 2.5")
# placement zones (spec §4.2)
COM_OPTIMAL = (Length.from_inches(0.75), Length.from_inches(1.0))
COM_UNSTABLE_BELOW = Length.from_inches(0.625)
# presets
CD_WEDGE, CD_BLOCK = 0.20, 0.85
MU_POLISHED_GRAPHITE, MU_UNPREPARED = 0.10, 0.35
RAIL_F_RAIL_RIDER = 0.05      # N
RAIL_PINGPONG_RANGE = (1.5, 3.0)  # N
```

## 6. Validation & error handling

`__post_init__` on each frozen dataclass validates and raises `ValueError` with a clear message:

| Input | Rule | AC |
| --- | --- | --- |
| `mass` | `> 0` | AC-W3 |
| `com_ahead_of_rear_axle` | `0 < d_COM < wheelbase` | AC-P5 |
| `wheelbase` | `> 0` | — |
| `wheels.count_touching` | `∈ {3, 4}` | AC-WH3 |
| `wheels` radii/mass | all `> 0`; `inner < outer`; `axle < outer` | AC-WH3 |
| `body.drag_coefficient`, `frontal_area` | `> 0` | AC-A3 |
| `axle.friction_coefficient` | `≥ 0` | AC-F2 |
| `track` lengths | `> 0` | AC-T3 |
| `track.ramp_angle` | `0° < θ < 90°` | AC-T3 |
| `track.transition_radius` | `≥ 0` | AC-T3 |
| `simulate(dt=...)` | `dt > 0` | — |

Over-weight (`mass > MAX_MASS`) is **not** an error — it sets `legal_weight = False` (AC-W2, A1).

## 7. Dependencies

- **Runtime:** Python **stdlib only** — `math`, `dataclasses`, `enum`, `random`, `typing`.
  `pyproject.toml` `dependencies = []` stays empty (profile: engine dependency-free).
- **Dev:** existing `pytest`, `pytest-cov`, `ruff`, `mypy` (already in `[dependency-groups].dev`).

## 8. Performance

- Standard track ≈ 12.8 m; race ≈ 3–4 s; at `dt = 1e-3` → ~3–4k iterations of scalar float math →
  well under the **5 ms** budget. SI floats in the loop (no per-step object allocation) keep it
  fast. A timed test asserts `< 5 ms` with margin.
- If `dt = 1e-3` ever threatens the budget on CI, it is tunable per call; AC-E3 (convergence)
  guards that coarsening `dt` stays accurate.

## 9. Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| **Euler doesn't conserve energy exactly** → naive energy test flakes | Frame AC-E1 as a *ledger* that closes by construction (discrete work-energy theorem); AC-E4 checks gravity-work vs analytic PE with a dt-shrinking tolerance; AC-E3 checks convergence. |
| **Missing geometry constants** (A4/A5) → educationally wrong magnitudes | Surfaced as assumptions; behavioral ACs assert *direction/ordering*, not magic numbers, so they hold under any reasonable constants — but final constants need user sign-off. |
| **Seeded RNG nondeterminism** | All randomness via a local `random.Random(seed)`; AC-AL3 pins bit-identical reproducibility; RAIL_RIDER path is RNG-free. |
| **Priority-order invariant (AC-ED1) too brittle** | Assert only that weight+placement is the *largest* lever and aero the *smallest*; do not over-constrain the middle levers' relative order. |
| **d_COM start-height model under-specified** | TRD gives the recommended parameterization; QA's monotonicity tests + adversarial domain-correctness pass enforce the real tradeoff curve. |
| **Float clamp `v ≥ 0` masking a stall** | Stall detection (v→0 on flat before finish) routes to DNF rather than an infinite loop; integration loop has a max-time guard. |

## 10. Test strategy

- **Behavior-driven**, one+ test per acceptance criterion (AC-id referenced in test names);
  assertions on *relationships and bounds* (monotonic ordering, DNF vs finish, ledger closure,
  validation raises), not on implementation-coupled magic constants — matching the profile.
- **Determinism:** repeat-call equality (AC-AL3); seeded RNG.
- **Convergence:** dt-halving stability (AC-E3); dt-shrinking PE tolerance (AC-E4).
- **Boundaries/validation:** every `ValueError` path (the adversarial-review checklist: min/zero/
  out-of-range/wrong-type). 
- **Domain correctness:** the priority-order test (AC-ED1) and every directional "better build =
  faster" relationship — the educational-accuracy guardrail.
- **NFRs:** coverage ≥ 90% engine via `pytest --cov`; timed perf test < 5 ms; `ruff` + `mypy
  strict` in the gate.

## 11. Traceability (AC → module)

| Area | ACs | Primary module(s) |
| --- | --- | --- |
| Units / boundary types | AC-W2, AC-O1 | `units.py` |
| Car validation | AC-W3, AC-P5, AC-WH3, AC-A3, AC-F2 | `car.py` |
| Track geometry | AC-T1, AC-T2, AC-T3 | `track.py` |
| Force model & integration | AC-W1, AC-P1/2/3, AC-WH1/2, AC-A1/2, AC-F1, AC-AL1/2 | `engine.py` |
| Determinism / purity | AC-AL3, AC-PU1 | `engine.py` |
| Energy ledger & invariants | AC-E1/2/3/4 | `engine.py`, `result.py` |
| Output contract | AC-O1, AC-O2, AC-P4 | `result.py`, `engine.py` |
| Educational priority order | AC-ED1 | `engine.py` (composite test) |
