// WI08 — builder controls <-> ControlState. The sliders expose the engine's continuous knobs
// directly (weight, placement, wheelbase, wheel weight, axle prep, body shape) within the
// engine's valid domains, so the UI pre-constrains inputs (PRD AC-C1; the Python validation is
// the backstop). The displayed weight updates live with a legal/over-limit badge that is never
// color-only (icon + text — AC-C2/AC-C3), and an over-limit car stays raceable. Axle/body
// sliders show a kid-friendly word, not a raw coefficient (no jargon — AC-X3).
import { type ControlState, LEGAL_WEIGHT_OZ } from "./types";

// Wheels must sit at least this far inside the body (front + rear), so the wheelbase can
// never be longer than the car. The two sliders are coupled to keep this true.
const WHEEL_OVERHANG_IN = 0.5;

function el<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element #${id}`);
  return node as T;
}

function axleWord(mu: number): string {
  if (mu <= 0.12) return "Slick";
  if (mu <= 0.22) return "Smooth";
  if (mu <= 0.32) return "Average";
  return "Rough";
}

function bodyWord(cd: number): string {
  if (cd <= 0.25) return "Sleek wedge";
  if (cd <= 0.5) return "Rounded";
  return "Blocky";
}

// Steer angle → just the raw value. No "rail-rider / ping-pongs / over-steered" descriptor: the
// Race tab is a test, so we don't hint at the sweet spot while a kid plays with the slider.
export function steerWord(deg: number): string {
  return `${deg.toFixed(1)}°`;
}

export class Controls {
  private readonly weight = el<HTMLInputElement>("weight");
  private readonly weightDisplay = el<HTMLOutputElement>("weight-display");
  private readonly weightLegal = el<HTMLParagraphElement>("weight-legal");
  private readonly placement = el<HTMLInputElement>("placement");
  private readonly placementDisplay = el<HTMLOutputElement>("placement-display");
  private readonly wheelbase = el<HTMLInputElement>("wheelbase");
  private readonly wheelbaseDisplay = el<HTMLOutputElement>("wheelbase-display");
  private readonly wheelMass = el<HTMLInputElement>("wheel-mass");
  private readonly wheelMassDisplay = el<HTMLOutputElement>("wheel-mass-display");
  private readonly axleMu = el<HTMLInputElement>("axle-mu");
  private readonly axleMuDisplay = el<HTMLOutputElement>("axle-mu-display");
  private readonly bodyCd = el<HTMLInputElement>("body-cd");
  private readonly bodyCdDisplay = el<HTMLOutputElement>("body-cd-display");
  private readonly bodyWidth = el<HTMLInputElement>("body-width");
  private readonly bodyWidthDisplay = el<HTMLOutputElement>("body-width-display");
  private readonly bodyHeight = el<HTMLInputElement>("body-height");
  private readonly bodyHeightDisplay = el<HTMLOutputElement>("body-height-display");
  private readonly bodyLength = el<HTMLInputElement>("body-length");
  private readonly bodyLengthDisplay = el<HTMLOutputElement>("body-length-display");
  private readonly steerAngle = el<HTMLInputElement>("steer-angle");
  private readonly steerAngleDisplay = el<HTMLOutputElement>("steer-angle-display");
  private readonly form = el<HTMLFormElement>("builder");

  /** Wire live displays. `onInput` fires whenever any control changes. */
  init(onInput: () => void): void {
    this.form.addEventListener("input", () => {
      this.syncDisplays();
      onInput();
    });
    this.syncDisplays();
  }

  private wheelsCount(): 3 | 4 {
    const checked = this.form.querySelector<HTMLInputElement>('input[name="wheels-count"]:checked');
    return checked && checked.value === "3" ? 3 : 4;
  }

  read(): ControlState {
    return {
      mass_oz: Number(this.weight.value),
      com_in: Number(this.placement.value),
      wheelbase_in: Number(this.wheelbase.value),
      wheels_count: this.wheelsCount(),
      wheel_mass_oz: Number(this.wheelMass.value),
      axle_mu: Number(this.axleMu.value),
      body_cd: Number(this.bodyCd.value),
      body_width_in: Number(this.bodyWidth.value),
      body_height_in: Number(this.bodyHeight.value),
      body_length_in: Number(this.bodyLength.value),
      steer_angle_deg: Number(this.steerAngle.value),
    };
  }

  /** Restore every control from a saved state (PRD AC-S2). */
  apply(state: ControlState): void {
    this.weight.value = String(state.mass_oz);
    this.placement.value = String(state.com_in);
    this.wheelbase.value = String(state.wheelbase_in);
    const radio = this.form.querySelector<HTMLInputElement>(
      `input[name="wheels-count"][value="${state.wheels_count}"]`,
    );
    if (radio) radio.checked = true;
    this.wheelMass.value = String(state.wheel_mass_oz);
    this.axleMu.value = String(state.axle_mu);
    this.bodyCd.value = String(state.body_cd);
    this.bodyWidth.value = String(state.body_width_in);
    this.bodyHeight.value = String(state.body_height_in);
    this.bodyLength.value = String(state.body_length_in);
    this.steerAngle.value = String(state.steer_angle_deg);
    this.syncDisplays();
  }

  /** Keep the wheelbase inside the body length so the axles never fall outside the car.
   *  We clamp the VALUES (not the sliders' min/max — changing those would knock a value off
   *  its step grid). Dragging the wheelbase past the body caps it at (length − overhang);
   *  shortening the body past the wheelbase pulls the wheelbase down with it. */
  private enforceFit(): void {
    const maxWheelbase = Number(this.bodyLength.value) - WHEEL_OVERHANG_IN;
    if (Number(this.wheelbase.value) > maxWheelbase) {
      this.wheelbase.value = String(maxWheelbase);
    }
    const minLength = Number(this.wheelbase.value) + WHEEL_OVERHANG_IN;
    if (Number(this.bodyLength.value) < minLength) {
      this.bodyLength.value = String(minLength);
    }
  }

  private syncDisplays(): void {
    this.enforceFit();
    const mass = Number(this.weight.value);
    this.weightDisplay.textContent = mass.toFixed(1);
    this.placementDisplay.textContent = Number(this.placement.value).toFixed(2);
    this.wheelbaseDisplay.textContent = Number(this.wheelbase.value).toFixed(2);
    this.wheelMassDisplay.textContent = Number(this.wheelMass.value).toFixed(2);
    this.axleMuDisplay.textContent = axleWord(Number(this.axleMu.value));
    this.bodyCdDisplay.textContent = bodyWord(Number(this.bodyCd.value));
    this.bodyWidthDisplay.textContent = Number(this.bodyWidth.value).toFixed(2);
    this.bodyHeightDisplay.textContent = Number(this.bodyHeight.value).toFixed(1);
    this.bodyLengthDisplay.textContent = Number(this.bodyLength.value).toFixed(2);
    this.steerAngleDisplay.textContent = steerWord(Number(this.steerAngle.value));
    // Icon + text (never color-only) — AC-A2.
    if (mass <= LEGAL_WEIGHT_OZ + 1e-9) {
      this.weightLegal.textContent = `✓ Legal — within the ${LEGAL_WEIGHT_OZ.toFixed(1)} oz limit`;
      this.weightLegal.className = "badge legal";
    } else {
      this.weightLegal.textContent = `⚠ Over the ${LEGAL_WEIGHT_OZ.toFixed(1)} oz limit (you can still race it)`;
      this.weightLegal.className = "badge over";
    }
  }
}
