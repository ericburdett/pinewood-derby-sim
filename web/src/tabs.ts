// Feature 0005 — Race ⇄ Learn ⇄ Board tab switching. The Race view (#app) is the simulator;
// the Learn view (#learn) is static educational content; the Board view (#board) shows the
// local leaderboard. Learn and Board work immediately (no engine needed); Race is gated on
// setReady. Pure DOM toggling.

function el<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element #${id}`);
  return node as T;
}

type ActiveTab = "race" | "learn" | "board";

export interface Tabs {
  /** Mark the simulator ready; the Race view shows only after this AND while the Race tab is active. */
  setReady(ready: boolean): void;
  /** Navigate to a specific tab programmatically (e.g. after loading a car from the board). */
  switchTo(tab: ActiveTab): void;
}

export function initTabs(): Tabs {
  const tabRace = el<HTMLButtonElement>("tab-race");
  const tabLearn = el<HTMLButtonElement>("tab-learn");
  const tabBoard = el<HTMLButtonElement>("tab-board");
  const app = el("app");
  const learn = el("learn");
  const board = el("board");
  const raceBtn = el<HTMLButtonElement>("race");

  let ready = false;
  let active: ActiveTab = "race";

  function apply(): void {
    app.hidden = !(active === "race" && ready);
    learn.hidden = active !== "learn";
    board.hidden = active !== "board";
    raceBtn.hidden = active !== "race";

    for (const [btn, key] of [
      [tabRace, "race"],
      [tabLearn, "learn"],
      [tabBoard, "board"],
    ] as [HTMLButtonElement, ActiveTab][]) {
      btn.classList.toggle("active", active === key);
      btn.setAttribute("aria-selected", String(active === key));
    }
  }

  tabRace.addEventListener("click", () => { active = "race"; apply(); });
  tabLearn.addEventListener("click", () => { active = "learn"; apply(); });
  tabBoard.addEventListener("click", () => { active = "board"; apply(); });

  apply();
  return {
    setReady(value: boolean): void {
      ready = value;
      apply();
    },
    switchTo(tab: ActiveTab): void {
      active = tab;
      apply();
    },
  };
}
