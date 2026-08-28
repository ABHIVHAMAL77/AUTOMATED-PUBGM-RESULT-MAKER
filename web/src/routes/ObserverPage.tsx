import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { ApiResultRow, Dashboard } from "@/lib/types";
import { useToast } from "@/components/Toasts";
import { Badge, Button, EmptyState, Panel, Skeleton } from "@/components/ui/primitives";

const MAPS = ["Erangel", "Miramar", "Sanhok", "Vikendi", "Rondo", "Karakin", "Livik"];
const DEFAULT_URL = "http://127.0.0.1:10086/gettotalplayerlist";

export default function ObserverPage() {
  const queryClient = useQueryClient();
  const { push } = useToast();

  const { data: dashboard, isPending } = useQuery<Dashboard>({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });

  const [apiUrl, setApiUrl] = React.useState(DEFAULT_URL);
  const [mock, setMock] = React.useState(true);
  const [autoPoll, setAutoPoll] = React.useState(false);
  const [map, setMap] = React.useState("Erangel");
  const [matchNumber, setMatchNumber] = React.useState<number | null>(null);
  const [results, setResults] = React.useState<ApiResultRow[]>([]);
  const [status, setStatus] = React.useState("Ready.");

  const effectiveMatch = matchNumber ?? dashboard?.nextMatch ?? 1;

  const poll = useMutation({
    mutationFn: (reset: boolean) => api.pollObserver(apiUrl, mock, reset),
    onSuccess: (data) => {
      setResults(data.results);
      setStatus(
        `${data.status} · ${data.aliveTeams} team(s) alive${data.isMatchOver ? " · match over" : ""}`,
      );
    },
    onError: (error: Error) => {
      setStatus(`Error: ${error.message}`);
      setAutoPoll(false);
    },
  });

  // Auto-poll runs on a timer rather than a tight loop, and stops itself the
  // moment a request fails so a dead observer can't spin forever.
  React.useEffect(() => {
    if (!autoPoll) return;
    const id = window.setInterval(() => poll.mutate(false), 2500);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPoll, apiUrl, mock]);

  const save = useMutation({
    mutationFn: () => api.saveObserverMatch(effectiveMatch, map),
    onSuccess: (data) => {
      queryClient.setQueryData(["dashboard"], data);
      setResults([]);
      setMatchNumber(data.nextMatch);
      setAutoPoll(false);
      push(`Match ${effectiveMatch} saved from the observer feed.`, "success");
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  if (isPending || !dashboard) return <Skeleton className="h-96" />;

  return (
    <div className="space-y-6">
      <Panel
        title="Observer API"
        description="Poll the in-game observer endpoint for live eliminations and placements instead of reading screenshots."
        actions={
          <>
            <Button
              loading={poll.isPending && !autoPoll}
              onClick={() => poll.mutate(false)}
              disabled={autoPoll}
            >
              Poll once
            </Button>
            <Button
              variant={autoPoll ? "danger" : "secondary"}
              onClick={() => setAutoPoll((current) => !current)}
            >
              {autoPoll ? "Stop auto-poll" : "Auto-poll"}
            </Button>
            <Button variant="ghost" onClick={() => poll.mutate(true)} disabled={autoPoll}>
              Reset match
            </Button>
          </>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="observer-url">
              Observer endpoint
            </label>
            <input
              id="observer-url"
              className="field font-mono text-xs"
              value={apiUrl}
              onChange={(event) => setApiUrl(event.target.value)}
            />
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-[hsl(var(--bronze))]"
                checked={mock}
                onChange={(event) => setMock(event.target.checked)}
              />
              Mock mode (generate sample data without a live game)
            </label>
          </div>
        </div>

        <p role="status" aria-live="polite" className="mt-4 text-sm text-muted">
          {status}
        </p>
      </Panel>

      <Panel
        title="Live standings"
        description="Refreshed on every poll. Save when the match is over."
        actions={
          <>
            <label className="sr-only" htmlFor="observer-match">
              Match number
            </label>
            <input
              id="observer-match"
              className="field w-20 text-center"
              inputMode="numeric"
              value={effectiveMatch}
              onChange={(event) => setMatchNumber(Math.max(1, Number(event.target.value) || 1))}
            />
            <label className="sr-only" htmlFor="observer-map">
              Map
            </label>
            <select
              id="observer-map"
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
              disabled={!results.length}
              onClick={() => save.mutate()}
            >
              Save match {effectiveMatch}
            </Button>
          </>
        }
      >
        {results.length === 0 ? (
          <EmptyState title="No data yet">
            Press <strong>Poll once</strong> to fetch the current match state, or turn on auto-poll
            to follow it live.
          </EmptyState>
        ) : (
          <div className="table-scroll max-h-[60vh] overflow-y-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">Team</th>
                  <th scope="col" className="text-right">
                    Elims
                  </th>
                  <th scope="col" className="text-right">
                    Placement
                  </th>
                  <th scope="col" className="text-right">
                    Total
                  </th>
                </tr>
              </thead>
              <tbody>
                {results.map((row) => (
                  <tr key={`${row.teamId}-${row.placement}`}>
                    <td className="font-mono tabular-nums">{row.placement}</td>
                    <td>
                      {row.teamName || `Team ${row.teamId}`}{" "}
                      {row.wwcd && <Badge tone="bronze">WWCD</Badge>}
                    </td>
                    <td className="text-right font-mono tabular-nums">{row.kills}</td>
                    <td className="text-right font-mono tabular-nums">{row.placementPoints}</td>
                    <td className="text-right font-mono font-semibold tabular-nums text-bronze-bright">
                      {row.totalPoints}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
