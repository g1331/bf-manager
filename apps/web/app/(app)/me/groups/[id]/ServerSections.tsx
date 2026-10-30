"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { KeyRound, MoreHorizontal, Plus, RefreshCw } from "lucide-react";
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
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { EaLoginDialog } from "@/components/common/EaLoginFlow";
import {
  accountLabel,
  type GroupAccount,
  type GroupDetail,
  type GroupServer,
  groupsApi,
} from "@/lib/api/groups";
import { bf1Api } from "@/lib/api/bf1";
import { groupLoginActor } from "@/lib/api/ea-login-tasks";
import { ApiException } from "@/lib/api-client";
import { cn } from "@/lib/utils";

function errorText(err: unknown, fallback: string) {
  return err instanceof ApiException ? err.message : fallback;
}

function Badge({ tone, children }: { tone: "amber" | "red" | "muted"; children: string }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold whitespace-nowrap",
        tone === "amber" && "bg-amber-500 text-black",
        tone === "red" && "bg-destructive/90 text-white",
        tone === "muted" && "bg-secondary text-secondary-foreground",
      )}
    >
      {children}
    </span>
  );
}

function useInvalidate(groupId: number) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["group-accounts", groupId] });
    qc.invalidateQueries({ queryKey: ["group-servers", groupId] });
    qc.invalidateQueries({ queryKey: ["group-audit", groupId] });
  };
}

// ===== 服务账号 =====

export function AccountsSection({ group }: { group: GroupDetail }) {
  const isOwner = group.my_role === "owner";
  const invalidate = useInvalidate(group.id);
  const [cookieOpen, setCookieOpen] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);
  const [remid, setRemid] = useState("");
  const [sid, setSid] = useState("");
  const [removing, setRemoving] = useState<GroupAccount | null>(null);

  const accounts = useQuery({
    queryKey: ["group-accounts", group.id],
    queryFn: () => groupsApi.accounts(group.id),
  });
  const addCookie = useMutation({
    mutationFn: () =>
      groupsApi.addAccountWithCookie(group.id, { remid: remid.trim(), sid: sid.trim() }),
    onSuccess: (a) => {
      toast.success(`已添加服务账号 ${accountLabel(a)}`);
      setCookieOpen(false);
      setRemid("");
      setSid("");
      invalidate();
    },
    onError: (err) => toast.error(errorText(err, "添加失败，请检查 remid / sid")),
  });
  const setDefault = useMutation({
    mutationFn: (accountId: number) => groupsApi.setDefaultAccount(group.id, accountId),
    onSuccess: invalidate,
    onError: (err) => toast.error(errorText(err, "操作失败，请稍后重试")),
  });
  const remove = useMutation({
    mutationFn: (accountId: number) => groupsApi.removeAccount(group.id, accountId),
    onSuccess: () => {
      toast.success("已删除服务账号");
      setRemoving(null);
      invalidate();
    },
    onError: (err) => toast.error(errorText(err, "删除失败，请稍后重试")),
  });

  const items = accounts.data?.items ?? [];

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <SectionHeading className="mb-0">服务账号</SectionHeading>
        {isOwner ? (
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setLoginOpen(true)}>
              <KeyRound className="size-4" />
              账号密码添加
            </Button>
            <Button size="sm" variant="outline" onClick={() => setCookieOpen(true)}>
              <Plus className="size-4" />填 remid 添加
            </Button>
          </div>
        ) : null}
      </div>
      <p className="text-muted-foreground mb-3 text-sm leading-relaxed">
        群里挂的服都用服务账号执行服管操作，EA 那边看到的操作者就是它。这个 EA
        号要先在游戏里被加成服务器管理员。凭据加密保存，只有服管操作会用到。
      </p>
      {items.length > 0 ? (
        <ul className="space-y-2">
          {items.map((a) => (
            <li key={a.id} className="border-border flex items-center gap-3 rounded-sm border p-3">
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="truncate font-medium">{accountLabel(a)}</span>
                  {a.is_default ? <Badge tone="amber">默认</Badge> : null}
                  {a.status === "invalid" ? <Badge tone="red">已失效</Badge> : null}
                </div>
                <div className="text-muted-foreground mt-0.5 text-xs leading-relaxed tabular-nums">
                  {a.status === "invalid"
                    ? `连续登录失败，重新提交凭据后恢复${a.last_error ? `（${a.last_error}）` : ""}`
                    : `persona ${a.persona_id}${
                        a.last_verified_at
                          ? ` · ${new Date(a.last_verified_at).toLocaleString("zh-CN")} 检查过`
                          : ""
                      }`}
                </div>
              </div>
              {isOwner ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`管理 ${accountLabel(a)}`}
                      className="size-11 shrink-0"
                    >
                      <MoreHorizontal className="size-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="dark w-48">
                    <DropdownMenuItem
                      disabled={a.is_default}
                      onSelect={() => setDefault.mutate(a.id)}
                    >
                      设为默认
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem className="text-destructive" onSelect={() => setRemoving(a)}>
                      删除
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-sm">
          {accounts.isLoading
            ? "加载中…"
            : isOwner
              ? "还没有服务账号。先添加一个，再把服挂到群上。"
              : "群主还没有添加服务账号。"}
        </p>
      )}

      <ConfirmSheet
        open={cookieOpen}
        onOpenChange={setCookieOpen}
        title="填 remid 添加服务账号"
        description="在登录了这个 EA 号的浏览器里，从 accounts.ea.com 的 cookie 里复制 remid 和 sid。添加前会先在 EA 上登录一次确认有效。"
        confirmText="添加"
        loading={addCookie.isPending}
        confirmDisabled={remid.trim().length < 10}
        onConfirm={() => addCookie.mutate()}
      >
        <div className="space-y-3">
          <div className="space-y-1.5">
            <div className="text-sm font-medium">remid</div>
            <Input
              value={remid}
              autoComplete="off"
              spellCheck={false}
              className="font-mono text-xs"
              onChange={(e) => setRemid(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <div className="text-sm font-medium">
              sid <span className="text-muted-foreground font-normal">（可不填）</span>
            </div>
            <Input
              value={sid}
              autoComplete="off"
              spellCheck={false}
              className="font-mono text-xs"
              onChange={(e) => setSid(e.target.value)}
            />
          </div>
        </div>
      </ConfirmSheet>

      {isOwner ? (
        <EaLoginDialog
          open={loginOpen}
          onOpenChange={setLoginOpen}
          actor={groupLoginActor(group.id)}
          onSucceeded={invalidate}
        />
      ) : null}

      <ConfirmSheet
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title="删除服务账号"
        description={
          removing
            ? `删除 ${accountLabel(removing)} 后，用它执行的服要换一个服务账号，否则服管操作会失败。`
            : undefined
        }
        confirmText="删除"
        variant="destructive"
        loading={remove.isPending}
        onConfirm={() => {
          if (removing) remove.mutate(removing.id);
        }}
      />
    </section>
  );
}

// ===== 服务器 =====

function ServerRow({
  item,
  accounts,
  isOwner,
  onSetExecutor,
  onUnbind,
}: {
  item: GroupServer;
  accounts: GroupAccount[];
  isOwner: boolean;
  onSetExecutor: (accountId: number) => void;
  onUnbind: () => void;
}) {
  const name = item.name ?? `服务器 #${item.server_id}`;
  const revoked = item.status === "revoked";
  return (
    <li className="border-border flex items-start gap-3 rounded-sm border p-3">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex min-w-0 items-center gap-2">
          {item.game_id ? (
            <Link
              href={`/bf1/server/${item.game_id}`}
              // 触控区保持 44px，用负外边距让它不撑开行距
              className="-my-3 flex min-w-0 items-center font-medium underline-offset-4 hover:underline"
            >
              <span className="truncate">{name}</span>
            </Link>
          ) : (
            <span className="truncate font-medium">{name}</span>
          )}
          {revoked ? <Badge tone="red">已失效</Badge> : null}
        </div>
        {revoked ? (
          <div className="text-destructive text-xs leading-relaxed">
            {item.status_reason ?? "绑定已失效"}，群成员在这台服上没有权限了。
          </div>
        ) : null}
        <div className="text-muted-foreground text-xs leading-relaxed">
          执行账号{" "}
          <span className="text-foreground">
            {item.executor ? accountLabel(item.executor) : "未指定"}
          </span>
          {" · "}
          {item.bound_by_name ?? "已注销的账号"} 以{item.bound_via === "owner" ? "服主" : "管理员"}
          身份挂上
        </div>
        {item.executor_problem && !revoked ? (
          <div className="text-xs leading-relaxed text-amber-400">
            {item.executor_problem}，服管操作会失败
          </div>
        ) : null}
      </div>
      {isOwner ? (
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
          <DropdownMenuContent align="end" className="dark w-56">
            <DropdownMenuLabel>换执行账号</DropdownMenuLabel>
            {accounts.map((a) => (
              <DropdownMenuItem
                key={a.id}
                disabled={a.id === item.executor?.id || a.status === "invalid"}
                onSelect={() => onSetExecutor(a.id)}
              >
                <span className="truncate">{accountLabel(a)}</span>
                {a.id === item.executor?.id
                  ? "（当前）"
                  : a.status === "invalid"
                    ? "（已失效）"
                    : ""}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-destructive" onSelect={onUnbind}>
              从群里移出
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </li>
  );
}

function BindSheet({
  open,
  onOpenChange,
  group,
  accounts,
  boundServerIds,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group: GroupDetail;
  accounts: GroupAccount[];
  boundServerIds: Set<number>;
}) {
  const qc = useQueryClient();
  const invalidate = useInvalidate(group.id);
  const [gameId, setGameId] = useState<number | null>(null);
  const [accountId, setAccountId] = useState<number | null>(null);
  const mine = useQuery({
    queryKey: ["bf1-my-servers"],
    queryFn: () => bf1Api.getMyServers(),
    enabled: open,
  });
  // 只能挂自己在 EA 上是服主或管理员的服；经由群组得来的权限不算
  const candidates = (mine.data?.items ?? []).filter(
    (s) =>
      (s.role === "owner" || s.role === "admin") &&
      !s.via_group &&
      s.game_id != null &&
      !boundServerIds.has(s.server_id),
  );
  const bind = useMutation({
    mutationFn: () =>
      groupsApi.bindServer(group.id, {
        game_id: gameId!,
        ...(accountId ? { account_id: accountId } : {}),
      }),
    onSuccess: (s) => {
      toast.success(`已把「${s.name ?? s.server_id}」挂到群上`);
      onOpenChange(false);
      setGameId(null);
      setAccountId(null);
      invalidate();
      qc.invalidateQueries({ queryKey: ["bf1-my-servers"] });
    },
    onError: (err) => toast.error(errorText(err, "挂服失败，请稍后重试")),
  });

  return (
    <ConfirmSheet
      open={open}
      onOpenChange={onOpenChange}
      title="把服挂到群上"
      description="挂上后群里的人都能在这台服上踢人、换边、封禁、加 V、换图，操作由服务账号执行。"
      confirmText="挂上"
      loading={bind.isPending}
      confirmDisabled={gameId === null || accounts.length === 0}
      onConfirm={() => bind.mutate()}
    >
      <div className="space-y-4">
        <div className="space-y-2">
          <div className="text-sm font-medium">选服务器</div>
          {mine.isLoading ? (
            <p className="text-muted-foreground text-sm">加载中…</p>
          ) : candidates.length > 0 ? (
            <div role="radiogroup" aria-label="选服务器" className="space-y-2">
              {candidates.map((s) => (
                <button
                  key={s.server_pk}
                  type="button"
                  role="radio"
                  aria-checked={gameId === s.game_id}
                  onClick={() => setGameId(s.game_id)}
                  className={cn(
                    "flex min-h-11 w-full items-center justify-between gap-3 rounded-sm border px-3 py-2 text-left text-sm transition-colors",
                    gameId === s.game_id
                      ? "border-amber-500/70 bg-amber-500/10"
                      : "border-border hover:bg-muted/40",
                  )}
                >
                  <span className="truncate">{s.name ?? `服务器 #${s.server_id}`}</span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    {s.role === "owner" ? "服主" : "管理员"}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground text-sm leading-relaxed">
              没有可以挂的服。只能挂你绑定的 EA
              账号是服主或管理员的服：先打开那台服的服务器页，识别出你的身份后它会出现在这里。
            </p>
          )}
        </div>
        {accounts.length > 0 ? (
          <div className="space-y-2">
            <div className="text-sm font-medium">执行账号</div>
            <div className="flex flex-wrap gap-2">
              {[
                { id: null as number | null, label: "自动选" },
                ...accounts
                  .filter((a) => a.status === "ok")
                  .map((a) => ({ id: a.id as number | null, label: accountLabel(a) })),
              ].map((o) => (
                <button
                  key={String(o.id)}
                  type="button"
                  onClick={() => setAccountId(o.id)}
                  className={cn(
                    "h-11 max-w-full truncate rounded-sm border px-3 text-sm transition-colors",
                    accountId === o.id
                      ? "border-amber-500/70 bg-amber-500/10"
                      : "border-border text-muted-foreground hover:text-foreground",
                  )}
                >
                  {o.label}
                </button>
              ))}
            </div>
            <p className="text-muted-foreground text-xs leading-relaxed">
              自动选会从默认账号开始，挑第一个是这台服管理员的。
            </p>
          </div>
        ) : (
          <p className="text-destructive text-sm">群里还没有服务账号，先在上面添加一个。</p>
        )}
      </div>
    </ConfirmSheet>
  );
}

export function ServersSection({ group }: { group: GroupDetail }) {
  const isOwner = group.my_role === "owner";
  const qc = useQueryClient();
  const invalidate = useInvalidate(group.id);
  const [bindOpen, setBindOpen] = useState(false);
  const [unbinding, setUnbinding] = useState<GroupServer | null>(null);

  const servers = useQuery({
    queryKey: ["group-servers", group.id],
    queryFn: () => groupsApi.servers(group.id),
  });
  const accounts = useQuery({
    queryKey: ["group-accounts", group.id],
    queryFn: () => groupsApi.accounts(group.id),
  });
  const setExecutor = useMutation({
    mutationFn: ({ bindingId, accountId }: { bindingId: number; accountId: number }) =>
      groupsApi.setExecutor(group.id, bindingId, accountId),
    onSuccess: () => {
      toast.success("已换执行账号");
      invalidate();
    },
    onError: (err) => toast.error(errorText(err, "操作失败，请稍后重试")),
  });
  const unbind = useMutation({
    mutationFn: (bindingId: number) => groupsApi.unbindServer(group.id, bindingId),
    onSuccess: () => {
      toast.success("已从群里移出");
      setUnbinding(null);
      invalidate();
      qc.invalidateQueries({ queryKey: ["bf1-my-servers"] });
    },
    onError: (err) => toast.error(errorText(err, "操作失败，请稍后重试")),
  });
  const recheck = useMutation({
    mutationFn: () => groupsApi.recheckServers(group.id),
    onSuccess: (data) => {
      qc.setQueryData(["group-servers", group.id], data);
      qc.invalidateQueries({ queryKey: ["group-accounts", group.id] });
      toast.success("已按 EA 现状重新检查");
    },
    onError: (err) => toast.error(errorText(err, "检查失败，请稍后重试")),
  });

  const items = servers.data?.items ?? [];
  const accountItems = accounts.data?.items ?? [];

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <SectionHeading className="mb-0">服务器</SectionHeading>
        {isOwner ? (
          <div className="flex gap-2">
            {items.length > 0 ? (
              <Button
                size="sm"
                variant="outline"
                disabled={recheck.isPending}
                onClick={() => recheck.mutate()}
              >
                <RefreshCw className={cn("size-4", recheck.isPending && "animate-spin")} />
                {recheck.isPending ? "检查中…" : "立即检查"}
              </Button>
            ) : null}
            <Button size="sm" onClick={() => setBindOpen(true)}>
              <Plus className="size-4" />
              挂服务器
            </Button>
          </div>
        ) : null}
      </div>
      <p className="text-muted-foreground mb-3 text-sm leading-relaxed">
        挂在群上的服，群里的人都能在上面踢人、换边、封禁、加 V、换图。只能挂你在 EA
        上是服主或管理员的服；每天会自动检查一次，挂服的人不再是服主或管理员时这台服在群里失效。
      </p>
      {items.length > 0 ? (
        <ul className="space-y-2">
          {items.map((s) => (
            <ServerRow
              key={s.id}
              item={s}
              accounts={accountItems}
              isOwner={isOwner}
              onSetExecutor={(accountId) => setExecutor.mutate({ bindingId: s.id, accountId })}
              onUnbind={() => setUnbinding(s)}
            />
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-sm">
          {servers.isLoading ? "加载中…" : "还没有挂服务器。"}
        </p>
      )}

      {isOwner ? (
        <BindSheet
          open={bindOpen}
          onOpenChange={setBindOpen}
          group={group}
          accounts={accountItems}
          boundServerIds={new Set(items.map((s) => s.server_id))}
        />
      ) : null}

      <ConfirmSheet
        open={unbinding !== null}
        onOpenChange={(o) => !o && setUnbinding(null)}
        title="从群里移出"
        description={
          unbinding
            ? `移出「${unbinding.name ?? unbinding.server_id}」后，群里的人在这台服上就没有权限了（自己在 EA 上是管理员的不受影响）。`
            : undefined
        }
        confirmText="移出"
        variant="destructive"
        loading={unbind.isPending}
        onConfirm={() => {
          if (unbinding) unbind.mutate(unbinding.id);
        }}
      />
    </section>
  );
}
