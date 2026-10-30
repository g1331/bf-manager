"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/layout/PageHeader";
import { AdminPageSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { useSession } from "@/hooks/useSession";
import { adminApi } from "@/lib/api/admin";
import type { RegistrationMode } from "@/lib/auth";
import { ApiException } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const REGISTRATION_OPTIONS: { value: RegistrationMode; label: string; hint: string }[] = [
  {
    value: "open",
    label: "开放注册",
    hint: "谁都能注册，不用邀请码。群邀请链接注册也不占发链接人的邀请名额。",
  },
  {
    value: "invite",
    label: "邀请注册",
    hint: "新账号要填邀请码，或者从群邀请链接进来（占发链接人的邀请名额）。",
  },
  {
    value: "closed",
    label: "暂停注册",
    hint: "不再新建账号，已经发出的注册验证信也打不开。已有账号照常登录，remid 时代的老用户仍能用 EA 邮箱认领旧账号。",
  },
];

const LABEL: Record<RegistrationMode, string> = {
  open: "开放注册",
  invite: "邀请注册",
  closed: "暂停注册",
};

export default function SiteSettingsPage() {
  const router = useRouter();
  const session = useSession();
  const qc = useQueryClient();
  const [pending, setPending] = useState<RegistrationMode | null>(null);

  const registration = useQuery({
    queryKey: ["admin-settings", "registration"],
    queryFn: adminApi.getRegistration,
    enabled: session.data?.role === "admin",
  });

  const save = useMutation({
    mutationFn: adminApi.setRegistration,
    onSuccess: (data) => {
      toast.success(`已切换为${LABEL[data.mode]}`);
      setPending(null);
      qc.setQueryData(["admin-settings", "registration"], data);
      // 注册页、邀请页读的是公开配置
      qc.invalidateQueries({ queryKey: ["auth-config"] });
    },
    onError: (err) => toast.error(err instanceof ApiException ? err.message : "保存失败"),
  });

  if (session.isLoading) {
    return <AdminPageSkeleton />;
  }
  if (!session.data) {
    return (
      <main className="mx-auto max-w-md space-y-4 px-4 py-12 text-center">
        <h1 className="text-xl font-semibold">站点设置</h1>
        <p className="text-muted-foreground text-sm">需要先登录</p>
        <Button onClick={() => router.push(`/login?next=${encodeURIComponent("/admin/settings")}`)}>
          去登录
        </Button>
      </main>
    );
  }
  if (session.data.role !== "admin") {
    return (
      <main className="mx-auto max-w-md space-y-4 px-4 py-12 text-center">
        <h1 className="text-xl font-semibold">无权访问</h1>
        <p className="text-muted-foreground text-sm">站点设置仅平台管理员可见。</p>
      </main>
    );
  }

  const current = registration.data;

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-6 sm:px-6">
      <PageHeader
        kicker="Admin"
        title="站点设置"
        description="改完立即生效，不用重启。每次切换都记在审计日志里。"
      />

      <section className="space-y-3">
        <SectionHeading>注册方式</SectionHeading>
        {registration.isLoading || !current ? (
          <div className="text-muted-foreground p-8 text-center">
            {registration.isError ? "读取失败" : "加载中…"}
          </div>
        ) : (
          <>
            <div role="radiogroup" aria-label="注册方式" className="space-y-2">
              {REGISTRATION_OPTIONS.map((o) => {
                const active = current.mode === o.value;
                return (
                  <button
                    key={o.value}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    disabled={active}
                    onClick={() => setPending(o.value)}
                    className={cn(
                      "flex w-full items-start gap-3 rounded-sm border p-4 text-left transition-colors",
                      active
                        ? "border-amber-500/60 bg-amber-500/10"
                        : "hover:bg-muted/40 border-border",
                    )}
                  >
                    <span
                      aria-hidden
                      className={cn(
                        "mt-1 size-3.5 shrink-0 rounded-full border",
                        active ? "border-amber-500 bg-amber-500" : "border-muted-foreground",
                      )}
                    />
                    <span className="min-w-0 space-y-1">
                      <span className="flex items-center gap-2 font-medium">
                        {o.label}
                        {active ? (
                          <span className="rounded-[2px] bg-amber-500 px-1.5 text-xs text-black">
                            当前
                          </span>
                        ) : null}
                      </span>
                      <span className="text-muted-foreground block text-sm leading-relaxed">
                        {o.hint}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
            <p className="text-muted-foreground text-xs leading-relaxed">
              {current.is_default
                ? "后台还没设过，用的是部署时 REGISTRATION_INVITE_REQUIRED 给的默认值。"
                : `${current.updated_by_name ?? "管理员"} 于 ${
                    current.updated_at ? new Date(current.updated_at).toLocaleString("zh-CN") : "—"
                  } 设置。`}
            </p>
          </>
        )}
      </section>

      <ConfirmSheet
        open={pending !== null}
        onOpenChange={(open) => !open && setPending(null)}
        title={pending ? `切换为${LABEL[pending]}？` : "切换注册方式"}
        description={REGISTRATION_OPTIONS.find((o) => o.value === pending)?.hint}
        confirmText="切换"
        variant={pending === "closed" ? "destructive" : "default"}
        loading={save.isPending}
        onConfirm={() => {
          if (pending) save.mutate(pending);
        }}
      />
    </main>
  );
}
