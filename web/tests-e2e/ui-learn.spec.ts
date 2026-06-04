import { test, expect } from "@playwright/test";
import { gotoReady } from "./util";

// Feature 0005 — Learn mode + the simulator reframed as a test (definitional hints, no cheats).
test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("the Learn tab teaches every lever and toggles cleanly with Race", async ({ page }) => {
  await gotoReady(page);

  // Race is the default view; Learn is hidden.
  await expect(page.locator("#app")).toBeVisible();
  await expect(page.locator("#learn")).toBeHidden();

  await page.locator("#tab-learn").click();
  await expect(page.locator("#learn")).toBeVisible();
  await expect(page.locator("#app")).toBeHidden();
  await expect(page.locator("#race")).toBeHidden(); // the Race button is meaningless on Learn

  // It covers each lever in Mark Rober's order and embeds his video.
  const learn = page.locator("#learn");
  for (const topic of [
    "Weight",
    "Weight placement",
    "Lighter wheels",
    "Axle prep",
    "Rail-riding",
    "Aerodynamics",
    "Three wheels",
  ]) {
    await expect(learn).toContainText(topic);
  }
  await expect(learn).toContainText("Mark Rober");
  await expect(learn.locator("iframe")).toHaveAttribute("src", /youtube-nocookie\.com\/embed\//);

  // Back to Race restores the simulator.
  await page.locator("#tab-race").click();
  await expect(page.locator("#app")).toBeVisible();
  await expect(page.locator("#learn")).toBeHidden();
  await expect(page.locator("#race")).toBeVisible();
});

test("the slider descriptions define each part rather than coaching how to win", async ({ page }) => {
  await gotoReady(page);
  const tune = (await page.locator(".tune").innerText()).toLowerCase();
  // Definitional, not prescriptive.
  expect(tune).toContain("distance between the front and rear axles");
  expect(tune).not.toContain("slide left");
  expect(tune).not.toContain("(faster");
});
