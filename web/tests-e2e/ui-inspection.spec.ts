import { test, expect } from "@playwright/test";
import { gotoReady, setRange } from "./util";

// Feature 0008 — legality inspection panel + drag-responds-to-size.
test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

const RULES = ["Weight", "Width", "Length", "Height"];

test("a legal default car passes every inspection rule, live", async ({ page }) => {
  await gotoReady(page);
  await expect(page.locator("#inspection li")).toHaveCount(RULES.length);
  for (const rule of RULES) {
    await expect(page.locator(`#inspection li[data-rule="${rule}"]`)).toHaveAttribute(
      "data-ok",
      "true",
    );
  }
});

test("each illegal dimension is flagged live, without racing", async ({ page }) => {
  await gotoReady(page);

  await setRange(page, "#body-width", "3.0"); // > 2.75 in
  await expect(page.locator('#inspection li[data-rule="Width"]')).toHaveAttribute("data-ok", "false");
  await expect(page.locator('#inspection li[data-rule="Length"]')).toHaveAttribute("data-ok", "true");

  await setRange(page, "#body-length", "8.0"); // > 7 in
  await expect(page.locator('#inspection li[data-rule="Length"]')).toHaveAttribute("data-ok", "false");

  await setRange(page, "#body-height", "4.0"); // > 3.5 in
  await expect(page.locator('#inspection li[data-rule="Height"]')).toHaveAttribute("data-ok", "false");

  await setRange(page, "#weight", "6.5"); // > 5.0 oz
  await expect(page.locator('#inspection li[data-rule="Weight"]')).toHaveAttribute("data-ok", "false");
});

test("a bigger body actually slows the car — drag responds to frontal area", async ({ page }) => {
  await gotoReady(page);
  const [tSmall, tBig] = (await page.evaluate(() => {
    const d = window.__derby as Record<string, any>;
    const base = d.default;
    const small = d.race({ ...base, body_width_in: 1.5, body_height_in: 1.0 });
    const big = d.race({ ...base, body_width_in: 2.75, body_height_in: 3.5 });
    return [small.time_seconds, big.time_seconds];
  })) as [number, number];
  expect(tBig).toBeGreaterThan(tSmall); // more frontal area → more air drag → slower
});
