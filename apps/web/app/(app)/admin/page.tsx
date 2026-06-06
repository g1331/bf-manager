"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, KeyRound, ScrollText, ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { useSession } from "@/hooks/useSession";
import { eaAccountsApi, type EAAccountItem } from "@/lib/api/ea-accounts";
import { membershipsApi } from "@/lib/api/memberships";
import { adminApi, type AdminMetrics } from "@/lib/api/admin";

/**
 * 管理员运维概览：平台整体运行情况入口。
 * 汇总 EA 账号池与服管授权概况，并接入访问量、活跃用户与接口调用分布等运维埋点。
 */
export default function AdminOverviewPage() {
  const router = useRouter();
  const session = useSession();
  const isAdmin = session.data?.role === "admin";

  useEffect(() => {
    if (session.isLoading) return;
    if (!session.data) {
      router.replace("/login?next=/admin");
    } else if (session.data.role !== "admin") {
      router.replace("/stats");
    }
  }, [session.isLoading, session.data, router]);

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
    return <main className="text-muted-foreground p-12 text-center">加载中…</main>;
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
            今日活跃用户 {m?.active_users_today ?? 0} 人
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
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <MiniStat label="累计请求" value={m.total_requests} />
              <MiniStat label="近 7 日请求" value={m.requests_7d} />
              <MiniStat label="今日活跃" value={m.active_users_today} suffix="人" />
              <MiniStat label="近 7 日活跃" value={m.active_users_7d} suffix="人" />
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <DailyTrend daily={m.daily} />
              <TopEndpoints endpoints={m.top_endpoints} />
            </div>
          </div>
        )}
      </section>

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

function DailyTrend({
  daily,
}: {
  daily: { date: string; requests: number; active_users: number }[];
}) {
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
                  title={`${d.date} · ${d.requests} 次 · 活跃 ${d.active_users} 人`}
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
