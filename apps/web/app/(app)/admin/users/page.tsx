"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/layout/PageHeader";
import { AdminPageSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";
import { useSession } from "@/hooks/useSession";
import { adminApi, type AdminUser, type AdminUserFilter } from "@/lib/api/admin";
import { ApiException } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 20;
const REASON_MAX = 200;

const FILTERS: { value: AdminUserFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "frozen", label: "已冻结" },
  { value: "admin", label: "平台管理员" },
];

const STATUS_LABEL: Record<string, string> = {
  active: "正常",
  pending_binding: "待绑 EA",
  legacy: "待认领",
};

function formatTime(value: string | null): string {
  return value
    ? new Date(value).toLocaleString("zh-CN", {
        year: "2-digit",
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
}

function userName(u: AdminUser): string {
  return u.display_name ?? u.username;
}

export default function UsersAdminPage() {
  const router = useRouter();
  const session = useSession();
  const qc = useQueryClient();
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [only, setOnly] = useState<AdminUserFilter>("all");
  const [page, setPage] = useState(1);
  const [freezing, setFreezing] = useState<AdminUser | null>(null);
  const [reason, setReason] = useState("");
  const [unfreezing, setUnfreezing] = useState<AdminUser | null>(null);

  // 输入停下 300ms 再查
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(input.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [input]);

  const isAdmin = session.data?.role === "admin";
  const list = useQuery({
    queryKey: ["admin-users", q, only, page],
    queryFn: () => adminApi.listUsers({ q: q || undefined, only, page, pageSize: PAGE_SIZE }),
    enabled: isAdmin,
    placeholderData: keepPreviousData,
  });

  // 解冻、冻结后总数变少，当前页可能超出末页：退回最后一页
  const lastPage = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.page_size)) : null;
  if (lastPage !== null && page > lastPage) setPage(lastPage);

  const done = (msg: string) => {
    toast.success(msg);
    qc.invalidateQueries({ queryKey: ["admin-users"] });
    qc.invalidateQueries({ queryKey: ["admin-api-keys"] });
  };
  const freeze = useMutation({
    mutationFn: ({ id, text }: { id: number; text: string }) => adminApi.freezeUser(id, text),
    onSuccess: (u) => {
      setFreezing(null);
      setReason("");
      done(`已冻结 ${userName(u)}`);
    },
    onError: (err) => toast.error(err instanceof ApiException ? err.message : "冻结失败"),
  });
  const unfreeze = useMutation({
    mutationFn: (id: number) => adminApi.unfreezeUser(id),
    onSuccess: (u) => {
      setUnfreezing(null);
      done(`已解冻 ${userName(u)}`);
    },
    onError: (err) => toast.error(err instanceof ApiException ? err.message : "解冻失败"),
  });

  if (session.isLoading) {
    return <AdminPageSkeleton />;
  }
  if (!session.data) {
    return (
      <main className="mx-auto max-w-md space-y-4 px-4 py-12 text-center">
        <h1 className="text-xl font-semibold">用户管理</h1>
        <p className="text-muted-foreground text-sm">需要先登录</p>
        <Button onClick={() => router.push(`/login?next=${encodeURIComponent("/admin/users")}`)}>
          去登录
        </Button>
      </main>
    );
  }
  if (!isAdmin) {
    return (
      <main className="mx-auto max-w-md space-y-4 px-4 py-12 text-center">
        <h1 className="text-xl font-semibold">无权访问</h1>
        <p className="text-muted-foreground text-sm">用户管理仅平台管理员可见。</p>
      </main>
    );
  }

  const data = list.data;
  const items = data?.items ?? [];
  const totalPages = lastPage ?? 1;
  const myId = session.data.id;
  const reasonText = reason.trim();

  const columns: Column<AdminUser>[] = [
    {
      key: "user",
      header: "用户",
      isCardTitle: true,
      className: "whitespace-normal",
      cell: (u) => (
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-medium">{userName(u)}</span>
            {u.role === "admin" ? (
              <span className="rounded bg-amber-500 px-1.5 py-0.5 text-[10px] font-semibold text-black">
                平台管理员
              </span>
            ) : null}
            {u.is_frozen ? (
              <span className="bg-destructive/90 rounded px-1.5 py-0.5 text-[10px] font-semibold text-white">
                已冻结
              </span>
            ) : null}
          </div>
          <div
            className="text-muted-foreground truncate text-xs lg:max-w-56"
            title={u.email ?? u.username}
          >
            #{u.id} · {u.email ?? u.username}
          </div>
          <div className="text-muted-foreground text-xs tabular-nums">
            {u.persona_id ? `persona ${u.persona_id}` : "未绑 EA"} · 有效 Key {u.active_api_keys} ·
            最近登录 {formatTime(u.last_login_at)}
          </div>
        </div>
      ),
    },
    {
      key: "status",
      header: "状态",
      className: "min-w-36 whitespace-normal",
      cell: (u) =>
        u.is_frozen ? (
          <div className="max-w-72 text-sm">
            <div className="text-destructive">冻结：{u.frozen_reason}</div>
            <div className="text-muted-foreground text-xs">
              {u.frozen_by_name ?? "—"} · {formatTime(u.frozen_at)}
            </div>
          </div>
        ) : (
          (STATUS_LABEL[u.status] ?? u.status)
        ),
    },
    {
      key: "actions",
      header: "操作",
      className: "whitespace-nowrap",
      cell: (u) =>
        u.is_frozen ? (
          <Button
            variant="ghost"
            size="sm"
            className="-ml-2 h-11 px-2 hover:bg-transparent hover:underline lg:ml-0 lg:h-auto lg:min-h-0 lg:p-0"
            onClick={() => setUnfreezing(u)}
          >
            解冻
          </Button>
        ) : u.role === "admin" || u.id === myId ? (
          <span className="text-muted-foreground text-sm">—</span>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive -ml-2 h-11 px-2 hover:bg-transparent hover:underline lg:ml-0 lg:h-auto lg:min-h-0 lg:p-0"
            onClick={() => {
              setReason("");
              setFreezing(u);
            }}
          >
            冻结
          </Button>
        ),
    },
  ];

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6">
      <PageHeader
        kicker="Admin"
        title="用户管理"
        description="冻结账号会立刻让他所有登录失效、吊销他全部 API Key、挂到群上的服在群里失效，自动换图、计时 VIP 这类他发起的后台任务也会停下。平台管理员不能在这里冻结。"
      />

      <section className="space-y-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <SectionHeading className="mb-0">用户（{data?.total ?? 0}）</SectionHeading>
          <div className="flex flex-col gap-2 xl:flex-row xl:items-center">
            <div
              role="radiogroup"
              aria-label="筛选"
              className="grid grid-cols-3 rounded-sm border border-white/10 bg-white/[0.03] p-1"
            >
              {FILTERS.map((f) => (
                <button
                  key={f.value}
                  type="button"
                  role="radio"
                  aria-checked={only === f.value}
                  onClick={() => {
                    setOnly(f.value);
                    setPage(1);
                  }}
                  className={cn(
                    "h-11 rounded-[2px] px-3 text-sm whitespace-nowrap transition-colors sm:h-9",
                    only === f.value
                      ? "bg-amber-500 font-medium text-black"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <div className="relative xl:w-72 xl:flex-none">
              <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
              <Input
                name="q"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="昵称、邮箱或 persona ID"
                aria-label="搜索用户"
                className="pl-9"
              />
            </div>
          </div>
        </div>

        {list.isLoading ? (
          <div className="text-muted-foreground p-8 text-center">加载中…</div>
        ) : (
          <ResponsiveTable
            data={items}
            columns={columns}
            rowKey={(u) => u.id}
            emptyState={q || only !== "all" ? "没有符合条件的用户" : "还没有用户"}
          />
        )}

        {totalPages > 1 || page > 1 ? (
          <Card>
            <CardContent className="flex items-center justify-between p-4 text-sm">
              <span className="text-muted-foreground tabular-nums">
                共 {data?.total} 人 · 第 {page} / {totalPages} 页
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
      </section>

      <ConfirmSheet
        open={freezing !== null}
        onOpenChange={(open) => !open && setFreezing(null)}
        title={freezing ? `冻结 ${userName(freezing)}？` : "冻结账号"}
        description={
          freezing
            ? `他会立刻被登出、不能再登录；${
                freezing.active_api_keys > 0
                  ? `${freezing.active_api_keys} 个有效 API Key 全部吊销（解冻后也不恢复）；`
                  : ""
              }他挂到群上的服在群里失效。原因会写进审计。`
            : undefined
        }
        confirmText="冻结"
        variant="destructive"
        loading={freeze.isPending}
        confirmDisabled={!reasonText || reasonText.length > REASON_MAX}
        onConfirm={() => {
          if (freezing) freeze.mutate({ id: freezing.id, text: reasonText });
        }}
      >
        <div className="space-y-1.5">
          <div className="text-sm font-medium">冻结原因</div>
          <Input
            name="reason"
            value={reason}
            aria-label="冻结原因"
            maxLength={REASON_MAX}
            placeholder="比如：API Key 刷接口"
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
      </ConfirmSheet>

      <ConfirmSheet
        open={unfreezing !== null}
        onOpenChange={(open) => !open && setUnfreezing(null)}
        title={unfreezing ? `解冻 ${userName(unfreezing)}？` : "解冻账号"}
        description="解冻后他可以重新登录。之前吊销的 API Key 不会恢复，要用得重新申请；失效的挂服等下次每日复核（或群主点「立即检查」）按 EA 现状恢复。"
        confirmText="解冻"
        loading={unfreeze.isPending}
        onConfirm={() => {
          if (unfreezing) unfreeze.mutate(unfreezing.id);
        }}
      />
    </main>
  );
}
