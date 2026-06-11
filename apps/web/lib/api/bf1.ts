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
  // 扩展字段（后端从 EA detailedStats result 提取，缺失为 null）
  skill: number | null;
  infantry_kills: number | null;
  vehicle_kills: number | null;
  assists: number | null;
  revives: number | null;
  heals: number | null;
  repairs: number | null;
  dogtags: number | null;
  max_killstreak: number | null;
  longest_headshot_meters: number | null;
  best_class: string | null;
}

/** 单兵种击杀分布，class 为小写兵种代号（assault/medic/support/scout/tanker/pilot/cavalry） */
export interface SoldierClassStat {
  class: string;
  kills: number;
  score: number;
  time_seconds: number;
}

export interface PlayerStatsDetail {
  summary: PlayerStatsSummary;
  soldiers: SoldierClassStat[];
  raw: Record<string, unknown>;
}

/** 在线状态。is_online 为 null 表示上游查询失败、无法判定 */
export interface OnlineStatus {
  persona_id: number;
  is_online: boolean | null;
  server_name: string | null;
}

/** 玩家当前所属战队（无战队时接口返回 null）。emblem_url 占位符已展开 */
export interface PlayerPlatoon {
  guid: string | null;
  tag: string | null;
  name: string | null;
  size: number | null;
  description: string | null;
  emblem_url: string | null;
  verified: boolean;
}

/** 单一封禁来源三态：clean 无记录 / hit 命中 / unknown 无法判定 */
export type BanSourceState = "clean" | "hit" | "unknown";

/** 外部封禁状态（BFBAN / BFEAC），各来源独立取三态 */
export interface BanStatus {
  persona_id: number;
  bfban: BanSourceState;
  bfeac: BanSourceState;
  bfban_url: string | null;
  bfeac_url: string | null;
}

export interface WeaponStat {
  name: string | null;
  category: string | null;
  kills: number | null;
  headshots: number | null;
  accuracy: number | null;
  time_seconds: number | null;
  image: string | null;
  skin_name: string | null;
  /** 上游稀有度原名（Superior / Enhanced / Standard），经 skinRarityFromName 归一 */
  skin_rarity: string | null;
  skin_image: string | null;
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
  skin_name: string | null;
  skin_rarity: string | null;
  skin_image: string | null;
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
  map_display_name: string | null;
  map_image_url: string | null;
  game_mode: string | null;
  mode_display_name: string | null;
  player_count: number;
  max_player_count: number;
  queue_count: number;
  spectator_count: number;
  region: string | null;
  region_display_name: string | null;
  /** ISO 国家代码（如 "JP"），官服多为 null */
  country: string | null;
  /** 服务器画面更新率 Hz（如 60），缺失为 null */
  tick_rate: number | null;
  /** EA ping 节点代号（如 "nrt"），用于映射数据中心标签；缺失为 null */
  ping_site: string | null;
  is_official: boolean;
  is_ranked: boolean;
  has_password: boolean;
  description: string | null;
}

export interface ServerListResponse {
  total: number;
  items: ServerSummary[];
}

/** 服务器搜索查询参数：maps/modes/regions/sizes 下推到 EA 按条件检索；空位由前端二次过滤 */
export interface ServerListQuery {
  name?: string;
  maps?: string[];
  modes?: string[];
  regions?: string[];
  sizes?: number[];
  limit?: number;
}

export interface MapRotationItem {
  map_name: string | null;
  map_display_name: string | null;
  game_mode: string | null;
  mode_display_name: string | null;
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

/** Blaze roster 单个玩家的生涯综合战绩，全部可能为 null（查询失败或未合并战绩） */
export interface BlazePlayerStats {
  win_rate: number | null;
  kd: number | null;
  kpm: number | null;
  time_hours: number | null;
}

/**
 * Blaze 实时房间名单中的单个玩家。role 取 normal / queue / spectator；team 是 EA 原始
 * TIDX（0/1 为对阵两队，65535 为排队或旁观）。is_admin / is_vip 来自服务器 RSP 名单，
 * is_registered 表示该 persona 已在本平台绑定（群版 UI 的「群友」高亮）。
 */
export interface BlazePlayer {
  persona_id: number;
  display_name: string;
  rank: number;
  team: number;
  latency: number;
  language: string | null;
  join_time: number | null;
  role: string;
  is_admin: boolean;
  is_vip: boolean;
  is_registered: boolean;
  stats: BlazePlayerStats | null;
}

export interface BlazeTeamGroup {
  team_id: number;
  /** 阵营名称（如「法国」「德意志帝国」）；真实数据暂未提供时为 null，UI 回退为「队伍 N」 */
  faction: string | null;
  players: BlazePlayer[];
  count: number;
  rank_150_count: number;
  avg_rank: number | null;
}

export interface ServerPlayersSummary {
  online_admin_count: number;
  online_vip_count: number;
  online_registered_count: number;
  rank_150_count: number;
}

export interface ServerPlayersResponse {
  game_id: number;
  server_name: string | null;
  max_players: number;
  player_count: number;
  queue_count: number;
  spectator_count: number;
  teams: BlazeTeamGroup[];
  queued: BlazePlayer[];
  spectators: BlazePlayer[];
  summary: ServerPlayersSummary;
  stats_included: boolean;
  is_mock: boolean;
}

export interface ServerOwner {
  persona_id: number | null;
  display_name: string | null;
  avatar_url: string | null;
  platform: string | null;
  platform_id: string | null;
  nucleus_id: string | null;
}

export interface ServerMember {
  persona_id: number;
  display_name: string | null;
  avatar_url: string | null;
  platform: string | null;
  platform_id: string | null;
  nucleus_id: string | null;
}

export interface ServerLifecycle {
  /** ISO-8601 UTC，例如 "2024-02-18T05:50:15Z" */
  created_at: string | null;
  expires_at: string | null;
  updated_at: string | null;
}

export interface PlatoonBrief {
  tag: string | null;
  name: string | null;
  size: number | null;
  description: string | null;
  emblem_url: string | null;
}

export interface ServerExtras {
  game_id: number | null;
  server_id: number | null;
  persisted_game_id: string | null;
  bookmark_count: number | null;
  owner: ServerOwner | null;
  lifecycle: ServerLifecycle;
  admins: ServerMember[];
  vips: ServerMember[];
  banned: ServerMember[];
  platoon: PlatoonBrief | null;
}

/**
 * 服务器自定义设置矩阵。EA 已按网关账号语言把键译为中文（繁体），值为 on/off；
 * Scales 组的值是小数字符串（"1.0" = 100%）。各组可能整体缺失（非 RSP 服务器）。
 */
export interface ServerSettings {
  Kits?: Record<string, string>;
  Vehicles?: Record<string, string>;
  Weapons?: Record<string, string>;
  Misc?: Record<string, string>;
  Scales?: Record<string, string>;
  [key: string]: unknown;
}

export interface ServerDetail {
  summary: ServerSummary;
  description: string | null;
  settings: ServerSettings;
  map_rotation: MapRotationItem[];
  players: ServerPlayer[];
  extras: ServerExtras;
  raw: Record<string, unknown>;
}

/** 全服统计：同一指标按官方/私服与亚洲/欧洲/其他地区的拆分 */
export interface CountBreakdown {
  total: number;
  official: number;
  private: number;
  asia: number;
  eu: number;
  other: number;
}

/** 按地图模式或游戏模式分组的服务器数与在线人数；image 为组内任一服务器的地图实景图 */
export interface NamedCount {
  label: string;
  servers: number;
  players: number;
  image: string | null;
}

/** 全服趋势采样点，ts 为 UTC epoch 秒，后端 poller 每分钟一个点 */
export interface TrendPoint {
  ts: number;
  players: number;
  servers: number;
}

export interface BF1Overview {
  available: boolean;
  updated_at: string | null;
  sample_pulls: number;
  raw_count: number;
  servers: CountBreakdown;
  players: CountBreakdown;
  queues: CountBreakdown;
  spectators: CountBreakdown;
  top_map_modes: NamedCount[];
  mode_distribution: NamedCount[];
  /** 最近 24h 趋势，按时间升序；服务刚部署时为空，前端需有占位态 */
  history: TrendPoint[];
}

/** 当前登录用户对某服务器的角色；role 为 null 且 is_platform_admin 为 false 表示无任何服管权限 */
export interface MyServerRole {
  role: "viewer" | "moderator" | "admin" | "owner" | null;
  is_platform_admin: boolean;
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

  getOnline: (personaId: number) => api.get<OnlineStatus>(`/bf1/stats/${personaId}/online`),

  getPlatoon: (personaId: number) =>
    api.get<PlayerPlatoon | null>(`/bf1/stats/${personaId}/platoon`),

  getBan: (personaId: number, name?: string) =>
    api.get<BanStatus>(
      `/bf1/stats/${personaId}/ban${name ? `?name=${encodeURIComponent(name)}` : ""}`,
    ),

  listServers: (query: ServerListQuery = {}) => {
    const params = new URLSearchParams();
    if (query.name) params.set("name", query.name);
    // maps/modes/regions/sizes 作为重复 query 参数下推到后端，由 EA 按条件检索
    query.maps?.forEach((m) => params.append("maps", m));
    query.modes?.forEach((m) => params.append("modes", m));
    query.regions?.forEach((r) => params.append("regions", r));
    query.sizes?.forEach((s) => params.append("sizes", String(s)));
    params.set("limit", String(query.limit ?? 200));
    return api.get<ServerListResponse>(`/bf1/servers?${params.toString()}`);
  },

  getServer: (gameId: number) => api.get<ServerDetail>(`/bf1/servers/${gameId}`),

  getServerPlayers: (gameId: number, includeStats = true) =>
    api.get<ServerPlayersResponse>(
      `/bf1/servers/${gameId}/players?include_stats=${includeStats ? "true" : "false"}`,
    ),

  getOverview: () => api.get<BF1Overview>(`/bf1/overview`),

  // 当前登录用户对该服务器的角色，供前端按角色 gating 内联服管入口
  getMyServerRole: (gameId: number) => api.get<MyServerRole>(`/bf1/server-admin/${gameId}/my-role`),

  // ===== 服管操作（需登录 + 权限）=====
  adminKick: (gameId: number, personaId: number, reason: string) =>
    api.post<{ success: boolean; message: string | null }>(`/bf1/server-admin/${gameId}/kick`, {
      persona_id: personaId,
      reason,
    }),

  // 换边：teamId 传玩家「当前所在队伍」的 Blaze team（0/1），后端据此换到对面阵营
  adminMove: (gameId: number, personaId: number, teamId: number) =>
    api.post<{ success: boolean; message: string | null }>(`/bf1/server-admin/${gameId}/move`, {
      persona_id: personaId,
      team_id: teamId,
    }),

  adminBan: (gameId: number, personaId: number) =>
    api.post<{ success: boolean; message: string | null }>(`/bf1/server-admin/${gameId}/ban`, {
      persona_id: personaId,
    }),

  adminUnban: (gameId: number, personaId: number) =>
    api.delete<{ success: boolean; message: string | null }>(
      `/bf1/server-admin/${gameId}/ban/${personaId}`,
    ),

  adminChooseLevel: (gameId: number, levelIndex: number) =>
    api.post<{ success: boolean; message: string | null }>(`/bf1/server-admin/${gameId}/level`, {
      level_index: levelIndex,
    }),

  adminAddVip: (gameId: number, personaId: number) =>
    api.post<{ success: boolean; message: string | null }>(`/bf1/server-admin/${gameId}/vip`, {
      persona_id: personaId,
    }),

  adminRemoveVip: (gameId: number, personaId: number) =>
    api.delete<{ success: boolean; message: string | null }>(
      `/bf1/server-admin/${gameId}/vip/${personaId}`,
    ),

  adminAddAdmin: (gameId: number, personaId: number) =>
    api.post<{ success: boolean; message: string | null }>(`/bf1/server-admin/${gameId}/admin`, {
      persona_id: personaId,
    }),

  adminRemoveAdmin: (gameId: number, personaId: number) =>
    api.delete<{ success: boolean; message: string | null }>(
      `/bf1/server-admin/${gameId}/admin/${personaId}`,
    ),
};
