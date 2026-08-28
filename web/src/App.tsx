import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { EventsResponse, Me } from "@/lib/types";
import { Shell } from "@/components/Shell";
import { Spinner } from "@/components/ui/primitives";
import AuthPage from "@/routes/AuthPage";
import EventsPage from "@/routes/EventsPage";
import ModePage from "@/routes/ModePage";
import SetupPage from "@/routes/SetupPage";
import CapturePage from "@/routes/CapturePage";
import ObserverPage from "@/routes/ObserverPage";
import DashboardPage from "@/routes/DashboardPage";

export default function App() {
  const { data: me, isPending } = useQuery<Me>({ queryKey: ["me"], queryFn: api.me });

  if (isPending) {
    return (
      <div className="flex h-full items-center justify-center text-muted">
        <Spinner className="size-6" />
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  if (!me?.authenticated) return <AuthPage />;

  return (
    <Shell me={me}>
      <Routes>
        <Route path="/" element={<Navigate to="/events" replace />} />
        <Route path="/events" element={<EventsPage />} />
        <Route path="/mode" element={<ModePage />} />
        <Route path="/setup" element={<EventRequired><SetupPage /></EventRequired>} />
        <Route path="/capture" element={<EventRequired><CapturePage /></EventRequired>} />
        <Route path="/observer" element={<EventRequired><ObserverPage /></EventRequired>} />
        <Route path="/dashboard" element={<EventRequired><DashboardPage /></EventRequired>} />
        <Route path="*" element={<Navigate to="/events" replace />} />
      </Routes>
    </Shell>
  );
}

function EventRequired({ children }: { children: ReactNode }) {
  const { data, isPending } = useQuery<EventsResponse>({ queryKey: ["events"], queryFn: api.events });

  if (isPending || !data) {
    return (
      <div className="flex h-72 items-center justify-center text-muted">
        <Spinner className="size-6" />
        <span className="sr-only">Loading event</span>
      </div>
    );
  }

  if (!data.activeEventId) return <Navigate to="/events" replace />;

  return <>{children}</>;
}
