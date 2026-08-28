import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { EventConfig, Team } from "@/lib/types";
import { duplicateValues } from "@/lib/utils";
import { useToast } from "@/components/Toasts";
import { GraphicTemplates } from "@/components/GraphicTemplates";
import { Button, EmptyState, Panel, Skeleton } from "@/components/ui/primitives";

export default function SetupPage() {
  const queryClient = useQueryClient();
  const { push } = useToast();

  const { data, isPending } = useQuery<EventConfig>({ queryKey: ["event"], queryFn: api.event });
  const [draft, setDraft] = React.useState<EventConfig | null>(null);

  React.useEffect(() => {
    if (data && !draft) setDraft(structuredClone(data));
  }, [data, draft]);

  const save = useMutation({
    mutationFn: (payload: EventConfig) => api.saveEvent(payload),
    onSuccess: (saved) => {
      queryClient.setQueryData(["event"], saved);
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      setDraft(structuredClone(saved));
      push("Event settings saved.", "success");
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  if (isPending || !draft) return <Skeleton className="h-96" />;

  const duplicateSlots = duplicateValues(draft.teams.map((team) => Number(team.teamId)));
  const patch = (changes: Partial<EventConfig>) =>
    setDraft((current) => (current ? { ...current, ...changes } : current));
  const patchTeam = (index: number, changes: Partial<Team>) =>
    setDraft((current) =>
      current
        ? {
            ...current,
            teams: current.teams.map((team, i) => (i === index ? { ...team, ...changes } : team)),
          }
        : current,
    );

  return (
    <div className="space-y-6">
      <Panel
        title="Event"
        description="Names and the point system used to score every match."
        actions={
          <Button
            variant="primary"
            loading={save.isPending}
            disabled={duplicateSlots.length > 0}
            onClick={() => save.mutate(draft)}
          >
            Save event
          </Button>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="label" htmlFor="event-name">
              Event name
            </label>
            <input
              id="event-name"
              className="field"
              value={draft.eventName}
              onChange={(event) => patch({ eventName: event.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="event-stage">
              Stage
            </label>
            <input
              id="event-stage"
              className="field"
              placeholder="e.g. Grand Finals"
              value={draft.stage}
              onChange={(event) => patch({ stage: event.target.value })}
            />
          </div>
          <div>
            <label className="label" htmlFor="event-matches">
              Total matches
            </label>
            <input
              id="event-matches"
              className="field"
              inputMode="numeric"
              value={draft.totalMatches}
              onChange={(event) =>
                patch({ totalMatches: Math.max(1, Number(event.target.value) || 1) })
              }
            />
          </div>
          <div>
            <label className="label" htmlFor="event-killpoint">
              Points per elimination
            </label>
            <input
              id="event-killpoint"
              className="field"
              inputMode="numeric"
              value={draft.killPoint}
              onChange={(event) =>
                patch({ killPoint: Math.max(0, Number(event.target.value) || 0) })
              }
            />
          </div>
        </div>

        <fieldset className="mt-6">
          <legend className="label">Placement points (1st place first)</legend>
          <div className="flex flex-wrap gap-2">
            {draft.placementPoints.map((value, index) => (
              <div key={index} className="w-16">
                <label className="sr-only" htmlFor={`placement-${index}`}>
                  Points for place {index + 1}
                </label>
                <input
                  id={`placement-${index}`}
                  className="field px-2 py-1 text-center"
                  inputMode="numeric"
                  value={value}
                  onChange={(event) =>
                    patch({
                      placementPoints: draft.placementPoints.map((current, i) =>
                        i === index ? Math.max(0, Number(event.target.value) || 0) : current,
                      ),
                    })
                  }
                />
                <p className="mt-1 text-center text-[11px] text-muted">#{index + 1}</p>
              </div>
            ))}
            <div className="flex items-start gap-1 pt-1">
              <Button
                size="sm"
                onClick={() => patch({ placementPoints: [...draft.placementPoints, 0] })}
              >
                +
              </Button>
              <Button
                size="sm"
                disabled={draft.placementPoints.length <= 1}
                onClick={() => patch({ placementPoints: draft.placementPoints.slice(0, -1) })}
              >
                −
              </Button>
            </div>
          </div>
        </fieldset>
      </Panel>

      <GraphicTemplates />

      <Panel
        title="Teams and slots"
        description="Slot numbers must match the lobby. OCR uses these names to identify teams on the results screen."
        actions={
          <Button
            onClick={() =>
              patch({
                teams: [
                  ...draft.teams,
                  {
                    teamId: Math.max(0, ...draft.teams.map((t) => Number(t.teamId))) + 1,
                    teamName: "",
                    shortName: "",
                    players: [],
                  },
                ],
              })
            }
          >
            + Add team
          </Button>
        }
      >
        {duplicateSlots.length > 0 && (
          <p role="alert" className="mb-4 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            Slot {duplicateSlots.join(", ")} is used more than once. Every team needs its own slot.
          </p>
        )}

        {draft.teams.length === 0 ? (
          <EmptyState title="No teams yet">
            Add them by hand, or upload lobby screenshots on the Match Capture page and the slots
            fill themselves in.
          </EmptyState>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col" className="w-20">
                    Slot
                  </th>
                  <th scope="col" className="min-w-40">
                    Team name
                  </th>
                  <th scope="col" className="w-32">
                    Tag
                  </th>
                  <th scope="col" className="min-w-[24rem]">
                    Players (comma separated)
                  </th>
                  <th scope="col" className="w-10">
                    <span className="sr-only">Remove</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {draft.teams.map((team, index) => (
                  <tr key={index}>
                    <td>
                      <input
                        className="field px-2 py-1 text-center"
                        aria-label={`Slot for team ${index + 1}`}
                        inputMode="numeric"
                        value={team.teamId}
                        onChange={(event) =>
                          patchTeam(index, { teamId: Number(event.target.value) || 0 })
                        }
                      />
                    </td>
                    <td>
                      <input
                        className="field px-2 py-1"
                        aria-label={`Name for team ${index + 1}`}
                        value={team.teamName}
                        onChange={(event) => patchTeam(index, { teamName: event.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        className="field px-2 py-1"
                        aria-label={`Tag for team ${index + 1}`}
                        value={team.shortName ?? ""}
                        onChange={(event) => patchTeam(index, { shortName: event.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        className="field px-2 py-1"
                        aria-label={`Players for team ${index + 1}`}
                        value={(team.players ?? []).join(", ")}
                        onChange={(event) =>
                          patchTeam(index, {
                            players: event.target.value
                              .split(",")
                              .map((name) => name.trim())
                              .filter(Boolean),
                          })
                        }
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        aria-label={`Remove team ${index + 1}`}
                        onClick={() =>
                          patch({ teams: draft.teams.filter((_, i) => i !== index) })
                        }
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
    </div>
  );
}
