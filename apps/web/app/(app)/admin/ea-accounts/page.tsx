"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { KeyRound, Pencil, PlugZap, Power, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { PageHeader } from "@/components/layout/PageHeader";
import { AdminPageSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { EaLoginFlow } from "@/components/common/EaLoginFlow";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";

import { useSession } from "@/hooks/useSession";
import { ApiException } from "@/lib/api-client";
import { eaAccountsApi, type EAAccountItem } from "@/lib/api/ea-accounts";

const createSchema = z.object({
  persona_id: z.coerce.number().int().positive("persona_id 必须是正整数"),
  display_name: z.string().max(64).optional(),
  remid: z.string().min(1, "remid 必填"),
  sid: z.string().min(1, "sid 必填"),
  session: z.string().optional(),
  access_token: z.string().optional(),
});

type CreateValues = z.infer<typeof createSchema>;

const CREATE_DEFAULTS: CreateValues = {
  persona_id: 0,
  display_name: "",
  remid: "",
  sid: "",
  session: "",
  access_token: "",
};

const credentialsSchema = z.object({
  remid: z.string().optional(),
  sid: z.string().optional(),
  session: z.string().optional(),
  access_token: z.string().optional(),
});

type CredentialsValues = z.infer<typeof credentialsSchema>;

const CREDENTIALS_DEFAULTS: CredentialsValues = {
  remid: "",
  sid: "",
  session: "",
  access_token: "",
};

const renameSchema = z.object({
  display_name: z.string().max(64, "备注名最长 64 字符").optional(),
});

type RenameValues = z.infer<typeof renameSchema>;

const RENAME_DEFAULTS: RenameValues = { display_name: "" };

function errMsg(err: unknown, fallback: string): string {
  return err instanceof ApiException ? err.message : fallback;
}

type BadgeTone = "default" | "muted" | "outline" | "destructive";

const BADGE_TONE: Record<BadgeTone, string> = {
  default: "bg-foreground text-background",
  muted: "bg-muted text-muted-foreground",
  outline: "border-border text-foreground border",
  destructive: "bg-destructive text-destructive-foreground",
};

function StatusBadge({ tone, children }: { tone: BadgeTone; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${BADGE_TONE[tone]}`}
    >
      {children}
    </span>
  );
}

/** 仅保留非空字段，避免把空字符串当成「清空凭据」写回去。 */
function nonEmpty(values: CredentialsValues): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(values)) {
    if (typeof value === "string" && value.trim() !== "") out[key] = value.trim();
  }
  return out;
}

function RenameSheet({ account, onClose }: { account: EAAccountItem | null; onClose: () => void }) {
  const qc = useQueryClient();
  const form = useForm<RenameValues>({
    resolver: zodResolver(renameSchema),
    defaultValues: RENAME_DEFAULTS,
  });

  // Sheet 打开时预填当前备注，便于在原值上微调
  useEffect(() => {
    if (account) form.reset({ display_name: account.display_name ?? "" });
  }, [account, form]);

  const rename = useMutation({
    mutationFn: (values: RenameValues) => {
      if (!account) throw new Error("no account");
      const trimmed = values.display_name?.trim() ?? "";
      // 空字符串视为「清空备注」→ 后端约定传 null 显式清空
      return eaAccountsApi.updateDisplayName(account.id, {
        display_name: trimmed === "" ? null : trimmed,
      });
    },
    onSuccess: () => {
      toast.success("已更新备注名");
      qc.invalidateQueries({ queryKey: ["ea-accounts"] });
      form.reset(RENAME_DEFAULTS);
      onClose();
    },
    onError: (err) => toast.error(errMsg(err, "更新备注名失败")),
  });

  return (
    <Sheet
      open={account !== null}
      onOpenChange={(open) => {
        if (!open) {
          form.reset(RENAME_DEFAULTS);
          onClose();
        }
      }}
    >
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>修改备注名</SheetTitle>
          <SheetDescription>
            {account
              ? `账号 Persona ${account.persona_id}：备注名仅用于后台辨识，留空将清除当前备注。`
              : ""}
          </SheetDescription>
        </SheetHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit((v) => rename.mutate(v))} className="space-y-4 p-4">
            <FormField
              control={form.control}
              name="display_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>备注名</FormLabel>
                  <FormControl>
                    <Input autoComplete="off" placeholder="留空表示清除备注" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <SheetFooter>
              <Button type="submit" disabled={rename.isPending}>
                {rename.isPending ? "保存中…" : "保存备注"}
              </Button>
            </SheetFooter>
          </form>
        </Form>
      </SheetContent>
    </Sheet>
  );
}

function CredentialsSheet({
  account,
  onClose,
}: {
  account: EAAccountItem | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const form = useForm<CredentialsValues>({
    resolver: zodResolver(credentialsSchema),
    defaultValues: CREDENTIALS_DEFAULTS,
  });

  const update = useMutation({
    mutationFn: (values: CredentialsValues) => {
      if (!account) throw new Error("no account");
      return eaAccountsApi.updateCredentials(account.id, nonEmpty(values));
    },
    onSuccess: () => {
      toast.success("已更新凭据，失败计数已清零");
      qc.invalidateQueries({ queryKey: ["ea-accounts"] });
      form.reset(CREDENTIALS_DEFAULTS);
      onClose();
    },
    onError: (err) => toast.error(errMsg(err, "更新凭据失败")),
  });

  return (
    <Sheet
      open={account !== null}
      onOpenChange={(open) => {
        if (!open) {
          form.reset(CREDENTIALS_DEFAULTS);
          onClose();
        }
      }}
    >
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>更新凭据</SheetTitle>
          <SheetDescription>
            {account
              ? `账号 ${account.display_name ?? `Persona ${account.persona_id}`}：仅填写需要替换的字段，留空保持原值。`
              : ""}
          </SheetDescription>
        </SheetHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit((v) => update.mutate(v))} className="space-y-4 p-4">
            <FormField
              control={form.control}
              name="remid"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>remid</FormLabel>
                  <FormControl>
                    <Input autoComplete="off" placeholder="留空保持原值" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="sid"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>sid</FormLabel>
                  <FormControl>
                    <Input autoComplete="off" placeholder="留空保持原值" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="session"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>session（可选）</FormLabel>
                  <FormControl>
                    <Input autoComplete="off" placeholder="留空保持原值" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="access_token"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>access_token（可选）</FormLabel>
                  <FormControl>
                    <Input autoComplete="off" placeholder="留空保持原值" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <SheetFooter>
              <Button type="submit" disabled={update.isPending}>
                {update.isPending ? "保存中…" : "保存凭据"}
              </Button>
            </SheetFooter>
          </form>
        </Form>
      </SheetContent>
    </Sheet>
  );
}

export default function EAAccountsAdminPage() {
  const router = useRouter();
  const session = useSession();
  const qc = useQueryClient();
  const [pendingDelete, setPendingDelete] = useState<EAAccountItem | null>(null);
  const [editing, setEditing] = useState<EAAccountItem | null>(null);
  const [renaming, setRenaming] = useState<EAAccountItem | null>(null);
  const [loginFlowOpen, setLoginFlowOpen] = useState(false);

  const isAdmin = session.data?.role === "admin";

  const list = useQuery({
    queryKey: ["ea-accounts"],
    queryFn: () => eaAccountsApi.list(),
    enabled: isAdmin,
  });

  const form = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: CREATE_DEFAULTS,
  });

  const create = useMutation({
    mutationFn: (values: CreateValues) =>
      eaAccountsApi.create({
        persona_id: values.persona_id,
        display_name: values.display_name?.trim() || null,
        remid: values.remid,
        sid: values.sid,
        session: values.session?.trim() || null,
        access_token: values.access_token?.trim() || null,
      }),
    onSuccess: () => {
      toast.success("已新增 EA 账号");
      qc.invalidateQueries({ queryKey: ["ea-accounts"] });
      form.reset(CREATE_DEFAULTS);
    },
    onError: (err) => toast.error(errMsg(err, "新增失败")),
  });

  const remove = useMutation({
    mutationFn: (id: number) => eaAccountsApi.delete(id),
    onSuccess: () => {
      toast.success("已删除 EA 账号");
      qc.invalidateQueries({ queryKey: ["ea-accounts"] });
      setPendingDelete(null);
    },
    onError: (err) => toast.error(errMsg(err, "删除失败")),
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      eaAccountsApi.setEnabled(id, enabled),
    onSuccess: (item) => {
      toast.success(item.enabled ? "已启用账号" : "已停用账号");
      qc.invalidateQueries({ queryKey: ["ea-accounts"] });
    },
    onError: (err) => toast.error(errMsg(err, "操作失败")),
  });

  const verify = useMutation({
    mutationFn: (id: number) => eaAccountsApi.verify(id),
    onSuccess: (res) => {
      if (res.success) toast.success(`连通性正常（persona ${res.persona_id}）`);
      else toast.error(`连通性失败：${res.message ?? "未知错误"}`);
      qc.invalidateQueries({ queryKey: ["ea-accounts"] });
    },
    onError: (err) => toast.error(errMsg(err, "验证失败")),
  });

  if (session.isLoading) {
    return <AdminPageSkeleton />;
  }
  if (!session.data) {
    return (
      <main className="mx-auto max-w-md space-y-4 px-4 py-12 text-center">
        <h1 className="text-xl font-semibold">EA 服管账号管理</h1>
        <p className="text-muted-foreground text-sm">需要先登录</p>
        <Button
          onClick={() => router.push(`/login?next=${encodeURIComponent("/admin/ea-accounts")}`)}
        >
          去登录
        </Button>
      </main>
    );
  }
  if (!isAdmin) {
    return (
      <main className="mx-auto max-w-md space-y-4 px-4 py-12 text-center">
        <h1 className="text-xl font-semibold">无权访问</h1>
        <p className="text-muted-foreground text-sm">EA 账号管理仅平台管理员可见。</p>
      </main>
    );
  }

  const columns: Column<EAAccountItem>[] = [
    {
      key: "account",
      header: "账号",
      cell: (a) => (
        <div className="space-y-0.5">
          <span className="font-medium">{a.display_name ?? `Persona ${a.persona_id}`}</span>
          <div className="text-muted-foreground text-xs">{a.persona_id}</div>
        </div>
      ),
      isCardTitle: true,
    },
    {
      key: "status",
      header: "状态",
      cell: (a) => (
        <div className="flex flex-wrap gap-1.5">
          <StatusBadge tone={a.enabled ? "default" : "muted"}>
            {a.enabled ? "启用" : "停用"}
          </StatusBadge>
          <StatusBadge tone={a.has_session ? "outline" : "muted"}>
            {a.has_session ? "有 session" : "无 session"}
          </StatusBadge>
          {a.failure_count > 0 ? (
            <StatusBadge tone="destructive">失败 {a.failure_count}</StatusBadge>
          ) : null}
        </div>
      ),
    },
    {
      key: "last_used",
      header: "使用情况",
      cell: (a) => (
        <div className="space-y-0.5">
          <div>
            {a.last_used_at ? (
              new Date(a.last_used_at).toLocaleString("zh-CN")
            ) : (
              <span className="text-muted-foreground">从未使用</span>
            )}
          </div>
          <div className="text-muted-foreground text-xs tabular-nums">
            累计取用 {a.use_count} 次
          </div>
        </div>
      ),
    },
    {
      key: "actions",
      header: "操作",
      cell: (a) => (
        <div className="flex flex-wrap gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="compact-action"
            disabled={verify.isPending}
            onClick={() => verify.mutate(a.id)}
          >
            <PlugZap className="size-3.5" />
            验证
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="compact-action"
            disabled={toggle.isPending}
            onClick={() => toggle.mutate({ id: a.id, enabled: !a.enabled })}
          >
            <Power className="size-3.5" />
            {a.enabled ? "停用" : "启用"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="compact-action"
            onClick={() => setRenaming(a)}
          >
            <Pencil className="size-3.5" />
            改备注
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="compact-action"
            onClick={() => setEditing(a)}
          >
            <KeyRound className="size-3.5" />
            改凭据
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="compact-action text-destructive"
            onClick={() => setPendingDelete(a)}
          >
            <Trash2 className="size-3.5" />
            删除
          </Button>
        </div>
      ),
    },
  ];

  return (
    <>
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6">
        <PageHeader
          kicker="Admin"
          title="EA 服管账号管理"
          description="维护平台代查询用的 EA 账号池。凭据写入后即加密存储，列表只展示健康状态，任何明文都不会回显。同一个 persona_id 只能存在一条记录。"
          action={
            <Button onClick={() => setLoginFlowOpen(true)} size="sm">
              邮箱密码登录添加
            </Button>
          }
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-base">新增账号</CardTitle>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form
                onSubmit={form.handleSubmit((v) => create.mutate(v))}
                className="grid grid-cols-1 gap-4 sm:grid-cols-2"
              >
                <FormField
                  control={form.control}
                  name="persona_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>persona_id</FormLabel>
                      <FormControl>
                        <Input inputMode="numeric" {...field} />
                      </FormControl>
                      <FormDescription>EA 账号的 persona_id</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="display_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>备注名（可选）</FormLabel>
                      <FormControl>
                        <Input placeholder="便于辨识" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="remid"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>remid</FormLabel>
                      <FormControl>
                        <Input autoComplete="off" {...field} />
                      </FormControl>
                      <FormDescription>EA 官网登录后 cookie 里的 remid</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="sid"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>sid</FormLabel>
                      <FormControl>
                        <Input autoComplete="off" {...field} />
                      </FormControl>
                      <FormDescription>EA 官网登录后 cookie 里的 sid</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="session"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>session（可选）</FormLabel>
                      <FormControl>
                        <Input autoComplete="off" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="access_token"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>access_token（可选）</FormLabel>
                      <FormControl>
                        <Input autoComplete="off" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="sm:col-span-2">
                  <Button
                    type="submit"
                    disabled={create.isPending}
                    size="lg"
                    className="w-full sm:w-auto"
                  >
                    {create.isPending ? "提交中…" : "新增账号"}
                  </Button>
                </div>
              </form>
            </Form>
          </CardContent>
        </Card>

        <section className="space-y-3">
          <SectionHeading className="">账号池（{list.data?.length ?? 0}）</SectionHeading>
          {list.isLoading ? (
            <div className="text-muted-foreground p-8 text-center">加载中…</div>
          ) : (
            <ResponsiveTable
              data={list.data ?? []}
              columns={columns}
              rowKey={(a) => a.id}
              emptyState="账号池为空，先新增一个 EA 账号"
            />
          )}
        </section>

        <RenameSheet account={renaming} onClose={() => setRenaming(null)} />

        <CredentialsSheet account={editing} onClose={() => setEditing(null)} />

        <ConfirmSheet
          open={pendingDelete !== null}
          onOpenChange={(open) => !open && setPendingDelete(null)}
          title={
            pendingDelete
              ? `删除账号 ${pendingDelete.display_name ?? `Persona ${pendingDelete.persona_id}`}？`
              : "确认删除"
          }
          description="删除后该账号立即从代查询账号池移除，凭据一并销毁，无法恢复。"
          confirmText="删除"
          cancelText="取消"
          variant="destructive"
          loading={remove.isPending}
          onConfirm={() => {
            if (pendingDelete) remove.mutate(pendingDelete.id);
          }}
        />

        <EaLoginFlow
          actor="admin"
          open={loginFlowOpen}
          onOpenChange={setLoginFlowOpen}
          onSucceeded={() => qc.invalidateQueries({ queryKey: ["ea-accounts"] })}
        />
      </main>
    </>
  );
}
