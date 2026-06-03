import { test, expect } from "@playwright/test";
import { gotoReady } from "./util";

// WI13 — offline after first load (PRD AC-P3). The service worker precaches every same-origin
// asset (HTML/JS/CSS/Pyodide/engine), so a later load with the network disabled still boots.
test("the app loads and is ready offline after the first visit (AC-P3)", async ({
  page,
  context,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });

  // First visit: registers the worker.
  await gotoReady(page);
  await page.waitForFunction(() => navigator.serviceWorker?.controller != null, null, {
    timeout: 30_000,
  });
  // Second visit: now SW-controlled, so every asset (incl. the multi-MB Pyodide runtime) is
  // served through — and cached by — the worker.
  await gotoReady(page);

  // Cut the network and reload: must still reach "Ready" purely from the cache.
  await context.setOffline(true);
  try {
    await page.reload();
    await expect(page.locator("#status")).toHaveText("Ready", { timeout: 60_000 });
    await expect(page.locator("#app")).toBeVisible();
  } finally {
    await context.setOffline(false);
  }
});
