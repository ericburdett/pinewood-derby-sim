import { test, expect } from "@playwright/test";
import { gotoReady, raceAndWait } from "./util";

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

test("a finished race shows a ranked 'where did your speed go?' breakdown (AC-X1)", async ({
  page,
}) => {
  await gotoReady(page);
  await raceAndWait(page);

  const shares = await page
    .locator("#breakdown .bar-row")
    .evaluateAll((els) => els.map((e) => Number((e as HTMLElement).dataset.share)));
  expect(shares.length).toBeGreaterThan(1);
  expect(shares).toEqual([...shares].sort((a, b) => b - a)); // largest-first (AC-X1)

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

// The Race tab is a TEST: the breakdown shows WHERE speed went, but the page does NOT explain
// WHY or hand out "try this next" tips (feature 0005) — that teaching lives on the Learn tab.
test("the Race page shows no 'why' explanation or coaching tips", async ({ page }) => {
  await gotoReady(page);
  await raceAndWait(page);
  await expect(page.locator("#why")).toHaveCount(0);
  await expect(page.locator("#tips")).toHaveCount(0);
  const result = (await page.locator("#result").innerText()).toLowerCase();
  expect(result).not.toContain("try this next");
});
