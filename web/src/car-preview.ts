// Live car preview (WI08 visual) — a neon side-view of the current design that redraws on
// every control change, using the SAME shared car art as the race (car-art.ts), so the car
// you tune is the car you race. Adds a balance (centre-of-mass) marker and a rail line on
// top. Pure presentation off ControlState — no physics, no I/O (AC-G1). Same-origin canvas.
import { type CarArtSpec, carSpec, drawCar } from "./car-art";
import type { ControlState } from "./types";

const LIME = "#a3e635";
const PX_PER_IN = 30; // preview is larger than the race view

export class CarPreview {
  private readonly ctx: CanvasRenderingContext2D;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly summary: HTMLElement,
  ) {
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2D canvas context unavailable");
    this.ctx = ctx;
  }

  render(state: ControlState): void {
    const { ctx } = this;
    const W = this.canvas.width;
    const H = this.canvas.height;
    ctx.clearRect(0, 0, W, H);

    const baseline = H - 42;
    const cx = W / 2;
    const spec = carSpec(state, PX_PER_IN);

    this.drawGround(baseline, W, state.alignment_rail);

    ctx.save();
    ctx.translate(cx, baseline);
    drawCar(ctx, spec);
    this.drawComMarker(spec, state);
    ctx.restore();

    this.summary.textContent = this.describe(state);
    this.canvas.setAttribute("aria-label", `Car preview: ${this.describe(state)}`);
  }

  private drawGround(baseline: number, W: number, rail: boolean): void {
    const { ctx } = this;
    ctx.save();
    ctx.strokeStyle = rail ? LIME : "#33425c";
    ctx.lineWidth = rail ? 3 : 2;
    if (rail) {
      ctx.shadowColor = LIME;
      ctx.shadowBlur = 8;
    }
    ctx.beginPath();
    ctx.moveTo(24, baseline + 2);
    ctx.lineTo(W - 24, baseline + 2);
    ctx.stroke();
    ctx.restore();
    if (rail) {
      ctx.fillStyle = LIME;
      ctx.font = "11px system-ui, sans-serif";
      ctx.textAlign = "right";
      ctx.fillText("rail-rider ›", W - 24, baseline + 18);
    }
  }

  /** Balance point sliding along the wheelbase (drawn in car-local coords). */
  private drawComMarker(spec: CarArtSpec, state: ControlState): void {
    const { ctx } = this;
    const f = Math.max(0, Math.min(1, state.com_in / state.wheelbase_in));
    const comX = -spec.wheelbasePx / 2 + f * spec.wheelbasePx;
    const bodyTop = -spec.wheelR * 1.15 - spec.heightPx;
    const my = bodyTop - 16;
    ctx.save();
    ctx.shadowColor = LIME;
    ctx.shadowBlur = 10;
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
