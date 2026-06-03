// WI12 — the local "garage": name/save/list/load/delete car designs in localStorage, fully
// on-device (PRD AC-S1/S2/S3; AC-P2 no PII, nothing leaves the browser). Each entry is the
// bridge's {state, design} JSON (the control-state to restore + the canonical CarDesign for
// re-validation on load), under a single versioned namespace for safe future migration.
const NAMESPACE = "pds.garage.v1";

interface GarageFile {
  schemaVersion: number;
  cars: Record<string, unknown>;
}

function readFile(): GarageFile {
  try {
    const raw = localStorage.getItem(NAMESPACE);
    if (!raw) return { schemaVersion: 1, cars: {} };
    const parsed = JSON.parse(raw) as GarageFile;
    if (!parsed || typeof parsed !== "object" || typeof parsed.cars !== "object") {
      return { schemaVersion: 1, cars: {} };
    }
    return parsed;
  } catch {
    return { schemaVersion: 1, cars: {} };
  }
}

function writeFile(file: GarageFile): void {
  localStorage.setItem(NAMESPACE, JSON.stringify(file));
}

export class Garage {
  constructor(
    private readonly listEl: HTMLUListElement,
    private readonly emptyEl: HTMLElement,
  ) {}

  names(): string[] {
    return Object.keys(readFile().cars).sort((a, b) => a.localeCompare(b));
  }

  /** Persist a garage entry (the bridge's {state, design} JSON string) under `name`. */
  save(name: string, entryJson: string): void {
    const file = readFile();
    file.cars[name] = JSON.parse(entryJson);
    writeFile(file);
  }

  /** The stored entry JSON for `name`, or null. Feed to fromGarageEntry to restore + validate. */
  load(name: string): string | null {
    const entry = readFile().cars[name];
    return entry === undefined ? null : JSON.stringify(entry);
  }

  remove(name: string): void {
    const file = readFile();
    delete file.cars[name];
    writeFile(file);
  }

  clear(): void {
    localStorage.removeItem(NAMESPACE);
  }

  /** Render the saved list with per-row Load/Delete buttons. */
  render(onLoad: (name: string) => void, onDelete: (name: string) => void): void {
    const names = this.names();
    this.listEl.replaceChildren();
    this.emptyEl.hidden = names.length > 0;
    for (const name of names) {
      const li = document.createElement("li");
      li.dataset.name = name;

      const label = document.createElement("span");
      label.className = "name";
      label.textContent = name;

      const loadBtn = document.createElement("button");
      loadBtn.type = "button";
      loadBtn.textContent = "Load";
      loadBtn.addEventListener("click", () => onLoad(name));

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "danger";
      delBtn.textContent = "Delete";
      delBtn.setAttribute("aria-label", `Delete ${name}`);
      delBtn.addEventListener("click", () => onDelete(name));

      li.append(label, loadBtn, delBtn);
      this.listEl.appendChild(li);
    }
  }
}
