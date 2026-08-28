/** Shapes returned by web_app.py. Mirrors the Pydantic models there. */

export interface EngineStatus {
  requested: string;
  effective: string;
  visionAvailable: boolean;
  visionModel: string;
}

export interface Me {
  authenticated: boolean;
  email?: string;
  name?: string;
  ocrEngine?: EngineStatus;
}

export type EventAccessRole = "owner" | "shared";

export interface EventSummary {
  id: string;
  eventId: string;
  eventName: string;
  stage: string;
  totalMatches: number;
  teams: number;
  matches: number;
  updatedAt: string;
  active: boolean;
  ownerEmail: string;
  accessRole: EventAccessRole;
  sharedCount: number;
  canManageAccess: boolean;
}

export interface EventsResponse {
  activeEventId: string | null;
  events: EventSummary[];
}

export interface EventAccess {
  eventId: string;
  eventName: string;
  ownerEmail: string;
  sharedEmails: string[];
  sharedCount: number;
  canManageAccess: boolean;
  accessRole: EventAccessRole;
}
export interface Team {
  teamId: number;
  teamName: string;
  shortName?: string;
  players?: string[];
}

export interface EventConfig {
  eventName: string;
  stage: string;
  totalMatches: number;
  placementPoints: number[];
  killPoint: number;
  teams: Team[];
}

export interface Player {
  name: string;
  kills: number;
}

/** A row in the review table, as returned by core/ocr_pipeline.build_rows. */
export interface ResultRow {
  rank: number | "";
  slot: number | "";
  teamName: string;
  kills: number;
  matchScore: number;
  players: Player[];
  confidence: number;
  confidenceReasons: string[];
  needsReview: boolean;
  source: string;
  sourceOrder: number;
}

export interface OcrResultsResponse {
  rows: ResultRow[];
  cards: unknown[];
  errors: string[];
  problems: string[];
  engineUsed: string;
  escalatedCards: number;
}

export interface RosterCard {
  slot: number | null;
  players: string[];
  tag?: string;
}

export interface OcrRosterResponse {
  cards: RosterCard[];
  errors: string[];
  applied: number;
  engineUsed: string;
  event: EventConfig;
}

export interface Standing {
  teamId: number;
  teamName: string;
  totalPoints: number;
  placementPoints: number;
  killPoints: number;
  kills: number;
  /** Count of Winner Winner Chicken Dinners, not a boolean. */
  wwcd: number;
  matches: number;
  bestPlacement: number;
  rank: number;
}

export interface PlayerStat {
  /** The server calls this `playerName`, not `name`. */
  playerName: string;
  teamName: string;
  kills: number;
  matches: number;
  contribution: number;
  mvpRating: number;
  rank: number;
}

export interface MatchSummary {
  matchNumber: number;
  map: string;
  finalizedAt: string;
  teams: number;
  winner: string;
}

export interface Dashboard {
  event: EventConfig;
  matches: MatchSummary[];
  standings: Standing[];
  players: PlayerStat[];
  nextMatch: number;
}

/** One editable row of the match the operator is building. */
export interface MatchRow {
  rank: number | "";
  slot: number | "";
  teamName: string;
  players: Player[];
  confidence?: number;
  confidenceReasons?: string[];
  needsReview?: boolean;
  saveProblem?: string;
  source?: string;
}

/** One team in a built match result — the observer feed and saved matches
 *  share this shape. Note the field is `placement`, not `rank`. */
export interface ApiResultRow {
  teamId: number;
  teamName: string;
  placement: number;
  kills: number;
  placementPoints: number;
  killPoints: number;
  totalPoints: number;
  wwcd: boolean;
}

export interface GraphicTemplate {
  key: string;
  name: string;
  blurb: string;
  columns: number;
  /** [bgFrom, bgTo, accent, text] — used for the swatch strip on the card. */
  swatch: string[];
}

export interface GraphicsConfig {
  template: string;
  accent: string;
  text: string;
  title: string;
  background: string;
  logo: string;
  logoPosition: string;
  showLogo: boolean;
  scrim: number | null;
  layout: string;
}

export interface GraphicsCatalogue {
  templates: GraphicTemplate[];
  graphics: GraphicsConfig;
  logoPositions: string[];
}

