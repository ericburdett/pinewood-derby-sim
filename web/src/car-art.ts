// Shared procedural car art (no image assets — same-origin, AC-P1). One renderer draws the
// car silhouette from the design, used by BOTH the live preview and the race animation, so
// the car you tune is the car you race. Drawn in car-local coords: x=0 is the car's centre,
// y=0 is the ground contact (wheel bottoms); the car extends to the right (downhill) and up.
import type { ControlState } from "./types";
import { RANGES } from "./types";

export interface CarArtSpec {
  lengthPx: number; // overall body length
  heightPx: number; // body height (tail)
  noseFrac: number; // 0..1 nose height as a fraction of body height (sleek wedge → block)
  wheelR: number; // wheel radius
  wheelbasePx: number; // axle spacing
  threeWheel: boolean; // one front wheel lifted
  spin: number; // wheel rotation (radians) — for the rolling animation
}

/** Body underside height above the ground, in px (shared by drawCar + the preview marker).
 *  Sits just above the axle line so the wheels read below the chassis. */
export function bodyBaseY(s: CarArtSpec): number {
  return -(s.wheelR * 1.15);
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * Math.max(0, Math.min(1, t));
}
function frac(v: number, r: { min: number; max: number }): number {
  return (v - r.min) / (r.max - r.min);
}

/** Derive pixel art dimensions from a design. `pxPerIn` sets the scale (preview uses a big
 *  value, the race a small one); length/height/wheelbase share it so proportions are real. */
export function carSpec(state: ControlState, pxPerIn: number, spin = 0): CarArtSpec {
  return {
    lengthPx: state.body_length_in * pxPerIn,
    heightPx: Math.max(8, state.body_height_in * pxPerIn * 0.85),
    noseFrac: lerp(0.26, 1.0, frac(state.body_cd, RANGES.body_cd)),
    wheelR: (0.42 + 0.16 * frac(state.wheel_mass_oz, RANGES.wheel_mass_oz)) * pxPerIn,
    wheelbasePx: state.wheelbase_in * pxPerIn,
    threeWheel: state.wheels_count === 3,
    spin,
  };
}

function drawWheel(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number, spin: number, dim: boolean): void {
  ctx.save();
  ctx.translate(cx, cy);
  if (dim) ctx.globalAlpha = 0.85;
  // Tire.
  ctx.fillStyle = "#0a1018";
  ctx.strokeStyle = dim ? "#6b7a93" : "#5aa6cf";
  ctx.lineWidth = Math.max(1.5, r * 0.18);
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  // Spokes (rotate to show rolling).
  ctx.rotate(spin);
  ctx.strokeStyle = "#5b6b86";
  ctx.lineWidth = Math.max(1, r * 0.12);
  for (let i = 0; i < 4; i++) {
    ctx.rotate(Math.PI / 2);
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(0, r * 0.72);
    ctx.stroke();
  }
  // Hub.
  ctx.fillStyle = "#9fb3cc";
  ctx.beginPath();
  ctx.arc(0, 0, r * 0.26, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

/** Draw the car centred at the current origin. Caller sets translate/rotate (track tilt). */
export function drawCar(ctx: CanvasRenderingContext2D, s: CarArtSpec): void {
  const rearX = -s.wheelbasePx / 2;
  const frontX = s.wheelbasePx / 2;
  const bodyBackX = -s.lengthPx / 2;
  const bodyFrontX = s.lengthPx / 2;
  const wheelCY = -s.wheelR;
  const bodyBase = bodyBaseY(s); // body underside sits just above the axle line
  const tailTop = bodyBase - s.heightPx;
  const noseTop = bodyBase - s.heightPx * s.noseFrac;

  // Body — glowing wedge/block silhouette with a slate gradient fill.
  ctx.save();
  ctx.shadowColor = "#5aa6cf";
  ctx.shadowBlur = 6;
  const grad = ctx.createLinearGradient(0, tailTop, 0, bodyBase);
  grad.addColorStop(0, "#2a5f82");
  grad.addColorStop(1, "#0e2638");
  ctx.fillStyle = grad;
  ctx.strokeStyle = "#7fb8d8";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(bodyBackX, bodyBase);
  ctx.lineTo(bodyBackX, tailTop);
  ctx.quadraticCurveTo(bodyBackX + s.lengthPx * 0.34, tailTop - s.heightPx * 0.12, bodyFrontX - s.lengthPx * 0.18, noseTop);
  ctx.lineTo(bodyFrontX, noseTop + (bodyBase - noseTop) * 0.35);
  ctx.lineTo(bodyFrontX, bodyBase);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.restore();

  // (No cockpit/windshield decoration — a clean body silhouette reads better than an
  // ambiguous shape at this scale; the gradient fill + glowing edge carry the styling.)

  // Wheels (front lifted for a 3-wheeler).
  drawWheel(ctx, rearX, wheelCY, s.wheelR, s.spin, false);
  const frontLift = s.threeWheel ? s.wheelR * 0.9 : 0;
  drawWheel(ctx, frontX, wheelCY - frontLift, s.wheelR, s.spin, s.threeWheel);
}
