"use client";

/**
 * BF1 服务器详情页（战地视觉：全屏地图背景 + 切角面板 + Tab 分页）
 *
 * 视觉语言与玩家详情页对齐：以服务器「当前地图大图」作为全屏模糊背景与 Hero 主体，
 * 用 Bf1Panel 切角面板承载信息，amber 下划线 Tab 导航。Tab 内容（玩家 / 轮换 /
 * 成员 / 审计）沿用既有数据与操作逻辑，仅置于半透明深色面板内保证可读。
 */

import { useMemo, useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useBack } from "@/hooks/useNavigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRightLeft } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import {
  DetailBackground,
  DetailError,
  DetailNote,
} from "@/components/bf1/visual/DetailBackground";
import { ServerDetailSkeleton } from "@/components/layout/PageSkeleton";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";
import {
  ServerAdminProvider,
  useServerAdmin,
  PlayerRowActions,
  TeamSelectAllCheckbox,
  BatchActionBar,
} from "@/components/bf1/server-admin/InlineServerAdmin";
import { SectionNav, useTabHash } from "@/components/bf1/SectionNav";
import { MembersPanel } from "@/components/bf1/server-admin/MembersPanel";
import { AutoSwitchPanel } from "@/components/bf1/server-detail/AutoSwitchPanel";
import { LeaderboardPanel } from "@/components/bf1/server-detail/LeaderboardPanel";
import { RoundsPanel } from "@/components/bf1/server-detail/RoundsPanel";
import { MapStatsPanel } from "@/components/bf1/server-detail/MapStatsPanel";
import { ServerAboutPanel } from "@/components/bf1/server-detail/ServerAboutPanel";
import { ServerProfilePanel } from "@/components/bf1/server-detail/ServerProfilePanel";
import { ServerHeroBanner } from "@/components/bf1/server-detail/ServerHeroBanner";
import { ServerHistoryPanel } from "@/components/bf1/server-detail/ServerHistoryPanel";
import { SnapshotPanel } from "@/components/bf1/server-detail/SnapshotPanel";
import {
  GAP_SECONDS,
  buildMapColors,
  formatDuration,
  mapKey,
  toMapSegments,
  useNowSeconds,
} from "@/components/bf1/server-detail/history";
import { nextMap, operationKey, operationStep } from "@/components/bf1/server-detail/operation";
import { useMyServerRole } from "@/hooks/useServerAdminActions";
import { useSession } from "@/hooks/useSession";
import { auditApi, type AuditLogItem } from "@/lib/api/audit";
import { FACTION_SLUG } from "@/lib/bf1/factions";
import { canDo } from "@/lib/bf1/server-admin-authz";
import { cn } from "@/lib/utils";
import {
  bf1Api,
  type ServerDetail,
  type ServerSettings,
  type MapRotationItem,
  type ServerMapStat,
  type BlazePlayer,
  type BlazeTeamGroup,
  type ServerPlayersResponse,
} from "@/lib/api/bf1";

const ACTION_LABEL: Record<string, string> = {
  kick_player: "踢人",
  add_ban: "封禁",
  remove_ban: "解封",
  choose_level: "换图",
  add_vip: "添加 VIP",
  remove_vip: "移除 VIP",
  vip_apply: "VIP 立即生效",
  vip_expire: "VIP 到期移除",
  add_admin: "添加管理员",
  remove_admin: "移除管理员",
  auto_switch_enable: "开启自动换图",
  auto_switch_disable: "关闭自动换图",
  card_start: "开始卡行动",
  card_anchor: "手动锚定",
  card_success: "卡行动完成",
  card_fail: "卡行动失败",
  card_restore: "恢复卡行动前设置",
};

const TAB_KEYS = [
  "overview",
  "players",
  "snapshots",
  "rounds",
  "leaderboard",
  "maps",
  "autoswitch",
  "rules",
  "members",
  "audit",
] as const;
type TabKey = (typeof TAB_KEYS)[number];

export default function ServerDetailPage() {
  const { id, game } = useParams<{ id: string; game: string }>();
  // 回到真正来的那一页（保留列表筛选），直接打开时退到服务器列表
  const back = useBack(`/${game}/servers`);
  const gameId = Number(id);

  const detail = useQuery({
    queryKey: ["bf1-server", gameId],
    queryFn: () => bf1Api.getServer(gameId),
    enabled: Number.isFinite(gameId),
  });

  if (!Number.isFinite(gameId)) {
    return <DetailNote text="无效的服务器 ID" />;
  }
  if (detail.isLoading) {
    return <ServerDetailSkeleton />;
  }
  if (!detail.data) {
    return (
      <DetailError
        error={detail.error}
        notFoundText="没有找到这台服务器"
        onRetry={() => void detail.refetch()}
        retrying={detail.isFetching}
      />
    );
  }

  return <ServerDetailView gameId={gameId} game={game} detail={detail.data} onBack={back} />;
}

function ServerDetailView({
  gameId,
  game,
  detail,
  onBack,
}: {
  gameId: number;
  game: string;
  detail: ServerDetail;
  onBack: () => void;
}) {
  const session = useSession();
  const isLoggedIn = !!session.data;
  const { map_rotation, extras } = detail;
  const memberCount = extras.admins.length + extras.vips.length + extras.banned.length;
  // 自动换图只对行动服的服管开放
  const isOperationServer = map_rotation.some((m) => m.operation);
  const myRole = useMyServerRole(gameId, isLoggedIn && isOperationServer);
  const canAutoSwitch = canDo("kick", myRole.data);

  // 实时名单要等 Blaze 与战绩好几秒，进页就在后台预取，切到「玩家」分区时直接可用
  const players = useQuery({
    queryKey: ["bf1-server-players", gameId],
    queryFn: () => bf1Api.getServerPlayers(gameId),
    staleTime: 15_000,
    // 行动服的区域进度随对局推进，页面可见时定时刷新；战绩后端按玩家缓存 10 分钟，刷新多半命中缓存
    refetchInterval: (q) => (q.state.data?.operation ? 30_000 : false),
  });
  // 详情按 Gateway 缓存更新慢，人数以实时名单为准（名单定时刷新，横幅与分区计数随之同步）
  const summary = useMemo(() => {
    const live = players.data;
    return live && !live.is_mock
      ? {
          ...detail.summary,
          player_count: live.player_count,
          queue_count: live.queue_count,
          spectator_count: live.spectator_count,
        }
      : detail.summary;
  }, [detail.summary, players.data]);

  const tabs: ReadonlyArray<{ key: TabKey; label: string; count?: number }> = [
    { key: "overview", label: "概览" },
    { key: "players", label: "玩家", count: summary.player_count },
    { key: "snapshots", label: "快照" },
    { key: "rounds", label: "对局" },
    { key: "leaderboard", label: "排行" },
    { key: "maps", label: "地图", count: map_rotation.length },
    ...(canAutoSwitch ? ([{ key: "autoswitch", label: "自动换图" }] as const) : []),
    { key: "rules", label: "规则" },
    { key: "members", label: "成员", count: memberCount },
    ...(isLoggedIn ? ([{ key: "audit", label: "审计" }] as const) : []),
  ];
  const [tab, setTab] = useTabHash(
    TAB_KEYS,
    tabs.map((t) => t.key),
  );

  // 人数采样每分钟一次，刚开的服还没有点；空列表时战况与热门地图整块不渲染
  const counts = useQuery({
    queryKey: ["bf1-server-player-counts", gameId],
    queryFn: () => bf1Api.getServerPlayerCounts(gameId),
    refetchInterval: 60_000,
  });
  const mapStats = useQuery({
    queryKey: ["bf1-server-map-stats", gameId],
    queryFn: () => bf1Api.getServerMapStats(gameId),
    staleTime: 5 * 60_000,
  });
  const points = useMemo(() => counts.data ?? [], [counts.data]);
  const stats = useMemo(() => mapStats.data ?? [], [mapStats.data]);
  const now = useNowSeconds();

  const colors = useMemo(
    () =>
      buildMapColors([
        ...stats.map((m) => m.map_name),
        ...points.flatMap((p) => (p.map_name ? [p.map_name] : [])),
      ]),
    [stats, points],
  );
  const mapInfo = useMemo(() => {
    const byMap = new Map(stats.map((m) => [m.map_name, m]));
    const byKey = new Map(stats.map((m) => [mapKey(m.map_name, m.game_mode), m]));
    return (mapName: string, mode: string | null) => ({
      name: byMap.get(mapName)?.map_display_name ?? mapName,
      mode: byKey.get(mapKey(mapName, mode))?.mode_display_name ?? mode,
    });
  }, [stats]);
  // 当前这张图已进行多久：最新采样还新鲜、且与详情里的当前地图一致时才采信
  const elapsedMinutes = useMemo(() => {
    const segs = toMapSegments(points);
    const last = segs[segs.length - 1];
    const fresh = last && now - last.end < GAP_SECONDS;
    return fresh && last.mapName === summary.map_name ? (now - last.start) / 60 : null;
  }, [points, summary.map_name, now]);

  return (
    <div className="relative min-h-screen w-full text-white">
      <DetailBackground url={summary.map_image_url} />

      <div className="relative z-10 max-w-[1600px] px-4 pt-4 pb-6 sm:px-10 sm:py-8">
        <button
          type="button"
          onClick={onBack}
          className="mb-4 hidden items-center gap-1.5 text-sm text-white/55 transition-colors hover:text-white lg:inline-flex"
        >
          <ArrowLeft className="size-4" />
          返回
        </button>

        <ServerHeroBanner
          summary={summary}
          extras={extras}
          rotation={map_rotation}
          elapsedMinutes={elapsedMinutes}
          operation={players.data?.operation ?? null}
        />

        <SectionNav tabs={tabs} tab={tab} onTab={setTab} />

        {/* Provider 包裹整个分区，让玩家、地图、成员共享同一份角色查询与确认机制 */}
        <ServerAdminProvider gameId={gameId}>
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
            className="mt-4 sm:mt-6"
          >
            {tab === "overview" && (
              <div className="space-y-4 sm:space-y-6">
                {points.length > 1 ? (
                  <div className="grid grid-cols-1 gap-4 sm:gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
                    <ServerHistoryPanel points={points} colors={colors} mapInfo={mapInfo} />
                    {stats.length > 0 ? (
                      <MapStatsPanel stats={stats} colors={colors} currentMap={summary.map_name} />
                    ) : null}
                  </div>
                ) : null}
                <div className="grid grid-cols-1 gap-4 sm:gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
                  <ServerAboutPanel
                    description={summary.description}
                    settings={detail.settings}
                    descriptions={detail.setting_descriptions}
                    onShowRules={() => setTab("rules")}
                  />
                  <ServerProfilePanel extras={extras} now={now} game={game} />
                </div>
              </div>
            )}
            {tab === "players" && (
              <Panel>
                <PlayersList gameId={gameId} game={game} />
              </Panel>
            )}
            {tab === "snapshots" && <SnapshotPanel gameId={gameId} game={game} mapInfo={mapInfo} />}
            {tab === "rounds" && <RoundsPanel gameId={gameId} game={game} />}
            {tab === "leaderboard" && <LeaderboardPanel gameId={gameId} game={game} />}
            {tab === "maps" && (
              <>
                {!summary.is_official ? (
                  <p className="mb-3 text-xs text-white/55">
                    服主可以用{" "}
                    <Link
                      href={`/bf1/card?gameId=${gameId}`}
                      className="inline-action text-amber-400 hover:underline"
                    >
                      一键卡行动
                    </Link>{" "}
                    把这台服卡成 24 图行动，已经是行动服的也可以用它补锚定。
                  </p>
                ) : null}
                <RotationGrid
                  items={map_rotation}
                  stats={stats}
                  colors={colors}
                  serverInitialized={summary.persisted_game_id != null}
                />
              </>
            )}
            {tab === "autoswitch" && canAutoSwitch && (
              <AutoSwitchPanel
                gameId={gameId}
                rotation={map_rotation}
                canEdit={canDo("chooseLevel", myRole.data)}
              />
            )}
            {tab === "rules" && (
              <Panel>
                <SettingsMatrix
                  settings={detail.settings}
                  descriptions={detail.setting_descriptions}
                />
              </Panel>
            )}
            {tab === "members" && (
              <Panel>
                <MembersPanel game={game} gameId={gameId} extras={extras} />
              </Panel>
            )}
            {tab === "audit" && isLoggedIn && (
              <Panel>
                <ServerAuditTab game={game} gameId={gameId} />
              </Panel>
            )}
          </motion.div>
        </ServerAdminProvider>
      </div>
    </div>
  );
}

/* ----------------------------- 自定义设置矩阵 ----------------------------- */

/**
 * 复刻游戏「伺服器資訊」的四列设置矩阵。数据来自 detail.settings，后端已把 EA 的繁体
 * 条目名换成简体，值为 on/off；Scales 组的值是小数字符串（"1.0"=100%）。
 * descriptions 是条目名 → EA 官方说明，作悬停提示；后端查不到的条目保留繁体、无说明。
 * 某一组整组缺失时（非 RSP 服务器）跳过该列；全部缺失时整块不渲染。
 */
function SettingsMatrix({
  settings,
  descriptions,
}: {
  settings: ServerSettings;
  descriptions: Record<string, string>;
}) {
  const columns = (
    [
      {
        title: "兵种 / 载具",
        entries: [...toEntries(settings.Kits), ...toEntries(settings.Vehicles)],
        kind: "toggle",
      },
      { title: "武器", entries: toEntries(settings.Weapons), kind: "toggle" },
      { title: "进阶", entries: toEntries(settings.Misc), kind: "toggle" },
      { title: "规则", entries: toEntries(settings.Scales), kind: "scale" },
    ] as const
  ).filter((c) => c.entries.length > 0);

  if (columns.length === 0) {
    return <div className="py-8 text-center text-sm text-white/40">该服务器没有自定义规则</div>;
  }

  return (
    <div className="grid grid-cols-1 gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-4">
      {columns.map((col) => (
        <section key={col.title}>
          <h3 className="mb-2 border-b border-white/10 pb-1.5 text-xs font-semibold tracking-wider text-white/55">
            {col.title}
          </h3>
          <dl className="space-y-1.5">
            {col.entries.map(([label, value]) => (
              <div key={label} className="flex items-baseline justify-between gap-3 text-sm">
                <dt
                  className={cn(
                    "min-w-0 truncate text-white/65",
                    descriptions[label] && "cursor-help",
                  )}
                  title={descriptions[label] ?? label}
                >
                  {label}
                </dt>
                <dd className="shrink-0">
                  <SettingValue value={value} kind={col.kind} />
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}

/** 把可能缺失的设置分组安全转成 [键, 值] 列表 */
function toEntries(group: Record<string, string> | undefined): [string, string][] {
  if (!group || typeof group !== "object") return [];
  return Object.entries(group).map(([k, v]) => [k, String(v)]);
}

function SettingValue({ value, kind }: { value: string; kind: "toggle" | "scale" }) {
  if (kind === "scale") {
    const num = Number(value);
    const text = Number.isFinite(num) ? `${Math.round(num * 100)}%` : value;
    return <span className="text-white/90 tabular-nums">{text}</span>;
  }
  const on = value.toLowerCase() === "on";
  return (
    <span className={cn("font-medium tabular-nums", on ? "text-amber-300" : "text-white/35")}>
      {on ? "开" : "关"}
    </span>
  );
}

/* ----------------------------- Tab 导航与通用面板 ----------------------------- */

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <Bf1Panel cut={20} className="p-4 sm:p-6" style={{ background: "rgba(12,12,15,0.72)" }}>
      {children}
    </Bf1Panel>
  );
}

/* ----------------------------- 玩家列表（Blaze 实时名单） ----------------------------- */

/**
 * 复刻群版「服务器玩家列表」效果：按阵营分双列，逐行展示等级 / 玩家名 / 胜率 / K-D /
 * KPM / 时长 / 延迟 / 语言。在线管理员以绿色高亮、VIP 以红色、平台已绑定用户（群友）以
 * 蓝色高亮；满级（150）等级以琥珀色方框突出。数据走独立的 Blaze 玩家列表接口拉取，与
 * 详情主体分开加载，避免实时名单的耗时拖慢页面其余部分。
 */
function PlayersList({ gameId, game }: { gameId: number; game: string }) {
  const query = useQuery({
    queryKey: ["bf1-server-players", gameId],
    queryFn: () => bf1Api.getServerPlayers(gameId),
    enabled: Number.isFinite(gameId),
    // 实时名单变动频繁，缓存短时即可；窗口聚焦时自动刷新交给 react-query 默认行为。
    staleTime: 15_000,
  });

  if (query.isLoading) {
    return <div className="py-10 text-center text-sm text-white/40">正在拉取实时玩家名单…</div>;
  }
  if (query.isError || !query.data) {
    return (
      <div className="py-10 text-center text-sm text-white/45">
        实时玩家名单暂时不可用（Blaze 连接失败或服务器未在线）
      </div>
    );
  }

  return <ServerPlayersView data={query.data} game={game} />;
}

/**
 * 玩家列表纯展示层（与数据获取解耦，便于用 mock 数据独立预览）。
 */
export function ServerPlayersView({ data, game }: { data: ServerPlayersResponse; game: string }) {
  const teams = data.teams;
  const hasPlayers =
    teams.some((t) => t.players.length > 0) || data.queued.length > 0 || data.spectators.length > 0;

  if (!hasPlayers) {
    return <div className="py-10 text-center text-sm text-white/40">服务器内暂无玩家</div>;
  }

  return (
    <div className="text-white/90">
      {data.is_mock ? (
        <div className="mb-3 inline-block rounded-sm border border-amber-400/30 bg-amber-500/10 px-2.5 py-1 text-[11px] text-amber-200/90">
          演示数据（BLAZE_MOCK_MODE 已开启），非真实房间名单
        </div>
      ) : null}

      {/* 多选批量操作栏：仅服管可见、选中玩家后浮现（含队列 / 旁观玩家） */}
      <BatchActionBar
        players={[...teams.flatMap((t) => t.players), ...data.queued, ...data.spectators]}
      />

      {/* 双阵营并排，中间以竖线分割，与群版整图风格一致 */}
      <div className="grid grid-cols-1 gap-x-8 gap-y-8 lg:grid-cols-2">
        {teams.map((team, idx) => (
          <TeamColumn
            key={team.team_id}
            team={team}
            index={idx}
            game={game}
            className={idx > 0 ? "lg:border-l lg:border-white/15 lg:pl-8" : undefined}
          />
        ))}
      </div>

      {data.queued.length > 0 || data.spectators.length > 0 ? (
        <div className="mt-7 space-y-3 border-t border-white/10 pt-4">
          {data.queued.length > 0 ? (
            <SidePlayerGroup title="排队中" players={data.queued} game={game} />
          ) : null}
          {data.spectators.length > 0 ? (
            <SidePlayerGroup title="旁观者" players={data.spectators} game={game} />
          ) : null}
        </div>
      ) : null}

      <PlayerLegend
        summary={data.summary}
        playerCount={data.player_count}
        maxPlayers={data.max_players}
        statsIncluded={data.stats_included}
        className="mt-4 sm:mt-6"
      />
    </div>
  );
}

const MAX_RANK = 150;

type TeamAverage = {
  rank: number | null;
  winRate: number | null;
  kd: number | null;
  kpm: number | null;
  hours: number | null;
};

/** 计算单列底部「平均」行：等级取整、战绩各项按有数据者求均值 */
function computeTeamAverage(players: BlazePlayer[]): TeamAverage {
  const mean = (values: number[]): number | null =>
    values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
  const pick = (fn: (p: BlazePlayer) => number | null | undefined): number[] =>
    players.map(fn).filter((v): v is number => typeof v === "number");

  const ranks = pick((p) => (p.rank > 0 ? p.rank : null));
  const rankMean = mean(ranks);
  return {
    rank: rankMean == null ? null : Math.round(rankMean),
    winRate: mean(pick((p) => p.stats?.win_rate)),
    kd: mean(pick((p) => p.stats?.kd)),
    kpm: mean(pick((p) => p.stats?.kpm)),
    hours: mean(pick((p) => p.stats?.time_hours)),
  };
}

function TeamColumn({
  team,
  index,
  game,
  className,
}: {
  team: BlazeTeamGroup;
  index: number;
  game: string;
  className?: string;
}) {
  const { canManage } = useServerAdmin();
  const title = team.faction ?? `队伍 ${index + 1}`;
  const slug = team.faction ? FACTION_SLUG[team.faction] : undefined;
  const avg = computeTeamAverage(team.players);
  // 有服管权限时在行尾追加一列（复选框 + ⋯ 菜单），列数随之变化，占位行与平均行的 colSpan 同步。
  const totalCols = canManage ? 10 : 9;

  return (
    // 列容器在 grid 中等高（items-stretch），table 撑满高度后由占位空行把平均行顶到列底，
    // 使两列平均行对齐同一底线；不用 table-fixed，玩家名列才能自适应吃满剩余宽度。
    <div className={cn("h-full", className)}>
      {/* 移动端(<lg)：密集战绩表宽于窄屏，裹 overflow-x-auto 让整表可左右滑动查看，
          避免右侧「延迟/语言/操作」列被推出视口而看不见、点不到；桌面双列各有空间，
          lg:overflow-x-visible + lg:min-w-0 完全保持原样不滚动。 */}
      <div className="h-full overflow-x-auto lg:overflow-x-visible">
        <table className="h-full w-full min-w-[26rem] border-collapse text-[12.5px] tabular-nums lg:min-w-0">
          {/* 自适应布局：数字列按 colgroup 宽取最小宽，名字列由 td 的 w-full+max-w-0 吃满剩余并截断长名 */}
          <colgroup>
            <col className="w-6" />
            <col className="w-10" />
            <col />
            <col className="w-12" />
            <col className="w-11" />
            <col className="w-11" />
            <col className="w-14" />
            <col className="w-12" />
            <col className="w-8" />
            {canManage ? <col className="w-16" /> : null}
          </colgroup>
          <thead>
            {/* 阵营标题行：旗帜 + 阵营名 + 人数，跨越序号/等级/玩家三列 */}
            <tr className="align-bottom">
              <th colSpan={3} className="pb-2 text-left">
                <span className="flex items-center gap-2.5 whitespace-nowrap">
                  {slug ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={`/factions/${slug}.png`}
                      alt={title}
                      className="h-9 w-9 shrink-0 object-contain drop-shadow"
                    />
                  ) : null}
                  <span className="text-[17px] leading-none font-bold tracking-wide text-white">
                    {title}
                  </span>
                  <span className="text-xs text-white/45 tabular-nums">{team.count}</span>
                </span>
              </th>
              <ColHeader className="pl-3">胜率</ColHeader>
              <ColHeader className="pl-3">K/D</ColHeader>
              <ColHeader className="pl-3">KPM</ColHeader>
              <ColHeader className="pl-3">时长</ColHeader>
              <ColHeader className="text-center">延迟</ColHeader>
              <ColHeader className="text-center">语言</ColHeader>
              {canManage ? (
                // 镜像行内 actions 单元格布局（选择框 + ⋯ 占位），让表头全选框与行内复选框同列对齐
                <th className="pb-2 align-bottom">
                  <div className="flex items-center justify-end gap-1.5">
                    <TeamSelectAllCheckbox players={team.players} />
                    <span className="size-6" aria-hidden />
                  </div>
                </th>
              ) : null}
            </tr>
          </thead>
          {/* 表头下的整条横线，呼应原图分隔样式 */}
          <tbody className="border-t border-white/25">
            {team.players.map((p, i) => (
              <PlayerRow key={p.persona_id} player={p} seq={i + 1} game={game} />
            ))}
            {/* 占位空行吸收剩余高度，把下方平均行顶到列底，实现两列平均行对齐 */}
            <tr aria-hidden className="h-full">
              <td colSpan={totalCols} />
            </tr>
          </tbody>
          <tfoot>
            <tr className="border-t border-white/20 text-[12px] font-semibold text-amber-300/90">
              <td colSpan={3} className="pt-2 pl-0.5">
                平均 {avg.rank ?? "—"}
              </td>
              <td className="pt-2 pl-3 text-right">{formatPercent(avg.winRate)}</td>
              <td className="pt-2 pl-3 text-right">{formatRatio(avg.kd)}</td>
              <td className="pt-2 pl-3 text-right">{formatRatio(avg.kpm)}</td>
              <td className="pt-2 pl-3 text-right">{formatHours(avg.hours)}</td>
              <td className="pt-2" />
              <td className="pt-2" />
              {canManage ? <td className="pt-2" /> : null}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

function ColHeader({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <th
      className={cn(
        "pb-2 text-right text-[11px] font-medium tracking-wide whitespace-nowrap text-white/55",
        className,
      )}
    >
      {children}
    </th>
  );
}

function PlayerRow({ player, seq, game }: { player: BlazePlayer; seq: number; game: string }) {
  const { canManage } = useServerAdmin();
  const stats = player.stats;
  const dot = roleDot(player);
  return (
    <tr className="border-b border-white/[0.06] transition-colors last:border-0 hover:bg-white/[0.05]">
      <td className="py-[5px] pr-1 text-right text-[11px] text-white/35">{seq}</td>
      <td className="py-[5px] text-center">
        <RankBadge rank={player.rank} />
      </td>
      {/* 名字列：移动端(<lg)限宽 9rem 截断，让胜率 / K/D / KPM 在一屏内露出来，其余列由外层
          overflow-x-auto 横滑查看；桌面(lg)恢复 max-w-0 + truncate，让名字吃满剩余宽度。 */}
      <td className="w-full max-w-[9rem] py-[5px] pr-2 pl-2 lg:max-w-0">
        <Link
          href={`/${game}/player/${player.persona_id}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex min-w-0 items-center gap-1.5 hover:underline"
          title={`${player.display_name}（在新标签查看战绩）`}
        >
          {dot ? <span className={cn("size-1.5 shrink-0 rounded-full", dot)} /> : null}
          <span className={cn("min-w-0 truncate font-medium whitespace-nowrap", nameColor(player))}>
            {player.display_name}
          </span>
        </Link>
      </td>
      <td className="py-[5px] pl-3 text-right text-white/85">{formatPercent(stats?.win_rate)}</td>
      <td className="py-[5px] pl-3 text-right text-white/85">{formatRatio(stats?.kd)}</td>
      <td className="py-[5px] pl-3 text-right text-white/60">{formatRatio(stats?.kpm)}</td>
      <td className="py-[5px] pl-3 text-right text-white/60">{formatHours(stats?.time_hours)}</td>
      <td className="py-[5px] pl-2">
        <LatencyCell latency={player.latency} />
      </td>
      <td className="py-[5px] text-center text-white/65">{player.language || "—"}</td>
      {canManage ? (
        <td className="py-[5px] pl-2">
          <PlayerRowActions player={player} />
        </td>
      ) : null}
    </tr>
  );
}

/** 高亮优先级：管理员（绿）> VIP（红）> 已绑定用户（蓝）> 普通（白） */
function nameColor(p: BlazePlayer): string {
  if (p.is_admin) return "text-green-400";
  if (p.is_vip) return "text-red-400";
  if (p.is_registered) return "text-sky-400";
  return "text-white/90";
}

/** 名字前的角色圆点，与字色同源，弱辨识场景下也能一眼区分管理/VIP/已绑定 */
function roleDot(p: BlazePlayer): string | null {
  if (p.is_admin) return "bg-green-400";
  if (p.is_vip) return "bg-red-400";
  if (p.is_registered) return "bg-sky-400";
  return null;
}

/** 等级方框：原图中每个等级都带框，满级 150 用实心琥珀块，其余用细灰描边 */
function RankBadge({ rank }: { rank: number }) {
  const isMax = rank >= MAX_RANK;
  return (
    <span
      className={cn(
        "inline-block min-w-[30px] rounded-[2px] px-1 text-center text-[11px] leading-[1.4] font-bold tabular-nums",
        isMax
          ? "bg-[#ff8400] text-black shadow-sm"
          : "border border-white/25 font-medium text-white/70",
      )}
    >
      {rank > 0 ? rank : "—"}
    </span>
  );
}

/** 延迟以三格信号条 + 数值表示，按强度亮格并着色（低绿 / 中黄 / 高红） */
function LatencyCell({ latency }: { latency: number }) {
  if (!latency || latency <= 0) {
    return <div className="text-center text-white/25">—</div>;
  }
  const level = latency < 60 ? 3 : latency < 120 ? 2 : 1;
  const barColor = latency < 60 ? "bg-green-400" : latency < 120 ? "bg-amber-300" : "bg-red-400";
  return (
    <div className="flex items-center justify-center gap-1">
      <span className="flex items-end gap-px" aria-hidden>
        {[1, 2, 3].map((n) => (
          <span
            key={n}
            className={cn("w-[3px] rounded-sm", n <= level ? barColor : "bg-white/15")}
            style={{ height: `${n * 3 + 1}px` }}
          />
        ))}
      </span>
      <span className="min-w-[3ch] text-right text-[11px] text-white/65 tabular-nums">
        {latency}
      </span>
    </div>
  );
}

/** 排队 / 旁观玩家组，使用与队伍列一致的高亮规则，但不拆队、不展示战绩；服管可逐个操作 */
function SidePlayerGroup({
  title,
  players,
  game,
}: {
  title: string;
  players: BlazePlayer[];
  game: string;
}) {
  const { canManage } = useServerAdmin();
  return (
    <div>
      <div className="mb-1.5 flex items-baseline gap-2 text-xs text-white/50">
        <span className="font-medium">{title}</span>
        <span className="tabular-nums">{players.length}</span>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {players.map((p) => (
          <span key={p.persona_id} className="inline-flex items-center gap-1">
            <Link
              href={`/${game}/player/${p.persona_id}`}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                "compact-action inline-flex items-center gap-1.5 text-[11px] hover:underline",
                nameColor(p),
              )}
            >
              <RankBadge rank={p.rank} />
              <span className="max-w-[140px] truncate">{p.display_name}</span>
            </Link>
            {canManage ? <PlayerRowActions player={p} /> : null}
          </span>
        ))}
      </div>
    </div>
  );
}

function PlayerLegend({
  summary,
  playerCount,
  maxPlayers,
  statsIncluded,
  className,
}: {
  summary: {
    online_admin_count: number;
    online_vip_count: number;
    online_registered_count: number;
    rank_150_count: number;
  };
  playerCount: number;
  maxPlayers: number;
  statsIncluded: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-white/10 pt-3 text-xs text-white/60",
        className,
      )}
    >
      <LegendItem markClass="bg-green-400" label="在线管理" value={summary.online_admin_count} />
      <LegendItem markClass="bg-red-400" label="在线VIP" value={summary.online_vip_count} />
      <LegendItem markClass="bg-sky-400" label="在线群友" value={summary.online_registered_count} />
      <LegendItem markClass="bg-[#ff8400]" label="满级150" value={summary.rank_150_count} />
      <span className="ml-auto text-white/45 tabular-nums">
        在线 {playerCount}/{maxPlayers}
        {statsIncluded ? "" : " · 未加载战绩"}
      </span>
    </div>
  );
}

function LegendItem({
  markClass,
  label,
  value,
}: {
  markClass: string;
  label: string;
  value: number;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("size-2.5 rounded-[2px]", markClass)} />
      <span>
        {label}：<span className="font-semibold text-white/90 tabular-nums">{value}</span>
      </span>
    </span>
  );
}

function formatPercent(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v)}%`;
}

function formatRatio(v: number | null | undefined): string {
  return v == null ? "—" : v.toFixed(2);
}

function formatHours(v: number | null | undefined): string {
  return v == null ? "—" : v.toFixed(1);
}

/* ----------------------------- 本服审计 ----------------------------- */

function ServerAuditTab({ game, gameId }: { game: string; gameId: number }) {
  const [page, setPage] = useState(1);
  const logs = useQuery({
    queryKey: ["audit-logs", "server", gameId, page],
    queryFn: () => auditApi.list({ serverId: gameId, page, pageSize: 20 }),
    enabled: Number.isFinite(gameId),
  });

  const columns: Column<AuditLogItem>[] = [
    {
      key: "time",
      header: "时间",
      cell: (l) => new Date(l.created_at).toLocaleString("zh-CN"),
      isCardTitle: true,
    },
    { key: "action", header: "操作", cell: (l) => ACTION_LABEL[l.action] ?? l.action },
    {
      key: "result",
      header: "结果",
      cell: (l) =>
        l.result === "success" ? (
          <span className="text-white/60">成功</span>
        ) : (
          <span className="text-red-400">失败</span>
        ),
    },
    {
      key: "target",
      header: "目标玩家",
      cell: (l) =>
        l.target_persona_id ? (
          <Link
            href={`/${game}/player/${l.target_persona_id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-white tabular-nums hover:text-amber-300 hover:underline"
          >
            {l.target_persona_id}
          </Link>
        ) : (
          "—"
        ),
    },
    {
      key: "actor",
      header: "操作人",
      cell: (l) => (l.payload?.auto_switch ? "自动换图" : String(l.acting_persona_id)),
    },
  ];

  const totalPages =
    logs.data && logs.data.page_size > 0 ? Math.ceil(logs.data.total / logs.data.page_size) : 0;

  if (logs.isLoading) {
    return <div className="py-8 text-center text-sm text-white/40">加载中…</div>;
  }
  if (!logs.data) return null;

  return (
    <div className="space-y-4">
      <ResponsiveTable
        data={logs.data.items}
        columns={columns}
        rowKey={(l) => l.id}
        emptyState="本服暂无操作记录"
      />
      {totalPages > 1 ? (
        <div className="flex items-center justify-between text-sm">
          <span className="text-white/45 tabular-nums">
            共 {logs.data.total} 条 · 第 {logs.data.page} / {totalPages} 页
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-sm border border-white/15 px-3 py-1.5 text-xs transition-colors hover:bg-white/5 disabled:opacity-40"
            >
              上一页
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-sm border border-white/15 px-3 py-1.5 text-xs transition-colors hover:bg-white/5 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/* ----------------------------- 地图轮换 ----------------------------- */

/**
 * 轮换卡片叠加近 7 天热度：每张图（地图 + 模式）实际玩了多久、平均多少人。当前图琥珀描边，
 * 下一张单独标出；服管可直接换图。
 */
function RotationGrid({
  items,
  stats,
  colors,
  serverInitialized,
}: {
  items: MapRotationItem[];
  stats: ServerMapStat[];
  colors: Record<string, string>;
  serverInitialized: boolean;
}) {
  const { can, chooseLevel } = useServerAdmin();
  const canSwitch = can("chooseLevel");
  if (items.length === 0) {
    return (
      <Panel>
        <div className="py-8 text-center text-sm text-white/40">暂无地图轮换数据</div>
      </Panel>
    );
  }
  const statByKey = new Map(stats.map((m) => [mapKey(m.map_name, m.game_mode), m]));
  const topPlayerMinutes = Math.max(...stats.map((m) => m.player_minutes), 1);
  const nm = nextMap(items);
  // 行动服的「下一张」是本战役的下一张图（攻破后进入），不是轮换里的下一项
  const nextIdx =
    nm?.kind === "rotation"
      ? nm.index
      : nm?.kind === "breakthrough"
        ? items.findIndex((m) => m.map_name === nm.map.map_name && m.operation)
        : -1;
  // 行动条目按战役分组（按首次出现的顺序），组内按战役进行顺序；单图行动与其它模式各归一组
  const groups: { key: string; title: string; entries: { m: MapRotationItem; i: number }[] }[] = [];
  items.forEach((m, i) => {
    const multi = m.operation && m.operation.length > 1;
    const key = multi ? operationKey(m)! : m.operation ? "single" : "other";
    let g = groups.find((x) => x.key === key);
    if (!g) {
      const title = multi
        ? m.operation!.map((o) => `${o.name}${o.sectors ? `（${o.sectors} 区）` : ""}`).join(" → ")
        : m.operation
          ? "单图行动"
          : "其它模式";
      g = { key, title, entries: [] };
      groups.push(g);
    }
    g.entries.push({ m, i });
  });
  for (const g of groups) g.entries.sort((a, b) => operationStep(a.m) - operationStep(b.m));
  const grouped = groups.some((g) => g.key !== "other");
  // 图池里的战役，点一下换到该战役开头（组内已按进行顺序排好，取第一项）；单图行动各算一个
  const shortcuts = groups
    .filter((g) => g.key !== "other")
    .flatMap((g) => (g.key === "single" ? g.entries.map((e) => [e]) : [g.entries]))
    .map((entries) => ({
      ...entries[0],
      label: entries[0].m.operation!.map((o) => o.name).join(" → "),
      current: entries.some((e) => e.m.is_current),
    }));

  const renderCard = ({ m, i }: { m: MapRotationItem; i: number }) => {
    const mapLabel = m.map_display_name ?? m.map_name ?? "未知地图";
    const modeLabel = m.mode_display_name ?? m.game_mode;
    const stat = m.map_name ? statByKey.get(mapKey(m.map_name, m.game_mode)) : undefined;
    const step = operationStep(m);
    const sectors = step >= 0 ? m.operation![step].sectors : null;
    const switchable = canSwitch && serverInitialized;
    const switchLabel = m.is_current ? "重开" : "换到";
    // 私服行动只能从战役第一张正常开局，切到中间的图要先警告
    const switchToMap = () =>
      chooseLevel(i, mapLabel, {
        restart: m.is_current,
        warning:
          step > 0
            ? `这是战役第 ${step + 1} 张图，行动只能从战役第一张图正常开始，换到这里可能无法按战役推进`
            : undefined,
      });
    return (
      <li key={`${m.map_name}-${i}`}>
        <Bf1Panel
          variant="transparent"
          cut={14}
          corners={["bottomRight"]}
          className={cn(
            "group relative overflow-hidden bg-black/50 ring-1 backdrop-blur-sm",
            m.is_current ? "ring-amber-400/80" : "ring-white/10",
          )}
        >
          <div className="relative aspect-[16/8] w-full overflow-hidden bg-white/[0.04]">
            {m.map_image_url ? (
              // EA CDN 自带缩放与缓存，不走 next/image
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={m.map_image_url}
                alt={mapLabel}
                loading="lazy"
                className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
              />
            ) : null}
            <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/20 to-transparent" />
            {switchable ? (
              <button
                type="button"
                aria-label={`${switchLabel} ${mapLabel}`}
                onClick={switchToMap}
                className="absolute inset-0 hidden items-center justify-center bg-black/35 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:hover)]:flex"
              >
                <span className="inline-flex items-center gap-1.5 bg-white/90 px-4 py-2 text-sm font-semibold text-black shadow-lg">
                  <ArrowRightLeft className="size-4" />
                  {m.is_current ? "重开这张图" : "换到这张图"}
                </span>
              </button>
            ) : null}
            <span className="font-display absolute top-2 left-2.5 text-sm font-bold text-white/70 tabular-nums drop-shadow">
              {String(i + 1).padStart(2, "0")}
            </span>
            {m.is_current ? (
              <span className="absolute top-2 right-2 bg-amber-400 px-2 py-0.5 text-xs font-bold text-black">
                正在进行
              </span>
            ) : i === nextIdx ? (
              <span className="absolute top-2 right-2 border border-white/40 bg-black/60 px-2 py-0.5 text-xs text-white/85">
                {nm?.kind === "breakthrough" ? "攻破后进入" : "下一张"}
              </span>
            ) : null}
            <div className="absolute inset-x-0 bottom-0 px-3 pb-2">
              <div className="truncate text-[15px] font-bold text-white sm:text-base">
                {mapLabel}
              </div>
              <div className="flex items-center gap-2 overflow-hidden text-xs whitespace-nowrap">
                {modeLabel ? <span className="text-amber-300/90">{modeLabel}</span> : null}
                {m.operation && m.operation.length > 1 ? (
                  <span className={step === 0 ? "text-sky-300" : "text-white/50"}>
                    {step === 0 ? "战役起点" : `第 ${step + 1} 张`}
                  </span>
                ) : null}
                {sectors ? <span className="text-white/50">{sectors} 区</span> : null}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5 sm:flex-nowrap">
            <div className="min-w-0 flex-1 basis-full sm:basis-auto">
              {stat ? (
                <>
                  <div className="h-1 bg-white/[0.08]">
                    <div
                      className="h-full"
                      style={{
                        width: `${(stat.player_minutes / topPlayerMinutes) * 100}%`,
                        background: colors[stat.map_name],
                      }}
                    />
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-x-3 text-[11px] text-white/50 tabular-nums">
                    <span>{formatDuration(stat.minutes)}</span>
                    <span>平均 {stat.avg_players.toFixed(0)} 人</span>
                  </div>
                </>
              ) : (
                <div className="text-[11px] text-white/35">近 7 天没玩过</div>
              )}
            </div>
            {canSwitch ? (
              <button
                type="button"
                disabled={!serverInitialized}
                title={
                  serverInitialized
                    ? m.is_current
                      ? "重开当前地图"
                      : "切换到此地图"
                    : "服务器尚未初始化，暂不可换图"
                }
                onClick={switchToMap}
                className="compact-action inline-flex h-9 w-full shrink-0 items-center justify-center gap-1.5 bg-white/[0.08] px-3 text-xs font-medium text-white/85 ring-1 ring-white/15 transition-colors group-hover:bg-white/15 hover:!bg-white hover:text-black disabled:bg-transparent disabled:text-white/35 sm:h-8 sm:w-auto"
              >
                <ArrowRightLeft className="size-3.5" />
                {m.is_current ? "重开" : "换图"}
              </button>
            ) : null}
          </div>
        </Bf1Panel>
      </li>
    );
  };
  // 手机上也排两列：一列一张图时 29 张图要划很久
  const gridCls = "grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3 2xl:grid-cols-4";

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-white/45">
        <span>
          {grouped ? "按战役分组，序号为轮换顺序" : "按轮换顺序排列"}，共 {items.length} 张
        </span>
        {stats.length > 0 ? <span>热度条为近 7 天人·分钟，越长越受欢迎</span> : null}
      </div>
      {canSwitch && shortcuts.length > 0 ? (
        <div className="mb-5 bg-black/40 px-4 py-3 ring-1 ring-white/10 backdrop-blur-sm">
          <div className="mb-2 text-xs text-white/45">从头开始一个战役</div>
          <div className="flex flex-wrap gap-2">
            {shortcuts.map(({ m, i, label, current }) => (
              <button
                key={i}
                type="button"
                disabled={!serverInitialized}
                title={
                  serverInitialized
                    ? `${current ? "重开" : "换到"} ${m.map_display_name ?? m.map_name}`
                    : "服务器尚未初始化，暂不可换图"
                }
                onClick={() =>
                  chooseLevel(i, m.map_display_name ?? m.map_name ?? "", { restart: m.is_current })
                }
                className={cn(
                  "compact-action inline-flex h-9 items-center gap-2 pr-3 text-xs ring-1 transition-colors",
                  current
                    ? "text-amber-200 ring-amber-400/70 hover:bg-amber-400 hover:text-black"
                    : "bg-white/[0.06] text-white/80 ring-white/10 hover:bg-white hover:text-black disabled:opacity-40 disabled:hover:bg-white/[0.06] disabled:hover:text-white/80",
                )}
              >
                {m.map_image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={m.map_image_url} alt="" className="h-full w-14 object-cover" />
                ) : null}
                <span className="truncate">{label}</span>
                {current ? <span className="text-[10px] text-amber-300">进行中</span> : null}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      {grouped ? (
        <div className="space-y-4 sm:space-y-6">
          {groups.map((g) => (
            <section key={g.key}>
              <h3 className="mb-2 text-sm font-semibold text-white/80">{g.title}</h3>
              <ul className={gridCls}>{g.entries.map(renderCard)}</ul>
            </section>
          ))}
        </div>
      ) : (
        <ul className={gridCls}>{items.map((m, i) => renderCard({ m, i }))}</ul>
      )}
    </div>
  );
}
