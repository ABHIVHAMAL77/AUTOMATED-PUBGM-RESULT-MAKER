import type {
  ApiResultRow,
  Dashboard,
  EngineStatus,
  EventAccess,
  EventConfig,
  EventsResponse,
  GraphicsCatalogue,
  GraphicsConfig,
  MatchRow,
  Me,
  OcrResultsResponse,
  OcrRosterResponse,
} from "./types";

/** Thrown for any non-2xx response, carrying the server's `detail` string. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers:
      options.body instanceof FormData
        ? options.headers
        : { "Content-Type": "application/json", ...options.headers },
  });

  let data: unknown = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    const detail = (data as { detail?: unknown }).detail;
    throw new ApiError(
      typeof detail === "string" ? detail : `Request failed (${response.status}).`,
      response.status,
    );
  }
  return data as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  me: () => request<Me>("/api/me"),
  engine: () => request<EngineStatus>("/api/ocr/engine"),

  login: (email: string, password: string) =>
    post<{ ok: boolean }>("/api/auth/login", { email, password }),
  register: (email: string, password: string, name: string) =>
    post<{ ok: boolean }>("/api/auth/register", { email, password, name }),
  logout: () => post<{ ok: boolean }>("/api/auth/logout"),

  events: () => request<EventsResponse>("/api/events"),
  createEvent: (payload: { eventName: string; stage?: string; totalMatches?: number }) =>
    post<EventsResponse>("/api/events", payload),
  selectEvent: (eventId: string) => post<EventsResponse>("/api/events/select", { eventId }),
  eventAccess: () => request<EventAccess>("/api/events/access"),
  addEventAccess: (email: string) => post<EventAccess>("/api/events/access", { email }),
  removeEventAccess: (email: string) =>
    request<EventAccess>("/api/events/access", { method: "DELETE", body: JSON.stringify({ email }) }),
  dashboard: () => request<Dashboard>("/api/dashboard"),
  event: () => request<EventConfig>("/api/event"),
  saveEvent: (payload: Partial<EventConfig>) =>
    request<EventConfig>("/api/event", { method: "PUT", body: JSON.stringify(payload) }),

  ocrRoster: (files: File[]) => upload<OcrRosterResponse>("/api/manual/ocr-roster", files),
  ocrResults: (files: File[]) => upload<OcrResultsResponse>("/api/manual/ocr-results", files),

  saveMatch: (matchNumber: number, map: string, rows: MatchRow[]) =>
    post<Dashboard>("/api/manual/match", {
      matchNumber,
      map,
      teams: rows.map((row) => ({
        rank: Number(row.rank),
        slot: Number(row.slot),
        teamName: row.teamName || `Team ${row.slot}`,
        kills: row.players.reduce((total, p) => total + Number(p.kills || 0), 0),
        players: row.players
          .filter((p) => p.name.trim())
          .map((p) => ({ name: p.name, kills: Number(p.kills || 0) })),
      })),
    }),

  deleteMatch: (matchNumber: number) =>
    request<Dashboard>(`/api/matches/${matchNumber}`, { method: "DELETE" }),

  pollObserver: (apiUrl: string, mockMode: boolean, reset = false) =>
    post<{
      status: string;
      aliveTeams: number;
      isMatchOver: boolean;
      seenAnyData: boolean;
      results: ApiResultRow[];
    }>("/api/observer/poll", { apiUrl, mockMode, reset }),

  ingestObserverSnapshot: (data: unknown, sourceKey: string, reset = false) =>
    post<{
      status: string;
      aliveTeams: number;
      isMatchOver: boolean;
      seenAnyData: boolean;
      results: ApiResultRow[];
    }>("/api/observer/ingest", { data, sourceKey, reset }),

  saveObserverMatch: (matchNumber: number, map: string) =>
    post<Dashboard>("/api/observer/save", { matchNumber, map }),

  graphics: () => request<GraphicsCatalogue>("/api/graphics/templates"),

  saveGraphics: (payload: Partial<GraphicsConfig>) =>
    request<{ graphics: GraphicsConfig; event: EventConfig }>("/api/graphics", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  uploadArtwork: (kind: "background" | "logo", file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ graphics: GraphicsConfig; event: EventConfig }>(
      `/api/graphics/artwork/${kind}`,
      { method: "POST", body: form },
    );
  },

  deleteArtwork: (kind: "background" | "logo") =>
    request<{ graphics: GraphicsConfig; event: EventConfig }>(
      `/api/graphics/artwork/${kind}`,
      { method: "DELETE" },
    ),
};

/**
 * Preview URL for one template. The `v` parameter busts the browser cache
 * whenever the artwork or colours change — without it the picker keeps showing
 * the render from before the operator's last edit.
 */
export function previewUrl(template: string, version: string | number) {
  return `/api/graphics/preview/${template}?v=${encodeURIComponent(String(version))}`;
}

async function upload<T>(path: string, files: File[]): Promise<T> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return request<T>(path, { method: "POST", body: form });
}

/**
 * Downloads go through fetch + blob rather than a plain <a href>.
 * A bare link to a 404 navigates the tab away from the SPA and throws away
 * every unsaved row the operator has been editing.
 */
export async function downloadExport(kind: "sheet" | "overall-png" | "match-png" | "player-details") {
  const response = await fetch(`/api/download/${kind}`, { credentials: "same-origin" });
  if (!response.ok) {
    let detail = "That file is not ready yet — save a match first.";
    try {
      const data = (await response.json()) as { detail?: string };
      if (data.detail) detail = data.detail;
    } catch {
      /* keep the default message */
    }
    throw new ApiError(detail, response.status);
  }

  const disposition = response.headers.get("content-disposition") ?? "";
  const named = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = named ? decodeURIComponent(named[1]) : kind;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}


