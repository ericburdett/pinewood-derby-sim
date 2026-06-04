# 🏆 Live-Build Script: Local Scoreboard

A runbook for building the scoreboard **live in front of the group** using Claude Code, as a demo of agentic coding. Read this once before the activity. Total time: ~10–15 min of model work, but you talk over it.

---

## Before the kids arrive (do this once)

1. Open a terminal in the project and start the app so the kids can see it working first:
   ```
   cd web && npm run dev
   ```
   Open http://localhost:5173 — confirm a car races and the animation plays.
2. Make a branch so the demo is safe and reversible (and you can `git stash`/reset if needed):
   ```
   git checkout -b live-scoreboard-demo
   ```
3. Open Claude Code in a **second** terminal in the project root, projected on the screen.
4. Have this file open for yourself. Keep the prompts below ready to paste.

> **Why a branch?** If anything goes sideways live, you say "watch this — `git checkout .` — and it's like it never happened." That itself is a great lesson about working safely with AI.

---

## The narration arc (what to say while it works)

You're not just building a feature — you're narrating the **agent loop** from the slides:
**Goal → Decide → Use a tool → See result → repeat.**

Call it out live: *"See — it's reading files first to understand the code... now it's deciding what to change... now it's writing... now it's running the test to check itself."* That's the whole point.

---

## Step 1 — Give it the goal (paste this)

> We're adding a **local scoreboard** to the pinewood derby web app. Before writing any code, explore `web/src` and tell me your plan: where race results are produced, how the existing garage uses `localStorage`, and which files you'll change. Don't write code yet — just give me a short plan I can approve.

**Talk track while it explores:** "Notice it isn't guessing — it's reading the actual project first, the same way a new employee would read the code before touching it."

When it shows a plan, read it aloud and say "approved, go ahead" (or tweak it).

### What a good plan should look like (so you can sanity-check it)
The app already has the pieces this needs:
- Race results come back as a `RaceView` object (has `outcome`, `time_seconds`, `finished`) after `race()` runs in `web/src/main.ts`.
- There's already a `localStorage` pattern in `web/src/garage.ts` (namespace `pds.garage.v1`) — the scoreboard should copy that pattern with its own namespace like `pds.scoreboard.v1`.
- The UI already has a tab system (`web/src/tabs.ts`) and modal pattern (the Save/Load garage modal) it can reuse.

If its plan touches roughly those files (`main.ts`, a new `scoreboard.ts`, `index.html`, maybe `tabs.ts`), it's on the right track.

---

## Step 2 — Let it build (paste this)

> Looks good. Build it:
> 1. New module `web/src/scoreboard.ts` mirroring `garage.ts`, storing entries `{ carName, timeSeconds, outcome, finishedFrac, timestamp }` under `localStorage` key `pds.scoreboard.v1`.
> 2. After each race finishes in `main.ts`, record the result. Use the car's saved name if there is one, otherwise prompt for or default the name.
> 3. Show the leaderboard in the UI — finishers sorted fastest-first, plus tipped/stalled cars listed below. Reuse the existing modal or tab styling so it matches.
> 4. Add a "Clear scoreboard" button.
> Keep it kid-friendly and match the existing code style.

**Talk track:** "It's writing real code into real files now. Watch the file names fly by — each one is a tool call. It's making decisions about *how* to do this, not just *what*."

---

## Step 3 — Make it check its own work (paste this)

> Now verify it works. Add a Playwright e2e test in `web/tests-e2e` (follow the style of `ui-garage.spec.ts` and use the helpers in `util.ts`) that races a car and asserts the result shows up on the scoreboard. Then run it with `npm test` and fix anything that fails.

**Talk track — this is the money moment:** "Here's the part that feels like magic — it runs the test, sees its *own* mistake, and fixes it without me. This is the loop from the slides: see the result, decide, try again."

If a test fails and it iterates: **let the kids watch.** Failure-then-self-repair is the single best illustration of "agent," better than anything going perfectly.

---

## Step 4 — See it in the browser

Switch to the running app at http://localhost:5173 (Vite hot-reloads, so the new UI should already be there). Race two or three cars with different settings and watch the leaderboard fill up. Let a kid pick the car settings.

> **Optional crowd-pleaser:** ask a couple of kids for car names and let them each "enter" a car. Now it's *their* scoreboard.

---

## If something goes wrong (it's fine — this is a feature, not a bug)

| Situation | What to do / say |
|---|---|
| It makes a mistake | "Perfect — this is real. Let me just tell it what I see." Paste the error or describe what's wrong. Watch it recover. |
| It goes down a rabbit hole | Press **Esc** to interrupt, then redirect: "Stop — simpler. Just do X." Great lesson: *you're* still the boss. |
| Totally broken | `git checkout .` to wipe changes, or `git stash`. "And it's like it never happened. Always work where you can undo." |
| App won't hot-reload | In the dev terminal, Ctrl-C and `npm run dev` again. |
| Out of time | Skip Step 3 (the test). The visible feature in Step 2 is enough. |

---

## The one-sentence wrap-up

> "I never opened a file. I described what I wanted, checked its work, and corrected it when it was wrong — that's agentic coding, and it's a skill you can start learning today."

---

## Cleanup after the activity (optional)

```
git checkout main
git branch -D live-scoreboard-demo     # throw away the demo, OR
# git checkout live-scoreboard-demo && (keep it / open a PR)
```
