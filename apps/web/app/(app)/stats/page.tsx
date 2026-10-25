"use client";

import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { animate, motion, useMotionValue, useTransform, type Variants } from "framer-motion";
import { Clock4, Eye, Server, Users } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { BfCard } from "@/components/bf1/visual/BfCard";
import { TrendPanel } from "@/components/bf1/visual/TrendPanel";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatsOverviewSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ENABLED_GAMES } from "@/lib/game-registry";
import { bf1Api, type BF1Overview, type CountBreakdown, type NamedCount } from "@/lib/api/bf1";
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
          <TrendPanel
            title="24 小时在线趋势"
            points={data.history}
            emptyText="趋势数据采集中，每分钟记录一次，约一小时后可见曲线。"
            describe={(p) => `${p.servers} 台`}
          />
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
