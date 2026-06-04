// Live car preview (WI08 visual) — a neon side-view of the current design that redraws on
// every control change, using the SAME shared car art as the race (car-art.ts), so the car
// you tune is the car you race. Adds a balance (centre-of-mass) marker and a rail line on
// top. Pure presentation off ControlState — no physics, no I/O (AC-G1). Same-origin canvas.
import { type CarArtSpec, bodyBaseY, carSpec, drawCar } from "./car-art";
import { setupHiDpiCanvas } from "./hidpi";
import type { ControlState } from "./types";

const LIME = "#a4c659";
const PX_PER_IN = 22; // car size in the preview (smaller than before, leaving room in the box)

export class CarPreview {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly w: number; // logical drawing width (HTML canvas width)
  private readonly h: number; // logical drawing height

  constructor(private readonly canvas: HTMLCanvasElement) {
    this.w = canvas.width;
    this.h = canvas.height;
    this.ctx = setupHiDpiCanvas(canvas, this.w, this.h);
  }

  render(state: ControlState): void {
    const { ctx } = this;
    const W = this.w;
    const H = this.h;
    ctx.clearRect(0, 0, W, H);

    const baseline = H - 42;
    const cx = W / 2;
    const spec = carSpec(state, PX_PER_IN);

    this.drawGround(baseline, W);

    ctx.save();
    ctx.translate(cx, baseline);
    drawCar(ctx, spec);
    this.drawComMarker(spec, state);
    ctx.restore();

    // No visible description (removed) — but keep the canvas's accessible label in sync.
    this.canvas.setAttribute("aria-label", `Car preview: ${this.describe(state)}`);
  }

  private drawGround(baseline: number, W: number): void {
    const { ctx } = this;
    // Just a plain line for the car to sit on — no alignment/steering hints (the Race tab is a
    // test; we don't give the sweet spot away while a kid plays with the slider).
    ctx.save();
    ctx.strokeStyle = "#33425c";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(24, baseline + 2);
    ctx.lineTo(W - 24, baseline + 2);
    ctx.stroke();
    ctx.restore();
  }

  /** Balance point sliding along the wheelbase (drawn in car-local coords). */
  private drawComMarker(spec: CarArtSpec, state: ControlState): void {
    const { ctx } = this;
    const f = Math.max(0, Math.min(1, state.com_in / state.wheelbase_in));
    const comX = -spec.wheelbasePx / 2 + f * spec.wheelbasePx;
    const bodyTop = bodyBaseY(spec) - spec.heightPx;
    const my = bodyTop - 16;
    ctx.save();
    ctx.shadowColor = LIME;
    ctx.shadowBlur = 6;
    ctx.fillStyle = LIME;
    ctx.beginPath();
    ctx.moveTo(comX, my - 6);
    ctx.lineTo(comX + 6, my);
    ctx.lineTo(comX, my + 6);
    ctx.lineTo(comX - 6, my);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
    ctx.strokeStyle = LIME;
    ctx.setLineDash([3, 3]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(comX, my + 6);
    ctx.lineTo(comX, bodyTop);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = LIME;
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("balance", comX, my - 12);
  }

  private describe(state: ControlState): string {
    const weight = state.mass_oz >= 4.5 ? "heavy" : state.mass_oz >= 2.5 ? "medium-weight" : "light";
    const body = state.body_cd <= 0.25 ? "a sleek wedge" : state.body_cd <= 0.5 ? "a rounded" : "a blocky";
    const wb = state.wheelbase_in >= 4.6 ? "long" : state.wheelbase_in >= 4.0 ? "standard" : "short";
    const place = state.com_in <= 0.7 ? "toward the back" : state.com_in >= 1.4 ? "up front" : "balanced";
    const wheels = state.wheels_count === 3 ? "3 wheels (one lifted)" : "4 wheels";
    return `A ${weight} car with ${body} body, a ${wb} wheelbase, ${wheels}, and its weight ${place}.`;
  }
}
