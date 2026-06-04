import { test, expect } from "@playwright/test";
import { gotoReady, raceAndWait, setRange } from "./util";

// WI12 — local garage: save/list/load/delete/clear (PRD AC-S1, AC-S2, AC-S3). The garage now
// lives in a modal opened by the Save/Load chips on the car (feature 0005).
test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("a design saves, persists across reload, and reloading reproduces its time (AC-S1, AC-S2)", async ({
  page,
}) => {
  await gotoReady(page);
  await setRange(page, "#weight", "4.2");
  await page.locator("#open-save").click();
  await page.locator("#garage-name").fill("Speedy");
  await page.locator("#save").click();
  await expect(page.locator('#garage-list li[data-name="Speedy"]')).toBeVisible();
  await page.locator("#garage-close").click();

  await raceAndWait(page);
  const savedTime = await page.locator("#result-time").textContent();

  // Persistence across a full reload (AC-S1).
  await gotoReady(page);
  await page.locator("#open-load").click();
  await expect(page.locator('#garage-list li[data-name="Speedy"]')).toBeVisible();

  // Move the controls away, then load — every control is restored (AC-S2). Loading closes the modal.
  await setRange(page, "#weight", "5.0");
  await page.locator('#garage-list li[data-name="Speedy"] button', { hasText: "Load" }).click();
  await expect(page.locator("#weight-display")).toHaveText("4.2");

  // Racing the loaded design reproduces its time (AC-S2 + AC-R3).
  await raceAndWait(page);
  expect(await page.locator("#result-time").textContent()).toBe(savedTime);
});

test("loading a saved car refreshes the preview and inspection, not just the sliders", async ({
  page,
}) => {
  await gotoReady(page);
  // Save a distinctive, oversize car (blocky body, too wide).
  await setRange(page, "#body-cd", "0.85");
  await setRange(page, "#body-width", "3.0");
  await page.locator("#open-save").click();
  await page.locator("#garage-name").fill("Barn");
  await page.locator("#save").click();
  await page.locator("#garage-close").click();

  // Switch to a clean, legal, sleek car.
  await setRange(page, "#body-cd", "0.20");
  await setRange(page, "#body-width", "1.75");
  await expect(page.locator("#car-preview")).toHaveAttribute("aria-label", /sleek wedge/);
  await expect(page.locator('#inspection li[data-rule="Width"]')).toHaveAttribute("data-ok", "true");

  // Load the saved car — the design views (not only the sliders) must update.
  await page.locator("#open-load").click();
  await page.locator('#garage-list li[data-name="Barn"] button', { hasText: "Load" }).click();
  await expect(page.locator("#car-preview")).toHaveAttribute("aria-label", /blocky/);
  await expect(page.locator('#inspection li[data-rule="Width"]')).toHaveAttribute("data-ok", "false");
});

test("saved designs can be deleted and the garage cleared (AC-S3)", async ({ page }) => {
  await gotoReady(page);
  await page.locator("#open-save").click();
  await page.locator("#garage-name").fill("Alpha");
  await page.locator("#save").click();
  await page.locator("#garage-name").fill("Bravo");
  await page.locator("#save").click();
  await expect(page.locator("#garage-list li")).toHaveCount(2);

  await page.locator('#garage-list li[data-name="Alpha"] button[aria-label="Delete Alpha"]').click();
  await expect(page.locator('#garage-list li[data-name="Alpha"]')).toHaveCount(0);
  await expect(page.locator("#garage-list li")).toHaveCount(1);

  await page.locator("#clear-garage").click();
  await expect(page.locator("#garage-list li")).toHaveCount(0);
  await expect(page.locator("#garage-empty")).toBeVisible();
});
