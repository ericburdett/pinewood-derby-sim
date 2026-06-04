import { test, expect } from "@playwright/test";
import { gotoReady, raceAndWait, setRange } from "./util";

// WI14 — accessibility & demo-ready presentation (PRD AC-A1, AC-A2, AC-A3).

test("a keyboard-only configure → race → read loop works and the result is announced (AC-A1)", async ({
  page,
}) => {
  await gotoReady(page);
  // Operable by keyboard: focus Race and activate with the keyboard (no mouse).
  await page.locator("#race").focus();
  await expect(page.locator("#race")).toBeFocused();
  await page.keyboard.press("Enter");

  // The result region is an aria-live region so a screen reader announces the outcome.
  await expect(page.locator("#result")).toHaveAttribute("aria-live", "polite");
  await expect(page.locator("#track-canvas")).toHaveAttribute("data-anim-done", "true", {
    timeout: 30_000,
  });
  await expect(page.locator("#result-headline")).toContainText("finished");
});

test.describe("non-color signals + responsive", () => {
  test("legal status and loss bars carry text/percentage, not color alone (AC-A2)", async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await gotoReady(page);
    expect((await page.locator("#weight-legal").textContent()) ?? "").toMatch(/legal/i);

    await raceAndWait(page);
    const rows = page.locator("#breakdown .bar-row");
    const count = await rows.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      await expect(rows.nth(i).locator(".bar-label")).not.toBeEmpty();
      await expect(rows.nth(i).locator(".bar-pct")).toContainText("%");
    }
  });

  test("layout is usable at ~1024px wide (AC-A3)", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: 1024, height: 800 });
    await gotoReady(page);
    await expect(page.locator("#builder")).toBeVisible();
    await expect(page.locator("#car-preview")).toBeVisible(); // car + track boxes both show on load
    await expect(page.locator("#race")).toBeVisible();
    await setRange(page, "#weight", "5.0"); // controls remain operable at this width
    await expect(page.locator("#weight-display")).toHaveText("5.0");
  });
});
