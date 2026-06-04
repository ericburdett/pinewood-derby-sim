// WI07 — the JS ↔ Python bridge. Boots the vendored same-origin Pyodide runtime, loads
// the pure-Python engine (+ present.py translation layer) into its FS, and exposes typed
// wrappers. The boundary is JSON in / JSON out, so no PyProxy ever leaks to the UI (TRD §5).
// All physics + validation stay in Python; this file adds none (PRD AC-G1).
import type { ControlState, LegalityRule, RaceView, TrackInfo, ValidationResult } from "./types";

type StatusCb = (message: string) => void;

interface PyApi {
  race: (stateJson: string) => string;
  validate: (stateJson: string) => string;
  to_garage: (stateJson: string) => string;
  from_garage: (entryJson: string) => string;
  legality: (stateJson: string) => string;
  track_info: () => string;
}

// The Python-side web API: maps the UI control-state to a CarDesign (engine validation is
// the single source of truth), races it with a FIXED seed (determinism, PRD AC-R3/A6), and
// translates the result via present.py. Pure: no I/O, no new physics.
const WEBAPI_SRC = String.raw`
import json
import sys

if "/engine" not in sys.path:
    sys.path.insert(0, "/engine")

from pinewood_derby.car import Axle, BodyShape, CarDesign, Wheels
from pinewood_derby.engine import simulate
from pinewood_derby.present import from_dict, legality_report, present, to_dict, to_json
from pinewood_derby.track import STANDARD_TRACK
from pinewood_derby.units import Length, Mass

FIXED_SEED = 0
IN2_TO_M2 = 0.0254 ** 2  # square inches → square metres (for frontal area)
OUTER_IN = 0.595
INNER_IN = 0.37
AXLE_IN = 0.045


def _car_from_state(state):
    # Every lever is a continuous value straight from the UI sliders (within the engine's
    # valid domains); the engine's own constructors remain the single validation source.
    # Real body width × height drives the frontal area the engine's drag model consumes.
    wheels = Wheels(
        count_touching=int(state["wheels_count"]),
        wheel_mass=Mass.from_ounces(float(state["wheel_mass_oz"])),
        outer_radius=Length.from_inches(OUTER_IN),
        inner_radius=Length.from_inches(INNER_IN),
        axle_radius=Length.from_inches(AXLE_IN),
    )
    frontal_area = float(state["body_width_in"]) * float(state["body_height_in"]) * IN2_TO_M2
    body = BodyShape(drag_coefficient=float(state["body_cd"]), frontal_area=frontal_area)
    axle = Axle(friction_coefficient=float(state["axle_mu"]))
    return CarDesign(
        mass=Mass.from_ounces(float(state["mass_oz"])),
        com_ahead_of_rear_axle=Length.from_inches(float(state["com_in"])),
        wheelbase=Length.from_inches(float(state["wheelbase_in"])),
        wheels=wheels,
        body=body,
        axle=axle,
        steer_angle_deg=float(state["steer_angle_deg"]),
    )


def validate(state_json):
    try:
        _car_from_state(json.loads(state_json))
        return json.dumps({"ok": True})
    except (ValueError, KeyError, TypeError) as exc:
        return json.dumps({"ok": False, "message": str(exc)})


def race(state_json):
    car = _car_from_state(json.loads(state_json))
    result = simulate(car, STANDARD_TRACK, dt=1e-3, seed=FIXED_SEED)
    return json.dumps(to_json(present(result, car)))


def to_garage(state_json):
    state = json.loads(state_json)
    car = _car_from_state(state)  # raises on an invalid design before we persist it
    return json.dumps({"state": state, "design": to_dict(car)})


def from_garage(entry_json):
    entry = json.loads(entry_json)
    from_dict(entry["design"])  # re-validate through the engine constructors (raises ValueError)
    return json.dumps(entry["state"])


def legality(state_json):
    s = json.loads(state_json)
    return json.dumps(legality_report(
        mass_oz=float(s["mass_oz"]),
        width_in=float(s["body_width_in"]),
        height_in=float(s["body_height_in"]),
        length_in=float(s["body_length_in"]),
    ))


def track_info():
    ramp = STANDARD_TRACK.ramp_length.m
    flat = STANDARD_TRACK.flat_length.m
    return json.dumps({
        "ramp_length_m": ramp,
        "ramp_angle_rad": STANDARD_TRACK.ramp_angle.radians,
        "flat_length_m": flat,
        "total_length_m": ramp + flat,
    })
`;

let api: PyApi | null = null;
let bootPromise: Promise<void> | null = null;

async function boot(onStatus: StatusCb): Promise<void> {
  const base = import.meta.env.BASE_URL;
  const indexURL = new URL(`${base}pyodide/`, window.location.href).href;
  onStatus("Loading the Python runtime…");
  // Anchor the dynamic import to the document URL (indexURL), NOT a base-relative
  // specifier: a bare `./pyodide/...` import resolves against the bundled module's
  // location (/assets/), producing /assets/pyodide/ under a Pages subpath.
  const mod = await import(/* @vite-ignore */ `${indexURL}pyodide.mjs`);
  const pyodide = await mod.loadPyodide({ indexURL });

  onStatus("Loading the physics engine…");
  const resp = await fetch(`${base}pinewood_derby.zip`);
  if (!resp.ok) throw new Error(`could not load engine bundle (${resp.status})`);
  const buf = await resp.arrayBuffer();
  pyodide.unpackArchive(buf, "zip", { extractDir: "/engine" });

  pyodide.runPython(WEBAPI_SRC);
  const g = pyodide.globals;
  api = {
    race: g.get("race"),
    validate: g.get("validate"),
    to_garage: g.get("to_garage"),
    from_garage: g.get("from_garage"),
    legality: g.get("legality"),
    track_info: g.get("track_info"),
  };
  onStatus("Ready");
}

/** Boot the engine in-browser. Idempotent; safe to await from multiple call sites. */
export function initBridge(onStatus: StatusCb = () => {}): Promise<void> {
  if (!bootPromise) bootPromise = boot(onStatus);
  return bootPromise;
}

export function isReady(): boolean {
  return api !== null;
}

function ensure(): PyApi {
  if (!api) throw new Error("bridge not initialised — await initBridge() first");
  return api;
}

/** Run a race: build the design in Python, simulate (fixed seed), translate to a RaceView. */
export function race(state: ControlState): RaceView {
  return JSON.parse(ensure().race(JSON.stringify(state))) as RaceView;
}

/** Validate a design via the engine's own constructors; never throws for invalid input. */
export function validate(state: ControlState): ValidationResult {
  return JSON.parse(ensure().validate(JSON.stringify(state))) as ValidationResult;
}

/** Serialize a design for the garage: a versioned {state, design} JSON string. */
export function toGarageEntry(state: ControlState): string {
  return ensure().to_garage(JSON.stringify(state));
}

/** Restore control-state from a garage entry, re-validating the stored design (throws if bad). */
export function fromGarageEntry(entryJson: string): ControlState {
  return JSON.parse(ensure().from_garage(entryJson)) as ControlState;
}

/** Standard-track geometry, for the animator's side-view (read-only; no physics). */
export function trackInfo(): TrackInfo {
  return JSON.parse(ensure().track_info()) as TrackInfo;
}

/** The legality-inspection checklist for the current design (pure rule checks). */
export function legalityReport(state: ControlState): LegalityRule[] {
  return JSON.parse(ensure().legality(JSON.stringify(state))) as LegalityRule[];
}
