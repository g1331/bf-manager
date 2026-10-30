"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ChevronRight, Plus, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageHeaderSkeleton, RowsSkeleton } from "@/components/layout/PageSkeleton";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { useSession } from "@/hooks/useSession";
import { groupsApi, ROLE_LABEL } from "@/lib/api/groups";
import { ApiException } from "@/lib/api-client";

export default function GroupsPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const session = useSession();
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");

  useEffect(() => {
    if (!session.isLoading && !session.isError && !session.data) {
      router.replace("/login?next=/me/groups");
    }
  }, [session.isLoading, session.isError, session.data, router]);

  const groups = useQuery({
    queryKey: ["groups"],
    queryFn: groupsApi.list,
    enabled: !!session.data,
  });

  const create = useMutation({
    mutationFn: () => groupsApi.create(name),
    onSuccess: (group) => {
      qc.invalidateQueries({ queryKey: ["groups"] });
      setCreateOpen(false);
      setName("");
      router.push(`/me/groups/${group.id}`);
    },
    onError: (err) =>
      toast.error(err instanceof ApiException ? err.message : "建群失败，请稍后重试"),
  });

  if (session.isLoading || !session.data || groups.isLoading) {
    return (
      <main className="mx-auto max-w-3xl space-y-6 px-4 py-4 sm:space-y-8 sm:px-6 sm:py-8">
        <PageHeaderSkeleton />
        <RowsSkeleton rows={3} />
      </main>
    );
  }

  const data = groups.data;
  const canCreate = data ? data.create_left === null || data.create_left > 0 : false;

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-4 sm:space-y-8 sm:px-6 sm:py-8">
      <PageHeader
        kicker="Groups"
        title="群组"
        description="和一起管服的人组个群：按角色分工，用邀请链接拉人进来。"
        action={
          <Button size="sm" disabled={!canCreate} onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" />
            建群
          </Button>
        }
      />

      {data && data.items.length > 0 ? (
        <ul className="space-y-3">
          {data.items.map((g) => (
            <li key={g.id}>
              <Link
                href={`/me/groups/${g.id}`}
                className="border-border bg-card group flex items-center gap-4 rounded-sm border p-4 transition-colors hover:border-white/20 hover:bg-white/5"
              >
                <div className="bg-muted flex size-11 shrink-0 items-center justify-center rounded-sm text-lg font-semibold">
                  {g.name.slice(0, 1)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{g.name}</div>
                  <div className="text-muted-foreground mt-0.5 flex items-center gap-3 text-xs">
                    <span>{ROLE_LABEL[g.my_role]}</span>
                    <span className="flex items-center gap-1">
                      <Users className="size-3.5" />
                      {g.member_count} 人
                    </span>
                  </div>
                </div>
                <ChevronRight className="text-muted-foreground group-hover:text-foreground size-4 shrink-0" />
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <div className="border-border text-muted-foreground rounded-sm border border-dashed p-8 text-center text-sm leading-relaxed">
          还没有加入任何群。自己建一个，或者让群管理发一条邀请链接给你。
        </div>
      )}

      {data && data.create_left !== null ? (
        <p className="text-muted-foreground text-xs">
          {data.create_left > 0
            ? `你还能再建 ${data.create_left} 个群。`
            : "建群数量已到上限，删掉不用的群后才能再建。"}
        </p>
      ) : null}

      <ConfirmSheet
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open);
          if (!open) setName("");
        }}
        title="建群"
        description="你会成为群主。之后可以在群里发邀请链接拉人。"
        confirmText="建群"
        loading={create.isPending}
        confirmDisabled={name.trim().length === 0}
        onConfirm={() => create.mutate()}
      >
        <Input
          autoFocus
          value={name}
          maxLength={32}
          placeholder="群名，最多 32 个字"
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && name.trim()) create.mutate();
          }}
        />
      </ConfirmSheet>
    </main>
  );
}
