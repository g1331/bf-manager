"use client";

/**
 * BF1 服务器详情页（战地视觉：全屏地图背景 + 切角面板 + Tab 分页）
 *
 * 视觉语言与玩家详情页对齐：以服务器「当前地图大图」作为全屏模糊背景与 Hero 主体，
 * 用 Bf1Panel 切角面板承载信息，amber 下划线 Tab 导航。Tab 内容（玩家 / 轮换 /
 * 成员 / 审计 / 管理）沿用既有数据与操作逻辑，仅置于半透明深色面板内保证可读。
 */

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Lock, Bookmark, MapPin, Crosshair, Globe2, ShieldCheck } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";
import { AdminPanel } from "@/components/bf1/AdminPanel";
import { useSession } from "@/hooks/useSession";
import { auditApi, type AuditLogItem } from "@/lib/api/audit";
import { FALLBACK_GRADIENT } from "@/lib/bf1/background";
import { cn } from "@/lib/utils";
import {
  bf1Api,
  type ServerDetail,
  type ServerSummary,
  type ServerSettings,
  type ServerPlayer,
  type MapRotationItem,
  type ServerExtras,
  type ServerMember,
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

type TabKey = "players" | "rotation" | "members" | "audit" | "admin";

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
    return <CenterNote text="正在加载服务器数据…" />;
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
  const { summary, map_rotation, players, extras } = detail;
  const memberCount = extras.admins.length + extras.vips.length + extras.banned.length;

  const tabs: ReadonlyArray<{ key: TabKey; label: string }> = [
    { key: "players", label: `玩家列表（${players.length}）` },
    { key: "rotation", label: `地图轮换（${map_rotation.length}）` },
    { key: "members", label: `成员名单（${memberCount}）` },
    ...(isLoggedIn
      ? ([
          { key: "audit", label: "本服审计" },
          { key: "admin", label: "管理" },
        ] as const)
      : []),
  ];
  const [tab, setTab] = useState<TabKey>("players");

  return (
    <div className="relative min-h-screen w-full overflow-hidden text-white">
      <ServerBackgroundLayer url={summary.map_image_url} />

      <div className="relative z-10 mx-auto max-w-6xl px-4 py-5 sm:px-6 sm:py-8">
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
          <div className="mt-5">
            {tab === "players" && (
              <Panel>
                <PlayersList players={players} game={game} />
              </Panel>
            )}
            {tab === "rotation" && (
              <Panel>
                <RotationList items={map_rotation} />
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
            {tab === "admin" && isLoggedIn && <AdminPanel gameId={gameId} detail={detail} />}
          </div>
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
            {regionLabel ? <StatPill icon={Globe2} text={regionLabel} /> : null}
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

  return (
    <div className="mt-4">
      <Panel>
        <SectionTitle>服务器设置</SectionTitle>
        <div className="grid grid-cols-1 gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-4">
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

/* ----------------------------- 玩家列表 ----------------------------- */

function PlayersList({ players, game }: { players: ServerPlayer[]; game: string }) {
  const columns: Column<ServerPlayer>[] = [
    {
      key: "name",
      header: "玩家",
      cell: (p) => (
        <Link
          href={`/${game}/player/${p.persona_id}`}
          className="text-white hover:text-amber-300 hover:underline"
        >
          {p.display_name}
        </Link>
      ),
      isCardTitle: true,
    },
    {
      key: "team",
      header: "队伍",
      cell: (p) => (p.is_spectator ? "旁观" : p.team_id ? `T${p.team_id}` : "—"),
    },
    { key: "rank", header: "等级", cell: (p) => p.rank ?? "—" },
    { key: "id", header: "ID", cell: (p) => p.persona_id },
  ];
  return (
    <ResponsiveTable
      data={players}
      columns={columns}
      rowKey={(p) => p.persona_id}
      emptyState="服务器内暂无玩家数据"
    />
  );
}

/* ----------------------------- 成员名单 ----------------------------- */

function MembersPanel({ extras }: { extras: ServerExtras }) {
  return (
    <div className="space-y-6">
      <MemberSection title="管理员" hint="/ 50" members={extras.admins} />
      <MemberSection title="VIP" hint="/ 50" members={extras.vips} />
      <MemberSection title="封禁名单" hint="/ 200" members={extras.banned} />
    </div>
  );
}

function MemberSection({
  title,
  hint,
  members,
}: {
  title: string;
  hint: string;
  members: ServerMember[];
}) {
  const columns: Column<ServerMember>[] = [
    {
      key: "name",
      header: title,
      cell: (m) => m.display_name ?? "—",
      isCardTitle: true,
    },
    {
      key: "platform",
      header: "平台",
      cell: (m) => (m.platform ? m.platform.toUpperCase() : "—"),
    },
    { key: "id", header: "Persona ID", cell: (m) => m.persona_id },
  ];
  return (
    <section>
      <div className="mb-2 flex items-baseline gap-2 text-xs text-white/50">
        <span className="font-medium">{title}</span>
        <span className="tabular-nums">
          {members.length} {hint}
        </span>
      </div>
      <ResponsiveTable
        data={members}
        columns={columns}
        rowKey={(m) => m.persona_id}
        emptyState={`暂无${title}`}
      />
    </section>
  );
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

function RotationList({ items }: { items: MapRotationItem[] }) {
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
              <div className="space-y-0.5 p-3">
                <div className="text-sm font-medium">{mapLabel}</div>
                {modeLabel ? <div className="text-xs text-white/50">{modeLabel}</div> : null}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
