/**
 * Draft persistence for in-progress match rows.
 *
 * OCR takes 10–20 seconds and the review table can hold twenty teams of
 * hand-checked numbers. Previously a refresh — or an accidental navigation —
 * threw all of it away, because the entire client state was one module-global
 * object. Drafts are keyed per match so switching match numbers doesn't clobber
 * the one you were working on.
 */

import type { MatchRow } from "./types";

const PREFIX = "ec-pubgm:draft:";
const MAX_AGE_MS = 1000 * 60 * 60 * 24 * 3;

interface Draft {
  savedAt: number;
  map: string;
  rows: MatchRow[];
}

const key = (matchNumber: number) => `${PREFIX}${matchNumber}`;

export function saveDraft(matchNumber: number, map: string, rows: MatchRow[]) {
  try {
    const payload: Draft = { savedAt: Date.now(), map, rows };
    localStorage.setItem(key(matchNumber), JSON.stringify(payload));
  } catch {
    // A full or disabled localStorage must never break the review table.
  }
}

export function loadDraft(matchNumber: number): Draft | null {
  try {
    const raw = localStorage.getItem(key(matchNumber));
    if (!raw) return null;
    const draft = JSON.parse(raw) as Draft;
    if (!Array.isArray(draft.rows) || Date.now() - draft.savedAt > MAX_AGE_MS) {
      localStorage.removeItem(key(matchNumber));
      return null;
    }
    return draft;
  } catch {
    return null;
  }
}

export function clearDraft(matchNumber: number) {
  try {
    localStorage.removeItem(key(matchNumber));
  } catch {
    /* nothing to clean up */
  }
}
