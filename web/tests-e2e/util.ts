import { type Page, expect } from "@playwright/test";

/** Load the app and wait for the in-browser engine to boot. */
export async function gotoReady(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 60_000 });
  await expect(page.locator("#app")).toBeVisible();
}

/** Set an <input type=range> value and fire the input event (Playwright can't drag sliders). */
export async function setRange(page: Page, selector: string, value: string): Promise<void> {
  await page.locator(selector).evaluate((el, v) => {
    const input = el as HTMLInputElement;
    input.value = v;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }, value);
}

/** Press Race and wait for the animation (or its reduced-motion end-state) to settle. */
export async function raceAndWait(page: Page): Promise<void> {
  await page.locator("#race").click();
  await expect(page.locator("#track-canvas")).toHaveAttribute("data-anim-done", "true", {
    timeout: 30_000,
  });
}
