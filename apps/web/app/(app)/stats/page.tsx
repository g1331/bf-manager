"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { animate, motion, useMotionValue, useTransform, type Variants } from "framer-motion";
import { Clock4, Eye, Server, Users } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { BfCard } from "@/components/bf1/visual/BfCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatsOverviewSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ENABLED_GAMES } from "@/lib/game-registry";
import {
  bf1Api,
  type BF1Overview,
  type CountBreakdown,
  type NamedCount,
  type TrendPoint,
} from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

/**
 * 公共全服统计页（战情板）：免登录可访问，同时是登录后的默认落点。
 * 数据来自后端定时轮询 EA 聚合后写入的 Redis 缓存，前端只读并每 60 秒刷新一次。
 *
 * 布局延续门户着陆页的视觉语言：满宽 bento 双列，左列为海报级数字带 + 24h 趋势
 * 面积图 + 地区/模式分布，右列为热门地图模式的大图卡排行；区块按 stagger 依次入场。
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
        title="全服统计"
        description="Battlefield 1 全服服务器、在线人数与热门地图模式概况"
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
        <OverviewContent data={data} />
      )}

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {game ? (
          <>
            <BfCard
              href={`/${game.id}/players`}
              image="/bf1/backgrounds/general/general-1.jpg"
              title={`${game.shortName} 战绩查询`}
              description="按玩家昵称查询武器、载具、地图等深度战绩。"
              action="进入查询"
            />
            <BfCard
              href={`/${game.id}/servers`}
              image="/bf1/backgrounds/general/general-4.jpg"
              title={`${game.shortName} 服务器`}
              description="浏览实时服务器列表，进入查看玩家、管理员、VIP 与封禁名单。"
              action="浏览服务器"
            />
          </>
        ) : null}
      </section>
    </main>
  );
}

/* ---------- 入场编排：与着陆页同一节奏的 stagger ---------- */

const staggerContainer: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};

const staggerItem: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.25, 0.46, 0.45, 0.94] } },
};

function OverviewContent({ data }: { data: BF1Overview }) {
  return (
    <motion.div
      variants={staggerContainer}
      initial="hidden"
      animate="show"
      className="grid grid-cols-1 gap-5 xl:grid-cols-12"
    >
      <div className="space-y-5 xl:col-span-8">
        {/* 海报级数字带：在线人数为主角，四格均按官方/私服拆分 */}
        <section className="grid grid-cols-2 gap-5 lg:grid-cols-4">
          <motion.div variants={staggerItem}>
            <HeroStat
              icon={Users}
              title="当前在线"
              value={data.players.total}
              suffix="人"
              breakdown={data.players}
              emphasis
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <HeroStat
              icon={Server}
              title="服务器总数"
              value={data.servers.total}
              suffix="台"
              breakdown={data.servers}
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <HeroStat
              icon={Clock4}
              title="排队中"
              value={data.queues.total}
              suffix="人"
              breakdown={data.queues}
            />
          </motion.div>
          <motion.div variants={staggerItem}>
            <HeroStat
              icon={Eye}
              title="观战中"
              value={data.spectators.total}
              suffix="人"
              breakdown={data.spectators}
            />
          </motion.div>
        </section>

        <motion.div variants={staggerItem}>
          <TrendPanel points={data.history} />
        </motion.div>

        <section className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <motion.div variants={staggerItem}>
            <RegionPanel data={data} />
          </motion.div>
          <motion.div variants={staggerItem}>
            <ModePanel items={data.mode_distribution} />
          </motion.div>
        </section>

        <motion.p variants={staggerItem} className="text-muted-foreground text-xs">
          {data.updated_at ? `更新于 ${new Date(data.updated_at).toLocaleString("zh-CN")}` : null}
          {data.raw_count > 0
            ? ` · 采样 ${data.servers.total.toLocaleString()} 台（去重后）`
            : null}
        </motion.p>
      </div>

      <motion.div variants={staggerItem} className="xl:col-span-4">
        <TopMapsPanel items={data.top_map_modes} />
      </motion.div>
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

/* ---------- 数字 count-up：mount 时从 0 滚入，60s 刷新时从旧值滚到新值 ---------- */

function CountUp({ value }: { value: number }) {
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => Math.round(v).toLocaleString());

  useEffect(() => {
    const controls = animate(mv, value, { duration: 1.1, ease: "circOut" });
    return () => controls.stop();
  }, [mv, value]);

  return <motion.span>{text}</motion.span>;
}

/* ---------- 数字带单格 ---------- */

function HeroStat({
  icon: Icon,
  title,
  value,
  suffix,
  breakdown,
  emphasis = false,
}: {
  icon: React.ElementType;
  title: string;
  value: number;
  suffix: string;
  breakdown: CountBreakdown;
  emphasis?: boolean;
}) {
  return (
    <Bf1Panel
      variant="transparent"
      cut={24}
      corners={["topLeft", "bottomRight"]}
      className="flex h-full flex-col bg-gradient-to-br from-white/[0.06] to-white/[0.01] p-5"
    >
      <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium tracking-[0.15em] uppercase">
        <Icon className={cn("size-3.5", emphasis ? "text-amber-400" : "text-muted-foreground")} />
        {title}
      </div>
      <div
        className={cn(
          "font-display mt-1.5 font-bold whitespace-nowrap tabular-nums",
          emphasis ? "text-5xl text-amber-400 sm:text-6xl" : "text-4xl text-white sm:text-5xl",
        )}
      >
        <CountUp value={value} />
        <span className="text-muted-foreground ml-1.5 text-base font-normal">{suffix}</span>
      </div>
      <div className="mt-auto pt-4">
        <ShareBar
          segments={[
            { label: "官方", value: breakdown.official, className: "bg-amber-500" },
            { label: "私服", value: breakdown.private, className: "bg-white/25" },
          ]}
        />
      </div>
    </Bf1Panel>
  );
}

/* ---------- 24h 在线趋势面积图（手写 SVG） ---------- */

/** SVG 逻辑坐标系尺寸；preserveAspectRatio="none" 拉伸适配容器，线宽靠 non-scaling-stroke 保持 */
const CHART_W = 1000;
const CHART_H = 240;
const CHART_PAD_TOP = 12;
const CHART_PAD_BOTTOM = 6;

/** 降采样上限：超过后按桶取均值，曲线更平滑、SVG path 更轻 */
const CHART_MAX_POINTS = 288;

function TrendPanel({ points: rawPoints }: { points: TrendPoint[] }) {
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
    // 顶部留 8% 余量，避免峰值顶到面板边缘
    const yMax = Math.max(...points.map((p) => p.players), 1) * 1.08;
    const plotH = CHART_H - CHART_PAD_TOP - CHART_PAD_BOTTOM;
    const x = (p: TrendPoint) => ((p.ts - t0) / span) * CHART_W;
    const y = (v: number) => CHART_PAD_TOP + (1 - v / yMax) * plotH;
    const line = points
      .map((p, i) => `${i === 0 ? "M" : "L"}${x(p).toFixed(1)} ${y(p.players).toFixed(1)}`)
      .join(" ");
    const baseline = CHART_H - CHART_PAD_BOTTOM;
    return { t0, span, yMax, x, y, line, area: `${line} L${CHART_W} ${baseline} L0 ${baseline} Z` };
  }, [points]);

  // 峰值取原始数据，不受降采样均值影响
  const peak = useMemo(
    () => (rawPoints.length > 0 ? Math.max(...rawPoints.map((p) => p.players)) : 0),
    [rawPoints],
  );

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

  const hovered = hoverIdx !== null ? points[hoverIdx] : null;

  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="bg-white/[0.03] p-5"
    >
      <div className="flex items-baseline justify-between gap-4">
        <SectionHeading className="mb-0">24 小时在线趋势</SectionHeading>
        <div className="text-muted-foreground shrink-0 text-xs tabular-nums">
          {hovered ? (
            <>
              {formatTime(hovered.ts)} ·{" "}
              <span className="text-foreground font-medium">
                {hovered.players.toLocaleString()}
              </span>{" "}
              人 · {hovered.servers} 台
            </>
          ) : (
            <>
              峰值 <span className="text-foreground font-medium">{peak.toLocaleString()}</span> 人
            </>
          )}
        </div>
      </div>

      {!chart ? (
        <div className="text-muted-foreground flex h-48 items-center justify-center text-sm">
          趋势数据采集中，每分钟记录一次，约一小时后可见曲线。
        </div>
      ) : (
        <div className="mt-4">
          <div
            ref={plotRef}
            className="relative"
            onMouseMove={handleMove}
            onMouseLeave={() => setHoverIdx(null)}
          >
            <svg
              width="100%"
              height="192"
              viewBox={`0 0 ${CHART_W} ${CHART_H}`}
              preserveAspectRatio="none"
              className="block"
              aria-hidden
            >
              <defs>
                <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgb(245 158 11 / 0.35)" />
                  <stop offset="100%" stopColor="rgb(245 158 11 / 0.02)" />
                </linearGradient>
              </defs>
              {/* 水平参考线：峰值与半值 */}
              {[chart.y(chart.yMax / 1.08), chart.y(chart.yMax / 1.08 / 2)].map((gy) => (
                <line
                  key={gy}
                  x1="0"
                  x2={CHART_W}
                  y1={gy}
                  y2={gy}
                  stroke="rgb(255 255 255 / 0.08)"
                  strokeDasharray="4 6"
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
                d={chart.line}
                fill="none"
                stroke="rgb(245 158 11 / 0.9)"
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 1.3, ease: "easeOut" }}
              />
            </svg>

            {/* hover 跟随竖线与圆点：HTML 绝对定位，避开 SVG 非等比拉伸 */}
            {hovered ? (
              <div
                className="pointer-events-none absolute inset-y-0"
                style={{ left: `${(chart.x(hovered) / CHART_W) * 100}%` }}
              >
                <div className="absolute inset-y-0 w-px bg-white/25" />
                <div
                  className="absolute size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.8)]"
                  style={{ top: `${(chart.y(hovered.players) / CHART_H) * 100}%`, left: "0.5px" }}
                />
              </div>
            ) : null}
          </div>

          {/* 时间轴：首 / 中 / 尾 */}
          <div className="text-muted-foreground/70 mt-2 flex justify-between text-[11px] tabular-nums">
            <span>{formatTime(chart.t0)}</span>
            <span>{formatTime(chart.t0 + chart.span / 2)}</span>
            <span>{formatTime(chart.t0 + chart.span)}</span>
          </div>
        </div>
      )}
    </Bf1Panel>
  );
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

/* ---------- 地区分布 ---------- */

function RegionPanel({ data }: { data: BF1Overview }) {
  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="flex h-full flex-col justify-center gap-5 bg-white/[0.03] p-5"
    >
      <SectionHeading className="mb-0">地区分布</SectionHeading>
      <div className="space-y-4">
        <div>
          <div className="text-muted-foreground mb-2 text-xs">在线人数</div>
          <ShareBar
            segments={[
              { label: "亚洲", value: data.players.asia, className: "bg-amber-500" },
              { label: "欧洲", value: data.players.eu, className: "bg-amber-500/45" },
              { label: "其他", value: data.players.other, className: "bg-white/20" },
            ]}
          />
        </div>
        <div>
          <div className="text-muted-foreground mb-2 text-xs">服务器数</div>
          <ShareBar
            segments={[
              { label: "亚洲", value: data.servers.asia, className: "bg-amber-500" },
              { label: "欧洲", value: data.servers.eu, className: "bg-amber-500/45" },
              { label: "其他", value: data.servers.other, className: "bg-white/20" },
            ]}
          />
        </div>
      </div>
    </Bf1Panel>
  );
}

/* ---------- 模式分布：单条多段堆叠条 + 图例 ---------- */

/** 按排行依次取色，amber 衰减到灰阶；超出部分聚合为「其他」 */
const MODE_SEGMENT_CLASSES = [
  "bg-amber-500",
  "bg-amber-500/70",
  "bg-amber-500/45",
  "bg-amber-500/25",
  "bg-white/30",
  "bg-white/15",
];

function ModePanel({ items }: { items: NamedCount[] }) {
  const segments = useMemo(() => {
    const head = items.slice(0, MODE_SEGMENT_CLASSES.length - 1);
    const tail = items.slice(MODE_SEGMENT_CLASSES.length - 1);
    const merged =
      tail.length > 0
        ? [
            {
              label: "其他",
              servers: tail.reduce((sum, m) => sum + m.servers, 0),
              players: tail.reduce((sum, m) => sum + m.players, 0),
              image: null,
            },
          ]
        : [];
    return [...head, ...merged].map((m, i) => ({ ...m, className: MODE_SEGMENT_CLASSES[i] }));
  }, [items]);

  const totalServers = segments.reduce((sum, s) => sum + s.servers, 0) || 1;

  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="flex h-full flex-col bg-white/[0.03] p-5"
    >
      <SectionHeading className="mb-4">模式分布</SectionHeading>

      <div className="flex h-3 w-full overflow-hidden rounded-sm bg-white/[0.04]">
        {segments.map((s, i) => (
          <motion.div
            key={s.label}
            className={cn("h-full", s.className)}
            initial={{ width: 0 }}
            animate={{ width: `${(s.servers / totalServers) * 100}%` }}
            transition={{ duration: 0.7, delay: 0.4 + i * 0.06, ease: "easeOut" }}
          />
        ))}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {segments.map((s) => (
          <div key={s.label} className="flex items-center gap-2 text-xs">
            <span className={cn("size-2 shrink-0 rounded-[1px]", s.className)} />
            <span className="text-foreground min-w-0 flex-1 truncate">{s.label}</span>
            <span className="text-muted-foreground shrink-0 tabular-nums">
              {s.servers} 台 · {s.players.toLocaleString()} 人
            </span>
          </div>
        ))}
      </div>
    </Bf1Panel>
  );
}

/* ---------- 热门地图模式：Top1 大图卡 + 缩略图行 ---------- */

/** 后端 label 约定为「模式 · 地图」，拆开做两级排版；无分隔符时整串当地图名 */
function splitLabel(label: string): { mode: string | null; map: string } {
  const idx = label.indexOf(" · ");
  if (idx < 0) return { mode: null, map: label };
  return { mode: label.slice(0, idx), map: label.slice(idx + 3) };
}

function TopMapsPanel({ items }: { items: NamedCount[] }) {
  if (items.length === 0) return null;
  const [top, ...rest] = items;
  const maxPlayers = Math.max(...items.map((i) => i.players), 1);
  const topLabel = splitLabel(top.label);

  return (
    <section className="flex h-full flex-col">
      <SectionHeading>热门地图模式</SectionHeading>
      <Bf1Panel
        variant="transparent"
        cut={20}
        corners={["topLeft", "bottomRight"]}
        className="flex flex-1 flex-col overflow-hidden bg-white/[0.02]"
      >
        {/* Top1：地图实景大图卡，延续门户 GameCard 的构图语言 */}
        <div className="group relative aspect-[16/10] shrink-0 overflow-hidden">
          {top.image ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={top.image}
              alt={topLabel.map}
              className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
            />
          ) : (
            <div className="absolute inset-0 bg-gradient-to-br from-white/[0.08] to-white/[0.02]" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/25 to-black/15" />

          <div className="font-display absolute top-3 left-3 flex items-center gap-2 text-xs font-bold tracking-[0.2em] text-amber-400 uppercase">
            <span className="h-[2px] w-5 bg-amber-500" />
            No.1
          </div>

          <div className="absolute inset-x-0 bottom-0 p-4">
            {topLabel.mode ? (
              <div className="font-display text-xs font-medium tracking-[0.2em] text-amber-400 uppercase">
                {topLabel.mode}
              </div>
            ) : null}
            <div className="font-display mt-1 text-2xl font-bold text-white">{topLabel.map}</div>
            <div className="text-muted-foreground mt-1 text-sm tabular-nums">
              {top.servers} 台 ·{" "}
              <span className="text-foreground font-medium">{top.players.toLocaleString()}</span> 人
            </div>
          </div>
        </div>

        {/* 2~N：缩略图行 */}
        <div className="flex-1 divide-y divide-white/[0.06]">
          {rest.map((item, idx) => (
            <MapRow key={item.label} item={item} rank={idx + 2} maxPlayers={maxPlayers} />
          ))}
        </div>
      </Bf1Panel>
    </section>
  );
}

function MapRow({
  item,
  rank,
  maxPlayers,
}: {
  item: NamedCount;
  rank: number;
  maxPlayers: number;
}) {
  const { mode, map } = splitLabel(item.label);
  return (
    <div className="relative px-3 py-2">
      <div
        className="absolute inset-y-0 left-0 bg-gradient-to-r from-amber-500/20 to-amber-500/[0.02]"
        style={{ width: `${(item.players / maxPlayers) * 100}%` }}
        aria-hidden
      />
      <div className="relative flex items-center gap-3">
        <span
          className={cn(
            "font-display w-5 shrink-0 text-center text-xs font-bold tabular-nums",
            rank <= 3 ? "text-amber-400" : "text-muted-foreground/60",
          )}
        >
          {rank}
        </span>
        {item.image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.image}
            alt=""
            className="h-10 w-[71px] shrink-0 rounded-[2px] object-cover"
            loading="lazy"
          />
        ) : (
          <div className="h-10 w-[71px] shrink-0 rounded-[2px] bg-white/[0.06]" />
        )}
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm text-white">{map}</div>
          {mode ? <div className="text-muted-foreground truncate text-xs">{mode}</div> : null}
        </div>
        <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
          {item.servers} 台 ·{" "}
          <span className="text-foreground text-sm">{item.players.toLocaleString()}</span> 人
        </span>
      </div>
    </div>
  );
}

/* ---------- 横向占比条 + 图例 ---------- */

/** 单段占比条用的分段定义：颜色类名直接复用于条与图例色块 */
interface ShareSegment {
  label: string;
  value: number;
  className: string;
}

function ShareBar({ segments }: { segments: ShareSegment[] }) {
  const total = segments.reduce((sum, s) => sum + s.value, 0) || 1;
  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-sm bg-white/[0.04]">
        {segments.map((s, i) => (
          <motion.div
            key={s.label}
            className={cn("h-full", s.className)}
            initial={{ width: 0 }}
            animate={{ width: `${(s.value / total) * 100}%` }}
            transition={{ duration: 0.7, delay: 0.35 + i * 0.06, ease: "easeOut" }}
            aria-hidden
          />
        ))}
      </div>
      <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1.5 text-xs">
        {segments.map((s) => (
          <span key={s.label} className="text-muted-foreground flex items-center gap-1.5">
            <span className={cn("size-2 rounded-[1px]", s.className)} />
            {s.label}
            <span className="text-foreground tabular-nums">{s.value.toLocaleString()}</span>
            <span className="text-muted-foreground/60 tabular-nums">
              {Math.round((s.value / total) * 100)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
