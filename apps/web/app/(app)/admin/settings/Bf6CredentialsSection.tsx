"use client";

import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { adminApi, type Bf6CredentialStatus } from "@/lib/api/admin";
import { ApiException } from "@/lib/api-client";
import { adminKeys, adminQueries } from "@/lib/queries/admin";
import { cn } from "@/lib/utils";

const DAY_MS = 86_400_000;

function fmt(value: string | null): string {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

type Tone = "ok" | "warn" | "error" | "idle";

function describe(status: Bf6CredentialStatus): { tone: Tone; label: string } {
  if (!status.configured) return { tone: "idle", label: "未配置" };
  const expires = status.refresh_expires_at ? new Date(status.refresh_expires_at).getTime() : null;
  if (expires !== null && expires <= Date.now()) return { tone: "error", label: "已过期" };
  if (status.last_error) return { tone: "error", label: "刷新失败" };
  // 每天自动刷新一次，正常时总剩 8 天以上；剩不到 3 天说明已经连续好几天没刷成功
  if (expires !== null && expires - Date.now() < 3 * DAY_MS)
    return { tone: "warn", label: "即将过期" };
  return { tone: "ok", label: "正常" };
}

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  warn: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  error: "bg-red-500/15 text-red-600 dark:text-red-400",
  idle: "bg-muted text-muted-foreground",
};

export function Bf6CredentialsSection() {
  const qc = useQueryClient();
  const status = useQuery(adminQueries.bf6Credentials());
  const [refreshToken, setRefreshToken] = useState("");
  const [clientSecret, setClientSecret] = useState("");

  const save = useMutation({
    mutationFn: adminApi.setBf6Credentials,
    onSuccess: (data) => {
      toast.success("已保存，EA 验证通过");
      setRefreshToken("");
      setClientSecret("");
      qc.setQueryData(adminKeys.bf6Credentials(), data);
    },
    onError: (err) => toast.error(err instanceof ApiException ? err.message : "保存失败"),
  });

  const current = status.data;
  const needsSecret = !current?.configured;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate({
      refresh_token: refreshToken.trim(),
      client_secret: clientSecret.trim() || undefined,
    });
  };

  return (
    <section className="space-y-3">
      <SectionHeading>BF6 查询凭据</SectionHeading>
      {status.isLoading || !current ? (
        <div className="text-muted-foreground p-8 text-center">
          {status.isError ? "读取失败" : "加载中…"}
        </div>
      ) : (
        <div className="space-y-4 rounded-sm border p-4">
          <StatusRows status={current} />
          <form onSubmit={onSubmit} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="bf6-refresh-token">Refresh token</Label>
              <Input
                id="bf6-refresh-token"
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={refreshToken}
                onChange={(e) => setRefreshToken(e.target.value)}
                placeholder="eyJ…"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="bf6-client-secret">Client secret</Label>
              <Input
                id="bf6-client-secret"
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={clientSecret}
                onChange={(e) => setClientSecret(e.target.value)}
                placeholder={needsSecret ? "" : "留空沿用已保存的值"}
              />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="submit"
                disabled={
                  !refreshToken.trim() || (needsSecret && !clientSecret.trim()) || save.isPending
                }
              >
                {save.isPending ? "验证中…" : "验证并保存"}
              </Button>
              <span className="text-muted-foreground text-xs">
                保存前会先向 EA 刷新一次，失败不保存。
              </span>
            </div>
          </form>
        </div>
      )}
    </section>
  );
}

function StatusRows({ status }: { status: Bf6CredentialStatus }) {
  const { tone, label } = describe(status);
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
      <dt className="text-muted-foreground">状态</dt>
      <dd>
        <span className={cn("rounded-[2px] px-1.5 py-0.5 text-xs font-medium", TONE_CLASS[tone])}>
          {label}
        </span>
      </dd>
      {status.configured ? (
        <>
          <dt className="text-muted-foreground">有效期至</dt>
          <dd className="tabular-nums">{fmt(status.refresh_expires_at)}</dd>
          <dt className="text-muted-foreground">上次刷新</dt>
          <dd className="tabular-nums">{fmt(status.last_refreshed_at)}</dd>
        </>
      ) : null}
      {status.last_error ? (
        <>
          <dt className="text-muted-foreground">失败原因</dt>
          <dd className="break-words text-red-600 dark:text-red-400">
            {status.last_error}
            <span className="text-muted-foreground ml-2 text-xs tabular-nums">
              {fmt(status.last_error_at)}
            </span>
          </dd>
        </>
      ) : null}
    </dl>
  );
}
