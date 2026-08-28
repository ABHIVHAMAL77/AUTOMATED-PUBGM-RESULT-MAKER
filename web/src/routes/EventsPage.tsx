import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { api } from "@/lib/api";
import type { EventAccess, EventsResponse } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { useToast } from "@/components/Toasts";
import { Badge, Button, EmptyState, Panel, Skeleton } from "@/components/ui/primitives";

export default function EventsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { push } = useToast();
  const [draft, setDraft] = React.useState({
    eventName: "",
    stage: "",
    totalMatches: 6,
  });
  const [shareEmail, setShareEmail] = React.useState("");

  const { data, isPending } = useQuery<EventsResponse>({
    queryKey: ["events"],
    queryFn: api.events,
  });

  const activeEventId = data?.activeEventId ?? null;
  const activeEvent = data?.events.find((event) => event.active) ?? null;

  const { data: access } = useQuery<EventAccess>({
    queryKey: ["event-access", activeEventId],
    queryFn: api.eventAccess,
    enabled: Boolean(activeEventId),
  });

  const refreshEventData = (updated?: EventAccess) => {
    if (updated && activeEventId) queryClient.setQueryData(["event-access", activeEventId], updated);
    queryClient.invalidateQueries({ queryKey: ["events"] });
    queryClient.invalidateQueries({ queryKey: ["event"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const finishSelection = (updated: EventsResponse, message: string) => {
    queryClient.setQueryData(["events"], updated);
    queryClient.invalidateQueries({ queryKey: ["event-access"] });
    queryClient.invalidateQueries({ queryKey: ["event"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    push(message, "success");
    navigate("/mode");
  };

  const create = useMutation({
    mutationFn: () =>
      api.createEvent({
        eventName: draft.eventName.trim() || "My PUBGM Event",
        stage: draft.stage.trim(),
        totalMatches: Math.max(1, Number(draft.totalMatches) || 1),
      }),
    onSuccess: (updated) => finishSelection(updated, "Event created."),
    onError: (error: Error) => push(error.message, "error"),
  });

  const select = useMutation({
    mutationFn: (eventId: string) => api.selectEvent(eventId),
    onSuccess: (updated) => finishSelection(updated, "Event selected."),
    onError: (error: Error) => push(error.message, "error"),
  });

  const grantAccess = useMutation({
    mutationFn: () => api.addEventAccess(shareEmail.trim()),
    onSuccess: (updated) => {
      setShareEmail("");
      refreshEventData(updated);
      push("Email added to this event.", "success");
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  const removeAccess = useMutation({
    mutationFn: (email: string) => api.removeEventAccess(email),
    onSuccess: (updated) => {
      refreshEventData(updated);
      push("Email removed from this event.", "success");
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  if (isPending || !data) return <Skeleton className="h-96" />;

  return (
    <div className="space-y-6">
      <section className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(22rem,0.9fr)]">
        <Panel
          title="Choose existing event"
          description="Pick the tournament you want to work on before opening Manual OCR or Live API."
        >
          {data.events.length === 0 ? (
            <EmptyState title="No events yet">
              Create your first event, then choose Manual OCR or Live API result making.
            </EmptyState>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {data.events.map((event) => (
                <article key={event.id} className="rounded-panel border border-line bg-raised/45 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-base font-semibold text-sand" title={event.eventName}>
                        {event.eventName}
                      </p>
                      <p className="mt-1 truncate text-xs text-muted">
                        {event.stage || "No stage set"}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      {event.active && <Badge tone="ok">Active</Badge>}
                      <Badge tone={event.accessRole === "owner" ? "bronze" : "neutral"}>
                        {event.accessRole === "owner" ? "Owner" : "Shared"}
                      </Badge>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-3 gap-2 text-xs text-muted">
                    <span><strong className="block text-sand">{event.matches}</strong>Matches</span>
                    <span><strong className="block text-sand">{event.totalMatches}</strong>Total</span>
                    <span><strong className="block text-sand">{event.teams}</strong>Teams</span>
                  </div>
                  <p className="mt-3 truncate text-xs text-muted" title={event.ownerEmail}>
                    Owner {event.ownerEmail}
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    {event.sharedCount} shared email{event.sharedCount === 1 ? "" : "s"}
                  </p>
                  <p className="mt-3 text-xs text-muted">Updated {formatDate(event.updatedAt)}</p>
                  <Button
                    className="mt-4 w-full"
                    variant={event.active ? "primary" : "secondary"}
                    loading={select.isPending && select.variables === event.id}
                    onClick={() => select.mutate(event.id)}
                  >
                    {event.active ? "Continue" : "Select event"}
                  </Button>
                </article>
              ))}
            </div>
          )}
        </Panel>

        <Panel
          title="Create event"
          description="Start a clean tournament with its own teams, matches, sheets, graphics, and Discord outputs."
          actions={
            <Button variant="primary" loading={create.isPending} onClick={() => create.mutate()}>
              Create and continue
            </Button>
          }
        >
          <div className="space-y-4">
            <div>
              <label className="label" htmlFor="new-event-name">Event name</label>
              <input
                id="new-event-name"
                className="field"
                placeholder="ESPORTS COUNTY Scrims"
                value={draft.eventName}
                onChange={(event) => setDraft((current) => ({ ...current, eventName: event.target.value }))}
              />
            </div>
            <div>
              <label className="label" htmlFor="new-event-stage">Stage</label>
              <input
                id="new-event-stage"
                className="field"
                placeholder="Grand Finals"
                value={draft.stage}
                onChange={(event) => setDraft((current) => ({ ...current, stage: event.target.value }))}
              />
            </div>
            <div>
              <label className="label" htmlFor="new-event-matches">Total matches</label>
              <input
                id="new-event-matches"
                className="field"
                inputMode="numeric"
                value={draft.totalMatches}
                onChange={(event) => setDraft((current) => ({ ...current, totalMatches: Math.max(1, Number(event.target.value) || 1) }))}
              />
            </div>
          </div>
        </Panel>
      </section>

      {activeEvent && (
        <Panel
          title="Event access"
          description="Give another purchased workspace email access to the active event."
          actions={<Badge tone={access?.canManageAccess ? "bronze" : "neutral"}>{access?.accessRole === "owner" ? "Owner controls" : "Shared access"}</Badge>}
        >
          <div className="space-y-4">
            <div className="rounded-panel border border-line bg-raised/35 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-semibold text-sand" title={activeEvent.eventName}>{activeEvent.eventName}</p>
                  <p className="mt-1 truncate text-xs text-muted" title={activeEvent.ownerEmail}>Owner {activeEvent.ownerEmail}</p>
                </div>
                <Badge tone="ok">Active event</Badge>
              </div>
            </div>

            {access?.canManageAccess ? (
              <>
                <form
                  className="flex flex-col gap-3 sm:flex-row"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (!shareEmail.trim()) return;
                    grantAccess.mutate();
                  }}
                >
                  <input
                    className="field flex-1"
                    inputMode="email"
                    placeholder="buyer-or-staff@email.com"
                    value={shareEmail}
                    onChange={(event) => setShareEmail(event.target.value)}
                  />
                  <Button type="submit" variant="primary" loading={grantAccess.isPending}>
                    Add access
                  </Button>
                </form>

                {access.sharedEmails.length === 0 ? (
                  <p className="text-sm text-muted">No extra emails have access yet.</p>
                ) : (
                  <div className="divide-y divide-line rounded-panel border border-line">
                    {access.sharedEmails.map((email) => (
                      <div key={email} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                        <span className="break-all text-sm text-sand">{email}</span>
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={removeAccess.isPending && removeAccess.variables === email}
                          onClick={() => removeAccess.mutate(email)}
                        >
                          Remove
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-muted">
                This event was shared with you. You can use setup, Manual OCR, Live API, results, and exports, but only the owner can add or remove emails.
              </p>
            )}
          </div>
        </Panel>
      )}
    </div>
  );
}
