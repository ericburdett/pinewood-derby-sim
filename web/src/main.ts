// App bootstrap — wires the proven bridge (WI07) to the builder controls (WI08), the canvas
// race animation (WI09/WI11), the result panel (WI10), and the garage (WI12), and registers
// the offline service worker (WI13). All physics/validation stays in Python (AC-G1).
import { RaceAnimator } from "./animator";
import { CarPreview } from "./car-preview";
import { Controls } from "./controls";
import { Garage } from "./garage";
import {
  fromGarageEntry,
  initBridge,
  legalityReport,
  race,
  toGarageEntry,
  trackInfo,
  validate,
} from "./pyodide-bridge";
import { renderResult } from "./result-panel";
import { initTabs } from "./tabs";
import { DEFAULT_CAR } from "./types";

declare global {
  interface Window {
    __derby?: Record<string, unknown>;
  }
}

function el<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element #${id}`);
  return node as T;
}

function registerServiceWorker(): void {
  if (!("serviceWorker" in navigator)) return;
  // Same-origin worker; precaches on first load so subsequent loads work offline (AC-P3).
  navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(() => {
    /* offline support is progressive — a failed registration must not break the app */
  });
}

async function main(): Promise<void> {
  const status = el("status");
  registerServiceWorker();
  // Tabs work immediately — the Learn view is static, so it's usable while the engine boots
  // (and even if booting fails). The Race view is gated on readiness via setReady below.
  const tabs = initTabs();

  try {
    await initBridge((msg) => {
      status.textContent = msg;
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    status.textContent = `Could not load the simulator: ${message} — the Learn tab still works.`;
    window.__derby = { ready: false, error: message };
    return;
  }

  status.textContent = "Ready";
  tabs.setReady(true);
  el<HTMLButtonElement>("race").disabled = false;

  const controls = new Controls();
  const animator = new RaceAnimator(
    el<HTMLCanvasElement>("track-canvas"),
    trackInfo(),
    el<HTMLOutputElement>("clock"),
    el<HTMLOutputElement>("mph"),
  );
  const preview = new CarPreview(el<HTMLCanvasElement>("car-preview"));
  const garage = new Garage(el<HTMLUListElement>("garage-list"), el("garage-empty"));
  const controlError = el<HTMLParagraphElement>("control-error");
  const stage = el("stage"); // data-raced flips to "true" on finish → reveal telemetry below
  const garageModal = el<HTMLDialogElement>("garage-modal");

  const inspectionList = el<HTMLUListElement>("inspection");
  function renderInspection(): void {
    inspectionList.replaceChildren();
    let rules: ReturnType<typeof legalityReport>;
    try {
      rules = legalityReport(controls.read());
    } catch (err) {
      // A mismatched/stale engine bundle (e.g. an old vendored zip) must NEVER brick setup:
      // throwing here would abort main() before the Race button's submit handler is wired,
      // leaving the form free to reload the page on every Race press (the GH Pages bug).
      console.error("inspection unavailable:", err);
      return;
    }
    for (const r of rules) {
      const li = document.createElement("li");
      li.className = r.ok ? "ok" : "bad";
      li.dataset.rule = r.rule;
      li.dataset.ok = String(r.ok);
      const icon = document.createElement("span");
      icon.className = "ins-icon";
      icon.textContent = r.ok ? "✓" : "✗";
      icon.setAttribute("aria-hidden", "true");
      const name = document.createElement("span");
      name.className = "ins-name";
      name.textContent = `${r.rule}: ${r.value}`;
      const detail = document.createElement("span");
      detail.className = "ins-detail";
      detail.textContent = r.ok ? "OK" : `too much — ${r.requirement}`;
      li.append(icon, name, detail);
      inspectionList.appendChild(li);
    }
  }

  // Redraw the car preview, the inspection checklist, and the start-line car whenever the
  // design changes — from a slider OR from loading a saved car (so Load refreshes the
  // visuals, not just the slider positions).
  function syncDesignViews(): void {
    const s = controls.read();
    stage.dataset.raced = "false"; // editing the design hides the stale telemetry again
    preview.render(s);
    renderInspection();
    animator.renderIdle(s); // the always-visible race box shows the staged car you're tuning
  }
  controls.init(syncDesignViews);
  controls.apply(DEFAULT_CAR); // AC-C2: a legal, finishing default car, immediately raceable
  syncDesignViews();

  function showError(message: string | undefined): void {
    controlError.textContent = message ?? "That design isn't buildable — adjust a control.";
    controlError.hidden = false;
  }
  function clearError(): void {
    controlError.hidden = true;
    controlError.textContent = "";
  }

  function doRace(): void {
    const state = controls.read();
    // AC-C1 backstop: the engine's own validation is the source of truth. The control domains
    // pre-constrain inputs so this should pass, but if not we surface a message — never throw.
    const verdict = validate(state);
    if (!verdict.ok) {
      showError(verdict.message);
      return;
    }
    clearError();
    let view: ReturnType<typeof race>;
    try {
      view = race(state);
    } catch (err) {
      console.error("race failed:", err);
      showError("The simulator couldn't run this design — try reloading the page.");
      return;
    }
    renderResult(view);
    // Hide any stale telemetry, animate the run in the always-visible race box, then reveal
    // the telemetry below it once the animation finishes (animator.play handles reduced motion).
    stage.dataset.raced = "false";
    void animator.play(view, state).then(() => {
      stage.dataset.raced = "true";
    });
  }

  el<HTMLFormElement>("builder").addEventListener("submit", (event) => {
    event.preventDefault();
    doRace();
  });

  function refreshGarage(): void {
    garage.render(
      (name) => {
        const entry = garage.load(name);
        if (!entry) return;
        try {
          controls.apply(fromGarageEntry(entry)); // restores every control (AC-S2)
          syncDesignViews(); // refresh preview + inspection + track to the loaded design
          clearError();
          garageModal.close(); // loaded — close the modal so the car is visible
        } catch {
          showError("That saved car couldn't be loaded.");
        }
      },
      (name) => {
        garage.remove(name);
        refreshGarage();
      },
    );
  }

  el("save").addEventListener("click", () => {
    const nameInput = el<HTMLInputElement>("garage-name");
    const name = nameInput.value.trim() || "My car";
    garage.save(name, toGarageEntry(controls.read()));
    nameInput.value = "";
    refreshGarage();
  });

  el("clear-garage").addEventListener("click", () => {
    garage.clear();
    refreshGarage();
  });

  // Garage modal: the Save/Load chips on the car open it; ✕, Esc, or a backdrop click close it.
  el("open-save").addEventListener("click", () => {
    if (!garageModal.open) garageModal.showModal();
    el<HTMLInputElement>("garage-name").focus();
  });
  el("open-load").addEventListener("click", () => {
    if (!garageModal.open) garageModal.showModal();
  });
  el("garage-close").addEventListener("click", () => garageModal.close());
  garageModal.addEventListener("click", (event) => {
    if (event.target === garageModal) garageModal.close(); // click outside the card
  });

  refreshGarage();

  // Low-level handle for the headless specs (mirrors the bridge; not used by the UI itself).
  window.__derby = { ready: true, default: DEFAULT_CAR, race, validate, trackInfo };
}

void main();
