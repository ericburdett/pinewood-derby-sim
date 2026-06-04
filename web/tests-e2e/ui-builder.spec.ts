import { test, expect } from "@playwright/test";
import { gotoReady, raceAndWait, setRange } from "./util";

// WI08 — builder controls (PRD AC-C1, AC-C2, AC-C3).
test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("a legal, finishing default car is loaded and immediately raceable (AC-C2)", async ({
  page,
}) => {
  await gotoReady(page);
  await expect(page.locator("#weight-display")).toHaveText("4.0"); // mid-range, legal sub-limit starter
  await expect(page.locator("#weight-legal")).toContainText("Legal");
  await expect(page.locator("#race")).toBeEnabled();

  await raceAndWait(page);
  await expect(page.locator("#track-canvas")).toHaveAttribute("data-outcome", "finished");
});

test("weight updates live with a legal/over-limit badge; over-limit is still raceable (AC-C3)", async ({
  page,
}) => {
  await gotoReady(page);
  await setRange(page, "#weight", "6.5");
  await expect(page.locator("#weight-display")).toHaveText("6.5");
  await expect(page.locator("#weight-legal")).toContainText("Over the 5.0 oz limit");
  await expect(page.locator("#race")).toBeEnabled();

  await raceAndWait(page); // over-limit car still races (rule shown, not enforced by physics)
  await expect(page.locator("#result-headline")).not.toBeEmpty();
});

test("extreme but in-range inputs never throw a stack trace and still race (AC-C1)", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await gotoReady(page);

  await setRange(page, "#weight", "1.0");
  await setRange(page, "#placement", "0.10");
  await setRange(page, "#wheelbase", "3.5");
  await setRange(page, "#wheel-mass", "0.20");
  await setRange(page, "#axle-mu", "0.40");
  await setRange(page, "#body-cd", "0.85");
  await setRange(page, "#steer-angle", "0"); // worst alignment: no steer → ping-pongs

  await raceAndWait(page);
  await expect(page.locator("#control-error")).toBeHidden();
  expect(errors).toEqual([]);
});

test("the wheelbase can never be set longer than the body", async ({ page }) => {
  await gotoReady(page);
  // Shrink the wheelbase so the body can be shortened, then shorten it.
  await setRange(page, "#wheelbase", "3.5");
  await setRange(page, "#body-length", "4.0");
  // Now try to drag the wheelbase past the (short) body — it must be constrained.
  await setRange(page, "#wheelbase", "5.0");

  const wheelbase = await page
    .locator("#wheelbase")
    .evaluate((e) => Number((e as HTMLInputElement).value));
  const length = await page
    .locator("#body-length")
    .evaluate((e) => Number((e as HTMLInputElement).value));
  expect(wheelbase).toBeLessThan(length); // axles sit inside the body
});
