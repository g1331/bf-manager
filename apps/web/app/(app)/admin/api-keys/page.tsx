"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/layout/PageHeader";
import { AdminPageSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";
import { useSession } from "@/hooks/useSession";
import { apiKeysApi, type AdminApiKeyItem } from "@/lib/api/api-keys";
import { ApiException } from "@/lib/api-client";

// 列多，时间用短格式
function formatTime(value: string | null): string {
  return value
    ? new Date(value).toLocaleString("zh-CN", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
}

export default function ApiKeysAdminPage() {
  const router = useRouter();
  const session = useSession();
  const qc = useQueryClient();
  const [editing, setEditing] = useState<AdminApiKeyItem | null>(null);
  const [multiplier, setMultiplier] = useState("");
  const [pendingRevoke, setPendingRevoke] = useState<AdminApiKeyItem | null>(null);

  const list = useQuery({
    queryKey: ["admin-api-keys"],
    queryFn: apiKeysApi.listAll,
    enabled: session.data?.role === "admin",
  });

  const update = useMutation({
    mutationFn: ({ id, value }: { id: number; value: number | null }) =>
      apiKeysApi.setMultiplier(id, value),
    onSuccess: () => {
      toast.success("已更新额度倍数");
      setEditing(null);
      qc.invalidateQueries({ queryKey: ["admin-api-keys"] });
    },
    onError: (err) => toast.error(err instanceof ApiException ? err.message : "更新失败"),
  });

  const revoke = useMutation({
    mutationFn: (id: number) => apiKeysApi.revoke(id),
    onSuccess: () => {
      toast.success("已吊销");
      setPendingRevoke(null);
      qc.invalidateQueries({ queryKey: ["admin-api-keys"] });
    },
    onError: (err) => toast.error(err instanceof ApiException ? err.message : "吊销失败"),
  });

  if (session.isLoading) {
    return <AdminPageSkeleton />;
  }
  if (!session.data) {
    return (
      <main className="mx-auto max-w-md space-y-4 px-4 py-12 text-center">
        <h1 className="text-xl font-semibold">API Key 管理</h1>
        <p className="text-muted-foreground text-sm">需要先登录</p>
        <Button onClick={() => router.push(`/login?next=${encodeURIComponent("/admin/api-keys")}`)}>
          去登录
        </Button>
      </main>
    );
  }
  if (session.data.role !== "admin") {
    return (
      <main className="mx-auto max-w-md space-y-4 px-4 py-12 text-center">
        <h1 className="text-xl font-semibold">无权访问</h1>
        <p className="text-muted-foreground text-sm">API Key 管理仅平台管理员可见。</p>
      </main>
    );
  }

  const items = list.data?.items ?? [];
  const activeCount = items.filter((k) => !k.revoked_at).length;
  const defaultMultiplier = list.data?.default_multiplier ?? 1;
  const parsed = Number(multiplier);
  const multiplierValid = Number.isInteger(parsed) && parsed >= 1 && parsed <= 50;

  const columns: Column<AdminApiKeyItem>[] = [
    {
      key: "name",
      header: "名称",
      cell: (k) => (
        <div>
          <div className="font-medium">{k.name}</div>
          <div className="text-muted-foreground text-xs">
            <span className="font-mono">{k.prefix}…</span> · {formatTime(k.created_at)} 创建
          </div>
        </div>
      ),
      isCardTitle: true,
    },
    {
      key: "user",
      header: "所属用户",
      cell: (k) => k.user_display_name ?? k.user_username,
    },
    {
      key: "multiplier",
      header: "倍数",
      className: "whitespace-nowrap",
      cell: (k) => (
        <span className="tabular-nums">
          ×{k.rate_multiplier}
          {k.custom_multiplier ? (
            <span className="text-muted-foreground ml-1 text-xs">已调</span>
          ) : null}
        </span>
      ),
    },
    {
      key: "usage",
      header: "今天 / 7 天",
      className: "whitespace-nowrap",
      cell: (k) => (
        <span className="tabular-nums">
          {k.used_today} / {k.used_7d}
        </span>
      ),
    },
    {
      key: "last_used",
      header: "最近使用",
      className: "whitespace-nowrap",
      cell: (k) => formatTime(k.last_used_at),
    },
    {
      key: "actions",
      header: "操作",
      className: "whitespace-nowrap",
      cell: (k) =>
        k.revoked_at ? (
          <span
            className="text-muted-foreground text-sm"
            title={`${formatTime(k.revoked_at)} 吊销`}
          >
            已吊销
          </span>
        ) : (
          <div className="flex gap-4">
            <Button
              variant="ghost"
              size="sm"
              className="compact-action h-auto p-0 hover:bg-transparent hover:underline"
              onClick={() => {
                setEditing(k);
                setMultiplier(String(k.rate_multiplier));
              }}
            >
              调额度
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="compact-action text-destructive h-auto p-0 hover:bg-transparent hover:underline"
              onClick={() => setPendingRevoke(k)}
            >
              吊销
            </Button>
          </div>
        ),
    },
  ];

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6">
      <PageHeader
        kicker="Admin"
        title="API Key 管理"
        description={`用户在「我的主页 → 开放 API」自助申请。默认额度倍数 ×${defaultMultiplier}，和登录用户一样；给可信的机器人调高倍数，滥用的直接吊销。全站 EA 预算对 key 同样生效。`}
      />

      <section className="space-y-3">
        <SectionHeading>
          全部 Key（有效 {activeCount} / 共 {items.length}）
        </SectionHeading>
        {list.isLoading ? (
          <div className="text-muted-foreground p-8 text-center">加载中…</div>
        ) : (
          <ResponsiveTable
            data={items}
            columns={columns}
            rowKey={(k) => k.id}
            emptyState="还没有人申请 API Key"
          />
        )}
      </section>

      <ConfirmSheet
        open={editing !== null}
        onOpenChange={(open) => !open && setEditing(null)}
        title={editing ? `调整「${editing.name}」的额度倍数` : "调整额度倍数"}
        description="查询、只读、头像三类额度都乘以这个倍数，1 到 50。"
        confirmText="保存"
        loading={update.isPending}
        confirmDisabled={!multiplierValid}
        onConfirm={() => {
          if (editing) update.mutate({ id: editing.id, value: parsed });
        }}
      >
        <div className="space-y-2">
          <Input
            type="number"
            inputMode="numeric"
            min={1}
            max={50}
            value={multiplier}
            onChange={(e) => setMultiplier(e.target.value)}
          />
          {editing?.custom_multiplier ? (
            <Button
              variant="link"
              size="sm"
              className="compact-action h-auto px-0"
              disabled={update.isPending}
              onClick={() => update.mutate({ id: editing.id, value: null })}
            >
              恢复默认（×{defaultMultiplier}）
            </Button>
          ) : null}
        </div>
      </ConfirmSheet>

      <ConfirmSheet
        open={pendingRevoke !== null}
        onOpenChange={(open) => !open && setPendingRevoke(null)}
        title={pendingRevoke ? `吊销「${pendingRevoke.name}」？` : "确认吊销"}
        description="吊销后用这个 key 的请求立即返回 401，用户需要重新申请。"
        confirmText="吊销"
        variant="destructive"
        loading={revoke.isPending}
        onConfirm={() => {
          if (pendingRevoke) revoke.mutate(pendingRevoke.id);
        }}
      />
    </main>
  );
}
