// Feature 0005 — Race ⇄ Learn tab switching. The Race view (#app) is the simulator/test; the
// Learn view (#learn) is static educational content. Learn works immediately (no engine needed);
// the Race view only appears once the in-browser engine has booted (setReady). Pure DOM toggling.

function el<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element #${id}`);
  return node as T;
}

export interface Tabs {
  /** Mark the simulator ready; the Race view shows only after this AND while the Race tab is active. */
  setReady(ready: boolean): void;
}

export function initTabs(): Tabs {
  const tabRace = el<HTMLButtonElement>("tab-race");
  const tabLearn = el<HTMLButtonElement>("tab-learn");
  const app = el("app");
  const learn = el("learn");
  const raceBtn = el<HTMLButtonElement>("race");

  let ready = false;
  let active: "race" | "learn" = "race";

  function apply(): void {
    const onRace = active === "race";
    app.hidden = !(onRace && ready); // the simulator needs the engine; Learn never does
    learn.hidden = onRace;
    raceBtn.hidden = !onRace; // the Race button is meaningless on the Learn tab
    tabRace.classList.toggle("active", onRace);
    tabLearn.classList.toggle("active", !onRace);
    tabRace.setAttribute("aria-selected", String(onRace));
    tabLearn.setAttribute("aria-selected", String(!onRace));
  }

  tabRace.addEventListener("click", () => {
    active = "race";
    apply();
  });
  tabLearn.addEventListener("click", () => {
    active = "learn";
    apply();
  });

  apply();
  return {
    setReady(value: boolean): void {
      ready = value;
      apply();
    },
  };
}
