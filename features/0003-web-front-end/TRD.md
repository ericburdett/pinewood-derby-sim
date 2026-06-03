# TRD — Web Front-End (Interactive Car Builder & Race UI)

- **App:** pinewood-derby-sim · **Feature:** `0003-web-front-end`
- **Status:** approved — 2026-06-02
- **Companion:** [`PRD.md`](./PRD.md) · **Engine contract:** [`0001-physics-engine/TRD.md`](../0001-physics-engine/TRD.md) ·
  **Domain truth:** [`docs/physics-spec.md`](../../docs/physics-spec.md) · **Profile:** [`profile.md`](../../profile.md)
- **Last updated:** 2026-06-02

This TRD describes *how* to build the front-end specified in the PRD. It honors the profile's hard
constraints (no network at runtime, no PII, safe for children, engine stays pure & dependency-free)
and the platform decision (static web + Pyodide on GitHub Pages). It also flags where this feature
**expands the app's stack** beyond pure Python.

---

## 1. Architecture overview

A **static single-page app** with the **pure Python engine running in the browser** via Pyodide.
Two clean layers, one boundary:

```
┌──────────────────────────────────────────────────────────────────┐
│ Browser (static site, same-origin assets, no network at runtime)  │
│                                                                    │
│  ┌── UI (TypeScript) ─────────────┐   ┌── Pyodide (WASM) ───────┐  │
│  │ Builder controls               │   │ pinewood_derby (0001)   │  │
│  │ Track <canvas> animation       │   │   simulate(car) → Result│  │
│  │ Result / "why" panel           │◄─►│ pinewood_derby.present  │  │
│  │ Garage (localStorage)          │   │   (NEW pure translation)│  │
│  └────────────────────────────────┘   └─────────────────────────┘  │
│            ▲ JS ↔ Python bridge (Pyodide proxies, JSON-able DTOs)   │
└──────────────────────────────────────────────────────────────────┘
        hosted on GitHub Pages (static files only)
```

- **Engine stays pure & untouched** (`0001`). The front-end imports it; it adds **no physics**
  (PRD AC-G1).
- **Translation layer = the folded `0002`**, implemented as a **new pure Python module**
  `pinewood_derby/present.py` (DOM-free, unit-tested with `pytest`). It maps `RaceResult` +
  `CarDesign` → a **JSON-serializable view-model** the JS UI renders. Keeping it in Python (a) reuses
  the profile's `uv run pytest` bar, (b) keeps all "what does this number mean" logic on one side of
  the bridge, and (c) ports for free if the app is ever re-hosted.
- **UI is thin TypeScript:** read controls → build a `CarDesign` (in Python, over the bridge) →
  `simulate` → `present` → render the returned view-model + animate the trajectory. No physics, no
  domain rules duplicated in JS.

## 2. Platform & hosting

- **Pyodide, vendored same-origin.** The Pyodide runtime (`.js` + `.wasm` + stdlib) and the
  `pinewood_derby` package (shipped as a **pure-Python wheel** built from `0001`, or loaded as source
  via `loadPackage`/`pyodide.FS`) are committed/copied into the published site. **No CDN** — required
  by PRD AC-P1 (no third-party calls) and to work offline (AC-P3).
- **GitHub Pages.** Static hosting; a CI workflow builds the site (Vite) + the engine wheel and
  publishes to Pages. Pages cannot run server code — fine, there is none. *(Single-threaded Pyodide
  only; we do **not** use `SharedArrayBuffer`/threads, so the COOP/COEP headers Pages can't set are
  not needed.)*
- **Offline (AC-P3).** A **service worker** precaches all static assets (HTML/JS/CSS/Pyodide/wheel)
  so the app loads offline after the first visit. The SW makes no network fetches of its own.

## 3. Component / module layout

```
web/                              # NEW front-end workspace (TypeScript + Vite)
  index.html
  src/
    main.ts                       # bootstrap: load Pyodide, wire UI
    pyodide-bridge.ts             # load runtime + engine wheel; typed call wrappers
    controls/                     # builder inputs → control-state
      controls.ts                 # six levers + weight; constrained to valid domains (AC-C1)
      presets.ts                  # default car (AC-C2) + named "good/bad build" demo presets
    race/
      animator.ts                 # <canvas> 2-D side-view; plays RaceResult.trajectory (AC-R1/R2)
    result/
      result-view.ts              # renders the view-model: time, "where did your speed go", "why"
    garage/
      garage.ts                   # save/list/load/delete via localStorage (AC-S1/2/3)
    a11y/, styles/                # focus management, WCAG-AA theme (AC-A1/A2/A3)
  sw.ts                           # service worker: precache static assets (AC-P3)
  public/pyodide/                 # vendored Pyodide runtime (same-origin, no CDN)
  tests-e2e/                      # Playwright headless-browser specs (UI ACs)

src/pinewood_derby/
  present.py                      # NEW pure translation layer (the folded 0002)
tests/
  test_present.py                # NEW pytest unit tests for present.py
```

The Python side adds exactly **one** new module (`present.py`) to the existing pure package; all UI
lives under the new `web/` workspace.

## 4. Translation layer — `pinewood_derby/present.py` (pure, the folded 0002)

A pure function from engine output to a kid-facing, JSON-serializable view-model. **No DOM, no I/O,
no physics, no technical units** (PRD AC-X3).

```python
@dataclass(frozen=True)
class LossBar:
    key: str            # "air" | "axle" | "rails" | "wheels" | "kept"
    label: str          # plain language, e.g. "Axle friction"
    proportion: float   # 0..1 share of the energy story (for bar length); NOT joules
    is_kept: bool       # the "speed you kept" bar vs a loss

Outcome = Literal["finished", "tipped", "stalled"]   # AC-R4: two distinct non-finish stories

@dataclass(frozen=True)
class RaceView:
    finished: bool
    outcome: Outcome                  # "finished" | "tipped" (wobble/crash) | "stalled" (ran out of speed) — AC-R4
    time_seconds: float | None        # None for any non-finish (PRD AC-R2); seconds is allowed (A7)
    stopped_distance_frac: float | None  # for "stalled": how far it got (0..1), to say "stopped just short"
    legal_weight: bool
    headline: str                     # "Nice! 2.91 seconds." / "Your car wobbled and tipped." / "Ran out of speed, just short."
    breakdown: tuple[LossBar, ...]    # ranked largest-first (AC-X1)
    why: str                          # dominant-factor coaching tied to a real principle (AC-X2); outcome-specific for non-finishes
    tips: tuple[str, ...]             # 1–3 next-step suggestions, priority-ordered (AC-X4)
    trajectory: tuple[FramePoint, ...]# down-sampled points the animator replays

def present(result: RaceResult, car: CarDesign) -> RaceView: ...
def to_json(view: RaceView) -> dict: ...   # plain dict for the JS bridge
```

- **"Where did your speed go?" (AC-X1, A8):** map ledger fields → bars —
  `w_drag`→`air`, `w_axle`→`axle`, `w_rail`→`rails`, `ke_rotational_final`→`wheels`,
  final linear KE→`kept`. Normalize to proportions of the **energy actually delivered on this run** —
  i.e. the **integrated gravity work `w_gravity`** (which the per-force ledger closes against:
  `w_gravity − w_drag − w_axle − w_rail = ke_linear + ke_rotational`), **not `pe_initial`** — so the
  bars sum to ~1 for *both* a finisher and a stalled car (a stalled car descends only part of the
  ramp, so `w_gravity < pe_initial`). **Guard the all-zero ledger** (a `tipped` DNF has
  `w_gravity == 0`): emit **no breakdown bars** for a tip — its story is the wobble headline, not a
  loss chart. **Rank largest-first.**
- **"Why" (AC-X2, AC-X4):** pick the **largest *loss*** bar and emit the matching plain-language
  principle from a small, reviewed lookup table (axle→polish & graphite; rails→fix alignment /
  rail-ride; air→smoother/lower body; wheels→lighter, truer wheels; plus weight/placement coaching
  driven by `legal_weight` and `car.com_ahead_of_rear_axle`). The table encodes the **real priority
  order**, so tips never invert it (aero is never advised over weight/friction). A **banned-terms
  guard** (shared with the test) keeps jargon out.
- **Non-finish disambiguation (AC-R2 / AC-R4):** `finished=False`, `time_seconds=None`, then classify
  the single engine `outcome=DNF` into **two** view outcomes **from the trajectory + ledger** (verified
  against `engine.py`/`result.py` 2026-06-02):
  - **`tipped`** — the engine short-circuits an unstable car (front-load fraction `d_COM/L` below the
    cliff) **before the run starts**: the result has a **single `trajectory` point at `position == 0`**
    and an **all-zero work ledger** (`w_gravity == w_drag == w_axle == w_rail == 0`,
    `ke_*_final == 0`). Detect via `len(trajectory) == 1 and trajectory[0].position == 0.0`. Headline +
    "why" speak to **wobble/tip**: weight too far back / past the stability cliff. `stopped_distance_frac
    = 0.0`.
  - **`stalled`** — the car ran but its velocity hit zero **before** the finish: a **multi-point
    trajectory** whose **last `position` satisfies `0 < position < track_length`**, with
    `finish_velocity ≈ 0` and a non-trivial ledger. Record `stopped_distance_frac = last_position /
    track_length` and speak to **"ran out of speed and stopped just short"**: too much friction / not
    enough starting energy — *not* a crash. *(The rare 60 s wall-clock guard — a near-stationary crawl —
    also lands here and is messaged as a stall.)*
  - **Discriminator note:** `normal_forces` is a **single static `(front, rear)` pair** computed once on
    the flat (`result.py`), **not** a per-frame series, and `front = M·g·(d_COM/L) ≥ 0` always — so it
    is **not** usable to detect a tip. The trajectory/ledger signals above are the real evidence.
  The classifier reads only `outcome`, `trajectory`, and the ledger — no new physics (AC-G1).
- **Purity:** frozen dataclasses, deterministic, ≥ 90% unit coverage (PRD NFR). Tested entirely
  without a browser.

## 5. UI ↔ Python bridge

- **Import paths (verified 2026-06-02):** `pinewood_derby/__init__.py` does **not** re-export the
  public API (it sets `__version__` only), so the Python side imports from the **submodules** —
  `from pinewood_derby.engine import simulate`, `from pinewood_derby.car import CarDesign`,
  `from pinewood_derby.result import RaceResult`, `from pinewood_derby.track import STANDARD_TRACK`.
  Alternatively `0001` adds a one-line re-export to `__init__.py` (tracked as a tiny follow-up, PRD A4a).
- On boot, `pyodide-bridge.ts` loads the vendored runtime, then the `pinewood_derby` wheel, and
  exposes typed wrappers:
  - `buildCar(controlState) → PyProxy(CarDesign)` — constructs the design **in Python** so the
    engine's own validation is the single source of truth (PRD AC-C1); a `ValueError` is caught and
    surfaced as an inline control message, never a stack trace.
  - `race(car) → RaceView(JSON)` — calls `simulate(car, seed=FIXED_SEED)` then `present(...)`,
    returning a plain JSON object (no lingering proxies) for the renderer (AC-R3 determinism via the
    fixed seed, A6).
- Control domains in `controls.ts` mirror the engine's validation bounds so the UI **pre-constrains**
  inputs; the Python validation remains the backstop. (Two-layer guard for AC-C1.)
- `CarDesign` (de)serialization for the garage goes through a small Python `to_dict`/`from_dict`
  (or a `present.py` helper), so localStorage holds a **plain, versioned JSON** snapshot — not a
  proxy — and load reconstructs + re-validates it (AC-S2).

## 6. Animation (`race/animator.ts`)

- A 2-D side view of `STANDARD_TRACK` (ramp → transition arc → flat) drawn on `<canvas>`; the car
  sprite is placed each frame from `RaceResult.trajectory` (position along the arc → screen x/y, plus
  the track angle for rotation). A running clock counts up to `race_time_s`.
- **Non-finish (AC-R2/AC-R4):** a **`stalled`** car has a real multi-point trajectory, so it animates
  its run and **coasts to a visible halt short of the line** (no crash visuals). A **`tipped`** car has
  only the single at-rest start point (the engine rules it unstable before the run), so there is **no
  run to animate** — it shows a **wobble-at-the-start-line** state instead. The two are rendered
  distinctly to match their headlines.
- **Determinism:** same trajectory in ⇒ same animation out (AC-R3).
- **Perf:** `requestAnimationFrame`, target **≥ 30 fps**; the trajectory is already down-sampled
  (≤ ~500 pts by the engine), so per-frame work is trivial.
- **Duration basis:** scale playback off the **trajectory's own last `t`**, *not* `race_time_s`
  (which is `None` for a non-finisher). A finisher plays near real-time (~3–4 s). A **`stalled`** run
  can carry a much longer trajectory `t` (the engine's stall path runs up to a 60 s wall-clock guard),
  so **cap/compress** the non-finisher playback to a few legible seconds rather than replaying a
  60 s crawl. A **`tipped`** run has a single `t=0` frame, so there is no timeline to scale.

## 7. Garage / persistence (`garage/garage.ts`)

- `localStorage` keyed under a single namespace (e.g. `pds.garage.v1`), holding a JSON map of
  `name → { schemaVersion, design }`.
- Operations: **save** (name + current design), **list**, **load** (restore controls + re-validate),
  **delete**, **clear**. All synchronous, on-device (AC-S1/S2/S3).
- **No PII, no network** (AC-P2): the only stored data is car designs the user explicitly saves; a
  visible "clear my garage" control exists.
- A `schemaVersion` on each entry allows safe migration if `CarDesign` changes (relevant given the
  build is deferred until the engine contract settles — A4).

## 8. Privacy, offline & safety (PRD AC-P1/P2/P3)

| Requirement | Implementation |
| --- | --- |
| No network at runtime | All assets same-origin & vendored; **no CDN, no fonts/analytics/embeds**; no `fetch`/`XHR`/`WebSocket` to any origin |
| No PII / data collection | Only `localStorage` car designs; no accounts, no input fields for personal data, no telemetry |
| Works offline | Service worker precaches the full static bundle; subsequent loads need no network |
| Safe for children | Encouraging copy, no external links opened without intent; the `0004` leaderboard (the only network feature) is explicitly **not** here |

CI/lint check: a test asserts the built bundle references **no off-origin URLs** (guards AC-P1
against regressions).

## 9. Accessibility (PRD AC-A1/A2/A3)

- Native, labeled form controls (`<input type=range>`, toggles, buttons) with `<label>`/`aria-*`;
  logical tab order; visible focus rings; **Race** reachable and operable by keyboard.
- Results announced via an `aria-live` region so a screen reader reads the time + "why" after a race.
- **WCAG-AA** contrast theme; **never color-only** — legal/over-limit, finish/DNF, and each loss bar
  carry text + icon. Animation respects `prefers-reduced-motion` (offer a static end-state).
- Responsive down to ~1024px; large targets for projector/Chromebook use.

## 10. Dependencies & stack changes

- **Python (runtime):** unchanged — `pinewood_derby` stays **stdlib-only**; `present.py` adds no
  dependency. `pyproject` `dependencies = []` holds.
- **New front-end toolchain (the stack expansion this feature introduces):**
  - **TypeScript + Vite** build; **Pyodide** vendored as a static asset.
  - **Playwright** (dev) for headless-browser UI tests; **Vitest** (or equivalent) for any pure TS
    units.
  - A **CI workflow** to build the engine wheel + the Vite bundle and deploy to GitHub Pages.
- **Profile impact (flagged, not done here):** the profile's `framework`, `commands`
  (build/test/run for the web app), `archetype` (desktop-app → web-app), deployment target, and
  audience age (→ 12–17) all need a follow-up update for consistency. Tracked as a flag for the
  synthesizer / a profile-update task (PRD §8).

## 11. Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| **Engine contract still in flux** (`0001` building) — UI built against a moving target | **Defer build** until the contract stabilizes (A4); isolate all engine touchpoints behind `pyodide-bridge.ts` + the Python `present.py`/`to_dict`; version the garage JSON for migration |
| **Pyodide first-load weight** (several MB) hurts the Chromebook/demo experience | Show a loading state (NFR); precache via service worker so it's a one-time cost; vendor + compress assets; lazy-load nothing the first race needs |
| **Physics/units leaking to the kid** (jargon, Joules) | All translation in one pure module with a **banned-terms guard** shared by `test_present.py` and a UI text scan (AC-X3) |
| **Priority order inverted in tips** (teaching wrong order) | The "why"/tips lookup is **reviewed, table-driven, priority-ordered**; a domain test asserts weight/placement & friction outrank aero across sample designs (AC-X4, rides engine AC-ED1) |
| **Determinism breaks** (random seed, animation jitter) | UI pins `seed=FIXED_SEED` (A6); animation is a pure function of the returned trajectory; AC-R3 test races twice and asserts identical time/frames |
| **Accidental third-party call** (font, CDN, analytics) creeps in | Same-origin-only policy + a build test asserting **no off-origin URLs** in the bundle (AC-P1) |
| **Test stack expansion** beyond the profile's Python-only toolchain | Keep the **richest logic in pure Python** (`present.py`, `pytest`); limit browser tests to genuinely UI behavior; document the new commands for the profile update |
| **Bigger UI surface than a TDD-friendly unit** | Push testable logic into `present.py` + control-domain mapping (unit-testable); reserve Playwright for a small set of end-to-end ACs (race, DNF, save/load, no-network, keyboard) |

## 12. Test strategy

- **Pure translation layer (`present.py`) — `uv run pytest`, the primary bar:**
  - View-model mapping: ledger → ranked `LossBar`s largest-first (AC-X1); dominant-factor "why"
    selection (AC-X2); legal/over-limit headline (AC-C3).
  - **Non-finish classifier (AC-R4):** drive `present()` with **real `simulate()` output** (not
    hand-built fixtures): an unstable design (`d_COM/L` below the cliff) → `outcome="tipped"`,
    `stopped_distance_frac == 0`, single-point trajectory, all-zero ledger; a stable-but-underpowered
    design (e.g. a light ~1–2 oz car that stalls short) → `outcome="stalled"`,
    `0 < stopped_distance_frac < 1`, *non-crash* message. Assert the two never collapse into one and a
    slow finisher (`outcome="finished"`) is neither.
  - **Banned-terms guard:** assert no jargon in any emitted string across a matrix of designs
    (AC-X3).
  - **Priority-order domain test:** across sample designs, weight/placement & friction produce the
    largest surfaced losses/tips, aero the smallest (AC-X4).
  - Determinism: `present(simulate(car, seed=S), car)` is stable (AC-R3, data side).
  - **≥ 90% coverage** on `present.py` (PRD NFR).
- **UI — Playwright (headless), one spec per UI AC:** default car loads & races (AC-C2/R1);
  out-of-range/invalid input never throws (AC-C1); over-limit raceable + flagged (AC-C3); both
  non-finish states render distinctly — `tipped` vs `stalled` (AC-R2/AC-R4); race-twice determinism
  (AC-R3); save→reload→load→race (AC-S1/S2/S3); **no off-origin
  network requests** via request interception (AC-P1); offline load after first visit (AC-P3);
  keyboard-only loop + `aria-live` result (AC-A1); not-color-only / contrast (AC-A2).
- **Engine untouched:** the `0001` suite continues to pass; a guard asserts no physics math lives
  outside `pinewood_derby` (AC-G1).

## 13. Traceability (AC → component)

| Area | ACs | Primary component(s) |
| --- | --- | --- |
| Controls → CarDesign | AC-C1, AC-C2, AC-C3 | `controls.ts`, `presets.ts`, `pyodide-bridge.ts` |
| Race & animation | AC-R1, AC-R2, AC-R3, AC-R4 | `animator.ts`, `pyodide-bridge.ts`, `present.py` (non-finish classifier) |
| Explanation / "why" | AC-X1, AC-X2, AC-X3, AC-X4 | `present.py`, `result-view.ts` |
| Garage | AC-S1, AC-S2, AC-S3 | `garage.ts`, `present.py` (to_dict/from_dict) |
| Privacy / offline / safety | AC-P1, AC-P2, AC-P3 | bundle policy, `sw.ts`, `garage.ts` |
| Accessibility | AC-A1, AC-A2, AC-A3 | `a11y/`, `styles/`, `result-view.ts` |
| Engine purity | AC-G1 | `present.py`, `pyodide-bridge.ts` |
