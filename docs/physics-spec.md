# Engineering Specification — Pinewood Derby Physics & Simulation Logic

> **Status:** authoritative domain reference (app-level, spans the whole simulator roadmap).
> **Provenance:** supplied by the product owner (Eric) on 2026-06-02. The Planner has lightly
> reformatted it into Markdown; the physics, constants, and constraints are unchanged.
> **How to use it:** this is the *domain truth* the engine must match. Each feature's TRD grounds
> its model in the relevant section here. Feature `0001-physics-engine` implements **all six
> levers** — weight (M), center-of-mass (d_COM), wheels/rotational inertia, aerodynamic drag, axle
> friction, and alignment/rail behavior — in one pure engine (scope broadened from weight+placement
> per PO decision 2026-06-02). The UI is a later feature. Teaching wrong physics is the worst
> possible bug — when in doubt, this document wins.

This document provides the exact physics equations, mechanical constraints, and algorithmic logic
required to program an accurate Pinewood Derby simulator. It is optimized for software developers
or AI agents building an educational tool for young men aged 12–17 to demonstrate aerodynamic and
mechanical optimization.

---

## 1. Simulation Constants & Environment Setup

To ensure the simulation reflects reality, use the standard track and physical constraints
specified by official BSA regulations.

### 1.1 Standard Constants

| Constant | Symbol | Value |
| --- | --- | --- |
| Maximum car weight | `M_max` | 5.0 oz ≈ 0.14175 kg |
| Standard wheel weight | `m_w` | 0.09 oz ≈ 0.00255 kg per wheel |
| Acceleration due to gravity | `g` | 9.81 m/s² |
| Density of air | `ρ` | 1.225 kg/m³ (at sea level) |

### 1.2 Track Geometry Setup

A standard competition track consists of two distinct zones:

- **The Ramp (inclined plane):** typically a 10-foot section inclined at an angle `θ ≈ 30°`.
- **The Flat (linear runout):** a 25-to-32-foot horizontal section (`0°`).
- **The Transition:** model this as a smooth circular-arc curve connecting the ramp to the flat to
  prevent abrupt normal-force spikes in the code.

---

## 2. Core Physics Engine Equations

The total energy of the system balances Potential Energy (`PE`), Linear Kinetic Energy
(`KE_lin`), Rotational Kinetic Energy (`KE_rot`), and Losses due to Friction (`W_fric`) and Drag
(`W_drag`):

```
PE_initial = KE_linear + KE_rotational + W_friction + W_drag
```

### 2.1 Total Kinetic Energy (`KE_total`)

Because the wheels spin while the chassis translates, the energy split is:

```
KE_total = ½·M·v²  +  Σ_{i=1..N} ½·I_i·ω_i²
```

Where:

- `M` = total mass of the car (chassis + wheels)
- `v` = linear velocity of the car (m/s)
- `N` = number of wheels in contact with the track (3 or 4)
- `I_i` = moment of inertia of a single wheel (kg·m²)
- `ω_i` = angular velocity of the wheel (`ω = v / R_wheel`)

### 2.2 Wheel Moment of Inertia (`I`)

A standard wheel is modeled as a thick-walled hollow cylinder:

```
I = ½·m_w·(R_outer² + R_inner²)
```

**Optimization logic:** if a user chooses "Lightweight Wheels," reduce `m_w` by up to 60%. This
reduces `I`, shifting energy from `KE_rotational` directly into `KE_linear`, drastically
increasing top speed.

---

## 3. Friction & Drag Loss Logic Modules

These modules must run at every physics time-step (`dt`) to calculate the net deceleration force:

```
F_net = F_gravity − F_friction − F_drag
```

### 3.1 Aerodynamic Drag (`F_drag`)

Standard drag equation:

```
F_drag = ½·ρ·v²·C_d·A
```

- **Frontal area (`A`):** height × width of the front profile.
- **Drag coefficient (`C_d`):**
  - Wedge / low-profile body: `C_d ≈ 0.20`
  - Standard wood block: `C_d ≈ 0.85`

### 3.2 Axle Bore Friction (`F_axle`)

Friction between the plastic wheel bore and the steel nail axle:

```
F_axle = N_wheel · μ_axle · (r_axle / R_outer)
```

- **Normal force (`N_wheel`):** derived from weight distribution (see Section 4).
- **Friction coefficient (`μ_axle`):**
  - Unpolished axle + no lube: `μ ≈ 0.35`
  - Polished axle + graphite lube: `μ ≈ 0.10`

### 3.3 Rail Friction & Guide Ping-Ponging (`F_rail`)

When a car is poorly aligned, it bounces off the center guide rail.

- **Straight alignment:** generates random, high-amplitude friction spikes
  (`F_rail = Random(1.5, 3.0) N`) as it "ping-pongs."
- **Rail Rider alignment:** generates a constant, minimal friction value (`F_rail = 0.05 N`)
  because one wheel rides smoothly along the rail.

#### 3.3a Continuous steer angle (graded model)

Real alignment is a **tunable steer angle**, not an on/off — racers cant the front a few degrees
so the car pins against **one** rail. The two modes above are the endpoints of a smooth *valley*
in steer angle `θ` (degrees), and the engine drives `F_rail` off `θ` (`CarDesign.effective_steer_deg`):

- **`θ = 0°` (no steer):** the car wanders and ping-pongs — the Straight case above (seeded
  spike × contact duty). Most rail loss.
- **`θ ≈ 3°` (the rail-rider *sweet spot*):** the car is pinned to one rail and rides it with a
  small, steady, **RNG-free** force — the Rail Rider constant. Least rail loss. As `θ` rises from
  0° to the sweet spot, the ping-pong contact duty fades **linearly to zero** (the car stops
  bouncing) while a steady single-rail force ramps in.
- **`θ` well past the sweet spot:** the steered wheel **scrubs** the rail; loss grows
  quadratically (`F_rail = base + k·(θ − θ_sweet)²`), so the car slows again but still finishes —
  a graded slowdown, not a DNF.

The endpoints reproduce the legacy enum **exactly** (`θ = 0°` ≡ Straight; `θ = θ_sweet` ≡ Rail
Rider, bit-for-bit), so this is a faithful *extension*, not a re-definition. The scrub gain and
sweet-spot angle are tuned calibration parameters (not spec-fixed formulas). Educationally it
teaches the real lesson: **a little steer is fastest; none and too much are both slower.**

> **Determinism note (engine convention):** any randomness (e.g. ping-ponging) must be **seeded**
> so a given input always produces an identical result. See `profile.md` conventions. An
> under-steered car (`θ` below the sweet spot) consumes the seeded RNG; a pinned car
> (`θ ≥ θ_sweet`) is RNG-free and seed-independent.

---

## 4. Center of Mass (COM) & Weight Distribution Matrix

The position of the center of mass relative to the rear axle (`d_COM`) changes how the normal
forces (`N_f`, `N_r`) are distributed across the wheels.

```
       |<------ d_COM ------>|
[Front Wheel] ------------ (COM) ------------ [Rear Wheel]

       |<----------------- Wheelbase (L) ------------->|
```

### 4.1 Normal Force Distribution (on the flat)

```
Rear  axle normal force:  N_r = M·g·(1 − d_COM / L)
Front axle normal force:  N_f = M·g·(d_COM / L)
```

### 4.2 Code Constraints for `d_COM` Optimization

- **`d_COM > 1.25 in`:** stable, but low potential energy. The car has a slow exit velocity from
  the ramp.
- **`0.75 in ≤ d_COM ≤ 1.0 in`:** **optimal zone.** Maximizes the height of the mass on the ramp
  while maintaining front-wheel tracking stability.
- **`d_COM < 0.625 in` (graded model):** the front goes **light** and the car becomes **tippy**.
  Because the front normal force `N_f = M·g·(d_COM/L)` falls *smoothly* toward zero as the COM
  nears the rear axle, instability is **gradual, not a cliff**: a "wander" penalty raises `F_rail`
  steeply as `d_COM` drops below this onset, so the car still **FINISHES but progressively slower**
  (it rubs the rails fighting for a straight line). Only when the front load has **essentially
  collapsed** — `d_COM/L ≲ 0.06` (≈ `0.625/4.375` is the onset; the collapse is much deeper, ≈
  `0.26 in` at the standard wheelbase) — can the car not run at all: a **DNF**. This replaces the
  earlier sharp 0.625 in "legible cliff" with the more physically faithful smooth front-load
  decline (the threshold is a front-load *fraction*, so it never inverts on non-standard
  wheelbases). Note: rear weight is still a *speed benefit* (more PE retained) — the penalty for
  going too far is the wander/instability, not an inherent slowdown.

---

## 5. Simulation Variables for UI Implementation

To make this an engaging teaching tool for 12–17 year-olds, map the physics to these UI toggles:

| UI Slider / Toggle | Physics Parameter | Best-Choice Value | Educational Takeaway |
| --- | --- | --- | --- |
| Total Car Weight | Mass (`M`) | 5.0 ounces | More mass = more starting potential energy. |
| Weight Location | Center of Mass (`d_COM`) | 0.85 in from rear | Keeps weight higher on the ramp for a longer push. |
| Body Shape Profile | Frontal Area (`A`) / Drag (`C_d`) | Aero Wedge (`C_d = 0.2`) | Air resistance actively steals speed on the flat. |
| Axle Preparation | Friction Coefficient (`μ_axle`) | Polished + Graphite | Eliminates microscopic surface imperfections. |
| Wheel Count Option | Number of Wheels (`N`) | 3 Wheels Touching | Reduces rotational inertia and wheel drag by 25%. |
| Steering Alignment | Rail Friction Logic (`F_rail`) | Rail Rider (slight drift) | Prevents energy loss from bouncing off the walls. |

---

## 6. Pseudocode Execution Loop

This logic should run inside the simulation's update ticker to calculate the live leaderboard or
visual playback:

```python
# Initialize Car Properties
mass = 0.14175           # 5 ounces in kg
velocity = 0.0
position = 0.0
time = 0.0
dt = 0.01                # Time step in seconds

while position < track_length:
    # 1. Determine Track Inclination Angle based on Position
    theta = get_track_angle(position)

    # 2. Calculate Forces
    f_gravity = mass * 9.81 * math.sin(theta)
    f_normal  = mass * 9.81 * math.cos(theta)

    f_drag = 0.5 * air_density * (velocity ** 2) * cd * frontal_area
    f_axle = wheels_touching * mu * (f_normal * (r_axle / R_wheel))
    f_rail = calculate_rail_friction(alignment_type, velocity)

    # 3. Net Acceleration
    f_net = f_gravity - (f_drag + f_axle + f_rail)
    acceleration = f_net / (mass + rotational_inertia_modifier)

    # 4. Euler Integration for Movement
    velocity += acceleration * dt
    position += velocity * dt
    time += dt
```

---

## Appendix — Planner notes on mapping to the feature roadmap

These are the Planner's annotations, not part of the original spec — flagged so QA/dev know what
this slice owns vs. defers.

> **Scope update (2026-06-02).** This appendix originally scoped `0001` to mass + d_COM only. Per
> the PO's decision that day the slice was **broadened to the full six-lever engine** and the
> feature renamed `0001-weight-placement-engine` → `0001-physics-engine`. The current ownership is
> below.

- **Feature `0001-physics-engine` (this slice) owns:** the complete single-car force/energy model —
  **mass `M`** and **center of mass `d_COM`** (§4, normal-force distribution §4.1, stability
  constraints §4.2), **wheels / rotational inertia** (§2), **aerodynamic drag** (§3.1), **axle bore
  friction** (§3.2), and **alignment / rail ping-ponging** (§3.3, seeded RNG) — integrated over the
  track geometry (ramp + transition arc + flat), returning a `RaceResult` with a closing energy
  ledger. All six levers are real, tunable inputs, not fixed baselines.
- **Deferred to later features:** the full UI toggle surface (§5) — sliders, animation, the visual
  "why it performed this way" explanation — and any multi-car / head-to-head heat orchestration.
- **Reconciliations resolved in the feature's TRD:** integration method (Euler time-step per §6),
  `dt = 1e-3` with linear finish-line interpolation for sub-`dt` timing precision, and the
  BSA-typical geometry constants (PRD A4/A5) the spec left unspecified.
