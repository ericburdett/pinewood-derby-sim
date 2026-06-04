// Crisp canvases at any display size. The drawing code works in a fixed LOGICAL coordinate
// space (e.g. 600×280); this boosts the canvas's backing-store resolution above that and scales
// the context to match, so when CSS stretches the canvas across the full-width stage it stays
// sharp instead of upscaling a 600px bitmap. Returns the scaled 2D context.
export function setupHiDpiCanvas(
  canvas: HTMLCanvasElement,
  logicalW: number,
  logicalH: number,
): CanvasRenderingContext2D {
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas context unavailable");
  // 2–4× the logical size, nudged by the device pixel ratio; capped to keep memory sane.
  const res = Math.min(4, Math.max(2, Math.round((window.devicePixelRatio || 1) * 2)));
  canvas.width = Math.round(logicalW * res);
  canvas.height = Math.round(logicalH * res);
  ctx.scale(res, res); // draw in logical units; the backing store is `res`× denser
  return ctx;
}
