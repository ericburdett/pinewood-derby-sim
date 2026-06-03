# 0003-web-front-end — BUILD SUMMARY (escalated → resolved → DONE)

**Status:** done · **Run:** `wf_192cd4bd-629` (build-loop) + direct resume · **Date:** 2026-06-03
**Run-records:** `evals/run-records/pinewood-derby-sim/0003-web-front-end.json` (completed)
· `…-run1-escalated.json` (the original escalated loop run, preserved for the eval-loop)

The feature is **complete and verified end-to-end**. It got there in three phases — the
build-loop run (escalated), a resume that resolved a real defect and finished the buildable
Python layer, and a human-directed phase that installed the web toolchain and built the UI.

## Final verified state (profile gate commands)

- **Python:** `uv run pytest` → **500 passed, 1 skipped**; `ruff` clean; `mypy --strict` clean
  (53 files); `present.py` coverage 96%.
- **Web:** `npm --prefix web test` (Playwright headless Chromium) → **18 passed**;
  `tsc --noEmit` clean; `eslint` clean; `vite build` produces a 13.9 kB app bundle + the
  vendored same-origin Pyodide runtime + engine zip + service worker in `dist/`.
- Every PRD acceptance criterion now has a covering test (see traceability below).

## How it was built (honest methodology note)

The build-loop **run escalated** (preserved in `-run1-escalated.json`): it crashed mid-run on
the recurring `subagent completed without calling StructuredOutput` error and surfaced two
blockers. Completion then happened **outside the QA→dev→adversarial→PO loop**, at the user's
explicit direction:

1. **Blocker 1 (cross-WI test contradiction) — adjudicated & fixed.** WI01's AC-R1 test
   required a `"trajectory"` key in the `to_json` payload while WI04's no-jargon scan banned
   it (it scanned dict *keys*). Ruling: AC-X3 governs kid-facing *rendered strings*, not
   internal data keys — so the no-jargon scan was re-scoped to values and the `"trajectory"`
   key kept for the animator. `BANNED_TERMS` is unchanged; jargon is still rejected in all
   rendered copy.
2. **WI05 (tipped-vs-stalled classifier) — completed.** It had been a stub (`present()`
   hard-coded every DNF to `"stalled"`, `stopped_distance_frac=None`). Now wired: `"tipped"`
   (unstable, single at-rest point) vs `"stalled"` (ran but lost speed, with
   `stopped_distance_frac`), distinct encouraging headlines, 8 new pytest cases on real
   `simulate()` output.
3. **WI06 garage serde + WI15 engine-purity guard — completed** (pure Python, 37 + 4 tests).
4. **Blocker 2 (no web toolchain) — resolved.** Installed Node 26 + Playwright (Homebrew, no
   sudo); proved headless Chromium works in this environment; **landed 0006** (profile
   reconciled to a web app with a dual Python+Playwright test stack).
5. **WI07–WI14 — built directly** as a `web/` workspace (TypeScript + Vite + `<canvas>` +
   vendored Pyodide), each AC covered by a Playwright headless spec.

> **Caveat for the eval-loop:** WI05 and WI07–WI14 were completed via direct, test-verified
> build — **not** the factory's adversarial-review / PO-sign-off gates. They pass pytest /
> Playwright / ruff / mypy / tsc / eslint / production build, but a targeted **adversarial
> sweep + PO sign-off** on the UI and the WI05 classifier is still worth running if/when the
> loop is re-exercised.

## Work-item ledger (all 15 passed)

| WI | Scope | Verified by |
| --- | --- | --- |
| WI01 viewmodel | present()/to_json core | pytest (trajectory key fixed) |
| WI02 breakdown | "where did your speed go?" | pytest |
| WI03 why/priority | dominant-factor + tips | pytest (+3 adversarial) |
| WI04 no-jargon | banned-terms guard (re-scoped to values) | pytest |
| WI05 DNF classifier | tipped vs stalled + distance | pytest (8, real simulate) |
| WI06 garage serde | to_dict/from_dict + schemaVersion | pytest (37) |
| WI07 Pyodide bridge | engine in-browser, JSON boundary | Playwright (4) |
| WI08 controls | levers → CarDesign, live legal-weight | Playwright (3) |
| WI09 race + canvas animation | trajectory replay to finish | Playwright (2) |
| WI10 result & why panel | ranked breakdown, why, tips, no jargon | Playwright (2) |
| WI11 non-finish render | tipped wobble vs stalled coast | Playwright (1) |
| WI12 garage UI | save/list/load/delete/clear | Playwright (2) |
| WI13 offline | service-worker precache, works offline | Playwright (1) |
| WI14 accessibility | keyboard loop, aria-live, not color-only, 1024px | Playwright (3) |
| WI15 engine-purity guard | UI adds no physics; stdlib-only engine | pytest (4) |

## AC traceability (all met with evidence)

AC-C1/C2/C3 → `ui-builder.spec` · AC-R1/R3 → `ui-race.spec` · AC-R2/R4 → `ui-nonfinish.spec`
+ `test_present_dnf_classifier_wi05` · AC-X1/X2/X3 → `ui-result.spec` + `present` pytest ·
AC-X4 → priority-order pytest · AC-S1/S2/S3 → `ui-garage.spec` · AC-P1 → `bridge.spec`
(no off-origin) · AC-P2 → localStorage-only by design · AC-P3 → `ui-offline.spec` ·
AC-A1/A2/A3 → `ui-a11y.spec` · AC-G1 → `test_engine_purity_wi15` + `bridge.spec`.

## Signals for the eval-loop / synthesizer

1. **`StructuredOutput` crash** recurs on long sessions — 6× across 0001+0003.
2. **No cross-WI acceptance-test consistency check** — WI01 vs WI04 shipped contradictory
   tests that only collided at the whole-suite green gate.
3. **No profile/toolchain pre-flight gate** — the build-loop launched a web feature against a
   Python-only profile (0006 was the unmet prerequisite); ~2.15M tokens spent before the gap
   surfaced.
4. **A "completed" work item can still be a stub** — WI05 was marked done in the first resume
   based on a grep, but `present()` hadn't wired the classifier in. Final-state credit should
   require a covering test that asserts the behavior, not just the presence of a helper.
5. **No-jargon guard over-reached** (policed data keys + banned non-unit terms) — a
   protective-guard scope signal.
