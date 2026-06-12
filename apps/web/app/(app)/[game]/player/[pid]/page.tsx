"use client";

/**
 * BF1 玩家主页（英雄区 + Tab 分页 + 全屏背景大图）
 *
 * 数据来自后端真实接口：persona 概要、生涯综合 + 兵种分布、武器、载具、最近
 * 服务器、在线状态、外部封禁、所属战队。武器/载具的 KPM 由前端按 击杀 /
 * (时长/60) 计算（后端该接口不直接给）；已装备皮肤随武器/载具接口下发，
 * 卡片优先展示皮肤图、皮肤名按稀有度着色。
 */

import * as React from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import {
  CardGridSkeleton,
  PlayerDetailSkeleton,
  RowsSkeleton,
} from "@/components/layout/PageSkeleton";
import { RarityStar } from "@/components/bf1/visual/RarityStar";
import { BanBadge } from "@/components/bf1/visual/BanBadge";
import { EquipmentFilterBar } from "@/components/bf1/EquipmentFilterBar";
import {
  rarityByKills,
  rarityByRank,
  rarityByStars,
  rarityHex,
  skinRarityFromName,
  skinRarityHex,
  starsByKills,
} from "@/lib/bf1/rarity";
import { pickBackgroundUrl, FALLBACK_GRADIENT } from "@/lib/bf1/background";
import { cn, formatCount, formatDuration } from "@/lib/utils";
import {
  bf1Api,
  type BanStatus,
  type PersonaBrief,
  type PlayerPlatoon,
  type PlayerStatsSummary,
  type RecentServer,
  type SoldierClassStat,
  type VehicleStat,
  type WeaponStat,
} from "@/lib/api/bf1";
import {
  Crosshair,
  Trophy,
  Zap,
  Skull,
  Gauge,
  Scale,
  Percent,
  Award,
  PersonStanding,
  Truck,
  Target,
  Handshake,
  Flame,
  Tag,
  HeartPulse,
  Syringe,
  Wrench,
  type LucideIcon,
} from "lucide-react";

type TabKey = "overview" | "weapons" | "vehicles" | "recent";

const TABS: ReadonlyArray<{ key: TabKey; label: string }> = [
  { key: "overview", label: "概览" },
  { key: "weapons", label: "武器" },
  { key: "vehicles", label: "载具" },
  { key: "recent", label: "最近" },
];

// 兵种代号 → 中文名。后端兵种代号为小写英文，未知代号回退为原值。
const SOLDIER_CLASS_LABEL: Record<string, string> = {
  assault: "突击兵",
  cavalry: "骑兵",
  medic: "医疗兵",
  pilot: "飞行员",
  scout: "侦察兵",
  support: "支援兵",
  tanker: "坦克兵",
};

const SOLDIER_ORDER: readonly string[] = [
  "assault",
  "medic",
  "support",
  "scout",
  "tanker",
  "pilot",
  "cavalry",
];

function classLabel(code: string): string {
  return SOLDIER_CLASS_LABEL[code] ?? code;
}

function fmtNum(value: number | null | undefined): string {
  return value == null ? "—" : formatCount(value);
}

// 生涯数据区使用完整数字（带千分位），避免「87.5k」这类失真简写
function fmtNumFull(value: number | null | undefined): string {
  return value == null ? "—" : value.toLocaleString("en-US");
}

function computeWinRate(
  wins: number | null | undefined,
  losses: number | null | undefined,
): string {
  if (wins == null || losses == null || wins + losses === 0) return "—";
  return `${((wins / (wins + losses)) * 100).toFixed(1)}%`;
}

function computeKpm(kills: number | null, timeSeconds: number | null): number | null {
  if (kills == null || !timeSeconds || timeSeconds <= 0) return null;
  return kills / (timeSeconds / 60);
}

export default function Bf1PlayerPage() {
  const params = useParams<{ game: string; pid: string }>();
  const personaId = Number(params.pid);
  const enabled = Number.isFinite(personaId) && personaId > 0;
  const [tab, setTab] = React.useState<TabKey>("overview");

  const playerQ = useQuery({
    queryKey: ["bf1-player", personaId],
    queryFn: () => bf1Api.getPlayer(personaId),
    enabled,
  });
  const statsQ = useQuery({
    queryKey: ["bf1-stats", personaId],
    queryFn: () => bf1Api.getStats(personaId),
    enabled,
  });
  const onlineQ = useQuery({
    queryKey: ["bf1-online", personaId],
    queryFn: () => bf1Api.getOnline(personaId),
    enabled,
  });
  const platoonQ = useQuery({
    queryKey: ["bf1-platoon", personaId],
    queryFn: () => bf1Api.getPlatoon(personaId),
    enabled,
  });
  const banQ = useQuery({
    queryKey: ["bf1-ban", personaId, playerQ.data?.display_name],
    queryFn: () => bf1Api.getBan(personaId, playerQ.data?.display_name),
    enabled: enabled && !!playerQ.data,
  });
  // 武器 / 载具 / 最近服务器仅在切到对应 Tab 时再拉，减少首屏请求
  const weaponsQ = useQuery({
    queryKey: ["bf1-weapons", personaId],
    queryFn: () => bf1Api.getWeapons(personaId),
    enabled: enabled && tab === "weapons",
  });
  const vehiclesQ = useQuery({
    queryKey: ["bf1-vehicles", personaId],
    queryFn: () => bf1Api.getVehicles(personaId),
    enabled: enabled && tab === "vehicles",
  });
  const recentQ = useQuery({
    queryKey: ["bf1-recent", personaId],
    queryFn: () => bf1Api.getRecentServers(personaId),
    enabled: enabled && tab === "recent",
  });

  if (!enabled) {
    return <CenterNote text="无效的玩家 ID" />;
  }
  if (statsQ.isLoading || playerQ.isLoading) {
    return <PlayerDetailSkeleton />;
  }
  if (statsQ.isError || !statsQ.data) {
    return <CenterNote text="加载玩家战绩失败，请稍后重试" />;
  }

  const player = playerQ.data;
  const summary = statsQ.data.summary;
  const soldiers = statsQ.data.soldiers;
  const ban = banQ.data;
  const platoon = platoonQ.data ?? null;
  const online = onlineQ.data?.is_online ?? null;
  const banned = ban?.bfban === "hit" || ban?.bfeac === "hit";
  const bgUrl = pickBackgroundUrl(personaId, recentQ.data?.servers[0]?.map_name);

  return (
    <div className="relative min-h-screen w-full overflow-hidden text-white">
      <BackgroundLayer url={bgUrl} grayscale={banned} />

      <div className="relative z-10 max-w-[1600px] px-6 py-5 sm:px-10 sm:py-8">
        <HeroBanner
          player={player}
          personaId={personaId}
          summary={summary}
          online={online}
          ban={ban}
          banned={banned}
          platoon={platoon}
        />
        <TabNav tab={tab} onTab={setTab} />
        <div className="mt-6">
          {tab === "overview" && (
            <OverviewTab summary={summary} soldiers={soldiers} bestClass={summary.best_class} />
          )}
          {tab === "weapons" && (
            <WeaponsTab weapons={weaponsQ.data?.weapons ?? []} loading={weaponsQ.isLoading} />
          )}
          {tab === "vehicles" && (
            <VehiclesTab vehicles={vehiclesQ.data?.vehicles ?? []} loading={vehiclesQ.isLoading} />
          )}
          {tab === "recent" && (
            <RecentTab servers={recentQ.data?.servers ?? []} loading={recentQ.isLoading} />
          )}
        </div>
      </div>
    </div>
  );
}

/* ----------------------------- 背景与外壳 ----------------------------- */

function BackgroundLayer({ url, grayscale }: { url: string | null; grayscale: boolean }) {
  return (
    <div className="pointer-events-none fixed inset-0 z-0">
      {url ? (
        <div
          className={cn(
            "absolute inset-0 scale-110 bg-cover bg-center bg-no-repeat blur-[2px]",
            grayscale && "grayscale",
          )}
          style={{ backgroundImage: `url(${url})` }}
        />
      ) : (
        <div className="absolute inset-0" style={{ background: FALLBACK_GRADIENT }} />
      )}
      {/* 整体压暗 + 上下渐变，保证前景文字在任意背景上可读 */}
      <div className="absolute inset-0 bg-black/55" />
      <div className="absolute inset-0 bg-gradient-to-b from-black/75 via-black/35 to-black/90" />
    </div>
  );
}

function CenterNote({ text }: { text: string }) {
  return (
    <div className="relative min-h-screen w-full overflow-hidden text-white">
      <BackgroundLayer url={null} grayscale={false} />
      <div className="relative z-10 flex min-h-screen items-center justify-center px-4">
        <span className="text-sm text-white/60">{text}</span>
      </div>
    </div>
  );
}

/* ----------------------------- 英雄区 ----------------------------- */

function HeroBanner({
  player,
  personaId,
  summary,
  online,
  ban,
  banned,
  platoon,
}: {
  player: PersonaBrief | undefined;
  personaId: number;
  summary: PlayerStatsSummary;
  online: boolean | null;
  ban: BanStatus | undefined;
  banned: boolean;
  platoon: PlayerPlatoon | null;
}) {
  const displayName = player?.display_name || summary.display_name || `Persona ${personaId}`;
  const rankRarity = rarityByRank(summary.rank);
  return (
    <Bf1Panel
      cut={28}
      corners={["topLeft", "bottomRight"]}
      // 英雄区两列布局按面板自身宽度（@container）切换而非视口断点：页面实际可用
      // 宽度被舞台 min(95vw,200vh) 与左右两条侧栏共同裁剪，视口断点测不准（#48）
      className="@container relative"
      style={{ background: "rgba(12,12,15,0.78)" }}
    >
      <div className="px-5 py-5 sm:px-8 sm:py-7">
        {banned && <BanWarning ban={ban} />}
        <div className="grid gap-6 @4xl:grid-cols-[minmax(0,1fr)_auto] @4xl:items-center">
          <div className="flex items-center gap-4 sm:gap-5">
            {/* 命中封禁时仅灰度化头像与身份文字，BanBadge 作为警示元素保留彩色，
                故灰度滤镜只施加在头像和昵称信息块上，不覆盖下方的 BanBadge 行 */}
            <div className={cn(banned && "grayscale")}>
              <Avatar
                avatarUrl={player?.avatar_url ?? null}
                displayName={displayName}
                online={online}
              />
            </div>
            <div className="min-w-0">
              <div className={cn(banned && "grayscale")}>
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  {platoon?.tag ? (
                    <span className="text-xl font-bold text-white/55 sm:text-2xl">
                      [{platoon.tag}]
                    </span>
                  ) : null}
                  <span className="truncate text-2xl font-bold tracking-wide sm:text-3xl">
                    {displayName}
                  </span>
                  <span
                    className="text-lg font-bold tabular-nums sm:text-xl"
                    style={{ color: rarityHex[rankRarity] }}
                  >
                    Lv. {summary.rank ?? "—"}
                  </span>
                </div>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-white/55">
                  <span>PID {personaId}</span>
                  <span className="text-white/25">·</span>
                  <OnlineDot online={online} />
                  <span className="text-white/25">·</span>
                  <span>总时长 {formatDuration(summary.time_played_seconds ?? 0)}</span>
                </div>
                <PlatoonLine platoon={platoon} />
              </div>
              <div className="mt-2.5 flex flex-wrap gap-2">
                <BanBadge source="bfban" state={ban?.bfban ?? "unknown"} size="sm" />
                <BanBadge source="bfeac" state={ban?.bfeac ?? "unknown"} size="sm" />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 @4xl:w-[440px]">
            <QuickStat label="K/D" value={summary.kd?.toFixed(2) ?? "—"} accent />
            <QuickStat label="KPM" value={summary.kpm?.toFixed(2) ?? "—"} />
            <QuickStat label="胜率" value={computeWinRate(summary.wins, summary.losses)} />
            <QuickStat label="最高连杀" value={fmtNum(summary.max_killstreak)} />
          </div>
        </div>
      </div>
    </Bf1Panel>
  );
}

function Avatar({
  avatarUrl,
  displayName,
  online,
}: {
  avatarUrl: string | null;
  displayName: string;
  online: boolean | null;
}) {
  const ring = online ? "#3aca6b" : "#6b6b72";
  return (
    <div
      className="flex size-20 shrink-0 items-center justify-center rounded-full border-4 bg-gradient-to-br from-zinc-700 to-zinc-900 text-2xl font-bold sm:size-24"
      style={{ borderColor: ring }}
    >
      {avatarUrl ? (
        // EA 头像域不在 next/image remotePatterns 内，用原生 img 避免额外配置
        // eslint-disable-next-line @next/next/no-img-element
        <img src={avatarUrl} alt={displayName} className="size-full rounded-full object-cover" />
      ) : (
        displayName.slice(0, 1).toUpperCase()
      )}
    </div>
  );
}

function OnlineDot({ online }: { online: boolean | null }) {
  // null 表示在线状态查询失败、无法判定，标注「未知」而非误判离线
  const label = online == null ? "状态未知" : online ? "在线" : "离线";
  const color = online == null ? "#6b6b72" : online ? "#3aca6b" : "#6b6b72";
  return (
    <span className="inline-flex items-center gap-1">
      <span className="inline-block size-1.5 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

function PlatoonLine({ platoon }: { platoon: PlayerPlatoon | null }) {
  // 玩家未加入战队（接口返回 null）时不渲染该行
  if (!platoon || (!platoon.name && !platoon.tag)) return null;
  return (
    <div className="mt-2 inline-flex items-center gap-2 rounded-sm border border-white/10 bg-white/[0.03] px-2.5 py-1">
      {platoon.emblem_url ? (
        // EA 徽章域不在 next/image remotePatterns 内，用原生 img 避免额外配置
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={platoon.emblem_url}
          alt={platoon.name ?? platoon.tag ?? "战队徽章"}
          className="size-7 shrink-0 rounded-sm object-contain"
          loading="lazy"
        />
      ) : null}
      <span className="text-xs text-white/55">
        战队 <span className="text-white/80">{platoon.name ?? platoon.tag}</span>
        {platoon.size != null ? <span className="text-white/45"> · {platoon.size} 人</span> : null}
        {platoon.verified ? <span className="text-amber-300/80"> · 已认证</span> : null}
      </span>
    </div>
  );
}

function QuickStat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <Bf1Panel variant="dark" cut={10} className="px-3 py-2.5">
      <div className="text-[11px] tracking-wider text-white/45 uppercase">{label}</div>
      <div
        className={cn(
          "mt-0.5 text-xl font-bold tabular-nums sm:text-2xl",
          accent ? "text-amber-300" : "text-white",
        )}
      >
        {value}
      </div>
    </Bf1Panel>
  );
}

function BanWarning({ ban }: { ban: BanStatus | undefined }) {
  const sources: string[] = [];
  if (ban?.bfban === "hit") sources.push("BFBAN");
  if (ban?.bfeac === "hit") sources.push("BFEAC");
  return (
    <div
      className="mb-4 flex items-center gap-2 bg-red-600/90 px-4 py-2 text-sm font-bold text-white [box-shadow:0_0_18px_rgba(239,68,68,0.5)]"
      style={{
        clipPath: "polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%)",
      }}
    >
      <span className="text-base leading-none">⚠</span>
      <span>该账号已被反作弊平台标记（{sources.join(" / ")}）</span>
    </div>
  );
}

/* ----------------------------- Tab 导航 ----------------------------- */

function TabNav({ tab, onTab }: { tab: TabKey; onTab: (t: TabKey) => void }) {
  return (
    <div className="mt-6 flex gap-1 border-b border-white/10">
      {TABS.map((t) => (
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

/* ----------------------------- 概览 Tab ----------------------------- */

type StatIcon = React.ComponentType<{ className?: string }>;

/**
 * 碎裂奖杯图标：在 lucide Trophy 轮廓上叠一道裂纹，与胜局的完整奖杯成对。
 * lucide 无现成的碎裂/失败奖杯变体，故按其 24×24、currentColor 描边风格内联绘制。
 */
function TrophyCrack(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" />
      <path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />
      <path d="M4 22h16" />
      <path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22" />
      <path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" />
      <path d="M18 2H6v7a6 6 0 0 0 12 0V2Z" />
      <path d="m12 2-1.5 4 2.2 1.8L11 11" />
    </svg>
  );
}

function OverviewTab({
  summary: s,
  soldiers,
  bestClass,
}: {
  summary: PlayerStatsSummary;
  soldiers: SoldierClassStat[];
  bestClass: string | null;
}) {
  // 按列语义分组（每列 3 项，配合下方 grid 的列优先填充）：
  //   击杀类 | 兵种/距离 | 胜负 | 节奏/技巧
  const items: ReadonlyArray<[string, string, StatIcon]> = [
    ["击杀", fmtNumFull(s.kills), Crosshair],
    ["死亡", fmtNumFull(s.deaths), Skull],
    ["KD", s.kd?.toFixed(2) ?? "—", Scale],
    ["步战击杀", fmtNumFull(s.infantry_kills), PersonStanding],
    ["载具击杀", fmtNumFull(s.vehicle_kills), Truck],
    ["最远爆头", s.longest_headshot_meters != null ? `${s.longest_headshot_meters}m` : "—", Target],
    ["胜局", fmtNumFull(s.wins), Trophy],
    ["败局", fmtNumFull(s.losses), TrophyCrack],
    ["胜率", computeWinRate(s.wins, s.losses), Percent],
    ["KPM", s.kpm?.toFixed(2) ?? "—", Zap],
    ["SPM", s.sps != null ? String(Math.round(s.sps)) : "—", Gauge],
    ["技巧值", s.skill != null ? String(Math.round(s.skill)) : "—", Award],
  ];
  return (
    <div className="space-y-4">
      <Panel>
        <SectionTitle>生涯数据</SectionTitle>
        {/* 桌面端按列优先填充：每 3 项落入同一列，形成上面注释的语义分组；窄屏退化为按行排布 */}
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-flow-col lg:grid-cols-4 lg:grid-rows-3">
          {items.map(([label, value, Icon]) => (
            <div key={label} className="border-l-2 border-white/15 pl-3">
              <div className="flex items-center gap-1.5 text-[11px] text-white/50">
                <Icon className="size-3.5 shrink-0 text-white/40" />
                {label}
              </div>
              <div className="mt-0.5 text-xl font-bold tabular-nums">{value}</div>
            </div>
          ))}
        </div>
      </Panel>

      {bestClass && SOLDIER_CLASS_LABEL[bestClass] ? (
        <BestClassCard summary={s} bestClass={bestClass} />
      ) : null}
      <SoldierDistribution soldiers={soldiers} best={bestClass} />
    </div>
  );
}

/* ----------------------------- 武器 / 载具 Tab ----------------------------- */

/** 武器/载具列表的分类 + 名称过滤；分类从数据 distinct 推导并保持出现顺序 */
function useEquipmentFilter<
  T extends { name: string | null; category: string | null; skin_name: string | null },
>(items: T[]) {
  const [search, setSearch] = React.useState("");
  const [category, setCategory] = React.useState<string | null>(null);
  const categories = React.useMemo(
    () => [...new Set(items.map((i) => i.category).filter((c): c is string => !!c))],
    [items],
  );
  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter(
      (i) =>
        (category == null || i.category === category) &&
        (!q ||
          (i.name ?? "").toLowerCase().includes(q) ||
          (i.skin_name ?? "").toLowerCase().includes(q)),
    );
  }, [items, category, search]);
  return { search, setSearch, category, setCategory, categories, filtered };
}

function WeaponsTab({ weapons, loading }: { weapons: WeaponStat[]; loading: boolean }) {
  const { search, setSearch, category, setCategory, categories, filtered } =
    useEquipmentFilter(weapons);
  if (loading) return <CardGridSkeleton />;
  if (weapons.length === 0) return <EmptyState text="暂无武器数据" />;
  return (
    <div>
      <EquipmentFilterBar
        categories={categories}
        selected={category}
        onSelect={setCategory}
        search={search}
        onSearch={setSearch}
        placeholder="搜索武器名 / 皮肤名…"
      />
      {filtered.length === 0 ? (
        <EmptyState text="无匹配结果" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((w, i) => {
            const kpm = computeKpm(w.kills, w.time_seconds);
            return (
              <EquipmentCard
                // EA 返回里存在同名条目（如 繃帶包 在多个兵种组重复出现），单用
                // name 作 key 会重复，过滤切换时 React diff 错乱渲染出残留卡片
                key={`${w.name ?? ""}-${i}`}
                kind="weapon"
                name={w.name}
                subtitle={w.category}
                image={w.image}
                kills={w.kills}
                skinName={w.skin_name}
                skinRarity={w.skin_rarity}
                skinImage={w.skin_image}
                stats={[
                  ["击杀", fmtNum(w.kills)],
                  ["KPM", kpm != null ? kpm.toFixed(2) : "—"],
                  ["命中", w.accuracy != null ? `${w.accuracy.toFixed(1)}%` : "—"],
                  [
                    "爆头",
                    w.kills && w.headshots != null
                      ? `${((w.headshots / w.kills) * 100).toFixed(1)}%`
                      : "—",
                  ],
                  ["时长", formatDuration(w.time_seconds ?? 0)],
                ]}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function VehiclesTab({ vehicles, loading }: { vehicles: VehicleStat[]; loading: boolean }) {
  const { search, setSearch, category, setCategory, categories, filtered } =
    useEquipmentFilter(vehicles);
  if (loading) return <CardGridSkeleton />;
  if (vehicles.length === 0) return <EmptyState text="暂无载具数据" />;
  return (
    <div>
      <EquipmentFilterBar
        categories={categories}
        selected={category}
        onSelect={setCategory}
        search={search}
        onSearch={setSearch}
        placeholder="搜索载具名 / 皮肤名…"
      />
      {filtered.length === 0 ? (
        <EmptyState text="无匹配结果" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((v, i) => {
            const kpm = computeKpm(v.kills, v.time_seconds);
            return (
              <EquipmentCard
                key={`${v.name ?? ""}-${i}`}
                kind="vehicle"
                name={v.name}
                subtitle={v.category}
                image={v.image}
                kills={v.kills}
                skinName={v.skin_name}
                skinRarity={v.skin_rarity}
                skinImage={v.skin_image}
                stats={[
                  ["击杀", fmtNum(v.kills)],
                  ["KPM", kpm != null ? kpm.toFixed(2) : "—"],
                  ["摧毁", fmtNum(v.destroyed)],
                  ["时长", formatDuration(v.time_seconds ?? 0)],
                ]}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function EquipmentCard({
  kind,
  name,
  subtitle,
  image,
  kills,
  stats,
  skinName,
  skinRarity,
  skinImage,
}: {
  kind: "weapon" | "vehicle";
  name: string | null;
  subtitle: string | null;
  image: string | null;
  kills: number | null;
  stats: ReadonlyArray<[string, string]>;
  skinName?: string | null;
  skinRarity?: string | null;
  skinImage?: string | null;
}) {
  const stars = starsByKills(kills ?? 0);
  const rarity = rarityByKills(kills ?? 0);
  return (
    <Bf1Panel variant="dark" cut={18} className="p-4">
      {/* 已装备皮肤时优先展示皮肤图，回退原图 */}
      <CardArtwork kind={kind} image={skinImage ?? image} name={name} />
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div
            className="truncate text-base font-bold tracking-wide"
            style={{ color: rarityHex[rarity] }}
            title={name ?? ""}
          >
            {name}
          </div>
          {skinName ? (
            <div
              className="truncate text-[11px] font-medium"
              style={{ color: skinRarityHex[skinRarityFromName(skinRarity)] }}
              title={skinName}
            >
              {skinName}
            </div>
          ) : null}
          {subtitle ? <div className="truncate text-[11px] text-white/45">{subtitle}</div> : null}
        </div>
        <span className="flex shrink-0 items-center gap-1.5">
          <RarityStar rarity={rarityByStars(stars)} size={18} />
          <span className="text-sm font-bold text-white/90 tabular-nums">{stars}</span>
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
        {stats.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-1">
            <span className="text-xs text-white/55">{label}</span>
            <span className="font-bold text-white tabular-nums">{value}</span>
          </div>
        ))}
      </div>
    </Bf1Panel>
  );
}

function CardArtwork({
  kind,
  image,
  name,
}: {
  kind: "weapon" | "vehicle";
  image: string | null;
  name: string | null;
}) {
  return (
    <div className="relative mb-3 h-24 w-full overflow-hidden rounded-sm border border-white/5 bg-gradient-to-br from-white/[0.08] via-transparent to-black/40">
      {image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={image}
          alt={name ?? ""}
          className="h-full w-full object-contain object-center p-1"
          loading="lazy"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          {kind === "weapon" ? (
            <WeaponIcon className="size-9 text-white/20" />
          ) : (
            <VehicleIcon className="size-9 text-white/20" />
          )}
        </div>
      )}
    </div>
  );
}

function WeaponIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      className={className}
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4M12 12h.01" />
    </svg>
  );
}

function VehicleIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      className={className}
      aria-hidden
    >
      <rect x="3" y="11" width="14" height="6" rx="1" />
      <path d="M17 13h3l1 2v2h-4M6 17v2M14 17v2" />
      <circle cx="7" cy="19" r="1.2" />
      <circle cx="13" cy="19" r="1.2" />
    </svg>
  );
}

/* --------------------- 兵种区块（并入概览） --------------------- */

function BestClassCard({
  summary: s,
  bestClass,
}: {
  summary: PlayerStatsSummary;
  bestClass: string;
}) {
  return (
    <div className="relative pt-10 sm:pt-12">
      <div
        className="absolute top-7 left-4 z-30 px-3 py-1 text-xs font-black tracking-[0.3em] text-black sm:top-9"
        style={{
          background: rarityHex.gold,
          clipPath: "polygon(10px 0, 100% 0, calc(100% - 10px) 100%, 0 100%)",
        }}
      >
        最佳兵种
      </div>

      <Bf1Panel
        cut={32}
        corners={["topLeft", "bottomRight"]}
        className="relative"
        style={{ background: "rgba(12,12,15,0.82)" }}
      >
        <div className="grid grid-cols-[160px_1fr] gap-3 px-4 py-6 sm:grid-cols-[300px_1fr] sm:gap-6 sm:px-8 sm:py-10">
          <div aria-hidden className="min-h-[14rem] sm:min-h-[18rem]" />
          <div className="flex min-w-0 flex-col justify-center">
            <div className="mb-5 flex items-baseline gap-4">
              <span
                className="text-3xl font-black tracking-wider text-white sm:text-4xl"
                style={{ textShadow: "0 2px 6px rgba(0,0,0,0.7)" }}
              >
                {classLabel(bestClass)}
              </span>
              <div
                className="h-px flex-1"
                style={{
                  background: `linear-gradient(to right, ${rarityHex.gold} 0%, ${rarityHex.gold}40 60%, transparent 100%)`,
                }}
              />
            </div>
            <div className="grid grid-cols-3 gap-x-3 gap-y-4 sm:gap-x-8">
              <SoldierStat label="协助击杀" value={s.assists} icon={Handshake} />
              <SoldierStat label="最高连杀" value={s.max_killstreak} icon={Flame} accent />
              <SoldierStat label="狗牌数" value={s.dogtags} icon={Tag} />
              <SoldierStat label="复活数" value={s.revives} icon={HeartPulse} />
              <SoldierStat label="治疗数" value={s.heals} icon={Syringe} />
              <SoldierStat label="修理数" value={s.repairs} icon={Wrench} />
            </div>
          </div>
        </div>
      </Bf1Panel>

      <div className="pointer-events-none absolute bottom-0 left-2 z-20 h-[18rem] w-[150px] sm:left-6 sm:h-[24rem] sm:w-[280px]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`/bf1/soldiers/portraits/${bestClass}.png`}
          alt={classLabel(bestClass)}
          className="block h-full w-full object-contain object-bottom [filter:drop-shadow(0_6px_14px_rgba(0,0,0,0.85))] select-none"
          loading="lazy"
        />
      </div>
    </div>
  );
}

function SoldierStat({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: number | null;
  icon: LucideIcon;
  accent?: boolean;
}) {
  return (
    <div className="border-l-2 border-white/15 pl-3">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.12em] text-white/50 uppercase">
        <Icon className="size-3.5 shrink-0 text-white/40" />
        {label}
      </div>
      <div
        className={cn(
          "mt-1 text-2xl font-bold tabular-nums",
          accent ? "text-amber-300" : "text-white",
        )}
      >
        {fmtNum(value)}
      </div>
    </div>
  );
}

function SoldierDistribution({
  soldiers,
  best,
}: {
  soldiers: SoldierClassStat[];
  best: string | null;
}) {
  if (soldiers.length === 0) return null;
  const byClass = new Map(soldiers.map((it) => [it.class, it]));
  const ordered = SOLDIER_ORDER.map((c) => byClass.get(c)).filter(
    (it): it is SoldierClassStat => it != null,
  );
  if (ordered.length === 0) return null;
  const max = Math.max(...ordered.map((it) => it.kills), 1);
  return (
    <Panel>
      <SectionTitle>兵种击杀分布</SectionTitle>
      <div className="space-y-3">
        {ordered.map((it) => {
          const pct = (it.kills / max) * 100;
          const isBest = it.class === best;
          return (
            <div key={it.class} className="flex items-center gap-3">
              <span className="w-16 shrink-0 text-sm text-white/70">{classLabel(it.class)}</span>
              <div className="h-2.5 flex-1 overflow-hidden rounded-sm bg-white/10">
                <div
                  className="h-full rounded-sm"
                  style={{
                    width: `${pct}%`,
                    background: isBest ? rarityHex.gold : "rgba(255,255,255,0.4)",
                  }}
                />
              </div>
              <span className="w-14 shrink-0 text-right text-sm font-bold text-white/90 tabular-nums">
                {formatCount(it.kills)}
              </span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

/* ----------------------------- 最近 Tab ----------------------------- */

function RecentTab({ servers, loading }: { servers: RecentServer[]; loading: boolean }) {
  if (loading) return <RowsSkeleton rows={5} />;
  if (servers.length === 0) return <EmptyState text="暂无最近游玩记录" />;
  return (
    <div className="space-y-3">
      {servers.map((sv) => (
        <Bf1Panel
          key={sv.server_id ?? sv.persisted_game_id ?? sv.name}
          variant="dark"
          cut={14}
          className="flex flex-wrap items-center justify-between gap-2 px-5 py-3.5"
        >
          <div className="min-w-0">
            <div className="truncate font-semibold text-white">{sv.name}</div>
            <div className="mt-0.5 text-xs text-white/50">
              {sv.map_name ?? "—"}
              {sv.game_mode ? ` · ${sv.game_mode}` : ""}
            </div>
          </div>
          {sv.server_id != null ? (
            <span className="shrink-0 text-xs text-white/35">SID {sv.server_id}</span>
          ) : null}
        </Bf1Panel>
      ))}
    </div>
  );
}

/* ----------------------------- 通用小件 ----------------------------- */

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <Bf1Panel cut={20} className="p-5 sm:p-7" style={{ background: "rgba(12,12,15,0.72)" }}>
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

function EmptyState({ text }: { text: string }) {
  return (
    <Panel>
      <div className="py-8 text-center text-sm text-white/40">{text}</div>
    </Panel>
  );
}
