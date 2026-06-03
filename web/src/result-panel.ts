// WI10 — render the kid-facing RaceView: headline, time (finishers only — AC-R2 shows no
// numeric time for a non-finish), the ranked "where did your speed go?" breakdown
// (largest-first, AC-X1), the dominant-factor "why" (AC-X2), and priority-ordered tips
// (AC-X4). Every bar carries a text label + percentage, never color alone (AC-A2). It only
// renders what present.py emits — no jargon is introduced here (AC-X3).
import type { RaceView } from "./types";

function el<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element #${id}`);
  return node as T;
}

export function renderResult(view: RaceView): void {
  el("result-headline").textContent = view.headline;

  const time = el<HTMLParagraphElement>("result-time");
  if (view.finished && view.time_seconds != null) {
    time.textContent = `Finish time: ${view.time_seconds.toFixed(3)} seconds`;
    time.hidden = false;
  } else {
    time.textContent = "";
    time.hidden = true; // AC-R2: a non-finish shows no numeric time
  }

  const wrap = el<HTMLDivElement>("breakdown-wrap");
  const list = el<HTMLUListElement>("breakdown");
  list.replaceChildren();
  if (view.breakdown.length > 0) {
    wrap.hidden = false;
    for (const bar of view.breakdown) {
      const li = document.createElement("li");
      const pct = Math.round(bar.share * 100);
      const row = document.createElement("div");
      row.className = "bar-row";
      row.dataset.key = bar.key;
      row.dataset.share = String(bar.share);

      const label = document.createElement("span");
      label.className = "bar-label";
      label.textContent = bar.label;

      const track = document.createElement("span");
      track.className = "bar-track";
      const fill = document.createElement("span");
      fill.className = bar.is_kept ? "bar-fill kept" : "bar-fill";
      fill.style.width = `${pct}%`;
      track.appendChild(fill);

      const pctText = document.createElement("span");
      pctText.className = "bar-pct";
      pctText.textContent = `${pct}%`;

      row.append(label, track, pctText);
      li.appendChild(row);
      list.appendChild(li);
    }
  } else {
    wrap.hidden = true;
  }

  const why = el<HTMLParagraphElement>("why");
  if (view.why) {
    why.textContent = view.why;
    why.hidden = false;
  } else {
    why.hidden = true;
  }

  const tipsWrap = el<HTMLDivElement>("tips-wrap");
  const tips = el<HTMLUListElement>("tips");
  tips.replaceChildren();
  if (view.tips.length > 0) {
    tipsWrap.hidden = false;
    for (const tip of view.tips) {
      const li = document.createElement("li");
      li.textContent = tip;
      tips.appendChild(li);
    }
  } else {
    tipsWrap.hidden = true;
  }
}
