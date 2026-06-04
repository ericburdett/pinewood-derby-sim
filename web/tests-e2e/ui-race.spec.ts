import { test, expect } from "@playwright/test";
import type { RaceView } from "../src/types";
import { gotoReady, raceAndWait } from "./util";

// WI09 — race + animation (PRD AC-R1, AC-R3).

test("racing the default car animates to the finish line and shows the engine time (AC-R1)", async ({
  page,
}) => {
  await gotoReady(page);
  const expected = (await page.evaluate(() => {
    const d = window.__derby!;
    return (d.race as (s: unknown) => RaceView)(d.default).time_seconds;
  })) as number;

  await raceAndWait(page); // full animated path (no reduced motion)
  await expect(page.locator("#track-canvas")).toHaveAttribute("data-reached-finish", "true");
  await expect(page.locator("#track-canvas")).toHaveAttribute("data-banner", /finished/i);
  await expect(page.locator("#result-time")).toContainText(expected.toFixed(3));
  // The live speed readout shows a real mph at the finish line.
  expect(Number(await page.locator("#mph").textContent())).toBeGreaterThan(0);
});

test("racing the same design twice yields the same time (AC-R3)", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await gotoReady(page);
  await raceAndWait(page);
  const first = await page.locator("#result-time").textContent();
  await raceAndWait(page);
  const second = await page.locator("#result-time").textContent();
  expect(first).toBe(second);
  expect(first).not.toBeNull();
});
