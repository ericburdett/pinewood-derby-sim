# Build-loop escalation — 0001-physics-engine

## ✅ CLOSED — feature marked DONE (2026-06-03, Eric)
The human accept-gate passed. Eric adjudicated WI-12's two open findings as **adversarial
over-reach beyond the AC scope** (WI12-ADV-005 tests the lever ordering outside AC-ED1/A6's
single-baseline promise; WI12-ADV-006's stable-car-DNF is consistent with the WI-5 stall=DNF
ruling and the worst-possible build legitimately falling short is acceptable). Feature
`status = done`; run-record top-line `status = completed` (WI-12's cap-hit is preserved at the
work-item level + in `metrics` as eval-loop signal). **Follow-up logged on feature
`0003-web-front-end`:** the presentation layer should distinguish "crashed (unstable)" from
"ran out of speed short of the line" so a kid doesn't read a slow car as a crash — a UI/wording
concern, not an engine defect (the engine already records *where* the car stopped).

---

## CURRENT STATUS (2026-06-03): feature-complete & PO-signed-off, but ESCALATED on WI-12

The feature is now **fully built across all 13 work items** and the **PO signed off every one
of the 30 acceptance criteria and all 8 NFRs with evidence**. The suite is **green: 316
passed, 0 failed**, `ruff` clean, `mypy --strict` clean, coverage 98%. Two run-records:
`…/0001-physics-engine.json` (consolidated final) and `…-run1-escalated.json` (first run).

It is recorded **`escalated`** (not `done`) for one reason, per the factory rule *"a loop cap
hit escalates to the user — never a silent pass; don't silence your critics"*: **WI-12 hit the
adversarial cap (3) with open HIGH findings the developer could not close within the cap.** A
human (the domain owner) should adjudicate them — my read is that both are likely **adversarial
over-reach beyond the agreed AC scope**, not defects:

- **WI12-ADV-005** — "aerodynamics isn't the smallest lever" *for a lighter-stock-wheel
  baseline* (4.0 oz, 0.04 oz wheels). But **AC-ED1 / assumption A6 deliberately pins only the
  TOP and BOTTOM of the ordering for the ONE all-levers-worst baseline** and explicitly does
  *not* constrain the order for other configurations. The reviewer is testing outside the
  AC's stated scope.
- **WI12-ADV-006** — a "stable" forward COM (d_COM = 1.25 in) is a DNF under worst-case
  friction (STRAIGHT + unprepared μ=0.35). Verified: it stalls at **12.51 m of 12.80 m — 0.29 m
  short**. This is **consistent with the team's earlier WI-5 ruling** (a car that stalls short
  is a DNF with `race_time_s = None`, wi5_adv_003), and stability (N_f > 0) was never a promise
  to finish regardless of friction. So this is arguably working-as-designed, though the
  0.29 m near-miss makes it a reasonable *calibration* question if you want such a car to
  finish-slowly instead.

**WI-7's escalation finding (WI7-ADV-P3-001, "suite is RED") is STALE** — it described a
transient red state during WI-7's review; subsequent work fixed it and the suite is green now.

### Energy/DNF root-defect fix (applied 2026-06-02, manual focused pass — now permanent)
**Root cause:** the WI-6 developer modelled the rear-weight-bias advantage as an injected
*head-start velocity*; that extra KE couldn't be booked consistently (fold into `w_gravity` →
breaks AC-E4; dock from KE → breaks AC-E2/WI6-ADV-003). **Fix:** the car now starts **at
rest** (so `w_gravity` is pure track geometry, ledger closes to the true final KE at ~1e-14),
and the placement advantage is modelled physically — **rear bias unloads the front wheels →
less front-wheel rail-tracking friction** (the same family as the 3-wheel-touch advantage).
Rear bias is still strictly faster (AC-P1/P2); the DNF cliff and calibration band are intact.
(The WI-10 developer later refined this from an axle-bore term to a rail-tracking term so the
placement and axle-friction levers stay physically distinct — see `engine.py`.)

### Decision for the human
Adjudicate WI12-ADV-005/006. If you agree they're out-of-scope / working-as-designed → the
feature is **done** (flip `status` to `done`). If WI12-ADV-006's 0.29 m near-miss should
finish-slowly instead → that's a small rail/friction calibration tweak, then done.

---

## Original escalation (historical — workflow run `wf_82a497c7-eac`)

**Status: ESCALATED** · Workflow run `wf_82a497c7-eac` (build-loop.mjs) ·
Span 2026-06-02T10:03:30Z → 2026-06-02T20:19:48Z (first run crashed; resumed once) ·
Run record: `evals/run-records/pinewood-derby-sim/0001-physics-engine.json`

## Why escalated
Per `gates.md`: *"hitting a loop cap → escalate to user, never silent pass."* The PO
decomposed the PRD/TRD into **13 work items**. The loop cleared WI-1..WI-3, **escalated WI-4
and WI-5 on loop caps**, was interrupted mid-WI-6, and never reached WI-7..WI-13 or PO sign-off.

| WI | Title | Outcome |
|----|-------|---------|
| WI-1 | Unit value objects | **PASSED** (adv rev0 clean) |
| WI-2 | Track model | **PASSED** (1 rework loop) |
| WI-3 | CarDesign + sub-objects | **PASSED** (2 rework loops) |
| WI-4 | Minimal end-to-end `simulate()` | **ESCALATED** — hit dev cap (6/6) *and* adversarial cap (3/3); 2 reproducible HIGH open at rev3 |
| WI-5 | Weight lever (PE, legal-weight) | **ESCALATED** — hit adversarial cap (3/3); 1 reproducible HIGH open at rev3 |
| WI-6 | Weight placement (d_COM) | **INTERRUPTED** by infra crash (dev att5 emitted no structured output, 5th occurrence); open HIGH findings |
| WI-7..WI-13 | wheels, aero, friction, alignment, energy-closure, AC-ED1 priority-order, NFRs | **NOT STARTED** |

### Open HIGH findings at the caps
- **WI4-ADV-003 / -004** — a car that stalls on an inclined section runs the full 60s
  wall-clock guard, blowing the `<5ms` performance NFR by ~10×; reachable via two triggers.
- **WI5-ADV-005** — stable, legal, optimally-placed **light** cars are wrongly reported as a
  crash (`outcome=DNF`, `race_time_s=None`).
- **WI6-ADV-002 / -003** — the placement "head-start" injects fake kinetic energy and corrupts
  the reported energy ledger.
- *(WI5-ADV-001, the `legal_weight` gram-boundary HIGH, was fixed during the continuation.)*

## Recurring root defect (the decision this escalates)
Across WI-4/WI-5/WI-6 the adversarial reviewer kept surfacing the **same** class of
domain-correctness defect the developer could not close within the caps:
1. the **energy ledger does not close** to AC-E1 tolerance; reported `pe_initial` omits the
   **transition-arc descent** (WI5-ADV-002/003/005/006, WI6-ADV-002/003); and
2. the **stall / DNF model is physically wrong** (light-but-stable cars flagged as crashes;
   stalled cars grind the 60s guard instead of being a clean non-finish).

This is the live signature of the **one currently-failing test on disk**:
`tests/test_engine_weight_wi5.py::test_ace4_w_gravity_matches_analytic_pe_drop_at_fine_dt`
(AC-E4: `w_gravity` vs analytic PE drop — **2.9% error vs the 0.1% tolerance**). WI-6's engine
changes regressed it; resolving it *is* the physics work the loop escalated, so it was left
red rather than papered over (modifying the test to pass is forbidden by the developer gate).

## On-disk state
220 passing tests, 1 failing (the AC-E4 regression), `ruff` clean, `mypy --strict` clean,
coverage 97% overall / 98% engine. **No test files were modified to force green.**

## Recommended next step (human)
Re-scope the WI-5/WI-6 **energy-ledger + DNF physics** as a focused fix (close the ledger
including the transition arc; make the stall/DNF model physical), then re-run the build-loop
for WI-6..WI-13. The protective gates behaved as designed — this is a genuine
physics-correctness escalation, not a process failure. Two orthogonal issues to also note for
the factory eval-loop: (a) the recurring *"subagent completed without calling StructuredOutput"*
crash (5×) on the long physics-dev sessions, and (b) the full suite runs each green gate, so a
later work item's edit can regress an earlier item's accepted test (WI-6 regressed WI-5's AC-E4).
