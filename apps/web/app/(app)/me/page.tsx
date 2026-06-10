"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageHeaderSkeleton, RowsSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";
import { EaLoginFlow } from "@/components/common/EaLoginFlow";
import { type BindingListItem, listMyBindings, unbindEa } from "@/lib/auth";
import { auditApi, type AuditLogItem } from "@/lib/api/audit";
import { ENABLED_GAMES } from "@/lib/game-registry";
import { useSession } from "@/hooks/useSession";

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

export default function MePage() {
  const router = useRouter();
  const session = useSession();
  const qc = useQueryClient();
  const [loginFlowOpen, setLoginFlowOpen] = useState(false);
  const [logPage, setLogPage] = useState(1);

  useEffect(() => {
    // 会话请求自身失败（5xx、网络中断等非 401 错误）时不当作未登录处理，避免把仍持有
    // 有效会话的用户误踢到登录页；getSession 仅在 401 时返回 null。
    if (!session.isLoading && !session.isError && !session.data) {
      router.replace("/login?next=/me");
    }
  }, [session.isLoading, session.isError, session.data, router]);

  const bindings = useQuery<BindingListItem[]>({
    queryKey: ["my-ea-bindings"],
    queryFn: listMyBindings,
    enabled: !!session.data,
  });

  const logs = useQuery({
    queryKey: ["audit-logs", "me", logPage],
    queryFn: () => auditApi.list({ page: logPage, pageSize: 10 }),
    enabled: !!session.data,
  });

  const unbindMutation = useMutation({
    mutationFn: unbindEa,
    onSuccess: () => {
      toast.success("已解绑该 EA 账号");
      qc.invalidateQueries({ queryKey: ["my-ea-bindings"] });
      qc.invalidateQueries({ queryKey: ["session"] });
    },
    onError: () => toast.error("解绑失败，请稍后重试"),
  });

  if (session.isLoading || !session.data) {
    return (
      <main className="mx-auto max-w-3xl space-y-8 px-4 py-8 sm:px-6">
        <PageHeaderSkeleton />
        <RowsSkeleton rows={5} />
      </main>
    );
  }

  const user = session.data;
  const primary = user.primary_binding;
  const defaultGame = ENABLED_GAMES[0];

  const logColumns: Column<AuditLogItem>[] = [
    {
      key: "time",
      header: "时间",
      cell: (l) => new Date(l.created_at).toLocaleString("zh-CN"),
      isCardTitle: true,
    },
    { key: "game", header: "游戏", cell: (l) => l.game.toUpperCase() },
    { key: "action", header: "操作", cell: (l) => ACTION_LABEL[l.action] ?? l.action },
    {
      key: "result",
      header: "结果",
      cell: (l) =>
        l.result === "success" ? (
          <span className="text-muted-foreground">成功</span>
        ) : (
          <span className="text-destructive">失败</span>
        ),
    },
    {
      key: "server",
      header: "服务器",
      cell: (l) =>
        l.server_id ? (
          <Link
            href={`/${l.game}/server/${l.server_id}`}
            className="text-foreground tabular-nums hover:underline"
          >
            {l.server_id}
          </Link>
        ) : (
          "—"
        ),
    },
    {
      key: "target",
      header: "目标玩家",
      cell: (l) =>
        l.target_persona_id ? (
          <Link
            href={`/${l.game}/player/${l.target_persona_id}`}
            className="text-foreground tabular-nums hover:underline"
          >
            {l.target_persona_id}
          </Link>
        ) : (
          "—"
        ),
    },
  ];

  const logTotalPages =
    logs.data && logs.data.page_size > 0 ? Math.ceil(logs.data.total / logs.data.page_size) : 0;

  return (
    <main className="mx-auto max-w-3xl space-y-8 px-4 py-8 sm:px-6">
      <PageHeader
        kicker="Profile"
        title="我的主页"
        description="账号信息、个人战绩、EA 绑定与操作记录"
      />

      {/* 账号信息 + 我的战绩 */}
      <section className="flex flex-col gap-4 sm:flex-row sm:items-stretch">
        <div className="border-border bg-card flex flex-1 items-center gap-4 rounded-sm border p-5">
          {primary?.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={primary.avatar_url}
              alt={primary.display_name ?? user.username}
              className="border-border size-14 shrink-0 rounded-sm border object-cover"
            />
          ) : (
            <div className="bg-muted border-border flex size-14 shrink-0 items-center justify-center rounded-sm border text-xl font-bold">
              {(primary?.display_name ?? user.username).slice(0, 1).toUpperCase()}
            </div>
          )}
          <div className="min-w-0">
            <div className="truncate text-lg font-semibold">
              {primary?.display_name ?? user.username}
            </div>
            <div className="text-muted-foreground mt-0.5 text-sm">
              <span className="font-mono">{user.username}</span>
              <span
                className={`ml-2 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                  user.role === "admin"
                    ? "bg-foreground text-background"
                    : "bg-secondary text-secondary-foreground"
                }`}
              >
                {user.role}
              </span>
            </div>
            {user.last_login_at ? (
              <div className="text-muted-foreground mt-1 text-xs">
                上次登录 {new Date(user.last_login_at).toLocaleString("zh-CN")}
              </div>
            ) : null}
          </div>
        </div>

        {primary && defaultGame ? (
          <Link
            href={`/${defaultGame.id}/player/${primary.persona_id}`}
            className="border-border bg-card group flex flex-1 flex-col justify-center gap-1 rounded-sm border p-5 transition-colors hover:border-white/20 hover:bg-white/5"
          >
            <div className="text-muted-foreground text-xs font-medium tracking-[0.15em] uppercase">
              我的战绩
            </div>
            <div className="flex items-center gap-1.5 font-medium">
              查看 {defaultGame.shortName} 战绩
              <ChevronRight className="text-muted-foreground group-hover:text-foreground size-4 transition-transform group-hover:translate-x-0.5" />
            </div>
            <div className="text-muted-foreground text-xs">
              基于主绑定 persona #{primary.persona_id}
            </div>
          </Link>
        ) : (
          <div className="border-border bg-card flex flex-1 flex-col justify-center gap-1 rounded-sm border border-dashed p-5">
            <div className="text-muted-foreground text-xs font-medium tracking-[0.15em] uppercase">
              我的战绩
            </div>
            <div className="text-muted-foreground text-sm">
              绑定 EA persona 后可直接查看个人战绩。
            </div>
          </div>
        )}
      </section>

      {/* EA 绑定 */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <SectionHeading className="mb-0">EA 绑定</SectionHeading>
          <Button size="sm" onClick={() => setLoginFlowOpen(true)}>
            用邮箱密码绑定
          </Button>
        </div>
        {bindings.isLoading ? (
          <p className="text-muted-foreground text-sm">加载中…</p>
        ) : !bindings.data || bindings.data.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            当前账号尚未绑定任何 EA persona。需要执行 EA 相关操作时，请退出后用 EA Cookie
            重新登录，或使用上方邮箱密码绑定。
          </p>
        ) : (
          <ul className="space-y-3">
            {bindings.data.map((b) => (
              <li
                key={b.id}
                className="border-border flex items-center justify-between gap-3 rounded-sm border p-3"
              >
                <div className="flex min-w-0 items-center gap-3">
                  {b.avatar_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={b.avatar_url}
                      alt={b.display_name ?? String(b.persona_id)}
                      className="size-10 shrink-0 rounded-full object-cover"
                    />
                  ) : (
                    <div className="bg-muted flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold">
                      {(b.display_name ?? `#${b.persona_id}`).slice(0, 1).toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium">
                        {b.display_name ?? `Persona ${b.persona_id}`}
                      </span>
                      {b.is_primary ? (
                        <span className="bg-foreground text-background rounded px-1.5 py-0.5 text-[10px] font-semibold">
                          primary
                        </span>
                      ) : null}
                      {b.is_frozen ? (
                        <span className="bg-destructive text-destructive-foreground rounded px-1.5 py-0.5 text-[10px] font-semibold">
                          frozen
                        </span>
                      ) : null}
                    </div>
                    <div className="text-muted-foreground text-xs">
                      ID {b.persona_id}
                      {b.last_verified_at
                        ? ` · 最近校验 ${new Date(b.last_verified_at).toLocaleString()}`
                        : ""}
                    </div>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={b.is_frozen || unbindMutation.isPending}
                  onClick={() => unbindMutation.mutate(b.id)}
                >
                  解绑
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 我的操作日志 */}
      <section>
        <SectionHeading>我的操作日志</SectionHeading>
        {logs.isLoading ? (
          <div className="text-muted-foreground p-8 text-center text-sm">加载中…</div>
        ) : logs.data ? (
          <div className="space-y-4">
            <ResponsiveTable
              data={logs.data.items}
              columns={logColumns}
              rowKey={(l) => l.id}
              emptyState="暂无操作记录"
            />
            {logTotalPages > 1 ? (
              <Card>
                <CardContent className="flex items-center justify-between p-4 text-sm">
                  <span className="text-muted-foreground tabular-nums">
                    共 {logs.data.total} 条 · 第 {logs.data.page} / {logTotalPages} 页
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={logPage <= 1}
                      onClick={() => setLogPage((p) => Math.max(1, p - 1))}
                    >
                      上一页
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={logPage >= logTotalPages}
                      onClick={() => setLogPage((p) => p + 1)}
                    >
                      下一页
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ) : null}
          </div>
        ) : null}
      </section>

      <EaLoginFlow
        actor="user"
        open={loginFlowOpen}
        onOpenChange={setLoginFlowOpen}
        onSucceeded={() => {
          qc.invalidateQueries({ queryKey: ["my-ea-bindings"] });
          qc.invalidateQueries({ queryKey: ["session"] });
        }}
      />
    </main>
  );
}
