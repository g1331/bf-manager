"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EaLoginFlow } from "@/components/common/EaLoginFlow";
import { type BindingListItem, listMyBindings, unbindEa } from "@/lib/auth";
import { useSession } from "@/hooks/useSession";

export default function AccountPage() {
  const router = useRouter();
  const session = useSession();
  const qc = useQueryClient();
  const [loginFlowOpen, setLoginFlowOpen] = useState(false);

  useEffect(() => {
    if (!session.isLoading && !session.data) {
      router.replace("/login?next=/account");
    }
  }, [session.isLoading, session.data, router]);

  const bindings = useQuery<BindingListItem[]>({
    queryKey: ["my-ea-bindings"],
    queryFn: listMyBindings,
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
    return <main className="text-muted-foreground p-12 text-center">加载中…</main>;
  }

  const user = session.data;

  return (
    <main className="mx-auto max-w-2xl space-y-6 px-4 py-8">
      <Card>
        <CardHeader>
          <CardTitle>账号信息</CardTitle>
          <CardDescription>当前登录的平台账号基础信息。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">username</span>
            <span className="font-mono">{user.username}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">role</span>
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${
                user.role === "admin"
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-secondary-foreground"
              }`}
            >
              {user.role}
            </span>
          </div>
          {user.last_login_at ? (
            <div className="flex justify-between">
              <span className="text-muted-foreground">最近登录</span>
              <span>{new Date(user.last_login_at).toLocaleString()}</span>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle>EA 绑定</CardTitle>
            <Button size="sm" onClick={() => setLoginFlowOpen(true)}>
              用邮箱密码绑定
            </Button>
          </div>
          <CardDescription>
            管理当前账号下的 EA persona 绑定。解绑后该 binding 的加密凭据会被立即清除，
            行记录保留作为历史。可重新走 EA Cookie 登录或邮箱密码绑定恢复关联。
          </CardDescription>
        </CardHeader>
        <CardContent>
          {bindings.isLoading ? (
            <p className="text-muted-foreground text-sm">加载中…</p>
          ) : !bindings.data || bindings.data.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              当前账号尚未绑定任何 EA persona。需要执行 EA 相关操作时，请退出后用 EA Cookie
              重新登录。
            </p>
          ) : (
            <ul className="space-y-3">
              {bindings.data.map((b) => (
                <li
                  key={b.id}
                  className="flex items-center justify-between gap-3 rounded-md border p-3"
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
                          <span className="bg-primary text-primary-foreground rounded px-1.5 py-0.5 text-[10px] font-semibold">
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
        </CardContent>
      </Card>

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
