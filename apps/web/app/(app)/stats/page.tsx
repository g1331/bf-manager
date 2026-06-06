"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Search, Server } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ENABLED_GAMES } from "@/lib/game-registry";
import { bf1Api, type BF1Overview, type CountBreakdown, type NamedCount } from "@/lib/api/bf1";

/**
 * 公共全站统计页：免登录可访问，同时是登录后的默认落点。
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
        title="全站统计"
        description="Battlefield 1 全服服务器、在线人数与热门地图模式概况"
      />

      {overview.isLoading ? (
        <div className="text-muted-foreground p-12 text-center text-sm">加载中…</div>
      ) : !ready ? (
        <section className="border-border bg-card rounded-sm border p-6">
          <div className="text-muted-foreground text-sm">
            全站统计数据正在汇总，稍后将在此处展示服务器总数与当前在线人数。
          </div>
        </section>
      ) : (
        <OverviewContent data={data} />
      )}

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {game ? (
          <>
            <EntryCard
              href={`/${game.id}/players`}
              icon={Search}
              title={`${game.shortName} 战绩查询`}
              description="按玩家昵称查询武器、载具、地图等深度战绩。"
            />
            <EntryCard
              href={`/${game.id}/servers`}
              icon={Server}
              title={`${game.shortName} 服务器`}
              description="浏览实时服务器列表，进入查看玩家、管理员、VIP 与封禁名单。"
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

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <SmallStat label="亚洲在线" value={data.players.asia} />
        <SmallStat label="欧洲在线" value={data.players.eu} />
        <SmallStat label="排队中" value={data.queues.total} />
        <SmallStat label="观战中" value={data.spectators.total} />
      </section>

      {data.top_map_modes.length > 0 ? (
        <section>
          <SectionHeading>热门地图模式</SectionHeading>
          <RankedList items={data.top_map_modes} />
        </section>
      ) : null}

      {data.mode_distribution.length > 0 ? (
        <section>
          <SectionHeading>模式分布</SectionHeading>
          <RankedList items={data.mode_distribution} sortLabel="服务器" />
        </section>
      ) : null}

      <p className="text-muted-foreground text-xs">
        {data.updated_at ? `更新于 ${new Date(data.updated_at).toLocaleString("zh-CN")}` : null}
        {data.raw_count > 0 ? ` · 采样 ${data.servers.total} 台（去重后）` : null}
      </p>
    </>
  );
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
    <div className="border-border bg-card rounded-sm border p-5">
      <div className="text-muted-foreground text-xs font-medium tracking-[0.15em] uppercase">
        {title}
      </div>
      <div className="font-display mt-2 text-5xl font-bold tabular-nums">
        {value.toLocaleString()}
        <span className="text-muted-foreground ml-1.5 text-base font-normal">{suffix}</span>
      </div>
      <div className="text-muted-foreground mt-2 text-xs tabular-nums">
        官方 {breakdown.official.toLocaleString()} · 私服 {breakdown.private.toLocaleString()}
      </div>
    </div>
  );
}

function SmallStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="border-border bg-card rounded-sm border p-4">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="font-display mt-1 text-2xl font-bold tabular-nums">
        {value.toLocaleString()}
      </div>
    </div>
  );
}

function RankedList({ items, sortLabel = "人数" }: { items: NamedCount[]; sortLabel?: string }) {
  const max = Math.max(...items.map((i) => (sortLabel === "服务器" ? i.servers : i.players)), 1);
  return (
    <div className="border-border bg-card divide-border divide-y rounded-sm border">
      {items.map((item) => {
        const primary = sortLabel === "服务器" ? item.servers : item.players;
        return (
          <div key={item.label} className="relative px-4 py-2.5">
            <div
              className="bg-foreground/[0.06] absolute inset-y-0 left-0"
              style={{ width: `${(primary / max) * 100}%` }}
              aria-hidden
            />
            <div className="relative flex items-center justify-between gap-3 text-sm">
              <span className="truncate">{item.label}</span>
              <span className="text-muted-foreground shrink-0 tabular-nums">
                {item.servers} 台 · {item.players.toLocaleString()} 人
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function EntryCard({
  href,
  icon: Icon,
  title,
  description,
}: {
  href: string;
  icon: React.ElementType;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="border-border bg-card group flex items-start gap-4 rounded-sm border p-5 transition-colors hover:border-white/20 hover:bg-white/5"
    >
      <span className="bg-muted text-muted-foreground group-hover:text-foreground flex size-10 shrink-0 items-center justify-center rounded-sm transition-colors">
        <Icon className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 font-medium">
          {title}
          <ChevronRight className="text-muted-foreground group-hover:text-foreground size-4 transition-transform group-hover:translate-x-0.5" />
        </div>
        <p className="text-muted-foreground mt-1 text-sm leading-relaxed">{description}</p>
      </div>
    </Link>
  );
}
