// WI09 / WI11 — a 2-D side-view of the standard track on <canvas>, replaying the engine's
// trajectory. The lane is a solid shaded beam with a centre guide rail, a start gate and a
// checkered finish banner; the car is the SAME silhouette you designed (shared car-art) with
// spinning wheels and a ground shadow. A finisher rolls to the line; a "stalled" car coasts
// to a visible halt short of it; a "tipped" car's front goes light and it rocks/lifts (PRD
// AC-R1/R2/R4). Every run paints a clear outcome banner + sets the canvas's accessible label.
// Pure function of the trajectory (AC-R3); respects prefers-reduced-motion (AC-A3); no physics.
import { type CarArtSpec, carSpec, drawCar } from "./car-art";
import { setupHiDpiCanvas } from "./hidpi";
import { type ControlState, DEFAULT_CAR } from "./types";
import type { FrameDTO, RaceView, TrackInfo } from "./types";

// Generous margins so the staged car (nose at the start line, body trailing UP-left) and the
// finish flag both sit fully inside the canvas instead of clipping at the edge.
const MARGIN_L = 70; // room for the start car's body extending back-uphill from the start line
const MARGIN_R = 46; // room for the finish flag past the finish line
const TOP_PAD = 64; // room above the ramp for the staged car's height + uphill rise
const LANE_THICK = 15; // beam depth (3-D edge)
const TRACK_PX_PER_IN = 9; // car scale on the track (sized so it fits the lane with margins)
const STAGING_PX = 96; // ramp drawn this far uphill past the start gate, so the staged car rests on track
const TRANSITION_M = 1.6; // arc-length over which the ramp rounds into the flat (longer = gentler curve)
const PATH_SAMPLES = 400; // resolution of the precomputed rounded centreline
const TRACK_SAMPLES = 160; // polyline segments used to draw the rounded lane
const WHEEL_ROLL_RADIUS_M = 0.0151; // for wheel-spin rate (≈ 0.595 in)
const MS_TO_MPH = 2.2369363; // metres/second → miles/hour, for the live speed readout
const MAX_PLAYBACK_S = 4;
const TIP_DURATION_MS = 1500;
const TIP_LIFT_RAD = -0.22; // front-light nose-up rest pose (negative = nose lifts) — not a rollover

interface Outcome {
  banner: string;
  aria: string;
  finished: boolean;
}

function reducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

export class RaceAnimator {
  private readonly ctx: CanvasRenderingContext2D;
  private readonly scale: number;
  private readonly w: number; // logical drawing width (HTML canvas width)
  private readonly h: number; // logical drawing height
  private raf = 0;
  private design: ControlState = DEFAULT_CAR;
  // Precomputed rounded centreline: cumulative world coords sampled along arc-position s, so
  // the drawn lane, the car's position, and angleAt all share ONE smooth ramp→flat path.
  private readonly pathX: number[] = [];
  private readonly pathY: number[] = [];
  private ridePts: { x: number; y: number }[] = [];

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly track: TrackInfo,
    private readonly clock: HTMLOutputElement,
    private readonly speedo: HTMLOutputElement,
  ) {
    this.w = canvas.width;
    this.h = canvas.height;
    this.ctx = setupHiDpiCanvas(canvas, this.w, this.h);
    this.buildPath(); // must precede scale (it reads worldX) and ridePts (reads sx/sy)
    this.scale = (this.w - MARGIN_L - MARGIN_R) / this.worldX(track.total_length_m);
    this.buildRidePts();
    this.drawScene(0, 0, 0);
  }

  // ── track geometry: a rounded ramp→flat centreline. The engine models a transition arc;
  // here the angle eases linearly (≈ a circular fillet) from the ramp angle to flat over a
  // TRANSITION_M window centred on the ramp/flat junction, so the car rotates level smoothly. ──
  private angleAt(s: number): number {
    const a = this.track.ramp_angle_rad;
    const j = this.track.ramp_length_m;
    const half = TRANSITION_M / 2;
    if (s <= j - half) return a;
    if (s >= j + half) return 0;
    return a * (1 - (s - (j - half)) / TRANSITION_M);
  }
  private buildPath(): void {
    const total = this.track.total_length_m;
    const ds = total / PATH_SAMPLES;
    let x = 0;
    let y = 0;
    this.pathX.push(0);
    this.pathY.push(0);
    for (let i = 1; i <= PATH_SAMPLES; i++) {
      const th = this.angleAt((i - 0.5) * ds); // midpoint angle → integrate the centreline
      x += Math.cos(th) * ds;
      y += Math.sin(th) * ds;
      this.pathX.push(x);
      this.pathY.push(y);
    }
  }
  private interp(arr: number[], s: number): number {
    const total = this.track.total_length_m;
    const f = (Math.max(0, Math.min(total, s)) / total) * PATH_SAMPLES;
    const i = Math.min(PATH_SAMPLES - 1, Math.floor(f));
    return arr[i] + (arr[i + 1] - arr[i]) * (f - i);
  }
  private worldX(s: number): number {
    return this.interp(this.pathX, s);
  }
  private worldDrop(s: number): number {
    return this.interp(this.pathY, s);
  }
  private sx(s: number): number {
    return MARGIN_L + this.worldX(s) * this.scale;
  }
  private sy(s: number): number {
    return TOP_PAD + this.worldDrop(s) * this.scale;
  }
  /** Screen point at arc-position s, extrapolating up the straight ramp for s < 0 (the staging
   *  region behind the start gate) so the car's tail has a surface to rest on at the line. */
  private pathPoint(s: number): { x: number; y: number } {
    if (s >= 0) return { x: this.sx(s), y: this.sy(s) };
    const a = this.track.ramp_angle_rad;
    return { x: MARGIN_L + s * Math.cos(a) * this.scale, y: TOP_PAD + s * Math.sin(a) * this.scale };
  }
  /** The drawn lane as a screen-space polyline (staging extension + sampled rounded centreline);
   *  cached because the track and scale never change after construction. */
  private buildRidePts(): void {
    const total = this.track.total_length_m;
    const a = this.track.ramp_angle_rad;
    const pts = [
      { x: this.sx(0) - STAGING_PX * Math.cos(a), y: this.sy(0) - STAGING_PX * Math.sin(a) },
    ];
    for (let i = 0; i <= TRACK_SAMPLES; i++) {
      const s = (i / TRACK_SAMPLES) * total;
      pts.push({ x: this.sx(s), y: this.sy(s) });
    }
    this.ridePts = pts;
  }

  private background(): void {
    const { ctx, w, h } = this;
    const g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "#0a1424");
    g.addColorStop(1, "#060b15");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    // Faint floor glow.
    const fg = ctx.createRadialGradient(w * 0.5, h, 40, w * 0.5, h, w * 0.7);
    fg.addColorStop(0, "rgba(56,189,248,0.10)");
    fg.addColorStop(1, "transparent");
    ctx.fillStyle = fg;
    ctx.fillRect(0, 0, w, h);
  }

  private drawTrack(): void {
    const { ctx } = this;
    const ramp = this.track.ramp_length_m;
    const total = this.track.total_length_m;
    const pts = this.ridePts;
    const yt = this.sy(total);

    // Beam (solid lane with a 3-D front face): the rounded ride polyline forward, then its
    // bottom edge (a constant vertical extrusion) backward.
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    for (let i = pts.length - 1; i >= 0; i--) ctx.lineTo(pts[i].x, pts[i].y + LANE_THICK);
    ctx.closePath();
    const beam = ctx.createLinearGradient(0, pts[0].y - 6, 0, yt + LANE_THICK);
    beam.addColorStop(0, "#26405c");
    beam.addColorStop(0.5, "#1a2c41");
    beam.addColorStop(1, "#0c1726");
    ctx.fillStyle = beam;
    ctx.fill();

    // Ride surface (bright top edge) + centre guide rail just above it.
    ctx.strokeStyle = "#5a93c4";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.stroke();
    ctx.strokeStyle = "rgba(164,198,89,0.6)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y - 3);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y - 3);
    ctx.stroke();

    // Distance ticks along the flat.
    ctx.strokeStyle = "rgba(120,150,190,0.35)";
    ctx.lineWidth = 1;
    for (let s = Math.ceil(ramp); s < total; s += 1.5) {
      const x = this.sx(s);
      const y = this.sy(s);
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x, y + 5);
      ctx.stroke();
    }

    this.drawStartGate(this.sx(0), this.sy(0));
    this.drawFinish(this.sx(total), yt);
  }

  private drawStartGate(x: number, y: number): void {
    const { ctx } = this;
    ctx.strokeStyle = "#9fb3cc";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(x - 4, y);
    ctx.lineTo(x - 4, y - 34);
    ctx.lineTo(x + 24, y - 30);
    ctx.stroke();
    ctx.fillStyle = "#9fb3cc";
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("START", x - 4, y - 38);
  }

  private drawFinish(x: number, y: number): void {
    const { ctx } = this;
    const top = y - 56;
    // Post.
    ctx.strokeStyle = "#cdd8e8";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(x, y + LANE_THICK);
    ctx.lineTo(x, top);
    ctx.stroke();
    // Checkered flag.
    const cols = 5;
    const rows = 3;
    const cell = 7;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        ctx.fillStyle = (r + c) % 2 === 0 ? "#f4f7fb" : "#10182a";
        ctx.fillRect(x + 2 + c * cell, top + r * cell, cell, cell);
      }
    }
    // Checkered strip across the lane at the line.
    for (let i = 0; i < 4; i++) {
      ctx.fillStyle = i % 2 === 0 ? "#f4f7fb" : "#10182a";
      ctx.fillRect(x - 2, y + (i * LANE_THICK) / 4, 4, LANE_THICK / 4);
    }
  }

  private carSpecFor(spin: number): CarArtSpec {
    return carSpec(this.design, TRACK_PX_PER_IN, spin);
  }

  private drawCarAt(pos: number, spin: number, extraRot: number): void {
    const { ctx } = this;
    const spec = this.carSpecFor(spin);
    const L = spec.lengthPx;
    // Rest the car on the lane as a CHORD: nose at the tracked position, tail one car-length
    // back ALONG the track surface. On the straight ramp/flat this is just the tangent; through
    // the rounded transition the car bridges the dip (nose AND tail on the line, body gently
    // above) — so the back never drops below the track. The nose stays the timing/finish point:
    // time stops when it crosses the line, and a longer car just trails further back.
    const nose = this.pathPoint(pos);
    const tail = this.pathPoint(pos - L / this.scale); // screen length L ≈ scale × arc-metres
    const angle = Math.atan2(nose.y - tail.y, nose.x - tail.x) + extraRot;
    ctx.save();
    ctx.translate(nose.x, nose.y);
    ctx.rotate(angle);
    ctx.translate(-L / 2, 0); // car-local centre at the chord midpoint; nose sits at +L/2
    // Ground shadow under the car body.
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    ctx.beginPath();
    ctx.ellipse(0, 4, L * 0.5, 4, 0, 0, Math.PI * 2);
    ctx.fill();
    drawCar(ctx, spec);
    ctx.restore();
  }

  private drawScene(pos: number, extraRot: number, spin: number): void {
    this.background();
    this.drawTrack();
    this.drawCarAt(pos, spin, extraRot);
  }

  private drawBanner(text: string, finished: boolean): void {
    const { ctx } = this;
    ctx.save();
    ctx.font = "bold 15px system-ui, sans-serif";
    const w = ctx.measureText(text).width + 24;
    const x = (this.w - w) / 2;
    ctx.fillStyle = finished ? "rgba(126,224,166,0.96)" : "rgba(255,209,102,0.96)";
    ctx.fillRect(x, 8, w, 26);
    ctx.fillStyle = "#0c1322";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, this.w / 2, 21);
    ctx.restore();
  }

  private describe(view: RaceView): Outcome {
    if (view.outcome === "finished") {
      const t = view.time_seconds != null ? ` ${view.time_seconds.toFixed(3)}s` : "";
      return { banner: `Finished!${t}`, aria: `Your car finished the race${t ? ` in${t}` : ""}.`, finished: true };
    }
    if (view.outcome === "tipped") {
      return {
        banner: "Front went light — did not finish",
        aria: "Your car's weight was so far back the front wheels lifted, so it wobbled off course and tipped instead of running — it did not finish the race.",
        finished: false,
      };
    }
    return {
      banner: "Ran out of speed — did not finish",
      aria: "Your car ran out of speed partway down the track and did not finish the race.",
      finished: false,
    };
  }

  private positionAt(frames: readonly FrameDTO[], simT: number): number {
    if (simT <= frames[0].t) return frames[0].position;
    const last = frames[frames.length - 1];
    if (simT >= last.t) return last.position;
    for (let i = 1; i < frames.length; i++) {
      if (simT <= frames[i].t) {
        const a = frames[i - 1];
        const b = frames[i];
        return a.position + (b.position - a.position) * ((simT - a.t) / (b.t - a.t || 1));
      }
    }
    return last.position;
  }

  private velocityAt(frames: readonly FrameDTO[], simT: number): number {
    if (simT <= frames[0].t) return frames[0].velocity;
    const last = frames[frames.length - 1];
    if (simT >= last.t) return last.velocity;
    for (let i = 1; i < frames.length; i++) {
      if (simT <= frames[i].t) {
        const a = frames[i - 1];
        const b = frames[i];
        return a.velocity + (b.velocity - a.velocity) * ((simT - a.t) / (b.t - a.t || 1));
      }
    }
    return last.velocity;
  }

  private setSpeed(mps: number): void {
    this.speedo.textContent = (Math.max(0, mps) * MS_TO_MPH).toFixed(1);
  }

  private tipRotation(p: number): number {
    if (p < 0.6) return Math.sin((p / 0.6) * Math.PI * 4) * 0.18;
    const q = (p - 0.6) / 0.4;
    return TIP_LIFT_RAD * (1 - (1 - q) * (1 - q));
  }

  /** Draw the start scene with the current design at the line (no animation, no data-* race
   *  state) — keeps the track showing the car you're tuning before you press Race. */
  renderIdle(design: ControlState): void {
    this.design = design;
    cancelAnimationFrame(this.raf);
    this.drawScene(0, 0, 0);
    this.setSpeed(0);
    delete this.canvas.dataset.animDone; // idle = no finished animation pending
  }

  /** Animate the run with the given design; resolves when finished. Sets data-* for tests. */
  play(view: RaceView, design: ControlState): Promise<void> {
    cancelAnimationFrame(this.raf);
    this.design = design;
    const frames = view.trajectory;
    const info = this.describe(view);
    const finalPos = frames.length ? frames[frames.length - 1].position : 0;
    const lastT = frames.length ? frames[frames.length - 1].t : 0;
    const tipped = view.outcome === "tipped";

    this.canvas.dataset.outcome = view.outcome;
    this.canvas.dataset.reachedFinish = String(info.finished);
    this.canvas.dataset.frames = String(frames.length);
    this.canvas.dataset.stoppedFrac = String(view.stopped_distance_frac ?? (view.finished ? 1 : 0));
    this.canvas.dataset.banner = info.banner;
    this.canvas.setAttribute("aria-label", info.aria);
    delete this.canvas.dataset.animDone;

    this.clock.textContent = view.finished && view.time_seconds != null ? `${view.time_seconds.toFixed(3)} s` : "—";

    if (tipped) {
      this.setSpeed(0); // a tipped car never gets rolling
      const settle = (): void => {
        this.drawScene(0, TIP_LIFT_RAD, 0);
        this.drawBanner(info.banner, false);
        this.canvas.dataset.animDone = "true";
      };
      if (reducedMotion()) {
        settle();
        return Promise.resolve();
      }
      const start = performance.now();
      return new Promise<void>((resolve) => {
        const step = (now: number): void => {
          const p = Math.min(1, (now - start) / TIP_DURATION_MS);
          this.drawScene(0, this.tipRotation(p), 0);
          this.drawBanner(info.banner, false);
          if (p < 1) {
            this.raf = requestAnimationFrame(step);
          } else {
            settle();
            resolve();
          }
        };
        this.raf = requestAnimationFrame(step);
      });
    }

    const finish = (): void => {
      this.drawScene(finalPos, 0, finalPos / WHEEL_ROLL_RADIUS_M);
      this.drawBanner(info.banner, info.finished);
      this.clock.textContent = view.finished && view.time_seconds != null ? `${view.time_seconds.toFixed(3)} s` : "—";
      this.setSpeed(frames.length ? frames[frames.length - 1].velocity : 0); // speed crossing the line
      this.canvas.dataset.animDone = "true";
    };

    if (reducedMotion() || frames.length <= 1 || lastT <= 0) {
      finish();
      return Promise.resolve();
    }

    const playbackS = Math.min(lastT, MAX_PLAYBACK_S);
    const start = performance.now();
    return new Promise<void>((resolve) => {
      const step = (now: number): void => {
        const p = Math.min(1, (now - start) / (playbackS * 1000));
        const simT = p * lastT;
        const pos = this.positionAt(frames, simT);
        this.drawScene(pos, 0, pos / WHEEL_ROLL_RADIUS_M);
        this.setSpeed(this.velocityAt(frames, simT)); // live mph as the car rolls
        if (view.finished) this.clock.textContent = `${simT.toFixed(3)} s`;
        if (p < 1) {
          this.raf = requestAnimationFrame(step);
        } else {
          finish();
          resolve();
        }
      };
      this.raf = requestAnimationFrame(step);
    });
  }
}
