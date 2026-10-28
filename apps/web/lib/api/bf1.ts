/**
 * BF1 API 客户端
 */
import { api } from "@/lib/api-client";

export interface PersonaBrief {
  persona_id: number;
  display_name: string;
  avatar_url: string | null;
  /**
   * BF1 生涯时长（小时，取整）。仅在搜索结果出现重名时为消歧回填：
   * 0 = 未玩过 BF1（空号，服管会报玩家不存在），>0 = 真号；null = 未查询（无重名）。
   */
  time_played_hours?: number | null;
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
  /** 在线时所在服务器的 gameId，用来跳转服务器详情 */
  game_id: number | null;
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

export type PlatoonRole = "general" | "colonel" | "lieutenant" | "private";

/** 战队成员；role 为 null 表示未知职位（正在玩的服务器里的成员也不带职位） */
export interface PlatoonMember {
  persona_id: number;
  name: string;
  role: PlatoonRole | null;
  avatar_url: string | null;
}

/** 战队详情：成员按职位从高到低排好，servers 为成员正在玩的服务器 */
export interface PlatoonDetail extends PlayerPlatoon {
  created_at: number | null;
  free_join: boolean;
  can_apply: boolean;
  members: PlatoonMember[];
  servers: { server: ServerSummary; members: PlatoonMember[] }[];
}

export interface PlatoonSearchItem {
  guid: string;
  tag: string | null;
  name: string | null;
  size: number | null;
  emblem_url: string | null;
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

/** 服务器搜索查询参数：maps/modes/regions/sizes 交后端筛选；空位由前端二次过滤 */
export interface ServerListQuery {
  name?: string;
  maps?: string[];
  modes?: string[];
  regions?: string[];
  sizes?: number[];
  /** 包含 0 人空服：全服快照不含空服，开启后后端改走 EA searchServers 抽样 */
  includeEmpty?: boolean;
  limit?: number;
}

/** 私服的人数采样点，ts 为 unix 秒 */
export interface ServerPlayerCountPoint {
  ts: number;
  players: number;
  queue: number;
  spectators: number;
  max_players: number;
  map_name: string | null;
  game_mode: string | null;
}

/** 服务器快照列表里的一项：有名单的采样点，附这一轮相对上一轮进入 / 退出的人数 */
export interface ServerRosterPoint extends ServerPlayerCountPoint {
  joined: number;
  left: number;
}

/** 快照列表按时间倒序分页，next_before 传回 before 取更早的一页，null 表示没有更早的了 */
export interface ServerRosterPage {
  items: ServerRosterPoint[];
  next_before: number | null;
}

export type RosterSlot = "team1" | "team2" | "queue" | "spectator";
export type RosterChange = "joined" | "left" | "seated" | "switched";

/** 快照名单里的一个人；离开的人 slot 是离开前的位置 */
export interface RosterPlayer {
  persona_id: number;
  name: string | null;
  slot: RosterSlot;
  change: RosterChange | null;
}

/** 某个采样时刻的完整名单 */
export interface ServerRosterSnapshot extends ServerRosterPoint {
  roster: RosterPlayer[];
  /** 当时地图的阵营，未知地图为 null */
  team1_faction: string | null;
  team2_faction: string | null;
}

/** 排行榜一行：seconds 为在两队里的时长（不含排队、观战），days 为活跃天数（北京时间），
 * joins 为进服次数，last_seen 为最后在服的 unix 秒，online 表示统计截止时仍在服 */
export interface ServerLeaderboardEntry {
  persona_id: number;
  name: string | null;
  seconds: number;
  days: number;
  joins: number;
  last_seen: number;
  online: boolean;
}

/** 私服近 days 天按在队时长排序的玩家；total_players 为窗口内上过场的总人数 */
export interface ServerLeaderboard {
  days: number;
  total_players: number;
  items: ServerLeaderboardEntry[];
}

/** 一局的概要（由生涯差分算出），时间为 unix 秒。observed_start 为假时开局时间是接手的时刻；
 * settled 为假时服务器中途关掉或采集断档，这一局没打完；winner 为 1 / 2，判不出为 null */
export interface RoundSummary {
  id: number;
  game_id: number;
  /** 这台服现在的 gameId：重启后换新，旧 gameId 打不开服务器详情，跳转用这个 */
  server_game_id: number;
  server_name: string | null;
  map_name: string | null;
  map_display_name: string | null;
  map_image_url: string | null;
  game_mode: string | null;
  mode_display_name: string | null;
  started_at: number;
  ended_at: number;
  observed_start: boolean;
  settled: boolean;
  winner: 1 | 2 | null;
  team1_faction: string | null;
  team2_faction: string | null;
  player_count: number;
}

/** 一个人在一局里用过的一件武器或载具（这一局的增量，没用到的指标为 0） */
export interface RoundWeapon {
  kind: "weapon" | "vehicle";
  name: string | null;
  category: string | null;
  image: string | null;
  kills: number;
  headshots: number;
  hits: number;
  shots: number;
  seconds: number;
  destroyed: number;
  /** 击杀里含骑乘时用别的武器打的（战马），和武器重复，不能和其他条目相加 */
  shared_kills: boolean;
}

/** 一个人在一局里的战绩：finished 打到结算、left 中途退出（没有胜负）、suspect 混了别的局。
 * seconds 为各兵种在场秒数之和，kd / kpm / spm 都按它算；kit 为在场最久的兵种（含 elite） */
export interface RoundPlayer {
  persona_id: number;
  name: string | null;
  team: 1 | 2;
  status: "finished" | "left" | "suspect";
  won: boolean | null;
  kills: number;
  deaths: number;
  score: number;
  assists: number;
  revives: number;
  heals: number;
  repairs: number;
  dogtags: number;
  vehicle_kills: number;
  seconds: number;
  kit: string | null;
  kd: number | null;
  kpm: number | null;
  spm: number | null;
  /** 按击杀、时长倒序；null 表示这一局没有武器载具数据（功能上线前，或当时没读到） */
  weapons: RoundWeapon[] | null;
}

export interface RoundDetail extends RoundSummary {
  players: RoundPlayer[];
}

export interface RoundPage {
  items: RoundSummary[];
  next_before: number | null;
}

export interface PlayerRound {
  round: RoundSummary;
  player: RoundPlayer;
}

export interface PlayerRoundPage {
  items: PlayerRound[];
  next_before: number | null;
}

/** 私服近 N 天在某张地图（地图 + 模式）上的累计情况，last_seen 为 unix 秒 */
export interface ServerMapStat {
  map_name: string;
  game_mode: string | null;
  map_display_name: string | null;
  mode_display_name: string | null;
  map_image_url: string | null;
  minutes: number;
  player_minutes: number;
  avg_players: number;
  rounds: number;
  last_seen: number;
}

export interface MapRotationItem {
  map_name: string | null;
  map_display_name: string | null;
  game_mode: string | null;
  mode_display_name: string | null;
  map_image_url: string | null;
  is_current: boolean;
  /** 行动模式条目所属战役的全部地图（按进行顺序），其它模式为 null */
  operation: OperationMap[] | null;
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

export interface OperationMap {
  /** 地图代号（MP_*） */
  map_name: string;
  name: string;
  image_url: string | null;
  /** 该图区域数，未收录的地图为 null */
  sectors: number | null;
}

export interface OperationProgress {
  /** 本行动全部地图，按进行顺序 */
  maps: OperationMap[];
  map_index: number;
  /** 进攻方在当前地图已拿下的区域数 */
  sectors_taken: number;
  /** waiting 开局前；new 战役第一张图且攻方未丢营；running 其它对局中 */
  state: string | null;
  attacker: string | null;
  defender: string | null;
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
  operation: OperationProgress | null;
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
  guid: string | null;
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
 * 服务器自定义设置矩阵。EA 按网关账号语言给出繁体键，后端已换成简体（查不到的保留原文），
 * 值为 on/off；Scales 组的值是小数字符串（"1.0" = 100%）。各组可能整体缺失（非 RSP 服务器）。
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
  /** settings 条目简体名 → EA 官方说明（悬停提示用） */
  setting_descriptions: Record<string, string>;
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
  /** 在线人数最多的服务器（含排队），按人数降序 */
  top_servers: ServerSummary[];
}

/** 当前登录用户对某服务器的角色；role 为 null 且 is_platform_admin 为 false 表示无任何服管权限 */
export interface MyServerRole {
  role: "viewer" | "moderator" | "admin" | "owner" | null;
  is_platform_admin: boolean;
}

/** 「我的服务器」列表项：当前用户有服管角色的一台服务器 */
export interface MyServerItem {
  server_pk: number;
  game: string;
  server_id: number;
  /** 末次解析到的 EA gameId，详情页据此寻址；null = 尚未在线时识别，链接不可点 */
  game_id: number | null;
  name: string | null;
  role: "viewer" | "moderator" | "admin" | "owner";
}

export interface MyServersResponse {
  items: MyServerItem[];
}

/** 交换物品。rarity 为 EA rarenessLevel.name（Superior / Enhanced / Standard） */
export interface ExchangeItem {
  key: string;
  name: string;
  parent_name: string | null;
  category: string | null;
  rarity: string;
  price: number;
  image_url: string | null;
}

export interface ExchangeSnapshot {
  captured_at: string;
  items: ExchangeItem[];
}

export interface Campaign {
  name: string;
  description: string;
  ends_at: string;
  daily_reset_at: string;
  operations: { name: string; image_url: string | null }[];
}

export const bf1Api = {
  searchPlayers: (name: string) =>
    api.get<PersonaSearchResult>(`/bf1/players/search?name=${encodeURIComponent(name)}`),

  getPlayer: (personaId: number) => api.get<PersonaBrief>(`/bf1/players/${personaId}`),

  /** 批量取头像（persona_id → URL，取不到为 null），最多 200 个 */
  getAvatars: (personaIds: number[]) =>
    api.get<Record<string, string | null>>(
      `/bf1/players/avatars?${personaIds.map((id) => `ids=${id}`).join("&")}`,
    ),

  getStats: (personaId: number) => api.get<PlayerStatsDetail>(`/bf1/stats/${personaId}`),

  getWeapons: (personaId: number) => api.get<WeaponStats>(`/bf1/stats/${personaId}/weapons`),

  getVehicles: (personaId: number) => api.get<VehicleStats>(`/bf1/stats/${personaId}/vehicles`),

  getRecentServers: (personaId: number) =>
    api.get<RecentServers>(`/bf1/stats/${personaId}/recent-servers`),

  getOnline: (personaId: number) => api.get<OnlineStatus>(`/bf1/stats/${personaId}/online`),

  getPlatoon: (personaId: number) =>
    api.get<PlayerPlatoon | null>(`/bf1/stats/${personaId}/platoon`),

  /** 关键字少于 3 个字符时后端返回空列表 */
  searchPlatoons: (name: string) =>
    api.get<PlatoonSearchItem[]>(`/bf1/platoons?name=${encodeURIComponent(name)}`),
  getPlatoonDetail: (guid: string) =>
    api.get<PlatoonDetail>(`/bf1/platoons/${encodeURIComponent(guid)}`),

  getBan: (personaId: number, name?: string) =>
    api.get<BanStatus>(
      `/bf1/stats/${personaId}/ban${name ? `?name=${encodeURIComponent(name)}` : ""}`,
    ),

  listServers: (query: ServerListQuery = {}) => {
    const params = new URLSearchParams();
    if (query.name) params.set("name", query.name);
    // maps/modes/regions/sizes 作为重复 query 参数交后端筛选
    query.maps?.forEach((m) => params.append("maps", m));
    query.modes?.forEach((m) => params.append("modes", m));
    query.regions?.forEach((r) => params.append("regions", r));
    query.sizes?.forEach((s) => params.append("sizes", String(s)));
    if (query.includeEmpty) params.set("include_empty", "true");
    params.set("limit", String(query.limit ?? 200));
    return api.get<ServerListResponse>(`/bf1/servers?${params.toString()}`);
  },

  getServer: (gameId: number) => api.get<ServerDetail>(`/bf1/servers/${gameId}`),

  getServerPlayerCounts: (gameId: number) =>
    api.get<ServerPlayerCountPoint[]>(`/bf1/servers/${gameId}/player-counts`),
  getServerMapStats: (gameId: number, days = 7) =>
    api.get<ServerMapStat[]>(`/bf1/servers/${gameId}/map-stats?days=${days}`),
  getServerLeaderboard: (gameId: number, days = 7) =>
    api.get<ServerLeaderboard>(`/bf1/servers/${gameId}/leaderboard?days=${days}`),
  getServerSnapshots: (gameId: number, before?: number | null) =>
    api.get<ServerRosterPage>(
      `/bf1/servers/${gameId}/snapshots${before ? `?before=${before}` : ""}`,
    ),
  getServerSnapshot: (gameId: number, ts: number) =>
    api.get<ServerRosterSnapshot>(`/bf1/servers/${gameId}/snapshots/${ts}`),

  getServerRounds: (gameId: number, before?: number | null) =>
    api.get<RoundPage>(`/bf1/servers/${gameId}/rounds${before ? `?before=${before}` : ""}`),
  getRound: (roundId: number) => api.get<RoundDetail>(`/bf1/rounds/${roundId}`),
  getPlayerRounds: (personaId: number, before?: number | null) =>
    api.get<PlayerRoundPage>(`/bf1/stats/${personaId}/rounds${before ? `?before=${before}` : ""}`),

  getServerPlayers: (gameId: number, includeStats = true) =>
    api.get<ServerPlayersResponse>(
      `/bf1/servers/${gameId}/players?include_stats=${includeStats ? "true" : "false"}`,
    ),

  getOverview: () => api.get<BF1Overview>(`/bf1/overview`),

  /** date 为北京时间 YYYY-MM-DD，取当天生效的那一期；不传为最新一期 */
  getExchange: (date?: string) =>
    api.get<ExchangeSnapshot>(`/bf1/exchange${date ? `?date=${date}` : ""}`),
  /** 全部历史期的开始时间，新的在前 */
  getExchangePeriods: () => api.get<string[]>(`/bf1/exchange/periods`),
  /** 当前行动；没有进行中的行动时为 null */
  getCampaign: () => api.get<Campaign | null>(`/bf1/campaign`),

  // 当前登录用户对该服务器的角色，供前端按角色 gating 内联服管入口
  getMyServerRole: (gameId: number) => api.get<MyServerRole>(`/bf1/server-admin/${gameId}/my-role`),

  // 当前登录用户有服管角色的服务器列表（自动识别的服主 / 管理员 + 人工授权）
  getMyServers: () => api.get<MyServersResponse>(`/bf1/server-admin/mine`),

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

  getAutoSwitch: (gameId: number) =>
    api.get<AutoSwitchView>(`/bf1/server-admin/${gameId}/auto-switch`),
  saveAutoSwitchPlan: (gameId: number, plan: AutoSwitchPlan) =>
    api.put<AutoSwitchView>(`/bf1/server-admin/${gameId}/auto-switch/plan`, plan),
  enableAutoSwitch: (gameId: number) =>
    api.post<AutoSwitchView>(`/bf1/server-admin/${gameId}/auto-switch/enable`),
  disableAutoSwitch: (gameId: number) =>
    api.post<AutoSwitchView>(`/bf1/server-admin/${gameId}/auto-switch/disable`),
};

/** 自动换图编排的一项：operation 从这张图打完整个战役算一次，map 打完这一张算一次 */
export interface AutoSwitchItem {
  map: string;
  scope: "operation" | "map";
  repeat: number;
}

export interface AutoSwitchPlan {
  items: AutoSwitchItem[];
  /** 整轮循环次数，0 为一直循环 */
  loops: number;
}

export interface AutoSwitchView {
  enabled: boolean;
  plan: AutoSwitchPlan;
  cursor: number;
  done: number;
  loop: number;
  pending_map: string | null;
  enabled_by: string | null;
  enabled_at: number | null;
  events: { ts: number; kind: string; message: string }[];
}
