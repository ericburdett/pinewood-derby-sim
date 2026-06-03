import { test, expect } from "@playwright/test";
import type { RaceView, ValidationResult } from "../src/types";

// WI07 — prove the engine actually runs in the browser through Pyodide and round-trips a
// race to a kid-facing view-model, with no off-origin requests and deterministic output.

test("bridge boots and races the default car in-browser (AC-R1 data path)", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 60_000 });

  const view = (await page.evaluate(() => {
    const d = window.__derby!;
    return (d.race as (s: unknown) => RaceView)(d.default);
  })) as RaceView;

  expect(view.finished).toBe(true);
  expect(view.outcome).toBe("finished");
  expect(typeof view.time_seconds).toBe("number");
  expect(view.legal_weight).toBe(true);
  expect(view.breakdown.length).toBeGreaterThan(0);
  expect(view.trajectory.length).toBeGreaterThan(1);
  // The "trajectory" key the animator needs survives the bridge (the AC-R1 / WI01 fix).
  expect(view.trajectory[0]).toHaveProperty("position");
});

test("racing the same design twice is deterministic (AC-R3)", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 60_000 });

  const [a, b] = (await page.evaluate(() => {
    const d = window.__derby!;
    const r = d.race as (s: unknown) => RaceView;
    return [r(d.default), r(d.default)];
  })) as [RaceView, RaceView];

  expect(a.time_seconds).toBe(b.time_seconds);
  expect(a.trajectory.length).toBe(b.trajectory.length);
  expect(a.trajectory.map((f) => f.position)).toEqual(b.trajectory.map((f) => f.position));
});

test("invalid designs are reported, not thrown (AC-C1 data path)", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 60_000 });

  const res = (await page.evaluate(() => {
    const d = window.__derby!;
    // wheels out-massing the car: 4 * heavy wheels vs a near-zero total mass -> ValueError.
    return (d.validate as (s: unknown) => ValidationResult)({
      ...(d.default as object),
      mass_oz: 0.1,
      wheels_light: false,
    });
  })) as ValidationResult;

  expect(res.ok).toBe(false);
  expect(typeof res.message).toBe("string");
});

test("no off-origin network requests during boot + race (AC-P1)", async ({ page }) => {
  const offOrigin: string[] = [];
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (url.origin !== "http://localhost:5173" && url.protocol !== "data:" && url.protocol !== "blob:") {
      offOrigin.push(req.url());
    }
  });

  await page.goto("/");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 60_000 });
  await page.evaluate(() => (window.__derby!.race as (s: unknown) => unknown)(window.__derby!.default));

  expect(offOrigin).toEqual([]);
});
