"use client";

/**
 * BF1 服务器详情页（战地视觉：全屏地图背景 + 切角面板 + Tab 分页）
 *
 * 视觉语言与玩家详情页对齐：以服务器「当前地图大图」作为全屏模糊背景与 Hero 主体，
 * 用 Bf1Panel 切角面板承载信息，amber 下划线 Tab 导航。Tab 内容（玩家 / 轮换 /
 * 成员 / 审计）沿用既有数据与操作逻辑，仅置于半透明深色面板内保证可读。
 */

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Lock,
  Bookmark,
  MapPin,
  Crosshair,
  Globe,
  ShieldCheck,
  ChevronDown,
} from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { ServerDetailSkeleton } from "@/components/layout/PageSkeleton";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";
import {
  ServerAdminProvider,
  useServerAdmin,
  PlayerRowActions,
  TeamSelectAllCheckbox,
  BatchActionBar,
} from "@/components/bf1/server-admin/InlineServerAdmin";
import { MembersPanel } from "@/components/bf1/server-admin/MembersPanel";
import { useSession } from "@/hooks/useSession";
import { auditApi, type AuditLogItem } from "@/lib/api/audit";
import { FALLBACK_GRADIENT } from "@/lib/bf1/background";
import { cn } from "@/lib/utils";
import {
  bf1Api,
  type ServerDetail,
  type ServerSummary,
  type ServerSettings,
  type MapRotationItem,
  type ServerExtras,
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
  add_admin: "添加管理员",
  remove_admin: "移除管理员",
};

type TabKey = "players" | "rotation" | "members" | "audit";

export default function ServerDetailPage() {
  const { id, game } = useParams<{ id: string; game: string }>();
  const router = useRouter();
  const gameId = Number(id);

  const detail = useQuery({
    queryKey: ["bf1-server", gameId],
    queryFn: () => bf1Api.getServer(gameId),
    enabled: Number.isFinite(gameId),
  });

  if (detail.isLoading) {
    return <ServerDetailSkeleton />;
  }
  if (!detail.data) {
    return <CenterNote text="未找到该服务器，请返回列表重试" />;
  }

  return (
    <ServerDetailView
      gameId={gameId}
      game={game}
      detail={detail.data}
      onBack={() => router.push(`/${game}/servers`)}
    />
  );
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
  const { summary, map_rotation, extras } = detail;
  const memberCount = extras.admins.length + extras.vips.length + extras.banned.length;

  const tabs: ReadonlyArray<{ key: TabKey; label: string }> = [
    { key: "players", label: `玩家列表（${summary.player_count}）` },
    { key: "rotation", label: `地图轮换（${map_rotation.length}）` },
    { key: "members", label: `成员名单（${memberCount}）` },
    ...(isLoggedIn ? ([{ key: "audit", label: "本服审计" }] as const) : []),
  ];
  const [tab, setTab] = useState<TabKey>("players");

  return (
    <div className="relative min-h-screen w-full overflow-hidden text-white">
      <ServerBackgroundLayer url={summary.map_image_url} />

      <div className="relative z-10 max-w-[1600px] px-6 py-5 sm:px-10 sm:py-8">
        <button
          type="button"
          onClick={onBack}
          className="mb-4 inline-flex items-center gap-1.5 text-sm text-white/55 transition-colors hover:text-white"
        >
          <ArrowLeft className="size-4" />
          返回服务器列表
        </button>

        <ServerHero summary={summary} />

        <SettingsMatrix settings={detail.settings} />

        <ServerInfoPanel extras={extras} />

        <div className="mt-6">
          <TabNav tabs={tabs} tab={tab} onTab={setTab} />
          {/* Provider 包裹整个 tab 区，让玩家列表、地图轮换、成员名单三个 tab 共享同一份角色查询与确认机制 */}
          <ServerAdminProvider gameId={gameId}>
            <div className="mt-5">
              {tab === "players" && (
                <div className="rounded-sm bg-black/25 p-4 backdrop-blur-md sm:p-6">
                  <PlayersList gameId={gameId} game={game} />
                </div>
              )}
              {tab === "rotation" && (
                <Panel>
                  <RotationList
                    items={map_rotation}
                    serverInitialized={summary.persisted_game_id != null}
                  />
                </Panel>
              )}
              {tab === "members" && (
                <Panel>
                  <MembersPanel extras={extras} />
                </Panel>
              )}
              {tab === "audit" && isLoggedIn && (
                <Panel>
                  <ServerAuditTab game={game} gameId={gameId} />
                </Panel>
              )}
            </div>
          </ServerAdminProvider>
        </div>
      </div>
    </div>
  );
}

/* ----------------------------- 背景与外壳 ----------------------------- */

function ServerBackgroundLayer({ url }: { url: string | null }) {
  return (
    <div className="pointer-events-none fixed inset-0 z-0">
      {url ? (
        <div
          className="absolute inset-0 scale-110 bg-cover bg-center bg-no-repeat blur-[2px]"
          style={{ backgroundImage: `url(${url})` }}
        />
      ) : (
        <div className="absolute inset-0" style={{ background: FALLBACK_GRADIENT }} />
      )}
      <div className="absolute inset-0 bg-black/55" />
      <div className="absolute inset-0 bg-gradient-to-b from-black/75 via-black/35 to-black/90" />
    </div>
  );
}

function CenterNote({ text }: { text: string }) {
  return (
    <div className="relative min-h-screen w-full overflow-hidden text-white">
      <ServerBackgroundLayer url={null} />
      <div className="relative z-10 flex min-h-screen items-center justify-center px-4">
        <span className="text-sm text-white/60">{text}</span>
      </div>
    </div>
  );
}

/* ----------------------------- Hero 区 ----------------------------- */

function ServerHero({ summary }: { summary: ServerSummary }) {
  const mapLabel = summary.map_display_name ?? summary.map_name;
  const modeLabel = summary.mode_display_name ?? summary.game_mode;
  const regionLabel = summary.region_display_name ?? summary.region;
  const fill =
    summary.max_player_count > 0
      ? Math.round((summary.player_count / summary.max_player_count) * 100)
      : 0;

  return (
    <Bf1Panel
      cut={28}
      corners={["topLeft", "bottomRight"]}
      className="relative"
      style={{ background: "rgba(12,12,15,0.78)" }}
    >
      <div className="grid gap-5 px-5 py-5 sm:px-8 sm:py-7 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        {/* 当前地图大图 */}
        <div className="relative aspect-[16/9] overflow-hidden rounded-sm border border-white/10">
          {summary.map_image_url ? (
            // EA CDN 自带缩放与缓存，不走 next/image，避免多套一层优化代理
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={summary.map_image_url}
              alt={mapLabel ?? "当前地图"}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-white/[0.04]">
              <MapPin className="size-8 text-white/20" />
            </div>
          )}
          {mapLabel ? (
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent px-3 pt-8 pb-2.5">
              <div className="text-base font-bold tracking-wide">{mapLabel}</div>
              {modeLabel ? <div className="text-xs text-white/60">{modeLabel}</div> : null}
            </div>
          ) : null}
        </div>

        {/* 标题与统计 */}
        <div className="flex min-w-0 flex-col justify-center">
          <div className="flex items-start gap-2.5">
            <h1 className="min-w-0 text-2xl font-bold tracking-wide break-words sm:text-3xl">
              {summary.name}
            </h1>
            {summary.has_password ? (
              <Lock className="mt-1.5 size-5 shrink-0 text-white/50" />
            ) : null}
          </div>

          <div className="mt-2.5 flex flex-wrap gap-2">
            {regionLabel ? <StatPill icon={Globe} text={regionLabel} /> : null}
            {modeLabel ? <StatPill icon={Crosshair} text={modeLabel} /> : null}
            {summary.is_official ? <StatPill text="官方" accent /> : null}
            {summary.is_ranked ? <StatPill text="Ranked" accent /> : null}
          </div>

          <div
            className={cn(
              "mt-4 grid grid-cols-2 gap-2.5",
              summary.tick_rate ? "sm:grid-cols-4" : "sm:grid-cols-3",
            )}
          >
            <QuickStat
              label="在线"
              value={`${summary.player_count}/${summary.max_player_count}`}
              accent
            />
            <QuickStat label="排队" value={String(summary.queue_count)} />
            <QuickStat label="旁观" value={String(summary.spectator_count)} />
            {summary.tick_rate ? (
              <QuickStat label="画面更新率" value={`${summary.tick_rate} Hz`} />
            ) : null}
          </div>

          <div className="mt-4">
            <div className="mb-1 flex items-center justify-between text-xs text-white/45">
              <span>满员率</span>
              <span className="tabular-nums">{fill}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-amber-400/80"
                style={{ width: `${Math.min(fill, 100)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {summary.description ? (
        <div className="border-t border-white/10 px-5 py-4 text-sm leading-relaxed whitespace-pre-line text-white/70 sm:px-8">
          {summary.description}
        </div>
      ) : null}
    </Bf1Panel>
  );
}

function StatPill({
  icon: Icon,
  text,
  accent,
}: {
  icon?: React.ElementType;
  text: string;
  accent?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium",
        accent ? "bg-amber-500/15 text-amber-300" : "bg-white/8 text-white/70",
      )}
    >
      {Icon ? <Icon className="size-3.5" /> : null}
      {text}
    </span>
  );
}

function QuickStat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <Bf1Panel variant="dark" cut={10} className="px-3 py-2.5">
      <div className="text-[11px] tracking-wider text-white/45 uppercase">{label}</div>
      <div
        className={cn(
          "mt-0.5 text-lg font-bold tabular-nums sm:text-xl",
          accent ? "text-amber-300" : "text-white",
        )}
      >
        {value}
      </div>
    </Bf1Panel>
  );
}

/* ----------------------------- 自定义设置矩阵 ----------------------------- */

/**
 * 复刻游戏「伺服器資訊」的四列设置矩阵。数据来自 detail.settings，EA 已按网关账号
 * 语言把条目键译为中文（繁体），值为 on/off；Scales 组的值是小数字符串（"1.0"=100%）。
 * 列标题为本应用自有文案，沿用全站简体；条目标签是 EA 来源数据，原样保留繁体。
 * 某一组整组缺失时（非 RSP 服务器）跳过该列；全部缺失时整块不渲染。
 */
function SettingsMatrix({ settings }: { settings: ServerSettings }) {
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

  if (columns.length === 0) return null;
  const totalCount = columns.reduce((n, c) => n + c.entries.length, 0);

  return (
    <div className="mt-4">
      <Panel>
        {/* 设置项偏运维向、平时少看，默认折叠避免挤占详情主信息；点标题展开 */}
        <details className="group">
          <summary className="flex cursor-pointer list-none items-center justify-between [&::-webkit-details-marker]:hidden">
            <span className="text-sm font-semibold tracking-[0.2em] text-white/60 uppercase">
              服务器设置
            </span>
            <span className="flex items-center gap-2 text-xs text-white/40">
              <span className="tabular-nums">{totalCount} 项</span>
              <ChevronDown className="size-4 transition-transform group-open:rotate-180" />
            </span>
          </summary>
          <div className="mt-4 grid grid-cols-1 gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-4">
            {columns.map((col) => (
              <section key={col.title}>
                <h3 className="mb-2 border-b border-white/10 pb-1.5 text-xs font-semibold tracking-wider text-white/55">
                  {col.title}
                </h3>
                <dl className="space-y-1.5">
                  {col.entries.map(([label, value]) => (
                    <div key={label} className="flex items-baseline justify-between gap-3 text-sm">
                      <dt className="min-w-0 truncate text-white/65" title={label}>
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
        </details>
      </Panel>
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
      {on ? "開" : "關"}
    </span>
  );
}

/* ----------------------------- 服务器信息面板 ----------------------------- */

function ServerInfoPanel({ extras }: { extras: ServerExtras }) {
  const hasOwner = !!extras.owner?.display_name;
  const hasIds = !!(extras.game_id || extras.server_id || extras.persisted_game_id);
  const hasLifecycle =
    !!extras.lifecycle.created_at || !!extras.lifecycle.expires_at || !!extras.lifecycle.updated_at;
  const hasPlatoon = !!extras.platoon?.name;
  if (!hasOwner && !hasIds && !hasLifecycle && !hasPlatoon && extras.bookmark_count == null) {
    return null;
  }
  return (
    <div className="mt-4">
      <Panel>
        <SectionTitle>服务器信息</SectionTitle>
        <dl className="grid grid-cols-1 gap-x-8 gap-y-2.5 text-sm sm:grid-cols-2">
          {extras.owner?.display_name ? (
            <InfoRow label="服主">
              <span className="text-white/90">{extras.owner.display_name}</span>
              {extras.owner.persona_id ? (
                <span className="ml-2 text-xs text-white/45 tabular-nums">
                  #{extras.owner.persona_id}
                </span>
              ) : null}
              {extras.owner.platform ? (
                <span className="ml-2 rounded bg-white/10 px-1.5 py-0.5 text-xs">
                  {extras.owner.platform.toUpperCase()}
                </span>
              ) : null}
            </InfoRow>
          ) : null}
          {extras.bookmark_count != null ? (
            <InfoRow label="收藏">
              <span className="inline-flex items-center gap-1 tabular-nums">
                <Bookmark className="size-3.5 text-white/40" />
                {extras.bookmark_count}
              </span>
            </InfoRow>
          ) : null}
          {extras.game_id ? (
            <InfoRow label="GameID">
              <span className="font-mono text-xs tabular-nums">{extras.game_id}</span>
            </InfoRow>
          ) : null}
          {extras.server_id ? (
            <InfoRow label="ServerID">
              <span className="font-mono text-xs tabular-nums">{extras.server_id}</span>
            </InfoRow>
          ) : null}
          {extras.persisted_game_id ? (
            <InfoRow label="PersistID">
              <span className="font-mono text-xs break-all">{extras.persisted_game_id}</span>
            </InfoRow>
          ) : null}
          {extras.lifecycle.created_at ? (
            <InfoRow label="创建时间">
              <span className="tabular-nums">{formatDateTime(extras.lifecycle.created_at)}</span>
            </InfoRow>
          ) : null}
          {extras.lifecycle.updated_at ? (
            <InfoRow label="更新时间">
              <span className="tabular-nums">{formatDateTime(extras.lifecycle.updated_at)}</span>
            </InfoRow>
          ) : null}
          {extras.lifecycle.expires_at ? (
            <InfoRow label="到期时间">
              <span className="tabular-nums">{formatDateTime(extras.lifecycle.expires_at)}</span>
            </InfoRow>
          ) : null}
        </dl>
        {extras.platoon?.name ? (
          <div className="mt-4 rounded-sm border border-white/10 bg-white/[0.03] p-3">
            <div className="flex items-start gap-3">
              {extras.platoon.emblem_url ? (
                // EA 徽章域不在 next/image remotePatterns 内，用原生 img 避免额外配置
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={extras.platoon.emblem_url}
                  alt={extras.platoon.name ?? extras.platoon.tag ?? "战队徽章"}
                  className="size-12 shrink-0 rounded-sm object-contain"
                  loading="lazy"
                />
              ) : (
                <ShieldCheck className="mt-0.5 size-5 shrink-0 text-amber-300/80" />
              )}
              <div className="min-w-0 flex-1 text-sm">
                <div className="mb-1 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 font-medium">
                  <span>
                    战队 [{extras.platoon.tag ?? "—"}] {extras.platoon.name}
                  </span>
                  {extras.platoon.size != null ? (
                    <span className="text-xs text-white/45">{extras.platoon.size} 人</span>
                  ) : null}
                </div>
                {extras.platoon.description ? (
                  <p className="text-xs leading-relaxed whitespace-pre-line text-white/55">
                    {extras.platoon.description}
                  </p>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="w-20 shrink-0 text-xs text-white/45">{label}</dt>
      <dd className="flex-1">{children}</dd>
    </div>
  );
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/* ----------------------------- Tab 导航与通用面板 ----------------------------- */

function TabNav({
  tabs,
  tab,
  onTab,
}: {
  tabs: ReadonlyArray<{ key: TabKey; label: string }>;
  tab: TabKey;
  onTab: (t: TabKey) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-white/10">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          onClick={() => onTab(t.key)}
          className={cn(
            "relative shrink-0 px-4 py-2.5 text-sm font-semibold tracking-wide transition-colors",
            tab === t.key ? "text-white" : "text-white/45 hover:text-white/75",
          )}
        >
          {t.label}
          {tab === t.key ? (
            <span className="absolute inset-x-2 -bottom-px h-0.5 bg-amber-400" />
          ) : null}
        </button>
      ))}
    </div>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <Bf1Panel cut={20} className="p-5 sm:p-6" style={{ background: "rgba(12,12,15,0.72)" }}>
      {children}
    </Bf1Panel>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-4 text-sm font-semibold tracking-[0.2em] text-white/60 uppercase">
      {children}
    </h2>
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
        className="mt-6"
      />
    </div>
  );
}

/** 阵营名称（中文）到旗帜图标文件名的映射，对应 public/factions/{slug}.png */
const FACTION_SLUG: Record<string, string> = {
  法国: "fra",
  德意志帝国: "ger",
  大英帝国: "uk",
  美国: "usa",
  意大利王国: "ita",
  俄罗斯帝国: "rus",
  奥匈帝国: "ahu",
  奥斯曼帝国: "otm",
  皇家海军陆战队: "rm",
  红军: "bol",
};

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
      <table className="h-full w-full border-collapse text-[12.5px] tabular-nums">
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
      <td className="w-full max-w-0 py-[5px] pr-2 pl-2">
        <Link
          href={`/${game}/player/${player.persona_id}`}
          className="flex min-w-0 items-center gap-1.5 hover:underline"
          title={player.display_name}
        >
          {dot ? <span className={cn("size-1.5 shrink-0 rounded-full", dot)} /> : null}
          <span className={cn("min-w-0 truncate font-medium", nameColor(player))}>
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

/** 排队 / 旁观玩家组，使用与队伍列一致的高亮规则，但不拆队、不展示战绩 */
function SidePlayerGroup({
  title,
  players,
  game,
}: {
  title: string;
  players: BlazePlayer[];
  game: string;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline gap-2 text-xs text-white/50">
        <span className="font-medium">{title}</span>
        <span className="tabular-nums">{players.length}</span>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {players.map((p) => (
          <Link
            key={p.persona_id}
            href={`/${game}/player/${p.persona_id}`}
            className={cn(
              "inline-flex items-center gap-1.5 text-[11px] hover:underline",
              nameColor(p),
            )}
          >
            <RankBadge rank={p.rank} />
            <span className="max-w-[140px] truncate">{p.display_name}</span>
          </Link>
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
            className="text-white tabular-nums hover:text-amber-300 hover:underline"
          >
            {l.target_persona_id}
          </Link>
        ) : (
          "—"
        ),
    },
    { key: "actor", header: "操作人", cell: (l) => String(l.acting_persona_id) },
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

function RotationList({
  items,
  serverInitialized,
}: {
  items: MapRotationItem[];
  serverInitialized: boolean;
}) {
  const { can, chooseLevel } = useServerAdmin();
  const canSwitch = can("chooseLevel");
  if (items.length === 0) {
    return <div className="py-8 text-center text-sm text-white/40">暂无地图轮换数据</div>;
  }
  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((m, i) => {
        const mapLabel = m.map_display_name ?? m.map_name ?? "未知地图";
        const modeLabel = m.mode_display_name ?? m.game_mode;
        return (
          <li key={`${m.map_name}-${i}`}>
            <div
              className={cn(
                "overflow-hidden rounded-sm border bg-black/30",
                m.is_current ? "border-amber-400/70" : "border-white/10",
              )}
            >
              {m.map_image_url ? (
                <div className="relative aspect-[16/9] w-full bg-white/[0.04]">
                  {/* EA CDN 自带缩放与缓存，不走 next/image */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={m.map_image_url}
                    alt={mapLabel}
                    loading="lazy"
                    className="h-full w-full object-cover"
                  />
                  {m.is_current ? (
                    <span className="absolute top-2 right-2 rounded-sm bg-amber-400 px-2 py-0.5 text-xs font-bold text-black">
                      当前
                    </span>
                  ) : null}
                </div>
              ) : null}
              <div className="flex items-end justify-between gap-2 p-3">
                <div className="min-w-0 space-y-0.5">
                  <div className="truncate text-sm font-medium">{mapLabel}</div>
                  {modeLabel ? <div className="text-xs text-white/50">{modeLabel}</div> : null}
                </div>
                {canSwitch && !m.is_current ? (
                  <button
                    type="button"
                    disabled={!serverInitialized}
                    title={serverInitialized ? "切换到此地图" : "服务器尚未初始化，暂不可换图"}
                    onClick={() => chooseLevel(i, mapLabel)}
                    className="inline-flex shrink-0 items-center gap-1 rounded-sm border border-white/15 px-2 py-1 text-xs text-white/80 transition-colors hover:bg-white/10 disabled:opacity-40"
                  >
                    <MapPin className="size-3.5" />
                    换图
                  </button>
                ) : null}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
