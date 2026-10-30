"use client";

/**
 * 服务器详情「成员名单」tab 底部：挂着这台服的群（仅服主与平台管理员可见）。
 *
 * 服务器管理员可以把服挂到自己的群上，群里的人因此在这台服上有服管权限。服主在这里能
 * 看到所有挂着这台服的群，并把任意一个移出。
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { useSession } from "@/hooks/useSession";
import { useMyServerRole } from "@/hooks/useServerAdminActions";
import { canDo } from "@/lib/bf1/server-admin-authz";
import { groupsApi, type ServerGroup } from "@/lib/api/groups";
import { ApiException } from "@/lib/api-client";

export function ServerGroupsPanel({ gameId }: { gameId: number }) {
  const session = useSession();
  const role = useMyServerRole(gameId, !!session.data);
  // 加删服务器管理员是服主权限，和后端 GET /{game_id}/groups 的 min_role 一致
  const isOwner = canDo("addAdmin", role.data);
  const qc = useQueryClient();
  const [removing, setRemoving] = useState<ServerGroup | null>(null);

  const groups = useQuery({
    queryKey: ["bf1-server-groups", gameId],
    queryFn: () => groupsApi.serverGroups(gameId),
    enabled: isOwner,
  });
  const remove = useMutation({
    mutationFn: (groupId: number) => groupsApi.removeServerFromGroup(gameId, groupId),
    onSuccess: () => {
      toast.success("已把这台服从群里移出");
      setRemoving(null);
      qc.invalidateQueries({ queryKey: ["bf1-server-groups", gameId] });
    },
    onError: (err) =>
      toast.error(err instanceof ApiException ? err.message : "操作失败，请稍后重试"),
  });

  if (!isOwner) return null;
  const items = groups.data?.items ?? [];

  return (
    <section className="mt-6 border-t border-white/10 pt-5">
      <h3 className="text-sm font-semibold">挂着这台服的群</h3>
      <p className="text-muted-foreground mt-1 mb-3 text-xs leading-relaxed">
        服务器管理员可以把服挂到自己在本站建的群上，群里的人都能在这台服上执行服管操作。服主可以把任意一个群移出。
      </p>
      {items.length > 0 ? (
        <ul className="divide-y divide-white/10 rounded-sm border border-white/10">
          {items.map((g) => (
            <li key={g.group_id} className="flex items-center gap-3 px-3 py-2">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">
                  {g.group_name}
                  {g.status === "revoked" ? (
                    <span className="text-destructive ml-2 text-xs font-normal">已失效</span>
                  ) : null}
                </div>
                <div className="text-muted-foreground truncate text-xs">
                  {g.bound_by_name ?? "已注销的账号"} 以
                  {g.bound_via === "owner" ? "服主" : "管理员"}
                  身份挂上 · {new Date(g.created_at).toLocaleDateString("zh-CN")}
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="h-11 shrink-0 sm:h-9"
                onClick={() => setRemoving(g)}
              >
                移出
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-sm">
          {groups.isLoading ? "加载中…" : groups.isError ? "读取失败" : "没有群挂着这台服。"}
        </p>
      )}

      <ConfirmSheet
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="从群里移出这台服"
        description={
          removing
            ? `移出后，群「${removing.group_name}」的人在这台服上就没有权限了（自己在 EA 上是管理员的不受影响）。挂服的人还能重新挂上，想彻底拦住要同时撤掉他的服务器管理员。`
            : undefined
        }
        confirmText="移出"
        variant="destructive"
        loading={remove.isPending}
        onConfirm={() => {
          if (removing) remove.mutate(removing.group_id);
        }}
      />
    </section>
  );
}
