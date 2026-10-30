"use client";

import { useEffect } from "react";
import { usePageState } from "@/hooks/useNavigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Filter } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/layout/PageHeader";
import { AdminPageSkeleton } from "@/components/layout/PageSkeleton";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";
import {
  auditApi,
  auditGameLabel,
  type AuditLogItem,
  GROUP_ACTION_LABEL,
  GROUP_AUDIT_GAME,
  SITE_ACTION_LABEL,
} from "@/lib/api/audit";
import { useSession } from "@/hooks/useSession";

const ACTION_LABEL: Record<string, string> = {
  kick_player: "踢人",
  add_ban: "封禁",
  remove_ban: "解封",
  choose_level: "换图",
  add_vip: "添加 VIP",
  remove_vip: "移除 VIP",
  vip_apply: "VIP 立即生效",
  vip_expire: "VIP 到期移除",
  add_admin: "添加管理员",
  remove_admin: "移除管理员",
  card_start: "开始卡行动",
  card_anchor: "手动锚定",
  card_success: "卡行动完成",
  card_fail: "卡行动失败",
  card_restore: "恢复卡行动前设置",
  ...GROUP_ACTION_LABEL,
  ...SITE_ACTION_LABEL,
};

export default function AdminAuditPage() {
  const router = useRouter();
  const session = useSession();
  const isAdmin = session.data?.role === "admin";

  const [filters, setFilters] = usePageState<{
    game?: string;
    serverId?: string;
    action?: string;
  }>("admin-audit-filters", {});
  const [page, setPage] = usePageState("admin-audit-page", 1);

  useEffect(() => {
    if (session.isLoading) return;
    // 会话请求自身失败（5xx、网络中断等非 401 错误）时不当作未登录处理，避免把仍持有
    // 有效会话的用户误踢到登录页；getSession 仅在 401 时返回 null。
    if (session.isError) return;
    if (!session.data) {
      router.replace("/login?next=/admin/audit");
    } else if (session.data.role !== "admin") {
      router.replace("/me");
    }
  }, [session.isLoading, session.isError, session.data, router]);

  const logs = useQuery({
    queryKey: ["audit-logs", "admin", filters, page],
    queryFn: () =>
      auditApi.list({
        game: filters.game || undefined,
        serverId: filters.serverId ? Number(filters.serverId) : undefined,
        action: filters.action || undefined,
        page,
        pageSize: 20,
      }),
    enabled: isAdmin,
  });

  if (session.isLoading || !isAdmin) {
    return <AdminPageSkeleton />;
  }

  const columns: Column<AuditLogItem>[] = [
    {
      key: "time",
      header: "时间",
      cell: (l) => new Date(l.created_at).toLocaleString("zh-CN"),
      isCardTitle: true,
    },
    {
      key: "game",
      header: "游戏",
      cell: (l) => auditGameLabel(l.game),
    },
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
        l.game === GROUP_AUDIT_GAME && l.group_id ? (
          <Link
            href={`/me/groups/${l.group_id}`}
            className="text-foreground tabular-nums hover:underline"
          >
            群 #{l.group_id}
          </Link>
        ) : l.server_id ? (
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
        l.game === GROUP_AUDIT_GAME ? (
          (l.target_persona_id ?? "—")
        ) : l.target_persona_id ? (
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
    {
      key: "actor",
      header: "操作人",
      cell: (l) => String(l.acting_persona_id),
    },
  ];

  const totalPages =
    logs.data && logs.data.page_size > 0 ? Math.ceil(logs.data.total / logs.data.page_size) : 0;

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6">
      <PageHeader
        kicker="Audit"
        title="审计日志"
        description="全平台服管操作记录"
        action={
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline">
                <Filter className="size-4" />
                筛选
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="dark w-full sm:max-w-md">
              <SheetHeader>
                <SheetTitle>筛选条件</SheetTitle>
                <SheetDescription>按服务器或操作类型过滤</SheetDescription>
              </SheetHeader>
              <div className="space-y-4 py-6">
                <div className="space-y-2">
                  <Label htmlFor="game-filter">游戏</Label>
                  <Input
                    id="game-filter"
                    value={filters.game ?? ""}
                    onChange={(e) => {
                      setFilters((f) => ({ ...f, game: e.target.value || undefined }));
                      setPage(1);
                    }}
                    placeholder="bf1 / bfv / bf2042"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="server-filter">服务器 game id</Label>
                  <Input
                    id="server-filter"
                    inputMode="numeric"
                    value={filters.serverId ?? ""}
                    onChange={(e) => {
                      setFilters((f) => ({ ...f, serverId: e.target.value || undefined }));
                      setPage(1);
                    }}
                    placeholder="例: 8901234567890"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="action-filter">操作类型</Label>
                  <Input
                    id="action-filter"
                    value={filters.action ?? ""}
                    onChange={(e) => {
                      setFilters((f) => ({ ...f, action: e.target.value || undefined }));
                      setPage(1);
                    }}
                    placeholder="kick_player / add_ban / choose_level"
                  />
                </div>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => {
                    setFilters({});
                    setPage(1);
                  }}
                >
                  清空筛选
                </Button>
              </div>
            </SheetContent>
          </Sheet>
        }
      />

      {logs.isLoading ? (
        <div className="text-muted-foreground p-12 text-center">加载中…</div>
      ) : logs.data ? (
        <>
          <ResponsiveTable
            data={logs.data.items}
            columns={columns}
            rowKey={(l) => l.id}
            emptyState="暂无操作记录"
          />
          {totalPages > 1 ? (
            <Card>
              <CardContent className="flex items-center justify-between p-4 text-sm">
                <span className="text-muted-foreground tabular-nums">
                  共 {logs.data.total} 条 · 第 {logs.data.page} / {totalPages} 页
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    上一页
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    下一页
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
