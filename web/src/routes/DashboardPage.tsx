import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, downloadExport } from "@/lib/api";
import type { Dashboard } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { useToast } from "@/components/Toasts";
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  Panel,
  Skeleton,
} from "@/components/ui/primitives";

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const { push } = useToast();
  const [pendingDelete, setPendingDelete] = React.useState<number | null>(null);
  const [downloading, setDownloading] = React.useState<string | null>(null);

  const { data, isPending } = useQuery<Dashboard>({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });

  const remove = useMutation({
    mutationFn: (matchNumber: number) => api.deleteMatch(matchNumber),
    onSuccess: (updated, matchNumber) => {
      queryClient.setQueryData(["dashboard"], updated);
      setPendingDelete(null);
      push(`Match ${matchNumber} deleted.`, "success");
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  async function download(kind: "sheet" | "overall-png" | "match-png" | "player-details", label: string) {
    setDownloading(kind);
    try {
      await downloadExport(kind);
      push(`${label} downloaded.`, "success");
    } catch (error) {
      push(error instanceof Error ? error.message : "Download failed.", "error");
    } finally {
      setDownloading(null);
    }
  }

  if (isPending || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-80" />
      </div>
    );
  }

  const totalKills = data.standings.reduce((total, team) => total + Number(team.kills || 0), 0);

  return (
    <div className="space-y-6">
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Event" value={data.event.eventName || "Untitled"} sub={data.event.stage} />
        <Metric
          label="Matches saved"
          value={`${data.matches.length} / ${data.event.totalMatches}`}
          sub={`Next up: match ${data.nextMatch}`}
        />
        <Metric label="Teams" value={String(data.event.teams?.length ?? 0)} sub="on the roster" />
        <Metric label="Total eliminations" value={String(totalKills)} sub="across all matches" />
      </section>

      <Panel
        title="Exports and Discord files"
        description="Regenerated automatically every time a match is saved."
      >
        <div className="flex flex-wrap gap-2">
          {(
            [
              ["sheet", "Tournament sheet (.xlsx)"],
              ["match-png", "Team SS - latest match (.png)"],
              ["overall-png", "Overall SS (.png)"],
              ["player-details", "Player details (.csv)"],
            ] as const
          ).map(([kind, label]) => (
            <Button
              key={kind}
              loading={downloading === kind}
              onClick={() => download(kind, label)}
            >
              {label}
            </Button>
          ))}
        </div>
      </Panel>

      <Panel title="Discord bot outputs" description="Use these commands in Discord after the bot is running.">
        <div className="flex flex-wrap gap-2 text-sm">
          {["/teamss", "/overallss", "/playerdetails", "/results", "/standings", "/players"].map((command) => (
            <code key={command} className="rounded-lg border border-line bg-raised px-3 py-2 text-bronze-bright">
              {command}
            </code>
          ))}
        </div>
      </Panel>

      <Panel title="Overall standings" description="PUBGM tiebreakers applied: points, then WWCD, then placement points, then eliminations.">
        {data.standings.length === 0 ? (
          <EmptyState title="No results yet">
            Save your first match on the Match Capture page and standings appear here.
          </EmptyState>
        ) : (
          <div className="table-scroll max-h-[60vh] overflow-y-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col" className="w-12">
                    #
                  </th>
                  <th scope="col">Team</th>
                  <th scope="col" className="text-right">
                    WWCD
                  </th>
                  <th scope="col" className="text-right">
                    Placement
                  </th>
                  <th scope="col" className="text-right">
                    Elims
                  </th>
                  <th scope="col" className="text-right">
                    Total
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.standings.map((team, index) => (
                  <tr key={team.teamId}>
                    <td className="font-mono tabular-nums">{index + 1}</td>
                    <td className="font-medium">{team.teamName || `Team ${team.teamId}`}</td>
                    <td className="text-right font-mono tabular-nums">{team.wwcd}</td>
                    <td className="text-right font-mono tabular-nums">{team.placementPoints}</td>
                    <td className="text-right font-mono tabular-nums">{team.kills}</td>
                    <td className="text-right font-mono font-semibold tabular-nums text-bronze-bright">
                      {team.totalPoints}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Saved matches">
          {data.matches.length === 0 ? (
            <EmptyState title="Nothing saved yet" />
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Match</th>
                    <th scope="col">Map</th>
                    <th scope="col">Winner</th>
                    <th scope="col">Saved</th>
                    <th scope="col" className="w-10">
                      <span className="sr-only">Delete</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.matches.map((match) => (
                    <tr key={match.matchNumber}>
                      <td className="font-mono tabular-nums">#{match.matchNumber}</td>
                      <td>{match.map || "—"}</td>
                      <td>
                        {match.winner ? <Badge tone="bronze">{match.winner}</Badge> : "—"}
                      </td>
                      <td className="whitespace-nowrap text-xs text-muted">
                        {formatDate(match.finalizedAt)}
                      </td>
                      <td>
                        <button
                          type="button"
                          aria-label={`Delete match ${match.matchNumber}`}
                          onClick={() => setPendingDelete(match.matchNumber)}
                          className="rounded px-1.5 py-1 text-muted transition hover:text-danger"
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Player stats" description="Ranked by total eliminations across the event.">
          {data.players.length === 0 ? (
            <EmptyState title="No player data yet" />
          ) : (
            <div className="table-scroll max-h-[24rem] overflow-y-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col" className="w-12">
                      #
                    </th>
                    <th scope="col">Player</th>
                    <th scope="col">Team</th>
                    <th scope="col" className="text-right">
                      Elims
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.players.slice(0, 50).map((player, index) => (
                    <tr key={`${player.playerName}-${index}`}>
                      <td className="font-mono tabular-nums">{index + 1}</td>
                      <td className="font-medium">{player.playerName}</td>
                      <td className="text-muted">{player.teamName}</td>
                      <td className="text-right font-mono tabular-nums">{player.kills}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title={`Delete match ${pendingDelete}?`}
        body="The saved result is removed and standings are recalculated. This cannot be undone."
        confirmLabel="Delete match"
        destructive
        pending={remove.isPending}
        onConfirm={() => pendingDelete !== null && remove.mutate(pendingDelete)}
      />
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="panel p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted">{label}</p>
      <p className="mt-1.5 truncate text-xl font-bold text-sand" title={value}>
        {value}
      </p>
      {sub && <p className="mt-0.5 truncate text-xs text-muted">{sub}</p>}
    </div>
  );
}
