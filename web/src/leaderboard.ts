// Local leaderboard — persists every finished race to localStorage, renders sorted fastest-first.
// All on-device: no network, no PII (AC-P2 parity with the garage).
import type { ControlState } from "./types";

const NAMESPACE = "pds.leaderboard.v1";
const MAX_ENTRIES = 200; // guard against unbounded growth

export interface LeaderboardEntry {
  id: string;       // timestamp string — unique enough for local use
  time_seconds: number;
  car: ControlState;
  at: string;       // ISO date of the run
}

interface LeaderboardFile {
  schemaVersion: number;
  entries: LeaderboardEntry[];
}

function readFile(): LeaderboardFile {
  try {
    const raw = localStorage.getItem(NAMESPACE);
    if (!raw) return { schemaVersion: 1, entries: [] };
    const parsed = JSON.parse(raw) as LeaderboardFile;
    if (!parsed || !Array.isArray(parsed.entries)) return { schemaVersion: 1, entries: [] };
    return parsed;
  } catch {
    return { schemaVersion: 1, entries: [] };
  }
}

function writeFile(file: LeaderboardFile): void {
  localStorage.setItem(NAMESPACE, JSON.stringify(file));
}

// Car description line: the two parameters that most affect time
function carSummary(car: ControlState): string {
  const wheels = car.wheels_count === 3 ? "3 wheels" : "4 wheels";
  const axle = car.axle_mu <= 0.10 ? "polished axles" : car.axle_mu <= 0.20 ? "good axles" : "avg axles";
  return `${car.mass_oz.toFixed(1)} oz · ${wheels} · ${axle}`;
}

export class Leaderboard {
  constructor(
    private readonly listEl: HTMLElement,
    private readonly emptyEl: HTMLElement,
    private readonly countEl: HTMLElement,
  ) {}

  record(time_seconds: number, car: ControlState): void {
    const file = readFile();
    const entry: LeaderboardEntry = {
      id: String(Date.now()),
      time_seconds,
      car,
      at: new Date().toISOString(),
    };
    file.entries.push(entry);
    // Keep the fastest MAX_ENTRIES runs (trim the slowest when over the cap)
    file.entries.sort((a, b) => a.time_seconds - b.time_seconds);
    if (file.entries.length > MAX_ENTRIES) file.entries.length = MAX_ENTRIES;
    writeFile(file);
  }

  entries(): LeaderboardEntry[] {
    return readFile().entries.slice().sort((a, b) => a.time_seconds - b.time_seconds);
  }

  clear(): void {
    localStorage.removeItem(NAMESPACE);
  }

  render(onLoad: (car: ControlState) => void): void {
    const entries = this.entries();
    this.listEl.replaceChildren();
    this.emptyEl.hidden = entries.length > 0;
    this.countEl.textContent = entries.length > 0 ? `${entries.length} run${entries.length === 1 ? "" : "s"}` : "";

    entries.forEach((entry, i) => {
      const li = document.createElement("li");
      li.className = "lb-row";
      if (i === 0) li.classList.add("lb-gold");
      else if (i === 1) li.classList.add("lb-silver");
      else if (i === 2) li.classList.add("lb-bronze");

      const rank = document.createElement("span");
      rank.className = "lb-rank";
      rank.textContent = i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : `#${i + 1}`;

      const time = document.createElement("span");
      time.className = "lb-time";
      time.textContent = `${entry.time_seconds.toFixed(3)} s`;

      const info = document.createElement("span");
      info.className = "lb-info";
      const date = new Date(entry.at);
      const dateStr = `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
      info.textContent = `${carSummary(entry.car)} · ${dateStr}`;

      const loadBtn = document.createElement("button");
      loadBtn.type = "button";
      loadBtn.className = "chip lb-load";
      loadBtn.textContent = "Load car";
      loadBtn.addEventListener("click", () => onLoad(entry.car));

      li.append(rank, time, info, loadBtn);
      this.listEl.appendChild(li);
    });
  }
}
