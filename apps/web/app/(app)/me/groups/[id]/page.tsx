"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Link2, MoreHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PageHeader } from "@/components/layout/PageHeader";
import { PageHeaderSkeleton, RowsSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { useSession } from "@/hooks/useSession";
import {
  type GroupAuditItem,
  type GroupDetail,
  type GroupMember,
  type GroupRole,
  groupsApi,
  INVITE_MAX_USES,
  INVITE_TTL_OPTIONS,
  type InviteRole,
  inviteUrl,
  ROLE_HINT,
  ROLE_LABEL,
  ROLE_LEVEL,
} from "@/lib/api/groups";
import { ApiException } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const ALL_ROLES: GroupRole[] = ["owner", "admin", "moderator", "viewer"];

function errorText(err: unknown, fallback: string) {
  return err instanceof ApiException ? err.message : fallback;
}

/** 和后端 group_service._can_manage 一致：owner 管所有人；admin 只在协管、观察员之间调整 */
function roleOptions(me: GroupRole, target: GroupMember): GroupRole[] {
  if (me === "owner") return ALL_ROLES;
  if (me === "admin" && (target.role === "moderator" || target.role === "viewer")) {
    return ["moderator", "viewer"];
  }
  return [];
}

function canRemove(me: GroupRole, target: GroupMember): boolean {
  if (target.is_me) return false;
  return me === "owner" || (me === "admin" && ROLE_LEVEL[target.role] < ROLE_LEVEL.admin);
}

async function copyText(text: string, done: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(done);
  } catch {
    toast.error("复制失败，请手动选中复制");
  }
}

function RoleBadge({ role }: { role: GroupRole }) {
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 text-[10px] font-semibold whitespace-nowrap",
        role === "owner"
          ? "bg-amber-500 text-black"
          : role === "admin"
            ? "bg-foreground text-background"
            : "bg-secondary text-secondary-foreground",
      )}
    >
      {ROLE_LABEL[role]}
    </span>
  );
}

function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="border-border bg-muted/40 grid rounded-sm border p-1"
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    >
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "h-10 rounded-[2px] text-sm font-medium transition-colors",
            value === o.value
              ? "bg-amber-500 text-black"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ===== 成员 =====

function MemberRow({
  member,
  myRole,
  onSetRole,
  onRemove,
}: {
  member: GroupMember;
  myRole: GroupRole;
  onSetRole: (role: GroupRole) => void;
  onRemove: () => void;
}) {
  const options = member.is_me
    ? myRole === "owner"
      ? ALL_ROLES
      : []
    : roleOptions(myRole, member);
  const removable = canRemove(myRole, member);
  const name = member.display_name ?? member.username;
  return (
    <li className="border-border flex items-center gap-3 rounded-sm border p-3">
      {member.avatar_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={member.avatar_url}
          alt={name}
          className="size-10 shrink-0 rounded-full object-cover"
        />
      ) : (
        <div className="bg-muted flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold">
          {name.slice(0, 1).toUpperCase()}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium">{name}</span>
          {member.is_me ? (
            <span className="text-muted-foreground shrink-0 text-xs">（我）</span>
          ) : null}
          <RoleBadge role={member.role} />
        </div>
        <div className="text-muted-foreground mt-0.5 truncate text-xs">
          {member.pending_binding
            ? "还没绑定 EA 账号，暂时没有权限"
            : `${new Date(member.joined_at).toLocaleDateString("zh-CN")} 加入`}
        </div>
      </div>
      {options.length > 0 || removable ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={`管理 ${name}`}
              className="size-11 shrink-0"
            >
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="dark w-48">
            {options.length > 0 ? <DropdownMenuLabel>设为</DropdownMenuLabel> : null}
            {options.map((role) => (
              <DropdownMenuItem
                key={role}
                disabled={role === member.role}
                onSelect={() => onSetRole(role)}
              >
                {ROLE_LABEL[role]}
                {role === member.role ? "（当前）" : ""}
              </DropdownMenuItem>
            ))}
            {removable ? (
              <>
                {options.length > 0 ? <DropdownMenuSeparator /> : null}
                <DropdownMenuItem className="text-destructive" onSelect={onRemove}>
                  移出群
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </li>
  );
}

// ===== 邀请链接 =====

function InviteSection({ group }: { group: GroupDetail }) {
  const qc = useQueryClient();
  const roles = (["admin", "moderator", "viewer"] as InviteRole[]).filter(
    (r) => ROLE_LEVEL[r] < ROLE_LEVEL[group.my_role],
  );
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState<InviteRole>("viewer");
  const [uses, setUses] = useState(1);
  const [ttl, setTtl] = useState(168);
  const [created, setCreated] = useState<string | null>(null);
  const invites = useQuery({
    queryKey: ["group-invites", group.id],
    queryFn: () => groupsApi.invites(group.id),
  });
  const create = useMutation({
    mutationFn: () => groupsApi.createInvite(group.id, { role, max_uses: uses, ttl_hours: ttl }),
    onSuccess: (res) => {
      setOpen(false);
      setCreated(inviteUrl(res.token));
      qc.invalidateQueries({ queryKey: ["group-invites", group.id] });
      qc.invalidateQueries({ queryKey: ["group-audit", group.id] });
    },
    onError: (err) => toast.error(errorText(err, "生成失败，请稍后重试")),
  });
  const revoke = useMutation({
    mutationFn: (inviteId: number) => groupsApi.revokeInvite(group.id, inviteId),
    onSuccess: () => {
      toast.success("链接已作废");
      qc.invalidateQueries({ queryKey: ["group-invites", group.id] });
      qc.invalidateQueries({ queryKey: ["group-audit", group.id] });
    },
    onError: (err) => toast.error(errorText(err, "操作失败，请稍后重试")),
  });

  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <SectionHeading className="mb-0">邀请链接</SectionHeading>
        <Button size="sm" onClick={() => setOpen(true)}>
          <Link2 className="size-4" />
          发邀请链接
        </Button>
      </div>
      <p className="text-muted-foreground mb-3 text-sm leading-relaxed">
        打开链接就能进群；没有账号的人可以直接用它注册，不用邀请码，但会占用你的邀请名额。链接只在生成时显示一次。
      </p>
      {invites.data && invites.data.items.length > 0 ? (
        <ul className="space-y-2">
          {invites.data.items.map((inv) => (
            <li
              key={inv.id}
              className="border-border flex flex-wrap items-center justify-between gap-x-3 gap-y-2 rounded-sm border p-3"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm">
                  <RoleBadge role={inv.role} />
                  <span className="tabular-nums">
                    已用 {inv.uses} / {inv.max_uses}
                  </span>
                </div>
                <div className="text-muted-foreground mt-0.5 text-xs">
                  {inv.created_by_name ?? "已注销的账号"} 发 ·{" "}
                  {new Date(inv.expires_at).toLocaleString("zh-CN")} 过期
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                disabled={revoke.isPending}
                onClick={() => revoke.mutate(inv.id)}
              >
                作废
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-sm">没有还能用的邀请链接。</p>
      )}

      <ConfirmSheet
        open={open}
        onOpenChange={setOpen}
        title="发邀请链接"
        description="链接上的角色要低于你自己的角色。"
        confirmText="生成链接"
        loading={create.isPending}
        onConfirm={() => create.mutate()}
      >
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="text-sm font-medium">进群后的角色</div>
            <Segmented
              label="进群后的角色"
              value={role}
              onChange={setRole}
              options={roles.map((r) => ({ value: r, label: ROLE_LABEL[r] }))}
            />
            <p className="text-muted-foreground text-xs">{ROLE_HINT[role]}</p>
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">能用几次</div>
            <Segmented
              label="能用几次"
              value={uses}
              onChange={setUses}
              options={[1, 3, 5, INVITE_MAX_USES].map((n) => ({ value: n, label: `${n} 次` }))}
            />
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium">有效期</div>
            <Segmented
              label="有效期"
              value={ttl}
              onChange={setTtl}
              options={INVITE_TTL_OPTIONS.map((o) => ({ value: o.hours, label: o.label }))}
            />
          </div>
        </div>
      </ConfirmSheet>

      <ConfirmSheet
        open={created !== null}
        onOpenChange={(o) => !o && setCreated(null)}
        title="邀请链接已生成"
        description="这条链接只显示这一次，现在复制发给要邀请的人。"
        confirmText="复制链接"
        cancelText="关闭"
        onConfirm={() => {
          if (created) void copyText(created, "链接已复制");
        }}
      >
        <Input
          readOnly
          value={created ?? ""}
          className="font-mono text-xs"
          onFocus={(e) => e.target.select()}
        />
      </ConfirmSheet>
    </section>
  );
}

// ===== 群组记录 =====

const ACTION_TEXT: Record<string, (i: GroupAuditItem) => string> = {
  group_create: (i) => `${i.actor_name} 建了群「${String(i.payload.name ?? "")}」`,
  group_rename: (i) =>
    `${i.actor_name} 把群名从「${String(i.payload.from ?? "")}」改成「${String(i.payload.to ?? "")}」`,
  group_member_join: (i) =>
    `${i.actor_name} 通过邀请链接加入，角色${ROLE_LABEL[i.payload.role as GroupRole] ?? ""}`,
  group_member_role: (i) =>
    `${i.actor_name} 把 ${i.target_name} 从${ROLE_LABEL[i.payload.from as GroupRole] ?? ""}调成${ROLE_LABEL[i.payload.to as GroupRole] ?? ""}`,
  group_member_remove: (i) => `${i.actor_name} 把 ${i.target_name} 移出了群`,
  group_leave: (i) => `${i.actor_name} 退出了群`,
  group_invite_create: (i) =>
    `${i.actor_name} 发了一条邀请链接（${ROLE_LABEL[i.payload.role as GroupRole] ?? ""}，可用 ${String(i.payload.max_uses ?? "")} 次）`,
  group_invite_revoke: (i) => `${i.actor_name} 作废了一条邀请链接`,
};

function AuditSection({ groupId }: { groupId: number }) {
  const [page, setPage] = useState(1);
  const audit = useQuery({
    queryKey: ["group-audit", groupId, page],
    queryFn: () => groupsApi.audit(groupId, page),
  });
  const totalPages = audit.data
    ? Math.max(1, Math.ceil(audit.data.total / audit.data.page_size))
    : 1;
  return (
    <section>
      <SectionHeading>群组记录</SectionHeading>
      {audit.data && audit.data.items.length > 0 ? (
        <>
          <ul className="divide-border border-border divide-y rounded-sm border">
            {audit.data.items.map((item) => (
              <li
                key={item.id}
                className="flex flex-col gap-0.5 p-3 sm:flex-row sm:items-baseline sm:gap-4"
              >
                <span className="text-muted-foreground shrink-0 text-xs tabular-nums sm:w-36">
                  {new Date(item.created_at).toLocaleString("zh-CN")}
                </span>
                <span className="text-sm leading-relaxed">
                  {(
                    ACTION_TEXT[item.action] ??
                    ((i: GroupAuditItem) => `${i.actor_name} ${i.action}`)
                  )({
                    ...item,
                    actor_name: item.actor_name ?? "已注销的账号",
                    target_name: item.target_name ?? "已注销的账号",
                  })}
                </span>
              </li>
            ))}
          </ul>
          {totalPages > 1 ? (
            <div className="mt-3 flex items-center justify-between text-sm">
              <span className="text-muted-foreground tabular-nums">
                第 {page} / {totalPages} 页
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
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
            </div>
          ) : null}
        </>
      ) : (
        <p className="text-muted-foreground text-sm">{audit.isLoading ? "加载中…" : "暂无记录"}</p>
      )}
    </section>
  );
}

// ===== 页面 =====

type Pending =
  | { kind: "remove"; member: GroupMember }
  | { kind: "delete" }
  | { kind: "leave" }
  | { kind: "rename" }
  | null;

export default function GroupDetailPage() {
  const params = useParams<{ id: string }>();
  const groupId = Number(params.id);
  const router = useRouter();
  const qc = useQueryClient();
  const session = useSession();
  const [pending, setPending] = useState<Pending>(null);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    if (!session.isLoading && !session.isError && !session.data) {
      router.replace(`/login?next=/me/groups/${groupId}`);
    }
  }, [session.isLoading, session.isError, session.data, router, groupId]);

  const group = useQuery({
    queryKey: ["group", groupId],
    queryFn: () => groupsApi.get(groupId),
    enabled: !!session.data && Number.isFinite(groupId),
    retry: false,
  });

  const refresh = (data?: GroupDetail) => {
    if (data) qc.setQueryData(["group", groupId], data);
    else qc.invalidateQueries({ queryKey: ["group", groupId] });
    qc.invalidateQueries({ queryKey: ["group-audit", groupId] });
    qc.invalidateQueries({ queryKey: ["groups"] });
  };

  const setRole = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: GroupRole }) =>
      groupsApi.setRole(groupId, userId, role),
    onSuccess: (data) => {
      toast.success("角色已调整");
      refresh(data);
    },
    onError: (err) => toast.error(errorText(err, "调整失败，请稍后重试")),
  });
  const removeMember = useMutation({
    mutationFn: (userId: number) => groupsApi.removeMember(groupId, userId),
    onSuccess: (data) => {
      toast.success("已移出");
      setPending(null);
      refresh(data);
    },
    onError: (err) => toast.error(errorText(err, "操作失败，请稍后重试")),
  });
  const rename = useMutation({
    mutationFn: () => groupsApi.rename(groupId, newName),
    onSuccess: (data) => {
      setPending(null);
      refresh(data);
    },
    onError: (err) => toast.error(errorText(err, "改名失败，请稍后重试")),
  });
  const leave = useMutation({
    mutationFn: () => groupsApi.leave(groupId),
    onSuccess: () => {
      toast.success("已退出群");
      qc.invalidateQueries({ queryKey: ["groups"] });
      router.replace("/me/groups");
    },
    onError: (err) => {
      setPending(null);
      toast.error(errorText(err, "操作失败，请稍后重试"));
    },
  });
  const remove = useMutation({
    mutationFn: () => groupsApi.remove(groupId),
    onSuccess: () => {
      toast.success("群已删除");
      qc.invalidateQueries({ queryKey: ["groups"] });
      router.replace("/me/groups");
    },
    onError: (err) => toast.error(errorText(err, "删除失败，请稍后重试")),
  });

  if (session.isLoading || !session.data || group.isLoading) {
    return (
      <main className="mx-auto max-w-3xl space-y-6 px-4 py-4 sm:space-y-8 sm:px-6 sm:py-8">
        <PageHeaderSkeleton />
        <RowsSkeleton rows={5} />
      </main>
    );
  }
  if (!group.data) {
    return (
      <main className="mx-auto max-w-3xl space-y-4 px-4 py-4 sm:px-6 sm:py-8">
        <PageHeader
          kicker="Group"
          title="找不到这个群"
          description="群不存在，或者你已经不在这个群里了。"
        />
        <Button variant="outline" onClick={() => router.push("/me/groups")}>
          回到群组列表
        </Button>
      </main>
    );
  }

  const g = group.data;
  const isOwner = g.my_role === "owner";
  const isAdmin = ROLE_LEVEL[g.my_role] >= ROLE_LEVEL.admin;
  const lastOwner = isOwner && g.members.filter((m) => m.role === "owner").length === 1;

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-4 sm:space-y-8 sm:px-6 sm:py-8">
      <PageHeader
        kicker="Group"
        title={g.name}
        description={`你是${ROLE_LABEL[g.my_role]} · ${g.members.length} 人`}
      />

      <section>
        <SectionHeading>成员</SectionHeading>
        <ul className="space-y-2">
          {g.members.map((m) => (
            <MemberRow
              key={m.user_id}
              member={m}
              myRole={g.my_role}
              onSetRole={(role) => setRole.mutate({ userId: m.user_id, role })}
              onRemove={() => setPending({ kind: "remove", member: m })}
            />
          ))}
        </ul>
      </section>

      {isAdmin ? <InviteSection group={g} /> : null}
      {isAdmin ? <AuditSection groupId={g.id} /> : null}

      <section>
        <SectionHeading>群设置</SectionHeading>
        <div className="border-border divide-border divide-y rounded-sm border">
          {isOwner ? (
            <div className="flex items-center justify-between gap-3 p-3">
              <div className="min-w-0">
                <div className="text-sm">群名</div>
                <div className="text-muted-foreground truncate text-xs">{g.name}</div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setNewName(g.name);
                  setPending({ kind: "rename" });
                }}
              >
                修改
              </Button>
            </div>
          ) : null}
          <div className="flex items-center justify-between gap-3 p-3">
            <div className="min-w-0">
              <div className="text-sm">退出群</div>
              <div className="text-muted-foreground text-xs">
                {lastOwner
                  ? "你是唯一的群主，先把别人设成群主才能退"
                  : "退出后要重新被邀请才能回来"}
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={lastOwner}
              onClick={() => setPending({ kind: "leave" })}
            >
              退出
            </Button>
          </div>
          {isOwner ? (
            <div className="flex items-center justify-between gap-3 p-3">
              <div className="min-w-0">
                <div className="text-destructive text-sm">删除群</div>
                <div className="text-muted-foreground text-xs">
                  所有成员和邀请链接一起删除，不能恢复
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => setPending({ kind: "delete" })}>
                删除
              </Button>
            </div>
          ) : null}
        </div>
      </section>

      <ConfirmSheet
        open={pending?.kind === "remove"}
        onOpenChange={(o) => !o && setPending(null)}
        title="移出成员"
        description={
          pending?.kind === "remove"
            ? `把 ${pending.member.display_name ?? pending.member.username} 移出「${g.name}」？`
            : undefined
        }
        confirmText="移出"
        variant="destructive"
        loading={removeMember.isPending}
        onConfirm={() => {
          if (pending?.kind === "remove") removeMember.mutate(pending.member.user_id);
        }}
      />
      <ConfirmSheet
        open={pending?.kind === "leave"}
        onOpenChange={(o) => !o && setPending(null)}
        title="退出群"
        description={`确定退出「${g.name}」？`}
        confirmText="退出"
        variant="destructive"
        loading={leave.isPending}
        onConfirm={() => leave.mutate()}
      />
      <ConfirmSheet
        open={pending?.kind === "delete"}
        onOpenChange={(o) => !o && setPending(null)}
        title="删除群"
        description={`「${g.name}」和它的 ${g.members.length} 个成员关系、所有邀请链接都会删除，不能恢复。`}
        confirmText="删除"
        variant="destructive"
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
      <ConfirmSheet
        open={pending?.kind === "rename"}
        onOpenChange={(o) => !o && setPending(null)}
        title="修改群名"
        confirmText="保存"
        loading={rename.isPending}
        confirmDisabled={newName.trim().length === 0}
        onConfirm={() => rename.mutate()}
      >
        <Input
          autoFocus
          value={newName}
          maxLength={32}
          onChange={(e) => setNewName(e.target.value)}
        />
      </ConfirmSheet>
    </main>
  );
}
