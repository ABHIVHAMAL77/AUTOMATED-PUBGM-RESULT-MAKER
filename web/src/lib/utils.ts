import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Values that appear more than once, sorted. Used for rank/slot collisions. */
export function duplicateValues(values: number[]): number[] {
  const seen = new Set<number>();
  const dupes = new Set<number>();
  for (const value of values) {
    if (seen.has(value)) dupes.add(value);
    seen.add(value);
  }
  return [...dupes].sort((a, b) => a - b);
}

export function padPlayers(players: { name: string; kills: number }[] = []) {
  const out = players.map((p) => ({ name: p.name ?? "", kills: Number(p.kills ?? 0) }));
  while (out.length < 4) out.push({ name: "", kills: 0 });
  return out.slice(0, 4);
}

export function formatDate(iso: string): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.valueOf())
    ? iso
    : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
