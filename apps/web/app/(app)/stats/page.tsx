"use client";

import { useQuery } from "@tanstack/react-query";
import { Clock4, Eye } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { BfCard } from "@/components/bf1/visual/BfCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatsOverviewSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ENABLED_GAMES } from "@/lib/game-registry";
import { bf1Api, type BF1Overview, type CountBreakdown, type NamedCount } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

/**
 * 公共全服统计页：免登录可访问，同时是登录后的默认落点。
 * 数据来自后端定时轮询 EA 聚合后写入的 Redis 缓存，前端只读并每 60 秒刷新一次。
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
    <main className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6">
      <PageHeader
        kicker="Overview"
        title="全服统计"
        description="Battlefield 1 全服服务器、在线人数与热门地图模式概况"
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

function OverviewContent({ data }: { data: BF1Overview }) {
  return (
    <>
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <BigStat
          title="服务器总数"
          value={data.servers.total}
          suffix="台"
          breakdown={data.servers}
        />
        <BigStat title="当前在线" value={data.players.total} suffix="人" breakdown={data.players} />
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Bf1Panel
          variant="transparent"
          cut={20}
          corners={["topLeft", "bottomRight"]}
          className="flex flex-col justify-center gap-5 bg-white/[0.03] p-5 lg:col-span-2"
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
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-1">
          <MiniStat icon={Clock4} label="排队中" value={data.queues.total} />
          <MiniStat icon={Eye} label="观战中" value={data.spectators.total} />
        </div>
      </section>

      {data.top_map_modes.length > 0 ? (
        <section>
          <SectionHeading>热门地图模式</SectionHeading>
          <RankBoard items={data.top_map_modes} metric="players" />
        </section>
      ) : null}

      {data.mode_distribution.length > 0 ? (
        <section>
          <SectionHeading>模式分布</SectionHeading>
          <RankBoard items={data.mode_distribution} metric="servers" />
        </section>
      ) : null}

      <p className="text-muted-foreground text-xs">
        {data.updated_at ? `更新于 ${new Date(data.updated_at).toLocaleString("zh-CN")}` : null}
        {data.raw_count > 0 ? ` · 采样 ${data.servers.total.toLocaleString()} 台（去重后）` : null}
      </p>
    </>
  );
}

/** 单段占比条用的分段定义：颜色类名直接复用于条与图例色块 */
interface ShareSegment {
  label: string;
  value: number;
  className: string;
}

function BigStat({
  title,
  value,
  suffix,
  breakdown,
}: {
  title: string;
  value: number;
  suffix: string;
  breakdown: CountBreakdown;
}) {
  return (
    <Bf1Panel
      variant="transparent"
      cut={24}
      corners={["topLeft", "bottomRight"]}
      className="bg-gradient-to-br from-white/[0.06] to-white/[0.01] p-5"
    >
      <div className="text-muted-foreground text-xs font-medium tracking-[0.15em] uppercase">
        {title}
      </div>
      <div className="font-display mt-1.5 text-5xl font-bold text-white tabular-nums sm:text-6xl">
        {value.toLocaleString()}
        <span className="text-muted-foreground ml-1.5 text-base font-normal">{suffix}</span>
      </div>
      <div className="mt-4">
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

/** 横向占比条 + 图例：分段宽度按数值占比，颜色与图例色块一致 */
function ShareBar({ segments }: { segments: ShareSegment[] }) {
  const total = segments.reduce((sum, s) => sum + s.value, 0) || 1;
  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-sm bg-white/[0.04]">
        {segments.map((s) => (
          <div
            key={s.label}
            className={cn("h-full", s.className)}
            style={{ width: `${(s.value / total) * 100}%` }}
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

function MiniStat({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
}) {
  return (
    <div className="flex items-center gap-3 rounded-sm border border-white/10 bg-white/[0.04] p-4 backdrop-blur-md">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-sm bg-white/[0.06] text-amber-400/80">
        <Icon className="size-4" />
      </span>
      <div className="min-w-0">
        <div className="text-muted-foreground text-xs">{label}</div>
        <div className="font-display text-2xl font-bold tabular-nums">{value.toLocaleString()}</div>
      </div>
    </div>
  );
}

/** 排行榜：序号 + 名称 + amber 渐变占比底条 + 台数/人数。metric 决定底条长度依据 */
function RankBoard({ items, metric }: { items: NamedCount[]; metric: "players" | "servers" }) {
  const max = Math.max(...items.map((i) => i[metric]), 1);
  return (
    <Bf1Panel
      variant="transparent"
      cut={16}
      corners={["topLeft", "bottomRight"]}
      className="divide-border divide-y bg-white/[0.02]"
    >
      {items.map((item, idx) => (
        <div key={item.label} className="relative px-4 py-2.5">
          <div
            className="absolute inset-y-0 left-0 bg-gradient-to-r from-amber-500/25 to-amber-500/[0.03]"
            style={{ width: `${(item[metric] / max) * 100}%` }}
            aria-hidden
          />
          <div className="relative flex items-center gap-3 text-sm">
            <span
              className={cn(
                "font-display w-5 shrink-0 text-center text-xs font-bold tabular-nums",
                idx < 3 ? "text-amber-400" : "text-muted-foreground/60",
              )}
            >
              {idx + 1}
            </span>
            <span className="flex-1 truncate">{item.label}</span>
            <span className="text-muted-foreground shrink-0 tabular-nums">
              {item.servers} 台 ·{" "}
              <span className="text-foreground">{item.players.toLocaleString()}</span> 人
            </span>
          </div>
        </div>
      ))}
    </Bf1Panel>
  );
}
