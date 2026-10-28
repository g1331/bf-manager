"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, KeyRound, ScrollText, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { AdminPageSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { useSession } from "@/hooks/useSession";
import { eaAccountsApi, type EAAccountItem } from "@/lib/api/ea-accounts";
import { membershipsApi } from "@/lib/api/memberships";
import {
  adminApi,
  type AdminMetrics,
  type DailyCount,
  type EaHourCount,
  type EaMethodCount,
  type EaSourceCount,
  type TrackerEventCount,
} from "@/lib/api/admin";

/**
 * 管理员运维概览：平台整体运行情况入口。
 * 汇总 EA 账号池与服管授权概况，并接入访问量、活跃用户、游客与接口调用分布等运维埋点。
 */
export default function AdminOverviewPage() {
  const router = useRouter();
  const session = useSession();
  const isAdmin = session.data?.role === "admin";

  useEffect(() => {
    if (session.isLoading) return;
    // 会话请求自身失败（5xx、网络中断等非 401 错误）时不当作未登录处理，避免把仍持有
    // 有效会话的用户误踢到登录页；getSession 仅在 401 时返回 null。
    if (session.isError) return;
    if (!session.data) {
      router.replace("/login?next=/admin");
    } else if (session.data.role !== "admin") {
      router.replace("/me");
    }
  }, [session.isLoading, session.isError, session.data, router]);

  const eaAccounts = useQuery<EAAccountItem[]>({
    queryKey: ["ea-accounts"],
    queryFn: eaAccountsApi.list,
    enabled: isAdmin,
  });

  const memberships = useQuery({
    queryKey: ["memberships", "admin-overview"],
    queryFn: () => membershipsApi.list({ pageSize: 1 }),
    enabled: isAdmin,
  });

  const metrics = useQuery<AdminMetrics>({
    queryKey: ["admin-metrics"],
    queryFn: adminApi.getMetrics,
    enabled: isAdmin,
    refetchInterval: 60_000,
  });

  if (session.isLoading || !isAdmin) {
    return <AdminPageSkeleton />;
  }

  const eaList = eaAccounts.data ?? [];
  const eaEnabled = eaList.filter((a) => a.enabled).length;
  const eaFailing = eaList.filter((a) => a.failure_count > 0).length;
  const eaUseTotal = eaList.reduce((sum, a) => sum + a.use_count, 0);
  const m = metrics.data;

  return (
    <main className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6">
      <PageHeader
        kicker="Admin"
        title="运维概览"
        description="平台账号池、授权、访问量与接口调用的整体运行情况"
      />

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard title="EA 账号池" value={eaList.length} suffix="个">
          <span className="text-muted-foreground text-xs">
            启用 {eaEnabled} · 故障 {eaFailing} · 累计取用 {eaUseTotal} 次
          </span>
        </StatCard>
        <StatCard title="服管授权" value={memberships.data?.total ?? 0} suffix="条">
          <span className="text-muted-foreground text-xs">当前全平台有效授权总数</span>
        </StatCard>
        <StatCard title="今日访问" value={m?.requests_today ?? 0} suffix="次">
          <span className="text-muted-foreground text-xs">
            今日活跃用户 {m?.active_users_today ?? 0} 人 · 游客 {m?.guests_today ?? 0} 人
          </span>
        </StatCard>
      </section>

      <section>
        <SectionHeading>访问统计</SectionHeading>
        {!m || !m.available ? (
          <div className="border-border bg-card text-muted-foreground rounded-sm border border-dashed p-6 text-sm">
            访问统计依赖 Redis 缓存层。当前缓存层不可用或尚未采集到数据，启用 Redis
            并产生访问后即可在此查看请求量、活跃用户与接口调用分布。
          </div>
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
              <MiniStat label="累计请求" value={m.total_requests} />
              <MiniStat label="近 7 日请求" value={m.requests_7d} />
              <MiniStat label="今日活跃" value={m.active_users_today} suffix="人" />
              <MiniStat label="近 7 日活跃" value={m.active_users_7d} suffix="人" />
              <MiniStat label="今日游客" value={m.guests_today} suffix="人" />
              <MiniStat label="近 7 日游客" value={m.guests_7d} suffix="人" />
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <DailyTrend daily={m.daily} />
              <TopEndpoints endpoints={m.top_endpoints} />
            </div>
          </div>
        )}
      </section>

      {m?.available ? <EaCalls m={m} /> : null}

      <section>
        <SectionHeading>运维入口</SectionHeading>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <NavCard href="/admin/ea-accounts" icon={KeyRound} label="EA 账号池" />
          <NavCard href="/admin/memberships" icon={ShieldCheck} label="服管权限" />
          <NavCard href="/admin/audit" icon={ScrollText} label="审计日志" />
        </div>
      </section>
    </main>
  );
}

function StatCard({
  title,
  value,
  suffix,
  children,
}: {
  title: string;
  value: number;
  suffix: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="border-border bg-card rounded-sm border p-5">
      <div className="text-muted-foreground text-xs font-medium tracking-[0.15em] uppercase">
        {title}
      </div>
      <div className="font-display mt-2 text-4xl font-bold tabular-nums">
        {value}
        {suffix ? (
          <span className="text-muted-foreground ml-1 text-sm font-normal">{suffix}</span>
        ) : null}
      </div>
      {children ? <div className="mt-1">{children}</div> : null}
    </div>
  );
}

function MiniStat({ label, value, suffix }: { label: string; value: number; suffix?: string }) {
  return (
    <div className="border-border bg-card rounded-sm border p-4">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">
        {value}
        {suffix ? (
          <span className="text-muted-foreground ml-1 text-xs font-normal">{suffix}</span>
        ) : null}
      </div>
    </div>
  );
}

function DailyTrend({ daily }: { daily: DailyCount[] }) {
  const max = Math.max(1, ...daily.map((d) => d.requests));
  return (
    <div className="border-border bg-card rounded-sm border p-5">
      <div className="text-muted-foreground mb-4 text-xs font-medium tracking-[0.15em] uppercase">
        近 7 日请求趋势
      </div>
      {daily.length === 0 ? (
        <p className="text-muted-foreground text-sm">暂无数据</p>
      ) : (
        <div className="flex items-stretch gap-2" style={{ height: 150 }}>
          {daily.map((d) => (
            <div key={d.date} className="flex flex-1 flex-col items-center gap-1.5">
              <span className="text-muted-foreground text-[10px] tabular-nums">{d.requests}</span>
              <div className="flex w-full flex-1 items-end">
                <div
                  className="bg-foreground/25 hover:bg-foreground/40 w-full rounded-sm transition-colors"
                  style={{ height: `${Math.max(2, (d.requests / max) * 100)}%` }}
                  title={`${d.date} · ${d.requests} 次 · 活跃 ${d.active_users} 人 · 游客 ${d.guests} 人`}
                />
              </div>
              <span className="text-muted-foreground text-[10px] tabular-nums">
                {d.date.slice(5)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TopEndpoints({ endpoints }: { endpoints: { group: string; count: number }[] }) {
  const max = Math.max(1, ...endpoints.map((e) => e.count));
  return (
    <div className="border-border bg-card rounded-sm border p-5">
      <div className="text-muted-foreground mb-4 text-xs font-medium tracking-[0.15em] uppercase">
        热门接口
      </div>
      {endpoints.length === 0 ? (
        <p className="text-muted-foreground text-sm">暂无数据</p>
      ) : (
        <ul className="space-y-2.5">
          {endpoints.map((e) => (
            <li key={e.group} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span className="font-mono text-xs">{e.group}</span>
                <span className="text-muted-foreground tabular-nums">{e.count}</span>
              </div>
              <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
                <div
                  className="bg-foreground/30 h-full rounded-full"
                  style={{ width: `${Math.max(2, (e.count / max) * 100)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** 后台任务的来源名；api:xxx 是用户访问对应接口分组时发出的 */
const EA_SOURCE_LABEL: Record<string, string> = {
  tracker: "对局跟踪",
  tracker_probe: "结算探测",
  tracker_weapons: "对局武器载具",
  snapshot: "全服快照",
  server_id: "serverId 解析",
  auto_switch: "自动换图",
  exchange: "交换",
  other: "其他",
};

function eaSourceLabel(source: string): string {
  if (source.startsWith("api:")) return `接口 ${source.slice(4)}`;
  return EA_SOURCE_LABEL[source] ?? source;
}

/**
 * 发给 EA 的请求：Blaze 长连接、Gateway JSON-RPC 和登录用的 HTTP 请求，按来源拆开。
 * 每 30 秒合并写入一次，所以最新半分钟还没算进来；日期和小时都按 UTC 分桶。
 */
function EaCalls({ m }: { m: AdminMetrics }) {
  const lastHour = m.ea_hourly.at(-1)?.count ?? 0;
  const prevHour = m.ea_hourly.at(-2)?.count ?? 0;
  return (
    <section>
      <SectionHeading>EA 请求</SectionHeading>
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <MiniStat label="今日（UTC）" value={m.ea_calls_today} suffix="次" />
          <MiniStat label="近 7 日" value={m.ea_calls_7d} suffix="次" />
          <MiniStat label="本小时" value={lastHour} suffix="次" />
          <MiniStat label="上一小时平均" value={Math.round(prevHour / 60)} suffix="次/分" />
        </div>
        <EaHourly hours={m.ea_hourly} />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <EaSources sources={m.ea_sources} />
          <EaMethods methods={m.ea_methods} />
        </div>
        <TrackerEvents events={m.tracker_events} />
      </div>
    </section>
  );
}

function EaHourly({ hours }: { hours: EaHourCount[] }) {
  const max = Math.max(1, ...hours.map((h) => h.count));
  return (
    <div className="border-border bg-card rounded-sm border p-5">
      <div className="text-muted-foreground mb-4 text-xs font-medium tracking-[0.15em] uppercase">
        近 24 小时
      </div>
      <div className="flex items-stretch gap-1" style={{ height: 120 }}>
        {hours.map((h) => {
          const at = new Date(h.hour);
          const label = `${String(at.getHours()).padStart(2, "0")}:00`;
          return (
            <div key={h.hour} className="flex flex-1 flex-col items-center gap-1">
              <div className="flex w-full flex-1 items-end">
                <div
                  className="bg-foreground/25 hover:bg-foreground/40 w-full rounded-sm transition-colors"
                  style={{ height: `${Math.max(2, (h.count / max) * 100)}%` }}
                  title={`${label} · ${h.count} 次`}
                />
              </div>
              <span className="text-muted-foreground text-[9px] tabular-nums">
                {at.getHours() % 3 === 0 ? label.slice(0, 2) : "\u00a0"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EaSources({ sources }: { sources: EaSourceCount[] }) {
  return (
    <div className="border-border bg-card rounded-sm border p-5">
      <div className="text-muted-foreground mb-4 text-xs font-medium tracking-[0.15em] uppercase">
        今日按来源
      </div>
      {sources.length === 0 ? (
        <p className="text-muted-foreground text-sm">暂无数据</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-muted-foreground text-xs">
            <tr>
              <th className="pb-2 text-left font-normal">来源</th>
              <th className="pb-2 text-right font-normal">请求</th>
              <th className="pb-2 text-right font-normal" title="Stats.getStats 查询的人次">
                查询人次
              </th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {sources.map((s) => (
              <tr key={s.source} className="border-border border-t">
                <td className="py-1.5">{eaSourceLabel(s.source)}</td>
                <td className="py-1.5 text-right">{s.calls.toLocaleString("en-US")}</td>
                <td className="text-muted-foreground py-1.5 text-right">
                  {s.pids ? s.pids.toLocaleString("en-US") : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function EaMethods({ methods }: { methods: EaMethodCount[] }) {
  return (
    <div className="border-border bg-card rounded-sm border p-5">
      <div className="text-muted-foreground mb-4 text-xs font-medium tracking-[0.15em] uppercase">
        今日按方法
      </div>
      {methods.length === 0 ? (
        <p className="text-muted-foreground text-sm">暂无数据</p>
      ) : (
        <ul className="max-h-80 space-y-1.5 overflow-y-auto pr-1">
          {methods.map((e) => (
            <li
              key={`${e.channel}|${e.method}|${e.source}`}
              className="flex items-baseline justify-between gap-3 text-sm"
            >
              <span className="min-w-0 truncate">
                <span className="font-mono text-xs">{e.method}</span>
                <span className="text-muted-foreground ml-2 text-xs">
                  {e.channel} · {eaSourceLabel(e.source)}
                </span>
              </span>
              <span className="text-muted-foreground shrink-0 tabular-nums">
                {e.count.toLocaleString("en-US")}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** 对局跟踪器各环节的人数，分三组：本轮查了谁、进服的人从哪来、复查查出了什么 */
const TRACKER_GROUPS: { title: string; items: [string, string][] }[] = [
  {
    title: "按原因查询的人数",
    items: [
      ["want_settle", "结算收尾"],
      ["want_leave", "离开"],
      ["recheck_light", "进服后复查（只查局数胜负）"],
      ["want_recheck", "复查有变化后重查基线"],
      ["want_join", "进服基线"],
    ],
  },
  {
    title: "进服的人",
    items: [
      ["join_fresh", "从离线进服"],
      ["join_hop", "15 分钟内从别的服换来"],
      ["join_reused", "沿用离开上一台服后查到的值"],
    ],
  },
  {
    title: "复查结果",
    items: [
      ["recheck_changed_hop", "有变化 · 换服来的"],
      ["recheck_same_hop", "没变化 · 换服来的"],
      ["recheck_changed_fresh", "有变化 · 离线进服的"],
      ["recheck_same_fresh", "没变化 · 离线进服的"],
    ],
  },
  {
    title: "查到的进服基线和上次比",
    items: [
      ["join_core_same", "没变（14 天内查过）"],
      ["join_core_changed", "变了"],
      ["join_core_unseen", "14 天内没查过"],
      ["stats_missing", "EA 没返回数据，10 分钟后再查"],
    ],
  },
  {
    title: "武器载具",
    items: [
      ["weapons_reused", "核心没变，沿用上次的值"],
      ["weapons_store_hit", "从存档取到上次的值"],
      ["weapons_read", "读了武器类别"],
      ["weapons_failed", "读失败或 EA 缺数据"],
      ["weapons_skipped", "超出每轮上限没读"],
    ],
  },
  {
    title: "驱逐舰 / 飞船 / 岸防炮（冷门类别 3）",
    items: [
      ["weapons_gate_read_3", "哨兵变了，读"],
      ["weapons_gate_skip_3", "哨兵没变，跳过"],
      ["weapons_audit_miss_3", "抽查发现漏判"],
    ],
  },
  {
    title: "轰炸机（冷门类别 4）",
    items: [
      ["weapons_gate_read_4", "哨兵变了，读"],
      ["weapons_gate_skip_4", "哨兵没变，跳过"],
      ["weapons_audit_miss_4", "抽查发现漏判"],
    ],
  },
  {
    title: "武器载具击杀和核心击杀对账（行数，不含战马）",
    items: [
      ["weapons_kills_match", "对得上"],
      ["weapons_kills_diff", "对不上"],
    ],
  },
];

function TrackerEvents({ events }: { events: TrackerEventCount[] }) {
  const byName = new Map(events.map((e) => [e.name, e.count]));
  return (
    <div className="border-border bg-card rounded-sm border p-5">
      <div className="text-muted-foreground mb-4 text-xs font-medium tracking-[0.15em] uppercase">
        对局跟踪（今日人数）
      </div>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
        {TRACKER_GROUPS.map((g) => (
          <div key={g.title}>
            <div className="text-muted-foreground mb-2 text-xs">{g.title}</div>
            <ul className="space-y-1.5 text-sm">
              {g.items.map(([name, label]) => (
                <li key={name} className="flex justify-between gap-3">
                  <span>{label}</span>
                  <span className="text-muted-foreground tabular-nums">
                    {(byName.get(name) ?? 0).toLocaleString("en-US")}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

function NavCard({
  href,
  icon: Icon,
  label,
}: {
  href: string;
  icon: React.ElementType;
  label: string;
}) {
  return (
    <Link
      href={href}
      className="border-border bg-card group flex items-center gap-3 rounded-sm border p-4 text-sm font-medium transition-colors hover:border-white/20 hover:bg-white/5"
    >
      <Icon className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-colors" />
      <span className="flex-1">{label}</span>
      <ChevronRight className="text-muted-foreground group-hover:text-foreground size-4 transition-transform group-hover:translate-x-0.5" />
    </Link>
  );
}
