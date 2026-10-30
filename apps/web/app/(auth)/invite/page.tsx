"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { AuthCard } from "@/components/auth/AuthCard";
import { useAuthConfig } from "@/components/auth/Turnstile";
import { useHashToken } from "@/hooks/useHashToken";
import { useSession } from "@/hooks/useSession";
import {
  clearPendingInvite,
  groupsApi,
  readPendingInvite,
  ROLE_HINT,
  ROLE_LABEL,
  savePendingInvite,
} from "@/lib/api/groups";
import { ApiException } from "@/lib/api-client";

/**
 * 群邀请链接 /invite#token=…：
 * token 读出后记进 sessionStorage，这样去登录、注册、绑定 EA 绕一圈回来还认得是哪个邀请。
 */
export default function InvitePage() {
  const router = useRouter();
  const qc = useQueryClient();
  const hashToken = useHashToken();
  const session = useSession();
  const config = useAuthConfig();
  const registrationClosed = config.data?.registration_mode === "closed";
  const [token, setToken] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    if (hashToken === undefined) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setToken(hashToken ?? readPendingInvite()?.token ?? null);
  }, [hashToken]);

  const lookup = useQuery({
    queryKey: ["group-invite", token],
    queryFn: () => groupsApi.lookupInvite(token as string),
    enabled: !!token,
    retry: false,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (token && lookup.data) savePendingInvite({ token, groupName: lookup.data.group_name });
    if (lookup.isError) clearPendingInvite();
  }, [token, lookup.data, lookup.isError]);

  const accept = useMutation({
    mutationFn: () => groupsApi.acceptInvite(token as string),
    onSuccess: (res) => {
      clearPendingInvite();
      qc.invalidateQueries({ queryKey: ["groups"] });
      toast.success(
        res.already_member ? "你已经在这个群里了" : `已加入 ${lookup.data?.group_name ?? "群组"}`,
      );
      router.replace(`/me/groups/${res.group_id}`);
    },
    onError: (err) => {
      toast.error(err instanceof ApiException ? err.message : "加入失败，请稍后重试");
      if (err instanceof ApiException && err.status === 404) {
        clearPendingInvite();
        qc.invalidateQueries({ queryKey: ["group-invite", token] });
      }
    },
  });

  if (token === undefined || (token && lookup.isLoading) || session.isLoading) {
    return <div className="text-muted-foreground p-12 text-sm">加载中…</div>;
  }

  if (!token || !lookup.data) {
    return (
      <AuthCard
        kicker="Group Invite"
        title="邀请链接用不了"
        description="链接可能已经过期、被作废、次数用完，或者没有复制完整。请找邀请你的人重新发一条。"
      >
        <Button asChild variant="outline" className="w-full">
          <Link href={session.data ? "/me/groups" : "/login"}>
            {session.data ? "看看我的群组" : "去登录"}
          </Link>
        </Button>
      </AuthCard>
    );
  }

  const info = lookup.data;
  const user = session.data;

  return (
    <AuthCard
      kicker="Group Invite"
      title={`加入「${info.group_name}」`}
      description={`${info.inviter_name ?? "群管理"} 邀请你加入这个群组，现在有 ${info.member_count} 人。`}
    >
      <div className="mb-5 space-y-2 rounded-sm border border-white/10 bg-white/[0.03] p-4 text-sm">
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-muted-foreground">进群后的角色</span>
          <span className="font-medium">{ROLE_LABEL[info.role]}</span>
        </div>
        <p className="text-muted-foreground text-xs leading-relaxed">{ROLE_HINT[info.role]}</p>
        <div className="flex items-baseline justify-between gap-3 border-t border-white/10 pt-2">
          <span className="text-muted-foreground">有效期至</span>
          <span className="tabular-nums">{new Date(info.expires_at).toLocaleString("zh-CN")}</span>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-muted-foreground">剩余次数</span>
          <span className="tabular-nums">{info.uses_left}</span>
        </div>
      </div>

      {!user ? (
        <div className="space-y-3">
          <Button asChild size="lg" className="w-full">
            <Link href="/login?next=/invite">已有账号，登录后加入</Link>
          </Button>
          {info.can_register ? (
            <Button asChild size="lg" variant="outline" className="w-full">
              <Link href="/register">没有账号，注册并加入</Link>
            </Button>
          ) : (
            <p className="text-muted-foreground text-sm leading-relaxed">
              {registrationClosed
                ? "现在暂停注册，这条链接只能给已有账号的人用。"
                : "邀请人的邀请名额已经用完，这条链接只能给已有账号的人用。"}
            </p>
          )}
        </div>
      ) : user.status === "pending_binding" ? (
        <div className="space-y-3">
          <p className="text-muted-foreground text-sm leading-relaxed">
            你的账号还没绑定 EA，绑好后会回到这里继续加入。
          </p>
          <Button asChild size="lg" className="w-full">
            <Link href="/bind">去绑定 EA 账号</Link>
          </Button>
        </div>
      ) : (
        <Button
          size="lg"
          className="w-full"
          disabled={accept.isPending}
          onClick={() => accept.mutate()}
        >
          {accept.isPending ? "加入中…" : "加入群组"}
        </Button>
      )}
    </AuthCard>
  );
}
