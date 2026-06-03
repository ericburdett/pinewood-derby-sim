import { test, expect } from "@playwright/test";
import { gotoReady, raceAndWait, setRange } from "./util";

// WI11 — distinct non-finish rendering: tipped vs stalled (PRD AC-R2, AC-R4).
test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("a tipped design and a stalled design tell different non-finish stories (AC-R4)", async ({
  page,
}) => {
  await gotoReady(page);

  // Tipped: weight too far back (below the stability cliff) — the engine rules it unstable.
  await setRange(page, "#placement", "0.10");
  await raceAndWait(page);
  const tippedOutcome = await page.locator("#track-canvas").getAttribute("data-outcome");
  const tippedHeadline = (await page.locator("#result-headline").textContent()) ?? "";
  expect(tippedOutcome).toBe("tipped");
  expect(tippedHeadline.toLowerCase()).toMatch(/tip|wobble/);
  await expect(page.locator("#result-time")).toBeHidden(); // AC-R2: no numeric time
  await expect(page.locator("#track-canvas")).toHaveAttribute("data-reached-finish", "false");
  // The race screen itself makes the non-finish obvious (banner + accessible label), so it
  // never looks like the simulation simply didn't run.
  await expect(page.locator("#track-canvas")).toHaveAttribute("data-banner", /did not finish/i);
  const tippedAria = await page.locator("#track-canvas").getAttribute("aria-label");
  expect(tippedAria?.toLowerCase()).toContain("tipped");
  expect(tippedAria?.toLowerCase()).toContain("did not finish");

  // Stalled: a stable but underpowered car (light, rough axles, blocky, heavy wheels) runs
  // out of speed before the finish.
  await setRange(page, "#placement", "0.85");
  await setRange(page, "#weight", "1.0");
  await setRange(page, "#wheel-mass", "0.20");
  await setRange(page, "#axle-mu", "0.40");
  await setRange(page, "#body-cd", "0.85");
  await raceAndWait(page);
  const stalledOutcome = await page.locator("#track-canvas").getAttribute("data-outcome");
  const stalledHeadline = (await page.locator("#result-headline").textContent()) ?? "";

  expect(stalledOutcome).toBe("stalled");
  expect(stalledOutcome).not.toBe(tippedOutcome); // the two never collapse into one
  // A slow-but-stable car is NEVER shown as a crash.
  expect(stalledHeadline.toLowerCase()).not.toMatch(/crash|tip|wobble|flip/);
  await expect(page.locator("#result-time")).toBeHidden();
  await expect(page.locator("#track-canvas")).toHaveAttribute("data-reached-finish", "false");
  await expect(page.locator("#track-canvas")).toHaveAttribute("data-banner", /did not finish/i);
});
