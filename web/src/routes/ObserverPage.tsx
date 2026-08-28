import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { ApiResultRow, Dashboard } from "@/lib/types";
import { useToast } from "@/components/Toasts";
import { Badge, Button, EmptyState, Panel, Skeleton } from "@/components/ui/primitives";

const MAPS = ["Erangel", "Miramar", "Sanhok", "Vikendi", "Rondo", "Karakin", "Livik"];
const DEFAULT_LOCAL_ENDPOINT = "http://127.0.0.1:10086/gettotalplayerlist";
const LOCAL_ENDPOINT_RE = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(?::|\/|$)/i;
const LIVE_REFRESH_MS = 1000;

type FeedMode = "browser" | "server" | "demo";

const FEED_MODES: Array<{ id: FeedMode; label: string }> = [
  { id: "browser", label: "This browser" },
  { id: "server", label: "Public URL" },
  { id: "demo", label: "Demo" },
];

function messageFrom(error: unknown) {
  return error instanceof Error ? error.message : String(error || "Something went wrong.");
}

async function readBrowserLiveFeed(url: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(url, {
      cache: "no-store",
      credentials: "omit",
      mode: "cors",
      referrerPolicy: "no-referrer",
    });
  } catch (error) {
    throw new Error(
      `Chrome could not read this local live URL. Keep gettotalplayerlist running on this PC and allow local network access if Chrome asks. If it still fails, run run_live_bridge.bat and use http://127.0.0.1:8765/gettotalplayerlist. (${messageFrom(error)})`,
    );
  }

  if (!response.ok) {
    throw new Error(`The local live feed opened, but returned HTTP ${response.status}.`);
  }

  try {
    return await response.json();
  } catch {
    throw new Error("The local live feed opened, but it did not return JSON data.");
  }
}

export default function ObserverPage() {
  const queryClient = useQueryClient();
  const { push } = useToast();
  const pollPendingRef = React.useRef(false);

  const { data: dashboard, isPending } = useQuery<Dashboard>({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });

  const [feedMode, setFeedMode] = React.useState<FeedMode>("browser");
  const [apiUrl, setApiUrl] = React.useState(DEFAULT_LOCAL_ENDPOINT);
  const [autoPoll, setAutoPoll] = React.useState(false);
  const [map, setMap] = React.useState("Erangel");
  const [matchNumber, setMatchNumber] = React.useState<number | null>(null);
  const [results, setResults] = React.useState<ApiResultRow[]>([]);
  const [status, setStatus] = React.useState(
    "This browser will read gettotalplayerlist from your game PC every 1 second.",
  );

  const effectiveMatch = matchNumber ?? dashboard?.nextMatch ?? 1;
  const cleanUrl = apiUrl.trim();
  const hasEndpoint = cleanUrl.length > 0;
  const isDemo = feedMode === "demo";
  const isBrowserFeed = feedMode === "browser";
  const canPoll = isDemo || hasEndpoint;
  const isServerLocalEndpoint = feedMode === "server" && LOCAL_ENDPOINT_RE.test(cleanUrl);

  const modeHelp = React.useMemo(() => {
    if (feedMode === "browser") {
      return "Best for your setup: this Chrome reads the local match feed from your game PC, then sends the data here for scoring.";
    }
    if (feedMode === "server") {
      return "Use this only when the live URL is public or tunnelled so the VPS can reach it.";
    }
    return "Sample rows for testing the page only. Do not save demo data into a real event.";
  }, [feedMode]);

  const poll = useMutation({
    mutationFn: async (reset: boolean) => {
      if (isBrowserFeed) {
        if (!hasEndpoint) throw new Error("Paste your local gettotalplayerlist URL first.");
        const json = await readBrowserLiveFeed(cleanUrl);
        return api.ingestObserverSnapshot(json, cleanUrl, reset);
      }
      return api.pollObserver(cleanUrl, isDemo, reset);
    },
    onSuccess: (data) => {
      setResults(data.results);
      const refresh = autoPoll ? " - refreshing every 1 sec" : "";
      setStatus(
        data.results.length
          ? `${data.status} - ${data.aliveTeams} team(s) alive${data.isMatchOver ? " - match over" : ""}${refresh}`
          : `${data.status} - no team data received yet${refresh}`,
      );
    },
    onError: (error: Error) => {
      setResults([]);
      setStatus(isBrowserFeed ? messageFrom(error) : `Connection failed: ${messageFrom(error)}`);
      setAutoPoll(false);
    },
  });

  React.useEffect(() => {
    pollPendingRef.current = poll.isPending;
  }, [poll.isPending]);

  React.useEffect(() => {
    setResults([]);
    setAutoPoll(false);
    if (feedMode === "browser") {
      setStatus("This browser will read gettotalplayerlist from your game PC every 1 second.");
    } else if (feedMode === "server") {
      setStatus("Paste a public or tunnel live URL, then poll once.");
    } else {
      setStatus("Demo sample mode is on. Use it only for testing the page.");
    }
  }, [cleanUrl, feedMode]);

  React.useEffect(() => {
    if (!autoPoll || !canPoll) return;
    const id = window.setInterval(() => {
      if (!pollPendingRef.current) poll.mutate(false);
    }, LIVE_REFRESH_MS);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPoll, cleanUrl, feedMode, canPoll]);

  const save = useMutation({
    mutationFn: () => api.saveObserverMatch(effectiveMatch, map),
    onSuccess: (data) => {
      queryClient.setQueryData(["dashboard"], data);
      setResults([]);
      setMatchNumber(data.nextMatch);
      setAutoPoll(false);
      push(`Match ${effectiveMatch} saved from the live feed.`, "success");
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  if (isPending || !dashboard) return <Skeleton className="h-96" />;

  return (
    <div className="space-y-6">
      <Panel
        title="Live API"
        description="Read live eliminations and placements from the running match feed."
        actions={
          <>
            <Button
              loading={poll.isPending && !autoPoll}
              onClick={() => poll.mutate(false)}
              disabled={autoPoll || !canPoll}
            >
              Poll once
            </Button>
            <Button
              variant={autoPoll ? "danger" : "secondary"}
              disabled={!canPoll}
              onClick={() => {
                const next = !autoPoll;
                setAutoPoll(next);
                if (next) poll.mutate(false);
              }}
            >
              {autoPoll ? "Stop live" : "Start 1s live"}
            </Button>
            <Button variant="ghost" onClick={() => poll.mutate(true)} disabled={autoPoll || !canPoll}>
              Reset match
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Live source
            </div>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Live feed source">
              {FEED_MODES.map((mode) => (
                <Button
                  key={mode.id}
                  type="button"
                  size="sm"
                  variant={feedMode === mode.id ? "primary" : "secondary"}
                  onClick={() => {
                    setFeedMode(mode.id);
                    if (mode.id === "browser" && !apiUrl.trim()) setApiUrl(DEFAULT_LOCAL_ENDPOINT);
                  }}
                >
                  {mode.label}
                </Button>
              ))}
            </div>
            <p className="mt-2 text-sm text-muted">{modeHelp}</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <div>
              <label className="label" htmlFor="observer-url">
                {isBrowserFeed ? "Local gettotalplayerlist URL" : "Live endpoint"}
              </label>
              <input
                id="observer-url"
                className="field font-mono text-xs"
                value={apiUrl}
                placeholder={isDemo ? "Demo mode does not need a URL" : DEFAULT_LOCAL_ENDPOINT}
                disabled={isDemo}
                onChange={(event) => setApiUrl(event.target.value)}
              />
              {isBrowserFeed && (
                <p className="mt-2 text-xs text-muted">
                  Keep the game feed running on this same PC. Opening the URL in Chrome proves the feed is live; this page still needs browser permission to read it.
                </p>
              )}
              {isServerLocalEndpoint && (
                <p className="mt-2 text-xs text-warn">
                  Public URL mode cannot read 127.0.0.1 from your game PC. Choose This browser for the local gettotalplayerlist feed.
                </p>
              )}
              {!isDemo && !hasEndpoint && (
                <p className="mt-2 text-xs text-warn">Paste the live endpoint before starting.</p>
              )}
            </div>
            <div className="text-sm text-muted">
              Refresh: <span className="font-mono text-sand">1 sec</span>
            </div>
          </div>
        </div>

        <p role="status" aria-live="polite" className="mt-4 text-sm text-muted">
          {status}
        </p>
      </Panel>

      <Panel
        title="Live standings"
        description="Refreshed on every successful read. Save when the match is over."
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
          <EmptyState title="No live data yet">
            Choose <strong>This browser</strong>, keep gettotalplayerlist running, then press <strong>Start 1s live</strong>.
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
                      {row.teamName || `Team ${row.teamId}`} {" "}
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

