# PRD — Web Front-End (Interactive Car Builder & Race UI)

- **App:** pinewood-derby-sim
- **Feature:** `0003-web-front-end`
- **Status:** approved — 2026-06-02 (open questions in §9 resolved)
- **Author:** Planner
- **Last updated:** 2026-06-02
- **Planning session:** `3fb6a1ed-cfb8-40c7-ab67-33ea52bb80b9`
- **Grounding docs:** [`profile.md`](../../profile.md) · [`docs/physics-spec.md`](../../docs/physics-spec.md) ·
  engine contract [`0001-physics-engine/PRD.md`](../0001-physics-engine/PRD.md) ·
  [`0001-physics-engine/TRD.md`](../0001-physics-engine/TRD.md)

> **Scope note.** This feature is the **interactive front-end** that lets a kid actually *drive* the
> simulator. Per user decisions on 2026-06-02 it **folds in the former `0002-kid-friendly
> explanation & presentation layer`** (now superseded): 0003 owns both the **plain-language
> translation** of the engine's raw `RaceResult` *and* the **UI** that renders it. Platform:
> a **static web app** that runs the pure Python engine **in-browser via Pyodide (WASM)**, hosted
> free on **GitHub Pages**. The simulator makes **no network calls at runtime**; the future
> `0004` leaderboard is the only networked feature and is out of scope here.
>
> **Build is deferred** until the `0001` engine's public contract (`CarDesign` / `RaceResult`)
> stabilizes. This document captures the front-end requirements now so the design intent is locked;
> the build loop runs once the backend settles.

---

## 1. Problem statement

The physics engine (`0001`) speaks in Joules, Newtons, normal forces, and a down-sampled
trajectory — correct, but unreadable to a kid. Nothing yet lets a child **configure a car, race it,
watch what happens, and understand *why*.** Without a front-end the engine teaches no one.

The front-end's job is to turn the engine into a **learning toy**: a 12–17-year-old (and a leader
running a pack demo on a projector) adjusts a car's design, hits **Race**, watches the run animate
down the track, and gets a **plain-language explanation of where their speed went** that reinforces
a *real, correct* building principle. The profile's hard line holds: **rich physics behind the
boundary, simple presentation in front of it** — nothing technical (Joules, Newtons, coefficients,
integration) ever reaches the kid. **Reading level and tone are tuned to the younger end of the band
(~12)** so the youngest target users aren't left behind; this stays legible for 17-year-olds (A2).

It must run **anywhere a browser does** — a school Chromebook, a tablet, a leader's laptop on a
projector — with **zero install, no accounts, no data collection, and no network at runtime**.

## 2. Target users

- **Primary:** kids **12–17**, **designed to the younger end (~12)** — building a pinewood derby car,
  learning the design tradeoffs by experimenting. *(Audience reconciled to 12–17 per the `0001`
  PRD/spec on 2026-06-02, skewed toward 12 per the user; the profile's "~7–12" is superseded — see §8
  A2 and §9 OQ1.)*
- **Secondary:** den leaders / parents / teachers running a **group demo** on a projector or
  classroom screen — so the UI must read at a distance and be operable quickly.
- **Downstream:** the future `0004` leaderboard (consumes a finished race's time) and `0005`
  educational content (cross-links into the simulator). Both out of scope here.

## 3. Goals

- A **single-car interactive builder**: controls for all six engine levers + weight → **Race** →
  **animated run** on the track → **result + plain-language "why."** (Full-builder scope, confirmed
  2026-06-02.)
- A **"where did your speed go?"** breakdown that ranks the run's energy losses in kid-language and
  ties the dominant one to a **real building principle** — preserving the engine's **priority order**
  (weight & placement and friction dominate; aerodynamics is smallest).
- A **local "garage"**: name, save, reload, and delete car designs in the browser, **offline, no
  accounts** (confirmed 2026-06-02).
- **Install-free, server-free, offline-capable, privacy-safe:** static site, engine in-browser via
  Pyodide, **all assets same-origin (no third-party CDN), no analytics, no network at runtime, no
  PII** — safe for children.
- **Accessible & demo-ready:** keyboard-operable, WCAG-AA contrast, legible on a projector and a
  Chromebook.
- **Faithful & deterministic:** the UI adds **no physics**; it consumes the engine's public API
  unchanged, and a given design always produces the **same** time and animation (fixed seed) — which
  also keeps a future leaderboard fair.

## 4. Non-goals / out of scope

- **No new physics.** All simulation stays in the `0001` engine; 0003 only configures inputs,
  translates outputs, and renders. (AC-G1.)
- **No leaderboard / network / accounts / telemetry** — that is `0004` (opt-in, networked, with its
  own COPPA-safe design). 0003 is fully local.
- **No educational/reference content pages** — that is `0005`. 0003 may leave a hook to link out,
  but authors no lessons.
- **No head-to-head / multi-car race view** in one screen (single-car builder; comparison is a
  possible later feature).
- **No alternate tracks in v1** — every race runs on the engine's `STANDARD_TRACK`. The engine already
  accepts a `track` argument, so choosing/editing track geometry is a clean later feature, but v1 fixes
  one track so a saved time is comparable (and a future leaderboard is fair).
- **No cloud sync of the garage** — local browser storage only; no cross-device.
- **No CAD / cut-file / 3D model** — principles, not part design (profile constraint).
- **No native desktop / pygame build** — superseded by the web platform decision (2026-06-02).
- **No account-based personalization, no ads, no third-party embeds.**

## 5. Functional requirements

The app is a single page with four regions; all four are in v1.

| Region | What it does | Engine touchpoint |
| --- | --- | --- |
| **Builder controls** | Adjust **weight (M)**, **weight placement (d_COM)**, **wheels** (3/4 touching, light/standard), **axle prep** (polished+graphite ↔ unprepared), **body shape** (wedge ↔ block), **alignment** (rail-rider ↔ straight). Live legal-weight (≤ 5.0 oz) indicator. | Builds a validated `CarDesign` |
| **Track & animation** | A 2-D side view of the standard track (ramp → flat); **Race** animates the car along the returned trajectory; finish line, running clock. | `simulate(car)` → `RaceResult.trajectory` |
| **Result & "why"** | Race time (or an encouraging non-finish state that **tells a wobble/crash apart from a stable car that ran out of speed and stopped short**), a **"where did your speed go?"** ranked breakdown, and a one-line **"why"** tied to a real principle. | Translates `RaceResult.energy`, `outcome`, `trajectory` (final position), times |
| **Garage** | Name/save the current design, list saved designs, load (restores all controls), delete. | Serialize/deserialize `CarDesign` ↔ localStorage |

**Primary flow:** open (a sensible default car loads) → adjust controls → **Race** → watch the
animation → read the time + "where did your speed go?" + "why" → tweak and race again → optionally
**save** the design to the garage.

**Translation layer (folded 0002), internal but required:** a **pure** module maps a `RaceResult`
(+ the `CarDesign`) to a kid-facing **view-model**: ranked energy losses with plain labels, the
dominant-factor message, legal/DNF wording, and the trajectory for animation. It computes no physics
and emits **no technical units or jargon**. It is unit-tested independently of the DOM.

## 6. Acceptance criteria (testable)

Each criterion is behavioral and machine-checkable. The **translation layer** ACs are unit-testable
(pure Python, `uv run pytest`); the **UI** ACs are checkable via headless browser tests. "Kid-facing
text" = any string rendered to the user.

### Configuration (controls → CarDesign)
- **AC-C1** Every control maps to its `CarDesign` field within the engine's valid domain; the UI
  **cannot** submit a design the engine would reject — out-of-range or invalid combinations (e.g.
  wheels out-massing the car) are prevented or shown as an inline message, **never** an uncaught
  exception or a stack trace.
- **AC-C2** On first open, a **legal, finishing** default car is loaded and immediately raceable.
- **AC-C3** The displayed weight updates live and shows **legal (≤ 5.0 oz) vs over-limit** status;
  an over-limit car is still raceable (the rule is shown, not enforced by physics) — consistent with
  engine AC-W2.

### Race & animation
- **AC-R1** **Race** runs `simulate(...)` on the current design and **animates** the car along the
  returned trajectory from start to finish; a finishing car visibly reaches the finish line, and the
  displayed time equals the engine's `race_time_s` (to display precision).
- **AC-R2** A **non-finishing** design shows a clear, **encouraging** "here's what happened — here's
  why" state with **no numeric time** — never an error dialog. A **stalled** car animates its real run
  and **coasts to a visible halt short of the line**; a **tipped** car never leaves the start line
  (the engine determines instability before the run), so it shows a **wobble-at-the-line** state
  rather than a mid-track animation.
- **AC-R4** **Two non-finish stories are told apart.** The engine reports a single `outcome=DNF` for
  *both* (a) an **unstable** car that tipped/wobbled (front-load fraction below the stability cliff)
  and (b) a **stable but underpowered** car that **ran out of speed and stopped short** of the finish.
  The UI must distinguish them from the engine's own evidence: a **tipped** run has a **single at-rest
  `trajectory` point at position 0** and an **all-zero energy ledger** (the car never moved); a
  **stalled** run has a **real multi-point trajectory whose last point sits between the start and the
  finish line** (`0 < position < track_length`) with `finish_velocity ≈ 0`. *(Note: `normal_forces` is
  a single static front/rear pair, not a per-frame series, so it is **not** the discriminator.)* Each
  gets the matching kid-language message (e.g. *"Your car wobbled and tipped right off the line"* vs
  *"Your car ran out of speed and stopped just short"*) and a *different*, correct "why." A
  slow-but-stable car is **never** shown as a crash.
- **AC-R3** **Determinism:** racing the same design twice yields the **same time and the same
  animation** (the UI pins the engine seed); identical saved designs reproduce their time on reload.

### Explanation / "why" (folded 0002)
- **AC-X1** After a finished race, the result shows the **time** and a **"where did your speed go?"**
  breakdown that **ranks** the run's energy outcomes — air/drag, axle friction, rail bumping,
  energy spent spinning the wheels, and **speed kept** — **largest first**, derived from
  `RaceResult.energy`.
- **AC-X2** The **"why"** names the **dominant factor for this run** in plain language and ties it to
  a **real building principle** (e.g. "Your biggest slowdown was axle friction — polish your axles
  and add graphite").
- **AC-X3** **No jargon:** no technical unit or term (Joules, Newtons, coefficient, m/s², `C_d`, `μ`,
  "moment of inertia", "normal force") appears in any kid-facing text. *(Checkable: scan all rendered
  strings against a banned-term list.)*
- **AC-X4** **Priority order preserved:** across designs, the breakdown and "why" reflect the
  engine's real ordering — improving **weight/placement** and **friction** yields the **biggest**
  surfaced gains and **aerodynamics the smallest** (rides on engine AC-ED1; the UI surfaces it
  faithfully and never inverts it).

### Garage (local save / load)
- **AC-S1** The current design can be **named and saved** to local browser storage and **persists
  across a reload**.
- **AC-S2** Saved designs are **listed**; loading one **restores every control** to the saved values,
  and racing the loaded design **reproduces its time** (with AC-R3).
- **AC-S3** A saved design can be **deleted** and storage **cleared**; **nothing is sent off-device**.

### Privacy / offline / safety
- **AC-P1** After initial asset load, the app makes **no network requests** — no third-party CDNs, no
  analytics, no telemetry; **all assets (Pyodide runtime + engine) are same-origin.** *(Checkable via
  request interception in a headless browser.)*
- **AC-P2** **No personal data** is collected or transmitted; the **only** persisted data is local
  car designs in browser storage. No accounts, no PII fields.
- **AC-P3** The app **works offline after first load** (cached static assets / service worker).

### Accessibility & presentation
- **AC-A1** All controls and **Race** are **keyboard-operable and labeled**, with a logical focus
  order and visible focus; a full configure→race→read-result loop is possible without a mouse.
- **AC-A2** **Color is never the sole signal** — legal/over-limit, finish/DNF, and the loss bars each
  carry text/icon labels; kid-facing text and controls meet **WCAG-AA** contrast.
- **AC-A3** The layout is **legible on a projector and a Chromebook** — responsive to ~1024px wide,
  with large, distinct touch/click targets.

### Engine integration
- **AC-G1** The front-end consumes the engine's **public API** (`simulate`, `CarDesign`, `Track`,
  `RaceResult`) **unchanged** and adds **no physics**; the translation layer imports from
  `pinewood_derby` and computes only presentation. *(Checkable: no force/integration math outside the
  engine package.)*

## 7. Non-functional requirements

| NFR | Requirement | Evidence |
| --- | --- | --- |
| Privacy / safety | No PII, no accounts, no network at runtime, no third-party calls — safe for children | AC-P1/P2 |
| Offline | Usable offline after first load | AC-P3 |
| Performance — load | First load (incl. Pyodide warm-up) is usable within a few seconds on a typical Chromebook; a **loading state** is shown until ready | timed/manual check; loading indicator present |
| Performance — race | After warm-up, a race result renders within **~100 ms** of pressing Race (engine itself is < 5 ms per profile); animation runs at **≥ 30 fps** | timed test / frame check |
| Determinism | Same design ⇒ same time & animation (fixed seed) | AC-R3 |
| Accessibility | Keyboard-operable; WCAG-AA contrast; not color-only | AC-A1/A2 |
| Browser support | Current evergreen Chrome/Edge/Safari/Firefox; **Chromebook Chrome** is a first-class target | smoke matrix |
| Educational accuracy | The surfaced ranking & "why" never contradict the engine's physics or priority order | AC-X1/X2/X4 |
| Translation purity & coverage | Translation layer is pure, DOM-free, deterministic; **≥ 90%** unit coverage (mirrors the engine bar) | `pytest --cov` |
| Maintainability | Front-end adds no physics; engine stays pure & dependency-free | AC-G1 |

## 8. Assumptions & decisions

Defaults the Planner chose where the spec/profile were silent or in tension. Items marked
**[confirmed 2026-06-02]** were set by the user this session; the rest are documented defaults the
user may revise at the approval gate.

- **A1 — Platform [confirmed 2026-06-02]:** static web app, **engine in-browser via Pyodide (WASM)**,
  hosted on **GitHub Pages**, **all assets same-origin (no CDN)**, **no network at runtime**. The
  pure Python engine ports unchanged.
- **A2 — Audience 12–17, skewed young [confirmed 2026-06-02]:** reconciles the conflict between the
  profile (~7–12) and the `0001` PRD/spec (12–17) **in favor of 12–17**, with **reading level and tone
  tuned to the younger end (~12)** per the user. The **profile should be updated** to match (it also
  governs `0005`); see §9 OQ1.
- **A3 — Save/load in v1 [confirmed 2026-06-02]:** a single-device **garage** via browser
  `localStorage`; offline, no accounts.
- **A4 — Contract now frozen; build can begin [updated 2026-06-02]:** `0001-physics-engine` is
  **`done`** — its `simulate(...) -> RaceResult` / `CarDesign` contract is stable and was **verified
  against the source** this session. The original "defer until the engine settles" rationale is
  satisfied; 0003 may enter the build loop. (The garage JSON still carries a `schemaVersion` in case a
  later engine revision changes `CarDesign` — TRD §7.)
- **A4a — Package does not re-export its public API [flagged 2026-06-02]:** `pinewood_derby/__init__.py`
  currently exports nothing (`__version__` only); `simulate`, `CarDesign`, `Track`, `RaceResult` live
  in submodules (`.engine`, `.car`, `.track`, `.result`). The bridge/`present.py` will therefore import
  from the **submodules**, *or* `0001` adds a small re-export to `__init__.py`. Tracked as a tiny
  follow-up for `0001` (or an import-path decision at build) — not a blocker.
- **A5 — Front-end stack (default, revisable):** **vanilla TypeScript + Vite + an HTML `<canvas>`**
  for the 2-D track animation, with **Pyodide vendored** into the static bundle. Keeps the bundle
  lean and matches the app's minimalist, dependency-light ethos. (See §9 OQ2.)
- **A6 — Fixed seed in the UI:** the UI pins the engine `seed` so a design's time is reproducible
  (AC-R3) and a future leaderboard is fair. A design's time is a stable function of its design.
- **A7 — Kid-facing numbers:** the **race time in seconds** is allowed (legible, not jargon); raw
  speed is shown **visually/relatively**, never as `m/s`. The energy ledger is shown as **relative
  proportions / bars**, never Joules.
- **A8 — "Where did your speed go?" mapping:** derived from `RaceResult.energy` —
  `w_drag`→"pushing air", `w_axle`→"axle friction", `w_rail`→"bumping the rails",
  `ke_rotational_final`→"spinning the wheels", final linear KE→"speed you kept". Ranked largest-first.
- **A9 — Test tooling expansion:** the pure translation layer is tested with the profile's
  `uv run pytest`; the **DOM/UI** needs a **headless-browser** test runner (e.g. Playwright), which
  adds dev tooling beyond the current Python-only toolchain. The **profile's `commands`/stack will
  need a follow-up update** to cover the web build & UI tests.

> **Profile drift flagged (for the synthesizer / a profile update):** this feature moves the app from
> "pure-Python desktop (pygame)" toward "static web + Pyodide." The profile's `framework`,
> `commands` (build/test/run), `archetype`, deployment target, and audience age all need a refresh to
> stay consistent. That update is **out of scope for this PRD** but is called out so it isn't lost.

## 9. Open questions — resolved at approval (2026-06-02)

All three were resolved by the user at the approval gate; recorded here and in `feature.json`.

1. **OQ1 — Audience → 12–17, skewed young. [resolved]** Reconcile the profile's `~7–12` to **12–17**
   (matching the `0001` PRD/spec), with **reading level and tone tuned to the younger end (~12)**. A
   follow-up **profile update** (also governing `0005`) is required; flagged for the synthesizer.
2. **OQ2 — Stack: vanilla TypeScript + Vite + canvas, Pyodide vendored same-origin. [resolved]** User
   had no preference and asked for the simplest robust option; the Planner selected A5 — no framework
   runtime, smallest bundle, easiest to keep same-origin/offline, good UX. No effect on user-visible
   behavior.
3. **OQ3 — Distinguish the two non-finish modes. [resolved]** The engine's single `outcome=DNF` covers
   both an **unstable wobble/crash** and a **stable-but-underpowered car that stopped short**; the
   presentation layer must tell them apart from `trajectory` + `normal_forces` and never show a slow
   car as a crash. Folded in as **AC-R4** (carried over from `0001` WI12-ADV-006, adjudicated
   2026-06-03 as a presentation concern, not an engine defect).
