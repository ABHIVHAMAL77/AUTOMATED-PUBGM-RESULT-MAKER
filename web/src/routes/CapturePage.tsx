import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Dashboard, MatchRow } from "@/lib/types";
import { padPlayers } from "@/lib/utils";
import { clearDraft, loadDraft, saveDraft } from "@/lib/storage";
import { Dropzone, type Shot } from "@/components/Dropzone";
import { ReviewTable, findIssues } from "@/components/ReviewTable";
import { useToast } from "@/components/Toasts";
import {
  Badge,
  Button,
  EmptyState,
  Panel,
  Skeleton,
} from "@/components/ui/primitives";

const MAPS = ["Erangel", "Miramar", "Sanhok", "Vikendi", "Rondo", "Karakin", "Livik"];

/**
 * Blank rows for typing a match in by hand, pre-filled from the event roster
 * so slots and team names are already right and only the numbers need typing.
 */
function seedRows(dashboard: Dashboard): MatchRow[] {
  const teams = [...(dashboard.event.teams ?? [])].sort((a, b) => a.teamId - b.teamId);
  if (!teams.length) {
    return Array.from({ length: 16 }, (_, index) => ({
      rank: index + 1,
      slot: index + 1,
      teamName: "",
      players: padPlayers(),
    }));
  }
  return teams.map((team, index) => ({
    rank: index + 1,
    slot: team.teamId,
    teamName: team.teamName || team.shortName || "",
    players: padPlayers((team.players ?? []).map((name) => ({ name, kills: 0 }))),
  }));
}

export default function CapturePage() {
  const queryClient = useQueryClient();
  const { push } = useToast();

  const { data: dashboard, isPending } = useQuery<Dashboard>({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });

  // One dropzone per step. These were a single shared list, which left the
  // lobby step with no upload box of its own: you had to drop lobby
  // screenshots into the box labelled "match results" and then press a button
  // in the panel above it.
  const [rosterShots, setRosterShots] = React.useState<Shot[]>([]);
  const [resultShots, setResultShots] = React.useState<Shot[]>([]);
  const [rows, setRows] = React.useState<MatchRow[]>([]);
  const [matchNumber, setMatchNumber] = React.useState<number | null>(null);
  const [map, setMap] = React.useState("Erangel");
  const [activeRow, setActiveRow] = React.useState<number | null>(null);
  const [problems, setProblems] = React.useState<string[]>([]);
  const [restored, setRestored] = React.useState(false);

  const effectiveMatch = matchNumber ?? dashboard?.nextMatch ?? 1;

  // Restore an in-progress match once the match number is known. A refresh
  // during a 20-second OCR run used to lose the whole table.
  React.useEffect(() => {
    if (!dashboard || matchNumber !== null) return;
    setMatchNumber(dashboard.nextMatch);
    const draft = loadDraft(dashboard.nextMatch);
    if (draft?.rows.length) {
      setRows(draft.rows);
      setMap(draft.map || "Erangel");
      setRestored(true);
    }
  }, [dashboard, matchNumber]);

  React.useEffect(() => {
    if (rows.length) saveDraft(effectiveMatch, map, rows);
  }, [rows, map, effectiveMatch]);

  const issues = React.useMemo(() => findIssues(rows), [rows]);

  const readRoster = useMutation({
    mutationFn: (files: File[]) => api.ocrRoster(files),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["event"] });
      push(
        `Read ${data.cards.length} lobby card(s); ${data.applied} slot(s) applied to the event roster.`,
        data.applied ? "success" : "info",
      );
      if (data.errors.length) push(data.errors.join(" · "), "error");
      setRosterShots([]);
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  const readResults = useMutation({
    mutationFn: (files: File[]) => api.ocrResults(files),
    onSuccess: (data) => {
      setRows(
        data.rows.map((row) => ({
          rank: row.rank,
          slot: row.slot,
          teamName: row.teamName,
          players: padPlayers(row.players),
          confidence: row.confidence,
          confidenceReasons: row.confidenceReasons,
          needsReview: row.needsReview,
          source: row.source,
        })),
      );
      setProblems(data.problems);
      setRestored(false);
      push(`Read ${data.rows.length} team(s) with the ${data.engineUsed} engine.`, "success");
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  const save = useMutation({
    mutationFn: () => api.saveMatch(effectiveMatch, map, rows),
    onSuccess: (data) => {
      queryClient.setQueryData(["dashboard"], data);
      clearDraft(effectiveMatch);
      setRows([]);
      setProblems([]);
      setResultShots([]);
      setMatchNumber(data.nextMatch);
      push(`Match ${effectiveMatch} saved. Sheet and graphics updated.`, "success");
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  if (isPending || !dashboard) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-40" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  const busy = readRoster.isPending || readResults.isPending;
  const blocked = issues.byRow.size > 0 || rows.length === 0;
  const activeShot = resultShots[0];
  const rosterCount = dashboard.event.teams?.length ?? 0;

  return (
    <div className="space-y-6">
      <Panel
        title="Step 1 · Before the match — lobby slot screenshots"
        description="Open the Observe lobby (the grid of numbered team cards) and screenshot every page. The app reads each slot number and its player names so result cards can be matched to the right team automatically."
        actions={
          <>
            <Button
              variant={rosterCount ? "secondary" : "primary"}
              loading={readRoster.isPending}
              disabled={!rosterShots.length || busy}
              onClick={() => readRoster.mutate(rosterShots.map((s) => s.file))}
            >
              Read lobby screenshots
            </Button>
            {rosterShots.length > 0 && (
              <Button variant="ghost" disabled={busy} onClick={() => setRosterShots([])}>
                Clear
              </Button>
            )}
          </>
        }
      >
        <p className="mb-4 text-sm">
          {rosterCount ? (
            <>
              <Badge tone="ok">{rosterCount} teams on file</Badge>{" "}
              <span className="text-muted">
                Done for this event — you only need this once, unless the lobby changes.
              </span>
            </>
          ) : (
            <span className="text-muted">
              No roster yet. You can skip this, but then you will have to type team names into
              every result row by hand.
            </span>
          )}
        </p>

        <Dropzone
          shots={rosterShots}
          onChange={setRosterShots}
          disabled={busy}
          label="Drop lobby slot screenshots here"
          hint="The screen with the big coloured slot numbers (05, 18, 23…) and up to four player names per card. One screenshot per page so every team is covered."
        />
        {readRoster.isPending && (
          <p className="mt-4 text-sm text-muted" role="status">
            Reading {rosterShots.length} lobby screenshot(s)…
          </p>
        )}
      </Panel>

      <Panel
        title="Step 2 · After the match — result screenshots"
        description="Scroll the final rankings screen and capture every page. Overlapping pages are fine — duplicate cards are merged automatically."
        actions={
          <>
            <Button
              variant="primary"
              loading={readResults.isPending}
              disabled={!resultShots.length || busy}
              onClick={() => readResults.mutate(resultShots.map((s) => s.file))}
            >
              Read results
            </Button>
            {resultShots.length > 0 && (
              <Button variant="ghost" disabled={busy} onClick={() => setResultShots([])}>
                Clear
              </Button>
            )}
          </>
        }
      >
        <Dropzone
          shots={resultShots}
          onChange={setResultShots}
          disabled={busy}
          label="Drop match result screenshots here"
          hint="The gold ranking cards, plus the #1 and #2 panel on the left. PNG, JPG, WEBP or BMP. Reading takes about 10–20 seconds per batch."
        />
        {readResults.isPending && (
          <p className="mt-4 text-sm text-muted" role="status">
            Reading {resultShots.length} result screenshot(s)…
          </p>
        )}
      </Panel>

      <Panel
        title="Step 3 · Review and save"
        description="Every value is editable. Fix anything flagged, then save."
        actions={
          <>
            <label className="sr-only" htmlFor="match-number">
              Match number
            </label>
            <input
              id="match-number"
              className="field w-20 text-center"
              inputMode="numeric"
              value={effectiveMatch}
              onChange={(event) => setMatchNumber(Math.max(1, Number(event.target.value) || 1))}
            />
            <label className="sr-only" htmlFor="match-map">
              Map
            </label>
            <select
              id="match-map"
              className="field w-32"
              value={map}
              onChange={(event) => setMap(event.target.value)}
            >
              {MAPS.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
            <Button
              variant="primary"
              loading={save.isPending}
              disabled={blocked}
              onClick={() => save.mutate()}
            >
              Save match {effectiveMatch}
            </Button>
          </>
        }
      >
        {restored && (
          <p className="mb-4 rounded-lg border border-bronze/40 bg-bronze/10 px-3 py-2 text-sm text-bronze-bright">
            Restored your unsaved work on match {effectiveMatch}.
          </p>
        )}

        {(problems.length > 0 || issues.summary.length > 0) && (
          <ul
            aria-live="polite"
            className="mb-4 space-y-1 rounded-lg border border-warn/40 bg-warn/10 px-4 py-3 text-sm text-warn"
          >
            {[...issues.summary, ...problems].map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}

        {rows.length === 0 ? (
          <EmptyState title="Nothing to review yet">
            Upload result screenshots above and press <strong>Read results</strong>, or start a
            match by hand.
            <span className="mt-4 block">
              <Button onClick={() => setRows(seedRows(dashboard))}>Enter results manually</Button>
            </span>
          </EmptyState>
        ) : (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
            {/* Screenshot beside the table so a suspect row can be checked
                against the source without leaving the page. */}
            <div className="hidden xl:block">
              <div className="sticky top-24 space-y-2">
                {activeShot ? (
                  <img
                    src={activeShot.url}
                    alt="Source screenshot"
                    className="w-full rounded-panel border border-line"
                  />
                ) : (
                  <EmptyState title="No screenshot loaded">
                    Keep the result screenshots loaded above and they show here beside the table.
                  </EmptyState>
                )}
                <p className="text-xs text-muted">
                  {activeRow !== null && rows[activeRow]
                    ? `Checking rank ${rows[activeRow].rank || "—"} · ${rows[activeRow].teamName || "unnamed team"}`
                    : "Hover a row to see which team you are checking."}
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge tone="neutral">{rows.length} teams</Badge>
                <Badge tone={issues.byRow.size ? "danger" : "ok"}>
                  {issues.byRow.size ? `${issues.byRow.size} to fix` : "ready to save"}
                </Badge>
                <Button
                  size="sm"
                  variant="ghost"
                  className="ml-auto"
                  onClick={() =>
                    setRows((current) => [
                      ...current,
                      { rank: "", slot: "", teamName: "", players: padPlayers() },
                    ])
                  }
                >
                  + Add row
                </Button>
              </div>

              <ReviewTable
                rows={rows}
                issues={issues}
                activeRow={activeRow}
                onSelectRow={setActiveRow}
                placementPoints={dashboard.event.placementPoints}
                killPoint={dashboard.event.killPoint}
                onChange={(index, patch) =>
                  setRows((current) =>
                    current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
                  )
                }
                onRemove={(index) =>
                  setRows((current) => current.filter((_, i) => i !== index))
                }
              />
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}
