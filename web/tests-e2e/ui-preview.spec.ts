import { test, expect } from "@playwright/test";
import { gotoReady, setRange } from "./util";

// Live car preview (WI08 visual) — the preview reacts to control changes in real time, so a
// kid sees the design morph. We assert via the preview's plain-language summary (also the
// canvas's accessible label), which is the queryable surface of the visual.
test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("the car preview reflects the default design and updates as controls change", async ({
  page,
}) => {
  await gotoReady(page);
  const summary = page.locator("#preview-summary");
  // Default car: sleek wedge body, 4 wheels.
  await expect(summary).toContainText("sleek wedge");
  await expect(summary).toContainText("4 wheels");

  // Body shape → blocky.
  await setRange(page, "#body-cd", "0.85");
  await expect(summary).toContainText("blocky");

  // Wheel count → 3 (one lifted).
  await page.locator('input[name="wheels-count"][value="3"]').check();
  await expect(summary).toContainText("3 wheels");

  // Weight placement → toward the back.
  await setRange(page, "#placement", "0.30");
  await expect(summary).toContainText("toward the back");

  // The canvas's accessible label tracks the same description.
  await expect(page.locator("#car-preview")).toHaveAttribute("aria-label", /Car preview:/);
});
