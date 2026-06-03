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
  ground_clearance_in: number; // legality only (clears the rail), not physics
  alignment_rail: boolean; // rail-rider vs straight
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

// A legal, finishing default car (PRD AC-C2): light wheels, slick axles, sleek wedge body,
// rail-rider, weight at the limit, COM in the optimal rearward-but-stable zone.
export const DEFAULT_CAR: ControlState = {
  mass_oz: 5.0,
  com_in: 0.85,
  wheelbase_in: 4.375,
  wheels_count: 4,
  wheel_mass_oz: 0.09,
  axle_mu: 0.1,
  body_cd: 0.2,
  body_width_in: 1.75,
  body_height_in: 2.5,
  body_length_in: 7.0,
  ground_clearance_in: 0.4,
  alignment_rail: true,
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
  ground_clearance_in: { min: 0.0, max: 1.0, step: 0.05 },
} as const;
