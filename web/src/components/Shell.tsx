import * as React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { EventsResponse, Me } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge, Button, Tooltip } from "@/components/ui/primitives";
import { useToast } from "@/components/Toasts";

const EVENT_NAV = [{ to: "/events", label: "Events" }];

const ACTIVE_EVENT_NAV = [
  { to: "/events", label: "Events" },
  { to: "/mode", label: "Manual or API" },
  { to: "/dashboard", label: "Results" },
];

export function Shell({ me, children }: { me: Me; children: React.ReactNode }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { push } = useToast();
  const { data: events } = useQuery<EventsResponse>({ queryKey: ["events"], queryFn: api.events });
  const activeEvent = events?.events.find((event) => event.active);
  const navItems = activeEvent ? ACTIVE_EVENT_NAV : EVENT_NAV;

  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear();
      navigate("/");
      push("Signed out.");
    },
    onError: (error: Error) => push(error.message, "error"),
  });

  return (
    <div className="flex min-h-full flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50
                   focus:rounded-lg focus:bg-bronze focus:px-4 focus:py-2 focus:text-ink"
      >
        Skip to content
      </a>

      <header className="sticky top-0 z-40 border-b border-line bg-bg/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-lg bg-bronze font-bold text-ink">
              EC
            </span>
            <span className="leading-tight">
              <span className="block text-sm font-semibold tracking-wide">ESPORTS COUNTY</span>
              <span className="block text-xs text-muted">
                {activeEvent ? activeEvent.eventName : "Create or choose event"}
              </span>
            </span>
          </div>

          <nav aria-label="Sections" className="order-3 -mx-1 w-full overflow-x-auto sm:order-none sm:mx-0 sm:w-auto">
            <ul className="flex items-center gap-1">
              {navItems.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    className={({ isActive }) =>
                      cn(
                        "block whitespace-nowrap rounded-lg px-3 py-2 text-sm transition",
                        isActive
                          ? "bg-raised font-semibold text-bronze-bright"
                          : "text-muted hover:bg-raised hover:text-sand",
                      )
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <EngineBadge me={me} />
            <ThemeToggle />
            <span className="hidden text-xs text-muted md:inline">{me.email}</span>
            <Button size="sm" variant="ghost" loading={logout.isPending} onClick={() => logout.mutate()}>
              Log out
            </Button>
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
        {children}
      </main>

      <footer className="border-t border-line px-4 py-4 text-center text-xs text-muted">
        All rights reserved to ESPORTS COUNTY
      </footer>
    </div>
  );
}

/**
 * Says which OCR engine is running.
 *
 * Offline is the normal, free, default state, so it is presented as a feature
 * rather than as a missing-API-key warning — nagging about a paid mode nobody
 * asked for makes a working app look broken.
 */
function EngineBadge({ me }: { me: Me }) {
  const engine = me.ocrEngine;
  if (!engine) return null;

  const usingVision = engine.effective !== "local";
  return (
    <Tooltip
      label={
        usingVision
          ? `Low-confidence cards are re-read with ${engine.visionModel}. This is the optional paid mode; unset OCR_ENGINE to go back to free offline reading.`
          : "Screenshots are read on this machine with RapidOCR — free, no account, no internet, and nothing ever leaves your computer."
      }
    >
      <span className="hidden sm:block">
        <Badge tone={usingVision ? "bronze" : "ok"}>
          {usingVision ? `OCR: ${engine.effective}` : "Offline OCR"}
        </Badge>
      </span>
    </Tooltip>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = React.useState<"dark" | "light">(
    () => (localStorage.getItem("ec-pubgm:theme") as "dark" | "light") ?? "dark",
  );

  React.useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("ec-pubgm:theme", theme);
  }, [theme]);

  return (
    <Button
      size="sm"
      variant="ghost"
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
    >
      {theme === "dark" ? "☾" : "☀"}
    </Button>
  );
}

