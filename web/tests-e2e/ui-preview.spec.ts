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
  // The visible description was removed; the preview's plain-language summary now lives only in
  // the canvas's accessible label, which still tracks the design.
  const car = page.locator("#car-preview");
  // Default starter car: a rounded body, 4 wheels.
  await expect(car).toHaveAttribute("aria-label", /rounded/);
  await expect(car).toHaveAttribute("aria-label", /4 wheels/);

  // Body shape → blocky.
  await setRange(page, "#body-cd", "0.85");
  await expect(car).toHaveAttribute("aria-label", /blocky/);

  // Wheel count → 3 (one lifted).
  await page.locator('input[name="wheels-count"][value="3"]').check();
  await expect(car).toHaveAttribute("aria-label", /3 wheels/);

  // Weight placement → toward the back.
  await setRange(page, "#placement", "0.30");
  await expect(car).toHaveAttribute("aria-label", /toward the back/);
});
