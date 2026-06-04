// The control surface the builder edits, mapped to a CarDesign in Python (the engine's
// validation is the single source of truth — PRD AC-C1; TRD §5). Plain JSON so it crosses
// the bridge and persists to the garage as-is.
export interface ControlState {
  mass_oz: number; // total car weight
  com_in: number; // weight placement: inches ahead of the rear axle
  wheelbase_in: number; // distance between the axles
  wheels_count: 3 | 4; // wheels touching the track
  wheel_mass_oz: number; // per-wheel weight (lighter spins up faster)
  axle_mu: number; // axle friction: lower = slicker = faster
  body_cd: number; // body taper: lower = sleeker = faster
  body_width_in: number; // body width → frontal area → drag (also a legality rule)
  body_height_in: number; // body height → frontal area → drag (also a legality rule)
  body_length_in: number; // legality only (fit), not physics
  steer_angle_deg: number; // alignment: 0° ping-pongs → ~3° rail-rider sweet spot → more scrubs
}

// One legality-inspection row (mirrors present.legality_report()).
export interface LegalityRule {
  rule: string;
  ok: boolean;
  value: string;
  requirement: string;
}

// The kid-facing view-model the Python present.py layer emits (mirrors to_json()).
export type Outcome = "finished" | "tipped" | "stalled";

export interface LossBar {
  key: string;
  label: string;
  share: number;
  is_kept: boolean;
}

export interface FrameDTO {
  t: number;
  position: number;
  velocity: number;
  angle: number;
}

export interface RaceView {
  finished: boolean;
  outcome: Outcome;
  time_seconds: number | null;
  stopped_distance_frac: number | null;
  legal_weight: boolean;
  headline: string;
  breakdown: LossBar[];
  why: string;
  tips: string[];
  trajectory: FrameDTO[];
}

export interface ValidationResult {
  ok: boolean;
  message?: string;
}

export interface TrackInfo {
  ramp_length_m: number;
  ramp_angle_rad: number;
  flat_length_m: number;
  total_length_m: number;
}

// A neutral starter car with EVERY slider parked at the middle of its range (per product
// decision — no pre-optimized defaults, so the kid tunes every lever themselves). Each value
// is the midpoint of the matching RANGES entry, snapped to the slider's step. Still legal and
// finishing, just deliberately un-tuned.
export const DEFAULT_CAR: ControlState = {
  mass_oz: 4.0, // mid of 1.0–7.0
  com_in: 1.3, // mid of 0.10–2.50
  wheelbase_in: 4.25, // mid of 3.5–5.0
  wheels_count: 4,
  wheel_mass_oz: 0.14, // mid of 0.07–0.20 (0.135 → 0.14 on the 0.01 step)
  axle_mu: 0.23, // mid of 0.05–0.40 (0.225 → 0.23 on the 0.01 step)
  body_cd: 0.5, // mid of 0.15–0.85
  body_width_in: 2.0, // mid of 1.0–3.0
  body_height_in: 2.3, // mid of 0.5–4.0 (2.25 → 2.3 on the 0.1 step)
  body_length_in: 6.0, // mid of 4.0–8.0
  steer_angle_deg: 5.0, // mid of 0–10
};

export const LEGAL_WEIGHT_OZ = 5.0;

// Slider bounds for the continuous knobs. Body width/height feed the engine's drag
// (frontal area); ranges intentionally extend past the legal limits so a kid can build —
// and the inspection panel can flag — an illegal car. (Verified: even a legal-max body
// keeps aero the smallest lever, AC-ED1.)
export const RANGES = {
  mass_oz: { min: 1.0, max: 7.0, step: 0.1 },
  com_in: { min: 0.1, max: 2.5, step: 0.05 },
  wheelbase_in: { min: 3.5, max: 5.0, step: 0.125 },
  wheel_mass_oz: { min: 0.07, max: 0.2, step: 0.01 },
  axle_mu: { min: 0.05, max: 0.4, step: 0.01 },
  body_cd: { min: 0.15, max: 0.85, step: 0.05 },
  body_width_in: { min: 1.0, max: 3.0, step: 0.05 },
  body_height_in: { min: 0.5, max: 4.0, step: 0.1 },
  body_length_in: { min: 4.0, max: 8.0, step: 0.25 },
  steer_angle_deg: { min: 0.0, max: 10.0, step: 0.25 },
} as const;
