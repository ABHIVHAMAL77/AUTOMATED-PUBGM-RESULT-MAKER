import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { EventsResponse } from "@/lib/types";
import { Badge, EmptyState, Panel, Skeleton } from "@/components/ui/primitives";

const actionLink =
  "inline-flex h-10 items-center justify-center rounded-lg px-4 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-bronze focus:ring-offset-2 focus:ring-offset-bg";
const primaryAction = `${actionLink} bg-bronze text-ink hover:bg-bronze-bright`;
const secondaryAction = `${actionLink} border border-line text-sand hover:border-bronze hover:bg-raised`;

export default function ModePage() {
  const { data, isPending } = useQuery<EventsResponse>({ queryKey: ["events"], queryFn: api.events });
  if (isPending || !data) return <Skeleton className="h-80" />;

  const active = data.events.find((event) => event.active);
  if (!active) {
    return (
      <Panel title="Choose event first">
        <EmptyState title="No active event">
          Go to Events, create or select a tournament, then choose Manual OCR or Live API.
          <span className="mt-4 block">
            <Link to="/events" className={primaryAction}>Open Events</Link>
          </span>
        </EmptyState>
      </Panel>
    );
  }

  return (
    <div className="space-y-6">
      <Panel title="Manual or API result" description="Choose how this event will create its next match result.">
        <div className="mb-5 flex flex-wrap items-center gap-2 text-sm">
          <Badge tone="ok">Active event</Badge>
          <strong className="text-sand">{active.eventName}</strong>
          <span className="text-muted">{active.matches} / {active.totalMatches} matches saved</span>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Link
            to="/capture"
            className="group rounded-panel border border-line bg-raised/45 p-5 transition hover:border-bronze hover:bg-raised focus:outline-none focus:ring-2 focus:ring-bronze focus:ring-offset-2 focus:ring-offset-bg"
          >
            <p className="text-lg font-bold text-sand">Manual OCR</p>
            <p className="mt-2 text-sm text-muted">
              Upload lobby screenshots, upload final result screenshots, review OCR rows, then save.
            </p>
            <span className="mt-5 inline-flex h-10 items-center rounded-lg bg-bronze px-4 text-sm font-semibold text-ink group-hover:bg-bronze-bright">
              Open Manual OCR
            </span>
          </Link>

          <Link
            to="/observer"
            className="group rounded-panel border border-line bg-raised/45 p-5 transition hover:border-bronze hover:bg-raised focus:outline-none focus:ring-2 focus:ring-bronze focus:ring-offset-2 focus:ring-offset-bg"
          >
            <p className="text-lg font-bold text-sand">Live API</p>
            <p className="mt-2 text-sm text-muted">
              Connect the PUBG observer endpoint, poll live standings, and save API-built results.
            </p>
            <span className="mt-5 inline-flex h-10 items-center rounded-lg border border-line px-4 text-sm font-semibold text-sand group-hover:border-bronze">
              Open Live API
            </span>
          </Link>
        </div>
      </Panel>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Event setup">
          <p className="mb-4 text-sm text-muted">Teams, slots, points, and graphics template for this event.</p>
          <Link to="/setup" className={secondaryAction}>Open setup</Link>
        </Panel>
        <Panel title="Results">
          <p className="mb-4 text-sm text-muted">Saved matches, standings, exports, and Discord output files.</p>
          <Link to="/dashboard" className={secondaryAction}>Open results</Link>
        </Panel>
      </div>
    </div>
  );
}
