/**
 * BF1 API 客户端
 */
import { api } from "@/lib/api-client";

export interface PersonaBrief {
  persona_id: number;
  display_name: string;
  avatar_url: string | null;
}

export interface PersonaSearchResult {
  query: string;
  personas: PersonaBrief[];
}

export interface PlayerStatsSummary {
  persona_id: number;
  display_name: string | null;
  rank: number | null;
  sps: number | null;
  kpm: number | null;
  kd: number | null;
  wins: number | null;
  losses: number | null;
  time_played_seconds: number | null;
  kills: number | null;
  deaths: number | null;
}

export interface PlayerStatsDetail {
  summary: PlayerStatsSummary;
  raw: Record<string, unknown>;
}

export interface WeaponStat {
  name: string | null;
  category: string | null;
  kills: number | null;
  headshots: number | null;
  accuracy: number | null;
  time_seconds: number | null;
  image: string | null;
}

export interface WeaponStats {
  persona_id: number;
  weapons: WeaponStat[];
}

export interface VehicleStat {
  name: string | null;
  category: string | null;
  kills: number | null;
  destroyed: number | null;
  time_seconds: number | null;
  image: string | null;
}

export interface VehicleStats {
  persona_id: number;
  vehicles: VehicleStat[];
}

export interface RecentServer {
  name: string;
  map_name: string | null;
  game_mode: string | null;
  last_played_at: string | null;
  server_id: number | null;
  persisted_game_id: string | null;
}

export interface RecentServers {
  persona_id: number;
  servers: RecentServer[];
}

export interface ServerSummary {
  server_id: number;
  game_id: number | null;
  persisted_game_id: string | null;
  name: string;
  map_name: string | null;
  game_mode: string | null;
  player_count: number;
  max_player_count: number;
  queue_count: number;
  spectator_count: number;
  region: string | null;
  is_official: boolean;
  is_ranked: boolean;
  has_password: boolean;
  description: string | null;
}

export interface ServerListResponse {
  total: number;
  items: ServerSummary[];
}

export interface MapRotationItem {
  map_name: string | null;
  game_mode: string | null;
  map_image_url: string | null;
  is_current: boolean;
}

export interface ServerPlayer {
  persona_id: number;
  display_name: string;
  team_id: number | null;
  rank: number | null;
  is_spectator: boolean;
}

export interface ServerDetail {
  summary: ServerSummary;
  description: string | null;
  settings: Record<string, unknown>;
  map_rotation: MapRotationItem[];
  players: ServerPlayer[];
  raw: Record<string, unknown>;
}

export const bf1Api = {
  searchPlayers: (name: string) =>
    api.get<PersonaSearchResult>(`/bf1/players/search?name=${encodeURIComponent(name)}`),

  getPlayer: (personaId: number) => api.get<PersonaBrief>(`/bf1/players/${personaId}`),

  getStats: (personaId: number) => api.get<PlayerStatsDetail>(`/bf1/stats/${personaId}`),

  getWeapons: (personaId: number) => api.get<WeaponStats>(`/bf1/stats/${personaId}/weapons`),

  getVehicles: (personaId: number) => api.get<VehicleStats>(`/bf1/stats/${personaId}/vehicles`),

  getRecentServers: (personaId: number) =>
    api.get<RecentServers>(`/bf1/stats/${personaId}/recent-servers`),

  listServers: (name?: string, limit = 50) => {
    const params = new URLSearchParams();
    if (name) params.set("name", name);
    params.set("limit", String(limit));
    return api.get<ServerListResponse>(`/bf1/servers?${params.toString()}`);
  },

  getServer: (gameId: number) => api.get<ServerDetail>(`/bf1/servers/${gameId}`),
};
