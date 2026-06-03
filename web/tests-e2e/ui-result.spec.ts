import { test, expect } from "@playwright/test";
import { gotoReady, raceAndWait, setRange } from "./util";

// WI10 — result & "why" panel (PRD AC-X1, AC-X2, AC-X3, AC-X4 surfaced).
test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

const BANNED = [
  "joule",
  "newton",
  "coefficient",
  "m/s",
  "moment of inertia",
  "normal force",
  "kinetic energy",
  "potential energy",
];

test("a finished race shows a ranked breakdown, a why, and tips (AC-X1, AC-X2)", async ({
  page,
}) => {
  await gotoReady(page);
  await raceAndWait(page);

  const shares = await page
    .locator("#breakdown .bar-row")
    .evaluateAll((els) => els.map((e) => Number((e as HTMLElement).dataset.share)));
  expect(shares.length).toBeGreaterThan(1);
  expect(shares).toEqual([...shares].sort((a, b) => b - a)); // largest-first (AC-X1)

  await expect(page.locator("#why")).toBeVisible();
  expect(((await page.locator("#why").textContent()) ?? "").length).toBeGreaterThan(0); // AC-X2

  // The "speed you kept" bar is present alongside the loss bars.
  const keys = await page
    .locator("#breakdown .bar-row")
    .evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.key));
  expect(keys).toContain("kept");
});

test("no technical jargon reaches the kid in the result panel (AC-X3)", async ({ page }) => {
  await gotoReady(page);
  await raceAndWait(page);
  const text = ((await page.locator("#result").innerText()) ?? "").toLowerCase();
  for (const term of BANNED) {
    expect(text, `result text must not contain jargon "${term}"`).not.toContain(term);
  }
});

// Coaching must be state-aware: the default car is already fully tuned, so it is celebrated —
// NOT told to "fix" levers it has already optimized (the reported bug). A genuinely suboptimal
// car still gets the real, actionable fix.
test("a fully-tuned car is celebrated, not nagged to fix already-optimal levers", async ({
  page,
}) => {
  await gotoReady(page);
  await raceAndWait(page);
  const tips = ((await page.locator("#tips").innerText()) ?? "").toLowerCase();
  expect(tips).toContain("tuned every part");
  expect(tips).not.toContain("polish your axles");
  expect(tips).not.toContain("fix your"); // no "fix your alignment" on a rail-rider
});

test("a genuinely suboptimal lever still gets actionable advice", async ({ page }) => {
  await gotoReady(page);
  await setRange(page, "#axle-mu", "0.40"); // rough axles — a real, fixable loss
  await raceAndWait(page);
  const tips = ((await page.locator("#tips").innerText()) ?? "").toLowerCase();
  expect(tips).toContain("polish your axles");
});
