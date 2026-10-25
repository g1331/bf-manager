"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { motion, type Variants } from "framer-motion";
import { ArrowRight, Clock4, Eye, Server, TrendingDown, TrendingUp, Users } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { CountUp } from "@/components/bf1/visual/CountUp";
import { CountryFlag } from "@/components/common/CountryFlag";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatsOverviewSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ENABLED_GAMES } from "@/lib/game-registry";
import { pingSiteCountry } from "@/lib/bf1/pingsite";
import {
  bf1Api,
  type BF1Overview,
  type NamedCount,
  type ServerSummary,
  type TrendPoint,
} from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

/**
 * 公共全服统计页（战情板）：免登录可访问，同时是登录后的默认落点。
 * 数据来自后端每分钟一次的 Blaze 全服快照，写入 Redis 缓存，前端只读并每 60 秒刷新。
 *
 * 版式按游戏大厅的「战情室」组织：首屏横幅以当前最热门地图的实景铺底，在线人数与
 * 24h 趋势同框；其下是最热闹的服务器排行与热门地图拼贴，最后是私服 / 地区 / 模式分布。
 */
export default function StatsPage() {
  const game = ENABLED_GAMES[0];

  const overview = useQuery<BF1Overview>({
    queryKey: ["bf1-overview"],
    queryFn: bf1Api.getOverview,
    refetchInterval: 60_000,
  });

  const data = overview.data;
  const ready = !!data?.available;

  return (
    <main className="w-full max-w-[110rem] space-y-6 px-4 py-8 sm:px-6">
      <PageHeader
        kicker="Overview"
        title="全服概况"
        description="Battlefield 1 全部在线服务器的实时人数、热门服务器与地图"
        action={ready ? <LiveBadge updatedAt={data.updated_at} /> : null}
      />

      {overview.isLoading ? (
        <StatsOverviewSkeleton />
      ) : !ready ? (
        <section className="rounded-sm border border-white/10 bg-white/[0.04] p-6 backdrop-blur-md">
          <div className="text-muted-foreground text-sm">
            全服统计数据正在汇总，稍后将在此处展示服务器总数与当前在线人数。
          </div>
        </section>
      ) : (
        <OverviewContent data={data} gameId={game?.id ?? "bf1"} />
      )}
    </main>
  );
}

/* ---------- 入场编排 ---------- */

const staggerContainer: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};

const staggerItem: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.25, 0.46, 0.45, 0.94] } },
};

function OverviewContent({ data, gameId }: { data: BF1Overview; gameId: string }) {
  const topServers = data.top_servers ?? [];
  return (
    <motion.div variants={staggerContainer} initial="hidden" animate="show" className="space-y-5">
      <motion.div variants={staggerItem}>
        <HeroBanner data={data} />
      </motion.div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        {topServers.length > 0 ? (
          <motion.div variants={staggerItem} className="xl:col-span-7">
            <TopServersPanel servers={topServers} gameId={gameId} />
          </motion.div>
        ) : null}
        <motion.div
          variants={staggerItem}
          className={topServers.length > 0 ? "xl:col-span-5" : "xl:col-span-12"}
        >
          <MapMosaic items={data.top_map_modes} />
        </motion.div>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 2xl:grid-cols-12">
        <motion.div variants={staggerItem} className="2xl:col-span-3">
          <PrivateSharePanel data={data} />
        </motion.div>
        <motion.div variants={staggerItem} className="2xl:col-span-4">
          <RegionPanel data={data} />
        </motion.div>
        <motion.div variants={staggerItem} className="md:col-span-2 2xl:col-span-5">
          <ModePanel items={data.mode_distribution} />
        </motion.div>
      </div>

      <motion.p variants={staggerItem} className="text-muted-foreground/70 text-xs">
        数据来自 Blaze 全服快照，覆盖全部有人的服务器，每分钟更新
        {data.updated_at ? ` · ${new Date(data.updated_at).toLocaleString("zh-CN")}` : null}
      </motion.p>
    </motion.div>
  );
}

/* ---------- LIVE 指示 ---------- */

function LiveBadge({ updatedAt }: { updatedAt: string | null }) {
  return (
    <div className="flex items-center gap-2.5 text-xs">
      <span className="relative flex size-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400/70" />
        <span className="relative inline-flex size-2 rounded-full bg-amber-400" />
      </span>
      <span className="font-display font-semibold tracking-[0.25em] text-amber-400 uppercase">
        Live
      </span>
      {updatedAt ? (
        <span className="text-muted-foreground tabular-nums">
          {new Date(updatedAt).toLocaleTimeString("zh-CN", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </span>
      ) : null}
    </div>
  );
}

/* ---------- 首屏横幅：热门地图铺底 + 在线人数 + 24h 趋势 ---------- */

function HeroBanner({ data }: { data: BF1Overview }) {
  const backdrop = data.top_map_modes.find((m) => m.image)?.image ?? null;
  const history = data.history;

  // 24h 对比与峰谷：取原始采样，不受图表降采样影响
  const summary = useMemo(() => {
    if (history.length < 2) return null;
    let peak = history[0];
    let low = history[0];
    for (const p of history) {
      if (p.players > peak.players) peak = p;
      if (p.players < low.players) low = p;
    }
    const first = history[0].players;
    const delta = first > 0 ? ((data.players.total - first) / first) * 100 : null;
    return { peak, low, delta };
  }, [history, data.players.total]);

  return (
    <Bf1Panel
      variant="transparent"
      cut={28}
      corners={["topLeft", "bottomRight"]}
      className="relative overflow-hidden bg-black/40"
    >
      {/* 实景铺底：当前人数最多的地图，左侧压暗承载大字，右侧透出画面 */}
      {backdrop ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={backdrop}
          alt=""
          className="absolute inset-0 h-full w-full scale-105 object-cover object-center opacity-75"
          aria-hidden
        />
      ) : null}
      <div className="absolute inset-0 bg-gradient-to-r from-black/95 via-black/70 to-black/15" />
      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-black/40" />
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-amber-500/70 via-amber-500/20 to-transparent" />

      <div className="relative grid grid-cols-1 gap-8 p-6 sm:p-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-10">
        <div className="flex flex-col">
          <div className="flex items-center gap-2 text-xs font-medium tracking-[0.25em] text-amber-400/90 uppercase">
            <Users className="size-3.5" />
            全服在线玩家
          </div>
          <div className="font-display mt-2 text-7xl leading-none font-bold whitespace-nowrap text-amber-400 tabular-nums drop-shadow-[0_0_28px_rgba(245,158,11,0.35)] sm:text-8xl">
            <CountUp value={data.players.total} />
          </div>

          {summary ? (
            <div className="mt-5 flex flex-wrap items-end gap-x-7 gap-y-3">
              {summary.delta !== null ? <DeltaChip delta={summary.delta} /> : null}
              <MiniStat label="24h 峰值" value={summary.peak.players} at={summary.peak.ts} />
              <MiniStat label="24h 低谷" value={summary.low.players} at={summary.low.ts} />
            </div>
          ) : null}

          <div className="mt-auto grid grid-cols-3 divide-x divide-white/10 border-t border-white/10 pt-5 lg:mt-10">
            <KpiCell
              icon={Server}
              label="服务器"
              value={data.servers.total}
              unit="台"
              hint={`私服 ${data.servers.private} · 官服 ${data.servers.official}`}
            />
            <KpiCell
              icon={Clock4}
              label="排队中"
              value={data.queues.total}
              unit="人"
              hint="等待进服"
            />
            <KpiCell
              icon={Eye}
              label="观战中"
              value={data.spectators.total}
              unit="人"
              hint="不占玩家位"
            />
          </div>
        </div>

        <TrendChart points={history} />
      </div>
    </Bf1Panel>
  );
}

function DeltaChip({ delta }: { delta: number }) {
  const up = delta >= 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <div>
      <div className="text-muted-foreground text-[11px]">较 24 小时前</div>
      <div
        className={cn(
          "font-display mt-0.5 flex items-center gap-1.5 text-xl font-semibold tabular-nums",
          up ? "text-emerald-400" : "text-rose-400",
        )}
      >
        <Icon className="size-4" />
        {up ? "+" : ""}
        {delta.toFixed(0)}%
      </div>
    </div>
  );
}

function MiniStat({ label, value, at }: { label: string; value: number; at: number }) {
  return (
    <div>
      <div className="text-muted-foreground text-[11px]">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-1.5">
        <span className="font-display text-xl font-semibold text-white tabular-nums">
          {value.toLocaleString()}
        </span>
        <span className="text-muted-foreground text-[11px] tabular-nums">{formatTime(at)}</span>
      </div>
    </div>
  );
}

function KpiCell({
  icon: Icon,
  label,
  value,
  unit,
  hint,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
  unit: string;
  hint: string;
}) {
  return (
    <div className="min-w-0 px-4 first:pl-0">
      <div className="text-muted-foreground flex items-center gap-1.5 text-[11px] tracking-wider">
        <Icon className="size-3" />
        {label}
      </div>
      <div className="font-display mt-1 text-3xl font-bold whitespace-nowrap text-white tabular-nums sm:text-4xl">
        <CountUp value={value} />
        <span className="text-muted-foreground ml-1 text-sm font-normal">{unit}</span>
      </div>
      <div className="text-muted-foreground/80 mt-0.5 truncate text-[11px]">{hint}</div>
    </div>
  );
}

/* ---------- 24h 趋势：玩家面积 + 服务器虚线，悬停查看任意时刻 ---------- */

/** SVG 逻辑坐标系尺寸；preserveAspectRatio="none" 拉伸适配容器，线宽靠 non-scaling-stroke 保持 */
const CHART_W = 1000;
const CHART_H = 300;
// 顶部多留空间给峰值提示框，避免压住图例
const CHART_PAD_TOP = 64;
const CHART_PAD_BOTTOM = 4;

/** 降采样上限：超过后按桶取均值，曲线更平滑、SVG path 更轻 */
const CHART_MAX_POINTS = 288;

/** 时间轴刻度数（含首尾） */
const CHART_TICKS = 5;

function TrendChart({ points: rawPoints }: { points: TrendPoint[] }) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const plotRef = useRef<HTMLDivElement>(null);

  const points = useMemo(() => {
    if (rawPoints.length <= CHART_MAX_POINTS) return rawPoints;
    const bucket = Math.ceil(rawPoints.length / CHART_MAX_POINTS);
    const out: TrendPoint[] = [];
    for (let i = 0; i < rawPoints.length; i += bucket) {
      const slice = rawPoints.slice(i, i + bucket);
      out.push({
        ts: slice[Math.floor(slice.length / 2)].ts,
        players: Math.round(slice.reduce((sum, p) => sum + p.players, 0) / slice.length),
        servers: Math.round(slice.reduce((sum, p) => sum + p.servers, 0) / slice.length),
      });
    }
    return out;
  }, [rawPoints]);

  const chart = useMemo(() => {
    if (points.length < 2) return null;
    const t0 = points[0].ts;
    const span = Math.max(points[points.length - 1].ts - t0, 1);
    // 顶部留 10% 余量，避免峰值顶到边缘；服务器线压在下半区，与玩家曲线错开
    const yMax = Math.max(...points.map((p) => p.players), 1) * 1.1;
    const sMax = Math.max(...points.map((p) => p.servers), 1) * 1.6;
    const plotH = CHART_H - CHART_PAD_TOP - CHART_PAD_BOTTOM;
    const x = (p: TrendPoint) => ((p.ts - t0) / span) * CHART_W;
    const y = (v: number) => CHART_PAD_TOP + (1 - v / yMax) * plotH;
    const ys = (v: number) => CHART_PAD_TOP + (1 - v / sMax) * plotH;
    const toPath = (f: (p: TrendPoint) => number) =>
      points.map((p, i) => `${i === 0 ? "M" : "L"}${x(p).toFixed(1)} ${f(p).toFixed(1)}`).join(" ");
    const line = toPath((p) => y(p.players));
    const baseline = CHART_H - CHART_PAD_BOTTOM;
    let peakIdx = 0;
    points.forEach((p, i) => {
      if (p.players > points[peakIdx].players) peakIdx = i;
    });
    return {
      t0,
      span,
      x,
      y,
      line,
      area: `${line} L${CHART_W} ${baseline} L0 ${baseline} Z`,
      servers: toPath((p) => ys(p.servers)),
      peak: points[peakIdx],
    };
  }, [points]);

  function handleMove(e: React.MouseEvent) {
    if (!chart || !plotRef.current) return;
    const rect = plotRef.current.getBoundingClientRect();
    const targetTs = chart.t0 + ((e.clientX - rect.left) / rect.width) * chart.span;
    // 二分找到 >= targetTs 的第一个点，再与前一个点比距离取更近者
    let lo = 0;
    let hi = points.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (points[mid].ts < targetTs) lo = mid + 1;
      else hi = mid;
    }
    const idx = lo > 0 && targetTs - points[lo - 1].ts < points[lo].ts - targetTs ? lo - 1 : lo;
    setHoverIdx(idx);
  }

  const focus = hoverIdx !== null ? points[hoverIdx] : (chart?.peak ?? null);

  return (
    <div className="flex min-w-0 flex-col">
      <div className="flex items-center justify-between gap-4">
        <div className="text-sm font-semibold text-white">24 小时趋势</div>
        <div className="text-muted-foreground flex items-center gap-4 text-[11px]">
          <span className="flex items-center gap-1.5">
            <span className="h-[3px] w-3.5 bg-amber-400" />
            在线玩家
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-3.5 border-t border-dashed border-white/60" />
            在线服务器
          </span>
        </div>
      </div>

      {!chart || !focus ? (
        <div className="text-muted-foreground flex h-60 items-center justify-center text-sm">
          趋势数据采集中，每分钟记录一次，约一小时后可见曲线。
        </div>
      ) : (
        <div className="mt-3 flex flex-1 flex-col">
          <div
            ref={plotRef}
            className="relative min-h-[220px] flex-1"
            onMouseMove={handleMove}
            onMouseLeave={() => setHoverIdx(null)}
          >
            <svg
              width="100%"
              height="100%"
              viewBox={`0 0 ${CHART_W} ${CHART_H}`}
              preserveAspectRatio="none"
              className="absolute inset-0 block"
              aria-hidden
            >
              <defs>
                <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgb(245 158 11 / 0.45)" />
                  <stop offset="100%" stopColor="rgb(245 158 11 / 0)" />
                </linearGradient>
              </defs>
              {[0.25, 0.5, 0.75].map((r) => (
                <line
                  key={r}
                  x1="0"
                  x2={CHART_W}
                  y1={CHART_H * r}
                  y2={CHART_H * r}
                  stroke="rgb(255 255 255 / 0.07)"
                  strokeDasharray="3 6"
                  vectorEffect="non-scaling-stroke"
                />
              ))}
              <motion.path
                d={chart.area}
                fill="url(#trend-fill)"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.9, delay: 0.5 }}
              />
              <motion.path
                d={chart.servers}
                fill="none"
                stroke="rgb(255 255 255 / 0.45)"
                strokeWidth="1"
                strokeDasharray="4 4"
                vectorEffect="non-scaling-stroke"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.9, delay: 0.8 }}
              />
              <motion.path
                d={chart.line}
                fill="none"
                stroke="rgb(251 191 36)"
                strokeWidth="2"
                vectorEffect="non-scaling-stroke"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 1.3, ease: "easeOut" }}
              />
            </svg>

            {/* 焦点：悬停时跟随鼠标，否则停在峰值。HTML 绝对定位，避开 SVG 非等比拉伸 */}
            <ChartFocus
              left={(chart.x(focus) / CHART_W) * 100}
              top={(chart.y(focus.players) / CHART_H) * 100}
              point={focus}
              label={hoverIdx === null ? "峰值" : null}
            />
          </div>

          <div className="text-muted-foreground/70 mt-2 flex justify-between text-[11px] tabular-nums">
            {Array.from({ length: CHART_TICKS }, (_, i) => (
              <span key={i}>{formatTime(chart.t0 + (chart.span * i) / (CHART_TICKS - 1))}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ChartFocus({
  left,
  top,
  point,
  label,
}: {
  left: number;
  top: number;
  point: TrendPoint;
  label: string | null;
}) {
  // 靠右时提示框翻到左侧，避免溢出
  const flip = left > 70;
  return (
    <div className="pointer-events-none absolute inset-y-0" style={{ left: `${left}%` }}>
      <div className="absolute inset-y-0 w-px bg-gradient-to-b from-white/0 via-white/30 to-white/0" />
      <div
        className="absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-black bg-amber-400 shadow-[0_0_12px_rgba(245,158,11,0.9)]"
        style={{ top: `${top}%`, left: "0.5px" }}
      />
      <div
        className={cn(
          "absolute -translate-y-full rounded-sm border border-white/10 bg-black/85 px-2.5 py-1.5 text-[11px] whitespace-nowrap backdrop-blur-sm",
          flip ? "right-3" : "left-3",
        )}
        style={{ top: `calc(${top}% - 6px)` }}
      >
        <div className="text-muted-foreground tabular-nums">
          {label ? <span className="mr-1.5 text-amber-400">{label}</span> : null}
          {formatTime(point.ts)}
        </div>
        <div className="mt-0.5 tabular-nums">
          <span className="font-display text-sm font-semibold text-amber-400">
            {point.players.toLocaleString()}
          </span>
          <span className="text-muted-foreground"> 人 · {point.servers} 台</span>
        </div>
      </div>
    </div>
  );
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

/* ---------- 最热闹的服务器 ---------- */

/** 人数条分段数：仿游戏内小队格，64 人服每格 4 人 */
const SLOT_SEGMENTS = 16;

function TopServersPanel({ servers, gameId }: { servers: ServerSummary[]; gameId: string }) {
  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="flex h-full flex-col bg-white/[0.03] p-5"
    >
      <div className="flex items-baseline justify-between gap-4">
        <SectionHeading className="mb-0">最热闹的服务器</SectionHeading>
        <Link
          href={`/${gameId}/servers`}
          className="group flex items-center gap-1 text-xs text-amber-400/90 hover:text-amber-300"
        >
          全部服务器
          <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
      <ol className="mt-4 flex-1 divide-y divide-white/[0.06]">
        {servers.map((s, i) => (
          <li key={s.game_id ?? `${s.name}-${i}`}>
            <ServerRow server={s} rank={i + 1} gameId={gameId} />
          </li>
        ))}
      </ol>
    </Bf1Panel>
  );
}

function ServerRow({
  server: s,
  rank,
  gameId,
}: {
  server: ServerSummary;
  rank: number;
  gameId: string;
}) {
  const cap = Math.max(s.max_player_count, 1);
  const filled = Math.round((Math.min(s.player_count, cap) / cap) * SLOT_SEGMENTS);
  const meta = [s.mode_display_name, s.map_display_name, s.region_display_name]
    .filter(Boolean)
    .join(" · ");
  const content = (
    <div className="relative flex items-center gap-3 py-2.5 pr-1 pl-2 sm:gap-4">
      <span className="absolute inset-y-1 left-0 w-[2px] scale-y-0 bg-amber-400 transition-transform group-hover:scale-y-100" />
      <span
        className={cn(
          "font-display w-6 shrink-0 text-center text-lg font-bold tabular-nums",
          rank <= 3 ? "text-amber-400" : "text-white/30",
        )}
      >
        {String(rank).padStart(2, "0")}
      </span>
      {s.map_image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={s.map_image_url}
          alt=""
          loading="lazy"
          className="hidden h-10 w-16 shrink-0 object-cover [clip-path:polygon(0_0,100%_0,100%_calc(100%-8px),calc(100%-8px)_100%,0_100%)] sm:block"
        />
      ) : (
        <div className="hidden h-10 w-16 shrink-0 bg-white/[0.06] sm:block" />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          {s.is_official ? (
            <span className="shrink-0 border border-white/25 px-1 text-[10px] leading-4 text-white/60">
              官服
            </span>
          ) : null}
          <span className="truncate text-sm text-white group-hover:text-amber-100">{s.name}</span>
        </div>
        <div className="text-muted-foreground mt-0.5 flex items-center gap-1.5 text-xs">
          <CountryFlag code={s.country ?? pingSiteCountry(s.ping_site)} />
          <span className="truncate">{meta}</span>
        </div>
      </div>
      <div className="w-24 shrink-0 sm:w-28">
        <div className="flex items-baseline justify-end gap-1.5 tabular-nums">
          {s.queue_count > 0 ? (
            <span className="text-[11px] text-amber-400">+{s.queue_count} 排队</span>
          ) : null}
          <span className="font-display text-base font-semibold text-white">{s.player_count}</span>
          <span className="text-muted-foreground text-xs">/{s.max_player_count}</span>
        </div>
        <div className="mt-1.5 flex gap-[2px]" aria-hidden>
          {Array.from({ length: SLOT_SEGMENTS }, (_, i) => (
            <span
              key={i}
              className={cn("h-1.5 flex-1", i < filled ? "bg-amber-400" : "bg-white/10")}
            />
          ))}
        </div>
      </div>
    </div>
  );
  if (s.game_id == null) return <div className="group">{content}</div>;
  return (
    <Link href={`/${gameId}/server/${s.game_id}`} className="group block hover:bg-white/[0.04]">
      {content}
    </Link>
  );
}

/* ---------- 热门地图拼贴 ---------- */

/** 后端 label 约定为「模式 · 地图」，拆开做两级排版；无分隔符时整串当地图名 */
function splitLabel(label: string): { mode: string | null; map: string } {
  const idx = label.indexOf(" · ");
  if (idx < 0) return { mode: null, map: label };
  return { mode: label.slice(0, idx), map: label.slice(idx + 3) };
}

/** 拼贴展示数：首张大图 + 两列小图 */
const MOSAIC_COUNT = 7;

function MapMosaic({ items }: { items: NamedCount[] }) {
  if (items.length === 0) return null;
  const shown = items.slice(0, MOSAIC_COUNT);
  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="flex h-full flex-col bg-white/[0.03] p-5"
    >
      <div className="flex items-baseline justify-between gap-4">
        <SectionHeading className="mb-0">热门地图</SectionHeading>
        <span className="text-muted-foreground text-xs">按在线人数</span>
      </div>
      <div className="mt-4 grid flex-1 auto-rows-[minmax(96px,1fr)] grid-cols-2 gap-2">
        {shown.map((item, i) => (
          <MapTile key={item.label} item={item} rank={i + 1} featured={i === 0} />
        ))}
      </div>
    </Bf1Panel>
  );
}

function MapTile({ item, rank, featured }: { item: NamedCount; rank: number; featured: boolean }) {
  const { mode, map } = splitLabel(item.label);
  return (
    <div
      className={cn(
        "group relative overflow-hidden bg-white/[0.04]",
        featured && "col-span-2 row-span-2 min-h-[200px]",
      )}
    >
      {item.image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={item.image}
          alt={map}
          loading="lazy"
          className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-110"
        />
      ) : null}
      <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent" />
      <span
        className={cn(
          "font-display absolute top-2 right-2.5 font-bold tracking-wider",
          featured ? "text-sm text-amber-400" : "text-xs text-white/70",
        )}
      >
        #{rank}
      </span>
      <div className={cn("absolute inset-x-0 bottom-0", featured ? "p-4" : "p-2.5")}>
        {mode ? (
          <div className="truncate text-[11px] tracking-wider text-amber-400/90">{mode}</div>
        ) : null}
        <div
          className={cn(
            "font-display truncate font-bold text-white",
            featured ? "text-3xl" : "text-base",
          )}
        >
          {map}
        </div>
        <div className="mt-0.5 text-[11px] text-white/70 tabular-nums">
          <span className="font-semibold text-white">{item.players.toLocaleString()}</span> 人 ·{" "}
          {item.servers} 台
        </div>
      </div>
    </div>
  );
}

/* ---------- 私服占比：环形图 ---------- */

function PrivateSharePanel({ data }: { data: BF1Overview }) {
  const total = data.players.total || 1;
  const share = data.players.private / total;
  const r = 52;
  const circ = 2 * Math.PI * r;
  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="flex h-full flex-col bg-white/[0.03] p-5"
    >
      <SectionHeading className="mb-0">私服 / 官服</SectionHeading>
      <div className="mt-4 flex flex-1 items-center gap-5">
        <div className="relative size-32 shrink-0">
          <svg viewBox="0 0 128 128" className="size-full -rotate-90" aria-hidden>
            <circle
              cx="64"
              cy="64"
              r={r}
              fill="none"
              stroke="rgb(255 255 255 / 0.1)"
              strokeWidth="10"
            />
            <motion.circle
              cx="64"
              cy="64"
              r={r}
              fill="none"
              stroke="rgb(251 191 36)"
              strokeWidth="10"
              strokeDasharray={circ}
              initial={{ strokeDashoffset: circ }}
              animate={{ strokeDashoffset: circ * (1 - share) }}
              transition={{ duration: 1.1, delay: 0.4, ease: "easeOut" }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="font-display text-3xl font-bold text-amber-400 tabular-nums">
              {Math.round(share * 100)}%
            </span>
            <span className="text-muted-foreground text-[10px]">玩家在私服</span>
          </div>
        </div>
        <div className="min-w-0 space-y-3 text-xs">
          <LegendLine
            swatch="bg-amber-400"
            label="私服"
            value={data.players.private}
            sub={`${data.servers.private} 台`}
          />
          <LegendLine
            swatch="bg-white/25"
            label="官服"
            value={data.players.official}
            sub={`${data.servers.official} 台`}
          />
        </div>
      </div>
    </Bf1Panel>
  );
}

function LegendLine({
  swatch,
  label,
  value,
  sub,
}: {
  swatch: string;
  label: string;
  value: number;
  sub: string;
}) {
  return (
    <div>
      <div className="text-muted-foreground flex items-center gap-1.5">
        <span className={cn("size-2 rounded-[1px]", swatch)} />
        {label}
      </div>
      <div className="mt-0.5 tabular-nums">
        <span className="font-display text-lg font-semibold text-white">
          {value.toLocaleString()}
        </span>
        <span className="text-muted-foreground ml-1">人 · {sub}</span>
      </div>
    </div>
  );
}

/* ---------- 地区分布 ---------- */

function RegionPanel({ data }: { data: BF1Overview }) {
  const regions = [
    { label: "亚洲", players: data.players.asia, servers: data.servers.asia },
    { label: "欧洲", players: data.players.eu, servers: data.servers.eu },
    { label: "其他", players: data.players.other, servers: data.servers.other },
  ];
  const total = data.players.total || 1;
  const max = Math.max(...regions.map((r) => r.players), 1);
  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="flex h-full flex-col bg-white/[0.03] p-5"
    >
      <SectionHeading className="mb-0">地区</SectionHeading>
      <div className="mt-4 grid flex-1 grid-cols-3 gap-4">
        {regions.map((r, i) => (
          <div key={r.label} className="flex flex-col justify-end">
            <div className="text-muted-foreground text-xs">{r.label}</div>
            <div className="font-display mt-1 text-2xl font-bold text-white tabular-nums">
              {Math.round((r.players / total) * 100)}
              <span className="text-muted-foreground ml-0.5 text-sm font-normal">%</span>
            </div>
            <div className="mt-2 h-20 bg-white/[0.04]">
              <div className="flex h-full flex-col justify-end">
                <motion.div
                  className={cn(
                    "w-full",
                    i === 0 ? "bg-amber-400" : i === 1 ? "bg-amber-400/55" : "bg-white/25",
                  )}
                  initial={{ height: 0 }}
                  animate={{ height: `${(r.players / max) * 100}%` }}
                  transition={{ duration: 0.8, delay: 0.4 + i * 0.08, ease: "easeOut" }}
                />
              </div>
            </div>
            <div className="text-muted-foreground mt-2 text-[11px] whitespace-nowrap tabular-nums">
              <span className="text-foreground">{r.players.toLocaleString()}</span> 人 · {r.servers}{" "}
              台
            </div>
          </div>
        ))}
      </div>
    </Bf1Panel>
  );
}

/* ---------- 模式分布：一行一个，名称完整 ---------- */

function ModePanel({ items: raw }: { items: NamedCount[] }) {
  // 后端按服务器数排序，这里条长按人数，排序也跟着人数走
  const items = useMemo(() => [...raw].sort((a, b) => b.players - a.players), [raw]);
  const max = Math.max(...items.map((m) => m.players), 1);
  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="flex h-full flex-col bg-white/[0.03] p-5"
    >
      <div className="flex items-baseline justify-between gap-4">
        <SectionHeading className="mb-0">模式</SectionHeading>
        <span className="text-muted-foreground text-xs">按在线人数</span>
      </div>
      <div className="mt-4 space-y-2.5">
        {items.map((m, i) => (
          <div
            key={m.label}
            className="grid grid-cols-[4.5rem_1fr_auto] items-center gap-3 text-xs"
          >
            <span className={cn("truncate", i === 0 ? "text-white" : "text-white/80")}>
              {m.label}
            </span>
            <div className="h-2 bg-white/[0.05]">
              <motion.div
                className="h-full bg-gradient-to-r from-amber-600 to-amber-400"
                style={{ opacity: Math.max(0.35, 1 - i * 0.12) }}
                initial={{ width: 0 }}
                animate={{ width: `${Math.max((m.players / max) * 100, 0.8)}%` }}
                transition={{ duration: 0.7, delay: 0.4 + i * 0.05, ease: "easeOut" }}
              />
            </div>
            <span className="text-muted-foreground w-28 text-right tabular-nums">
              <span className="text-foreground font-medium">{m.players.toLocaleString()}</span> 人 ·{" "}
              {m.servers} 台
            </span>
          </div>
        ))}
      </div>
    </Bf1Panel>
  );
}
