import type { MatchRow } from "@/lib/types";
import { cn, duplicateValues } from "@/lib/utils";
import { Badge, Tooltip } from "@/components/ui/primitives";

export interface RowIssues {
  /** Row index -> the reasons that row cannot be saved as it stands. */
  byRow: Map<number, string[]>;
  summary: string[];
}

/**
 * Live validation of the whole table. Runs on every edit, so a duplicate rank
 * lights up the moment it is typed rather than at save time — the old flow
 * only found out when the server rejected the POST.
 */
export function findIssues(rows: MatchRow[]): RowIssues {
  const byRow = new Map<number, string[]>();
  const summary: string[] = [];
  const add = (index: number, reason: string) => {
    const list = byRow.get(index) ?? [];
    list.push(reason);
    byRow.set(index, list);
  };

  rows.forEach((row, index) => {
    if (!Number(row.rank)) add(index, "needs a rank");
    if (!Number(row.slot)) add(index, "needs a slot");
  });

  for (const rank of duplicateValues(rows.map((r) => Number(r.rank)).filter(Boolean))) {
    summary.push(`Two rows both claim rank ${rank}.`);
    rows.forEach((row, index) => {
      if (Number(row.rank) === rank) add(index, `duplicate rank ${rank}`);
    });
  }
  for (const slot of duplicateValues(rows.map((r) => Number(r.slot)).filter(Boolean))) {
    summary.push(`Two rows both use slot ${slot}.`);
    rows.forEach((row, index) => {
      if (Number(row.slot) === slot) add(index, `duplicate slot ${slot}`);
    });
  }

  const missingRank = rows.filter((row) => !Number(row.rank)).length;
  if (missingRank) summary.push(`${missingRank} row(s) still need a rank.`);
  const missingSlot = rows.filter((row) => !Number(row.slot)).length;
  if (missingSlot) summary.push(`${missingSlot} row(s) still need a slot.`);

  return { byRow, summary };
}

export function ReviewTable({
  rows,
  issues,
  activeRow,
  onSelectRow,
  onChange,
  onRemove,
  placementPoints,
  killPoint,
}: {
  rows: MatchRow[];
  issues: RowIssues;
  activeRow: number | null;
  onSelectRow: (index: number | null) => void;
  onChange: (index: number, patch: Partial<MatchRow>) => void;
  onRemove: (index: number) => void;
  placementPoints: number[];
  killPoint: number;
}) {
  return (
    <div className="table-scroll max-h-[70vh] overflow-y-auto">
      {/* A real table, not a div grid — screen readers get row and column
          semantics, and the header stays put while the operator scrolls. */}
      <table className="data-table">
        <caption className="sr-only">
          Match results read from your screenshots. Edit any cell to correct it.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="w-16">
              Rank
            </th>
            <th scope="col" className="w-16">
              Slot
            </th>
            <th scope="col" className="min-w-40">
              Team
            </th>
            <th scope="col" className="min-w-[22rem]">
              Players &amp; eliminations
            </th>
            <th scope="col" className="w-16 text-right">
              Elims
            </th>
            <th scope="col" className="w-16 text-right">
              Points
            </th>
            <th scope="col" className="w-28">
              Confidence
            </th>
            <th scope="col" className="w-10">
              <span className="sr-only">Remove</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const rowIssues = issues.byRow.get(index) ?? [];
            const kills = row.players.reduce((total, p) => total + Number(p.kills || 0), 0);
            const rank = Number(row.rank);
            const points =
              (rank ? (placementPoints[rank - 1] ?? 0) : 0) + kills * killPoint;

            return (
              <tr
                key={index}
                onFocus={() => onSelectRow(index)}
                onMouseEnter={() => onSelectRow(index)}
                className={cn(
                  "transition",
                  rowIssues.length && "bg-danger/[0.07]",
                  activeRow === index && "bg-bronze/[0.08]",
                )}
              >
                <td>
                  <input
                    className={cn("field px-2 py-1 text-center", rowIssues.length && "border-danger/60")}
                    aria-label={`Rank for row ${index + 1}`}
                    inputMode="numeric"
                    value={row.rank}
                    onChange={(event) =>
                      onChange(index, { rank: numberOrBlank(event.target.value) })
                    }
                  />
                </td>
                <td>
                  <input
                    className={cn("field px-2 py-1 text-center", rowIssues.length && "border-danger/60")}
                    aria-label={`Slot for row ${index + 1}`}
                    inputMode="numeric"
                    value={row.slot}
                    onChange={(event) =>
                      onChange(index, { slot: numberOrBlank(event.target.value) })
                    }
                  />
                </td>
                <td>
                  <input
                    className="field px-2 py-1"
                    aria-label={`Team name for row ${index + 1}`}
                    value={row.teamName}
                    onChange={(event) => onChange(index, { teamName: event.target.value })}
                  />
                </td>
                <td>
                  <div className="grid gap-1.5 sm:grid-cols-2">
                    {row.players.map((player, playerIndex) => (
                      <div key={playerIndex} className="flex gap-1">
                        <input
                          className="field min-w-0 flex-1 px-2 py-1"
                          aria-label={`Player ${playerIndex + 1} name, row ${index + 1}`}
                          placeholder={`Player ${playerIndex + 1}`}
                          value={player.name}
                          onChange={(event) =>
                            onChange(index, {
                              players: row.players.map((p, i) =>
                                i === playerIndex ? { ...p, name: event.target.value } : p,
                              ),
                            })
                          }
                        />
                        <input
                          className="field w-14 px-1 py-1 text-center"
                          aria-label={`Player ${playerIndex + 1} eliminations, row ${index + 1}`}
                          inputMode="numeric"
                          value={player.kills}
                          onChange={(event) =>
                            onChange(index, {
                              players: row.players.map((p, i) =>
                                i === playerIndex
                                  ? { ...p, kills: Math.max(0, Number(event.target.value) || 0) }
                                  : p,
                              ),
                            })
                          }
                        />
                      </div>
                    ))}
                  </div>
                </td>
                <td className="text-right font-mono tabular-nums">{kills}</td>
                <td className="text-right font-mono font-semibold tabular-nums text-bronze-bright">
                  {points}
                </td>
                <td>
                  <ConfidenceCell row={row} issues={rowIssues} />
                </td>
                <td>
                  <button
                    type="button"
                    onClick={() => onRemove(index)}
                    aria-label={`Remove row ${index + 1}`}
                    className="rounded px-1.5 py-1 text-muted transition hover:text-danger"
                  >
                    ✕
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ConfidenceCell({ row, issues }: { row: MatchRow; issues: string[] }) {
  const reasons = [...issues, ...(row.confidenceReasons ?? [])];
  const score = row.confidence;

  if (issues.length) {
    return (
      <Tooltip label={<ul className="space-y-1">{reasons.map((r) => <li key={r}>{r}</li>)}</ul>}>
        <span>
          <Badge tone="danger">Fix this</Badge>
        </span>
      </Tooltip>
    );
  }
  if (score === undefined) return <span className="text-xs text-muted">manual</span>;

  const tone = score >= 0.85 ? "ok" : score >= 0.7 ? "warn" : "danger";
  return (
    <Tooltip
      label={
        reasons.length ? (
          <ul className="space-y-1">
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        ) : (
          "Read cleanly — nothing looked wrong."
        )
      }
    >
      <span className="flex items-center gap-1.5">
        <Badge tone={tone}>{Math.round(score * 100)}%</Badge>
        {row.source === "vision" && (
          <span aria-label="Re-read with Claude vision" title="Re-read with Claude vision">
            ✦
          </span>
        )}
      </span>
    </Tooltip>
  );
}

function numberOrBlank(value: string): number | "" {
  const trimmed = value.trim();
  if (!trimmed) return "";
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : "";
}
