/**
 * BF1 读查询的 queryKey 与 queryFn 集中在这里，调用处只补 enabled / staleTime 等各自的选项：
 * useQuery({ ...bf1Queries.serverPlayers(gameId), staleTime: 15_000 })
 *
 * queryFn 都把 React Query 的 signal 传给请求，组件卸载或防抖搜索换词时旧请求随之取消。
 * 失效 / 写缓存用 bf1Keys，前缀匹配与原先的数组字面量一致。
 */
import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";
import { bf1Api, cardApi } from "@/lib/api/bf1";
import { groupsApi } from "@/lib/api/groups";

/** 服务器列表的筛选条件：数组已排序，作为 queryKey 的一部分 */
export interface ServerListSelection {
  maps: string[];
  modes: string[];
  regions: string[];
  sizes: number[];
  serverTypes: string[];
  /** 已按键排序的 vehicles.L:off 形式 */
  rules: string[];
  slots: string[];
  includeEmpty: boolean;
}

/**
 * 对局列表的筛选：结束时间在 [since, until) 内（选中某一天时），服务器对局可再按 player（personaId）、
 * 玩家对局可再按 server（gameId）筛。
 */
export interface RoundsFilter {
  since?: number;
  until?: number;
  player?: number;
  server?: number;
}

export const bf1Keys = {
  // 服务器
  servers: (selection: ServerListSelection, name: string) =>
    ["bf1-servers", selection, name] as const,
  serverFilterOptions: () => ["bf1-server-filter-options"] as const,
  server: (gameId: number) => ["bf1-server", gameId] as const,
  serverPlayers: (gameId: number) => ["bf1-server-players", gameId] as const,
  serverPlayerCounts: (gameId: number) => ["bf1-server-player-counts", gameId] as const,
  serverMapStats: (gameId: number) => ["bf1-server-map-stats", gameId] as const,
  serverLeaderboard: (gameId: number, days: number) =>
    ["bf1-server-leaderboard", gameId, days] as const,
  serverSnapshots: (gameId: number, jumpTo: number | null) =>
    ["bf1-server-snapshots", gameId, jumpTo] as const,
  serverSnapshot: (gameId: number, ts: number) => ["bf1-server-snapshot", gameId, ts] as const,
  serverVisits: (gameId: number, q: string) => ["bf1-server-visits", gameId, q] as const,
  serverRounds: (gameId: number, filter: RoundsFilter = {}) =>
    ["bf1-server-rounds", gameId, filter] as const,
  serverRoundDays: (gameId: number, tz: string, player: string | null) =>
    ["bf1-server-round-days", gameId, tz, player] as const,
  round: (roundId: number) => ["bf1-round", roundId] as const,
  serverGroups: (gameId: number) => ["bf1-server-groups", gameId] as const,

  // 服管
  myServers: () => ["bf1-my-servers"] as const,
  myServerRole: (gameId: number) => ["bf1-my-server-role", gameId] as const,
  timedVips: (gameId: number) => ["bf1-timed-vips", gameId] as const,
  autoSwitch: (gameId: number) => ["bf1-auto-switch", gameId] as const,
  cardJob: (id: number | undefined) => ["bf1-card-job", id] as const,

  // 玩家
  playerSearch: (q: string) => ["bf1-player-search", q.toLowerCase()] as const,
  avatars: (personaIds: number[]) => ["bf1-avatars", personaIds] as const,
  stats: (personaId: number) => ["bf1-stats", personaId] as const,
  player: (personaId: number) => ["bf1-player", personaId] as const,
  online: (personaId: number) => ["bf1-online", personaId] as const,
  playerPlatoon: (personaId: number) => ["bf1-player-platoon", personaId] as const,
  ban: (personaId: number, name: string | undefined) => ["bf1-ban", personaId, name] as const,
  weapons: (personaId: number) => ["bf1-weapons", personaId] as const,
  vehicles: (personaId: number) => ["bf1-vehicles", personaId] as const,
  playerServers: (personaId: number) => ["bf1-player-servers", personaId] as const,
  recent: (personaId: number) => ["bf1-recent", personaId] as const,
  collection: (personaId: number) => ["bf1-collection", personaId] as const,
  playerRounds: (personaId: number, filter: RoundsFilter = {}) =>
    ["bf1-player-rounds", personaId, filter] as const,
  playerRoundDays: (personaId: number, tz: string, server: number | null) =>
    ["bf1-player-round-days", personaId, tz, server] as const,

  // 战队
  platoonSearch: (q: string) => ["bf1-platoon-search", q.toLowerCase()] as const,
  platoonDetail: (guid: string) => ["bf1-platoon-detail", guid] as const,

  // 全站
  overview: () => ["bf1-overview"] as const,
  exchangePeriods: () => ["bf1-exchange-periods"] as const,
  exchange: (date: string | undefined) => ["bf1-exchange", date ?? "latest"] as const,
  campaign: () => ["bf1-campaign"] as const,
};

export const bf1Queries = {
  // ===== 服务器 =====
  servers: (selection: ServerListSelection, name: string) =>
    queryOptions({
      queryKey: bf1Keys.servers(selection, name),
      queryFn: ({ signal }) =>
        bf1Api.listServers(
          {
            name: name || undefined,
            maps: selection.maps.length ? selection.maps : undefined,
            modes: selection.modes.length ? selection.modes : undefined,
            regions: selection.regions.length ? selection.regions : undefined,
            sizes: selection.sizes.length ? selection.sizes : undefined,
            serverTypes: selection.serverTypes.length ? selection.serverTypes : undefined,
            rules: selection.rules.length ? selection.rules : undefined,
            slots: selection.slots.length ? selection.slots : undefined,
            includeEmpty: selection.includeEmpty || undefined,
            limit: 500,
          },
          { signal },
        ),
    }),
  /** 筛选目录是静态的，拿一次就够 */
  serverFilterOptions: () =>
    queryOptions({
      queryKey: bf1Keys.serverFilterOptions(),
      queryFn: ({ signal }) => bf1Api.getServerFilterOptions({ signal }),
      staleTime: Infinity,
      gcTime: Infinity,
    }),
  server: (gameId: number) =>
    queryOptions({
      queryKey: bf1Keys.server(gameId),
      queryFn: ({ signal }) => bf1Api.getServer(gameId, { signal }),
    }),
  /** 带全队战绩的实时名单 */
  serverPlayers: (gameId: number) =>
    queryOptions({
      queryKey: bf1Keys.serverPlayers(gameId),
      queryFn: ({ signal }) => bf1Api.getServerPlayers(gameId, undefined, { signal }),
    }),
  serverPlayerCounts: (gameId: number) =>
    queryOptions({
      queryKey: bf1Keys.serverPlayerCounts(gameId),
      queryFn: ({ signal }) => bf1Api.getServerPlayerCounts(gameId, { signal }),
    }),
  /** 默认 7 天 */
  serverMapStats: (gameId: number) =>
    queryOptions({
      queryKey: bf1Keys.serverMapStats(gameId),
      queryFn: ({ signal }) => bf1Api.getServerMapStats(gameId, undefined, { signal }),
    }),
  serverLeaderboard: (gameId: number, days: number) =>
    queryOptions({
      queryKey: bf1Keys.serverLeaderboard(gameId, days),
      queryFn: ({ signal }) => bf1Api.getServerLeaderboard(gameId, days, { signal }),
    }),
  /** jumpTo 为空从最新一页开始，否则从该时刻往前翻 */
  serverSnapshots: (gameId: number, jumpTo: number | null) =>
    infiniteQueryOptions({
      queryKey: bf1Keys.serverSnapshots(gameId, jumpTo),
      queryFn: ({ pageParam, signal }) => bf1Api.getServerSnapshots(gameId, pageParam, { signal }),
      initialPageParam: jumpTo,
      getNextPageParam: (last) => last.next_before,
    }),
  serverSnapshot: (gameId: number, ts: number) =>
    queryOptions({
      queryKey: bf1Keys.serverSnapshot(gameId, ts),
      queryFn: ({ signal }) => bf1Api.getServerSnapshot(gameId, ts, { signal }),
    }),
  serverVisits: (gameId: number, q: string) =>
    queryOptions({
      queryKey: bf1Keys.serverVisits(gameId, q),
      queryFn: ({ signal }) => bf1Api.getServerVisits(gameId, q, { signal }),
    }),
  /** filter.until 是这一天的结束（不含），翻页时由 next_before 接着往前 */
  serverRounds: (gameId: number, filter: RoundsFilter = {}) =>
    infiniteQueryOptions({
      queryKey: bf1Keys.serverRounds(gameId, filter),
      queryFn: ({ pageParam, signal }) =>
        bf1Api.getServerRounds(
          gameId,
          { before: pageParam ?? filter.until, since: filter.since, player: filter.player },
          { signal },
        ),
      initialPageParam: null as number | null,
      getNextPageParam: (last) => last.next_before,
    }),
  /** player 是名字或 PID，对不上时 404 */
  serverRoundDays: (gameId: number, tz: string, player: string | null) =>
    queryOptions({
      queryKey: bf1Keys.serverRoundDays(gameId, tz, player),
      queryFn: ({ signal }) => bf1Api.getServerRoundDays(gameId, tz, player, { signal }),
    }),
  round: (roundId: number) =>
    queryOptions({
      queryKey: bf1Keys.round(roundId),
      queryFn: ({ signal }) => bf1Api.getRound(roundId, { signal }),
    }),
  /** 挂着这台服的群（服主视图） */
  serverGroups: (gameId: number) =>
    queryOptions({
      queryKey: bf1Keys.serverGroups(gameId),
      queryFn: ({ signal }) => groupsApi.serverGroups(gameId, { signal }),
    }),

  // ===== 服管 =====
  myServers: () =>
    queryOptions({
      queryKey: bf1Keys.myServers(),
      queryFn: ({ signal }) => bf1Api.getMyServers({ signal }),
    }),
  myServerRole: (gameId: number) =>
    queryOptions({
      queryKey: bf1Keys.myServerRole(gameId),
      queryFn: ({ signal }) => bf1Api.getMyServerRole(gameId, { signal }),
    }),
  timedVips: (gameId: number) =>
    queryOptions({
      queryKey: bf1Keys.timedVips(gameId),
      queryFn: ({ signal }) => bf1Api.getTimedVips(gameId, { signal }),
    }),
  autoSwitch: (gameId: number) =>
    queryOptions({
      queryKey: bf1Keys.autoSwitch(gameId),
      queryFn: ({ signal }) => bf1Api.getAutoSwitch(gameId, { signal }),
    }),
  /** 卡行动任务；job 为空时调用方须 enabled: false */
  cardJob: (job: { id: number; token: string | null } | null) =>
    queryOptions({
      queryKey: bf1Keys.cardJob(job?.id),
      queryFn: ({ signal }) => cardApi.get(job!.id, job!.token, { signal }),
    }),

  // ===== 玩家 =====
  /** key 按小写去重，请求带原始大小写 */
  playerSearch: (q: string) =>
    queryOptions({
      queryKey: bf1Keys.playerSearch(q),
      queryFn: ({ signal }) => bf1Api.searchPlayers(q, { signal }),
    }),
  avatars: (personaIds: number[]) =>
    queryOptions({
      queryKey: bf1Keys.avatars(personaIds),
      queryFn: ({ signal }) => bf1Api.getAvatars(personaIds, { signal }),
    }),
  stats: (personaId: number) =>
    queryOptions({
      queryKey: bf1Keys.stats(personaId),
      queryFn: ({ signal }) => bf1Api.getStats(personaId, { signal }),
    }),
  player: (personaId: number) =>
    queryOptions({
      queryKey: bf1Keys.player(personaId),
      queryFn: ({ signal }) => bf1Api.getPlayer(personaId, { signal }),
    }),
  online: (personaId: number) =>
    queryOptions({
      queryKey: bf1Keys.online(personaId),
      queryFn: ({ signal }) => bf1Api.getOnline(personaId, { signal }),
    }),
  /** 玩家所在战队（按 personaId），与 platoonDetail 是两种数据 */
  playerPlatoon: (personaId: number) =>
    queryOptions({
      queryKey: bf1Keys.playerPlatoon(personaId),
      queryFn: ({ signal }) => bf1Api.getPlatoon(personaId, { signal }),
    }),
  ban: (personaId: number, name: string | undefined) =>
    queryOptions({
      queryKey: bf1Keys.ban(personaId, name),
      queryFn: ({ signal }) => bf1Api.getBan(personaId, name, { signal }),
    }),
  weapons: (personaId: number) =>
    queryOptions({
      queryKey: bf1Keys.weapons(personaId),
      queryFn: ({ signal }) => bf1Api.getWeapons(personaId, { signal }),
    }),
  vehicles: (personaId: number) =>
    queryOptions({
      queryKey: bf1Keys.vehicles(personaId),
      queryFn: ({ signal }) => bf1Api.getVehicles(personaId, { signal }),
    }),
  playerServers: (personaId: number) =>
    queryOptions({
      queryKey: bf1Keys.playerServers(personaId),
      queryFn: ({ signal }) => bf1Api.getPlayerServers(personaId, { signal }),
    }),
  recent: (personaId: number) =>
    queryOptions({
      queryKey: bf1Keys.recent(personaId),
      queryFn: ({ signal }) => bf1Api.getRecentServers(personaId, { signal }),
    }),
  collection: (personaId: number) =>
    queryOptions({
      queryKey: bf1Keys.collection(personaId),
      queryFn: ({ signal }) => bf1Api.getCollection(personaId, { signal }),
    }),
  playerRounds: (personaId: number, filter: RoundsFilter = {}) =>
    infiniteQueryOptions({
      queryKey: bf1Keys.playerRounds(personaId, filter),
      queryFn: ({ pageParam, signal }) =>
        bf1Api.getPlayerRounds(
          personaId,
          { before: pageParam, since: filter.since, until: filter.until, server: filter.server },
          { signal },
        ),
      initialPageParam: null as number | null,
      getNextPageParam: (last) => last.next_before,
    }),
  playerRoundDays: (personaId: number, tz: string, server: number | null) =>
    queryOptions({
      queryKey: bf1Keys.playerRoundDays(personaId, tz, server),
      queryFn: ({ signal }) => bf1Api.getPlayerRoundDays(personaId, tz, server, { signal }),
    }),

  // ===== 战队 =====
  /** key 按小写去重，请求带原始大小写 */
  platoonSearch: (q: string) =>
    queryOptions({
      queryKey: bf1Keys.platoonSearch(q),
      queryFn: ({ signal }) => bf1Api.searchPlatoons(q, { signal }),
    }),
  platoonDetail: (guid: string) =>
    queryOptions({
      queryKey: bf1Keys.platoonDetail(guid),
      queryFn: ({ signal }) => bf1Api.getPlatoonDetail(guid, { signal }),
    }),

  // ===== 全站 =====
  overview: () =>
    queryOptions({
      queryKey: bf1Keys.overview(),
      queryFn: ({ signal }) => bf1Api.getOverview({ signal }),
    }),
  exchangePeriods: () =>
    queryOptions({
      queryKey: bf1Keys.exchangePeriods(),
      queryFn: ({ signal }) => bf1Api.getExchangePeriods({ signal }),
    }),
  /** date 不传为最新一期 */
  exchange: (date: string | undefined) =>
    queryOptions({
      queryKey: bf1Keys.exchange(date),
      queryFn: ({ signal }) => bf1Api.getExchange(date, { signal }),
    }),
  campaign: () =>
    queryOptions({
      queryKey: bf1Keys.campaign(),
      queryFn: ({ signal }) => bf1Api.getCampaign({ signal }),
    }),
};
