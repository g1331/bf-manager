"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { KeyRound, ScrollText, Server, ShieldCheck, UserCog, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { useSession } from "@/hooks/useSession";
import { listMyBindings, type BindingListItem } from "@/lib/auth";
import { auditApi, type AuditLogItem } from "@/lib/api/audit";
import { eaAccountsApi, type EAAccountItem } from "@/lib/api/ea-accounts";
import { membershipsApi } from "@/lib/api/memberships";

const ACTION_LABEL: Record<string, string> = {
  kick_player: "踢人",
  add_ban: "封禁",
  remove_ban: "解封",
  choose_level: "换图",
};

export default function DashboardPage() {
  const router = useRouter();
  const session = useSession();
  const user = session.data;

  const bindings = useQuery<BindingListItem[]>({
    queryKey: ["my-ea-bindings"],
    queryFn: listMyBindings,
    enabled: !!user,
  });

  const recentAudit = useQuery({
    queryKey: ["audit-logs", "dashboard"],
    queryFn: () => auditApi.list({ pageSize: 5 }),
    enabled: !!user,
  });

  const isAdmin = user?.role === "admin";

  const eaAccounts = useQuery<EAAccountItem[]>({
    queryKey: ["ea-accounts"],
    queryFn: eaAccountsApi.list,
    enabled: isAdmin,
  });

  const memberships = useQuery({
    queryKey: ["memberships", "dashboard"],
    queryFn: () => membershipsApi.list({ pageSize: 1 }),
    enabled: isAdmin,
  });

  if (session.isLoading) {
    return <main className="text-muted-foreground p-12 text-center">加载中…</main>;
  }
  if (!user) {
    return (
      <main className="mx-auto max-w-md space-y-4 px-4 py-12 text-center">
        <h1 className="text-xl font-semibold">仪表盘</h1>
        <p className="text-muted-foreground text-sm">查看仪表盘需要先登录</p>
        <Button onClick={() => router.push("/login?next=/dashboard")}>去登录</Button>
      </main>
    );
  }

  const primary = user.primary_binding;
  const displayName = primary?.display_name ?? user.username;
  const bindingCount = bindings.data?.length ?? 0;
  const frozenCount = bindings.data?.filter((b) => b.is_frozen).length ?? 0;

  const eaList = eaAccounts.data ?? [];
  const eaEnabled = eaList.filter((a) => a.enabled).length;
  const eaFailing = eaList.filter((a) => a.failure_count > 0).length;
  const eaNoSession = eaList.filter((a) => !a.has_session).length;

  return (
    <main className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-6">
      {/* 欢迎区 */}
      <section className="flex items-center gap-4">
        {primary?.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={primary.avatar_url}
            alt={displayName}
            className="border-border size-14 shrink-0 rounded-sm border object-cover"
          />
        ) : (
          <div className="bg-muted border-border flex size-14 shrink-0 items-center justify-center rounded-sm border text-xl font-bold">
            {displayName.slice(0, 1).toUpperCase()}
          </div>
        )}
        <div>
          <div className="font-display text-muted-foreground mb-1 flex items-center gap-2 text-xs font-medium tracking-[0.2em] uppercase">
            <span className="bg-muted-foreground h-[2px] w-6" />
            Dashboard
          </div>
          <h1 className="text-2xl font-bold">欢迎回来，{displayName}</h1>
          <p className="text-muted-foreground text-sm">
            {user.role === "admin" ? "平台管理员" : "普通用户"}
            {user.last_login_at
              ? ` · 上次登录 ${new Date(user.last_login_at).toLocaleString("zh-CN")}`
              : ""}
          </p>
        </div>
      </section>

      {/* 统计卡片 */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard title="EA 绑定" value={bindingCount} suffix="个">
          {frozenCount > 0 ? (
            <span className="text-destructive text-xs">其中 {frozenCount} 个已冻结</span>
          ) : bindingCount > 0 ? (
            <span className="text-muted-foreground text-xs">全部正常</span>
          ) : (
            <span className="text-muted-foreground text-xs">尚未绑定 EA 账号</span>
          )}
        </StatCard>

        {isAdmin ? (
          <>
            <StatCard title="EA 账号池" value={eaList.length} suffix="个">
              <span className="text-muted-foreground text-xs">
                启用 {eaEnabled} · 故障 {eaFailing} · 无会话 {eaNoSession}
              </span>
            </StatCard>
            <StatCard title="服管授权" value={memberships.data?.total ?? 0} suffix="条">
              <span className="text-muted-foreground text-xs">当前全平台有效授权总数</span>
            </StatCard>
          </>
        ) : null}
      </section>

      {/* 快捷入口 */}
      <section>
        <SectionHeading>快捷入口</SectionHeading>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <QuickLink href="/bf1/players" icon={Users} label="BF1 战绩查询" />
          <QuickLink href="/bf1/servers" icon={Server} label="BF1 服务器" />
          <QuickLink href="/account" icon={UserCog} label="账号设置" />
          <QuickLink href="/audit-logs" icon={ScrollText} label="操作日志" />
          {isAdmin ? (
            <>
              <QuickLink href="/admin/memberships" icon={ShieldCheck} label="服管权限" />
              <QuickLink href="/admin/ea-accounts" icon={KeyRound} label="EA 账号管理" />
            </>
          ) : null}
        </div>
      </section>

      {/* 最近操作 */}
      {recentAudit.data && recentAudit.data.items.length > 0 ? (
        <section>
          <div className="mb-3 flex items-center justify-between">
            <SectionHeading className="mb-0">最近操作</SectionHeading>
            <Link href="/audit-logs" className="text-foreground text-sm hover:underline">
              查看全部
            </Link>
          </div>
          <div className="border-border bg-card divide-border divide-y rounded-sm border">
            {recentAudit.data.items.map((log) => (
              <RecentLogRow key={log.id} log={log} />
            ))}
          </div>
        </section>
      ) : null}
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
        <span className="text-muted-foreground ml-1 text-sm font-normal">{suffix}</span>
      </div>
      {children ? <div className="mt-1">{children}</div> : null}
    </div>
  );
}

function QuickLink({
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
      className="border-border bg-card group flex items-center gap-3 rounded-sm border p-3 text-sm font-medium transition-colors hover:border-white/20 hover:bg-white/5"
    >
      <Icon className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-colors" />
      {label}
    </Link>
  );
}

function RecentLogRow({ log }: { log: AuditLogItem }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
      <div className="flex items-center gap-3">
        <span className={log.result === "success" ? "text-muted-foreground" : "text-destructive"}>
          {log.result === "success" ? "成功" : "失败"}
        </span>
        <span>{ACTION_LABEL[log.action] ?? log.action}</span>
        <span className="text-muted-foreground font-display tracking-wide">
          {log.game.toUpperCase()}
        </span>
      </div>
      <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
        {new Date(log.created_at).toLocaleString("zh-CN")}
      </span>
    </div>
  );
}
