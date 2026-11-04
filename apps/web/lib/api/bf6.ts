/**
 * BF6 API 客户端。数值都是生涯（global 维度），null 表示 EA 没给这一项（没用过、没玩过），不是 0。
 */
import { api, type RequestOpts } from "@/lib/api-client";

export type Bf6Platform = "ea" | "psn" | "xbox" | "steam" | "epic";

export interface Bf6ResolvedPlayer {
  nucleus_id: number;
  display_name: string | null;
  /** Drop API 的命名空间：cem_ea_id / ps3 / xbox / epic */
  platform: string | null;
  avatar_url: string | null;
  has_current_season_stats: boolean;
}

export interface Bf6Career {
  /** 含击杀 AI；K/D、KPM 用 human_kills */
  kills: number | null;
  human_kills: number | null;
  deaths: number | null;
  score: number | null;
  matches: number | null;
  wins: number | null;
  losses: number | null;
  /** 实际在场上的战斗时间 */
  time_seconds: number | null;
  shots_fired: number | null;
  shots_hit: number | null;
  headshots: number | null;
  longest_killstreak: number | null;
  damage: number | null;
  assists: number | null;
  revives: number | null;
  captures: number | null;
  vehicles_destroyed: number | null;
  repairs: number | null;
  healing: number | null;
  vehicle_kills: number | null;
  melee_kills: number | null;
  distance_m: number | null;
  xp: number | null;
  ads_kills: number | null;
  hipfire_kills: number | null;
  multi_kills: number | null;
  long_distance_kills: number | null;
  takedowns: number | null;
  resupplies: number | null;
  spot_assists: number | null;
  kd: number | null;
  kpm: number | null;
  spm: number | null;
  win_rate: number | null;
  accuracy: number | null;
  headshot_rate: number | null;
  best_class: string | null;
}

export interface Bf6CareerBests {
  round_kills: number | null;
  round_score: number | null;
  life_kills: number | null;
  longest_kill_m: number | null;
  round_headshots: number | null;
  round_defends: number | null;
  round_revives: number | null;
  round_damage: number | null;
}

export interface Bf6RedsecStats {
  matches: number | null;
  wins: number | null;
  top3: number | null;
  top10: number | null;
  kills: number | null;
  time_seconds: number | null;
  longest_win_streak: number | null;
  round_squad_wipes: number | null;
  intel_pickups: number | null;
  round_chests: number | null;
  win_rate: number | null;
}

export interface Bf6WeaponStats {
  id: string;
  kills: number | null;
  damage: number | null;
  shots_fired: number | null;
  shots_hit: number | null;
  headshots: number | null;
  time_seconds: number | null;
  hipfire_kills: number | null;
  ads_kills: number | null;
  accuracy: number | null;
  headshot_rate: number | null;
  kpm: number | null;
}

export interface Bf6VehicleStats {
  id: string;
  kills: number | null;
  damage: number | null;
  time_seconds: number | null;
  distance_m: number | null;
  spawns: number | null;
  kpm: number | null;
}

export interface Bf6GadgetStats {
  id: string;
  uses: number | null;
  kills: number | null;
  damage: number | null;
  time_seconds: number | null;
  repairs: number | null;
  vehicles_destroyed: number | null;
}

export interface Bf6KitStats {
  id: string;
  kills: number | null;
  deaths: number | null;
  score: number | null;
  time_seconds: number | null;
  spawns: number | null;
  revives: number | null;
  kd: number | null;
}

export interface Bf6ModeStats {
  id: string;
  kills: number | null;
  matches: number | null;
  wins: number | null;
  losses: number | null;
  score: number | null;
  time_seconds: number | null;
  win_rate: number | null;
}

export interface Bf6MapStats {
  id: string;
  matches: number | null;
  wins: number | null;
  losses: number | null;
  time_seconds: number | null;
  win_rate: number | null;
}

export interface Bf6PlayerStats {
  nucleus_id: number;
  /** EA 有没有返回这名玩家的多人统计 */
  has_data: boolean;
  career: Bf6Career;
  bests: Bf6CareerBests;
  /** 没玩过大逃杀时为 null */
  redsec: Bf6RedsecStats | null;
  weapons: Bf6WeaponStats[];
  /** 武器大类汇总，id 为 ar / smg 这类 */
  weapon_categories: Bf6WeaponStats[];
  vehicles: Bf6VehicleStats[];
  vehicle_categories: Bf6VehicleStats[];
  gadgets: Bf6GadgetStats[];
  kits: Bf6KitStats[];
  modes: Bf6ModeStats[];
  maps: Bf6MapStats[];
  fetched_at: string;
}

export const bf6Api = {
  resolvePlayer: (name: string, platform: Bf6Platform | null, opts?: RequestOpts) => {
    const qs = new URLSearchParams({ name });
    if (platform) qs.set("platform", platform);
    return api.get<Bf6ResolvedPlayer>(`/bf6/players/resolve?${qs}`, opts);
  },

  getStats: (nucleusId: number, opts?: RequestOpts) =>
    api.get<Bf6PlayerStats>(`/bf6/players/${nucleusId}/stats`, opts),
};
