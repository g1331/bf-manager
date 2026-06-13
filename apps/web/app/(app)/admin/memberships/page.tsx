"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
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
import { PageHeader } from "@/components/layout/PageHeader";
import { AdminPageSkeleton } from "@/components/layout/PageSkeleton";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";

import { useSession } from "@/hooks/useSession";
import { membershipsApi, type MembershipItem, type MembershipRole } from "@/lib/api/memberships";
import { ApiException } from "@/lib/api-client";

const ROLE_LABEL: Record<MembershipRole, string> = {
  viewer: "查看者",
  moderator: "协管（踢人）",
  admin: "管理员（封禁/换图）",
  owner: "服主",
};

const upsertSchema = z.object({
  target_persona_id: z.coerce.number().int().positive("persona_id 必须是正整数"),
  game: z.string().min(1, "需要游戏代号").max(16),
  server_id: z.coerce.number().int().positive("server_id 必须是正整数"),
  role: z.enum(["viewer", "moderator", "admin", "owner"]),
});

type UpsertValues = z.infer<typeof upsertSchema>;

export default function MembershipsAdminPage() {
  const router = useRouter();
  const session = useSession();
  const qc = useQueryClient();
  const [pendingDelete, setPendingDelete] = useState<MembershipItem | null>(null);

  const list = useQuery({
    queryKey: ["memberships"],
    queryFn: () => membershipsApi.list({ pageSize: 200 }),
    enabled: session.data?.role === "admin",
  });

  const form = useForm<UpsertValues>({
    // zod 4 起 z.coerce 的 input 类型为 unknown，与 useForm 的 output 泛型不一致；
    // resolver 运行时仍照常 coerce，这里按 output 形态断言以对齐 RHF 类型
    resolver: zodResolver(upsertSchema) as Resolver<UpsertValues>,
    defaultValues: { target_persona_id: 0, game: "bf1", server_id: 0, role: "moderator" },
  });

  const upsert = useMutation({
    mutationFn: (values: UpsertValues) => membershipsApi.upsert(values),
    onSuccess: () => {
      toast.success("已写入权限");
      qc.invalidateQueries({ queryKey: ["memberships"] });
      form.reset({ target_persona_id: 0, game: "bf1", server_id: 0, role: "moderator" });
    },
    onError: (err) => {
      const msg = err instanceof ApiException ? err.message : "授权失败";
      toast.error(msg);
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => membershipsApi.delete(id),
    onSuccess: () => {
      toast.success("已删除权限");
      qc.invalidateQueries({ queryKey: ["memberships"] });
      setPendingDelete(null);
    },
    onError: (err) => {
      const msg = err instanceof ApiException ? err.message : "删除失败";
      toast.error(msg);
    },
  });

  if (session.isLoading) {
    return <AdminPageSkeleton />;
  }
  if (!session.data) {
    return (
      <main className="mx-auto max-w-md space-y-4 px-4 py-12 text-center">
        <h1 className="text-xl font-semibold">服管权限授予</h1>
        <p className="text-muted-foreground text-sm">需要先登录</p>
        <Button
          onClick={() => router.push(`/login?next=${encodeURIComponent("/admin/memberships")}`)}
        >
          去登录
        </Button>
      </main>
    );
  }
  if (session.data.role !== "admin") {
    return (
      <main className="mx-auto max-w-md space-y-4 px-4 py-12 text-center">
        <h1 className="text-xl font-semibold">无权访问</h1>
        <p className="text-muted-foreground text-sm">
          服管权限授予仅平台管理员可见。如需协管权限，请联系平台 admin。
        </p>
      </main>
    );
  }

  const columns: Column<MembershipItem>[] = [
    {
      key: "user",
      header: "授权对象",
      cell: (m) => (
        <span className="font-medium">
          {m.user_display_name ??
            (m.user_persona_id !== null ? `Persona ${m.user_persona_id}` : m.user_username)}
        </span>
      ),
      isCardTitle: true,
    },
    {
      key: "server",
      header: "服务器",
      cell: (m) => (
        <span className="text-sm">
          [{m.game.toUpperCase()}] {m.server_name ?? `#${m.server_id}`}
        </span>
      ),
    },
    {
      key: "role",
      header: "角色",
      cell: (m) => ROLE_LABEL[m.role] ?? m.role,
    },
    {
      key: "granted_at",
      header: "授予时间",
      cell: (m) => new Date(m.granted_at).toLocaleString("zh-CN"),
    },
    {
      key: "actions",
      header: "操作",
      cell: (m) => (
        <Button
          variant="ghost"
          size="sm"
          className="compact-action text-destructive"
          onClick={() => setPendingDelete(m)}
        >
          <Trash2 className="size-3.5" />
          删除
        </Button>
      ),
    },
  ];

  return (
    <>
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-6">
        <PageHeader
          kicker="Admin"
          title="服管权限授予"
          description="为某个玩家在某个服务器赋予 viewer / moderator / admin / owner 权限。同 user × server 组合再次提交会覆盖现有角色。"
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-base">新增 / 更新权限</CardTitle>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form
                onSubmit={form.handleSubmit((v) => upsert.mutate(v))}
                className="grid grid-cols-1 gap-4 sm:grid-cols-2"
              >
                <FormField
                  control={form.control}
                  name="target_persona_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>目标 persona_id</FormLabel>
                      <FormControl>
                        <Input inputMode="numeric" {...field} />
                      </FormControl>
                      <FormDescription>该玩家需先登录过本平台一次</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="game"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>游戏</FormLabel>
                      <FormControl>
                        <Input placeholder="bf1" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="server_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>EA serverId</FormLabel>
                      <FormControl>
                        <Input inputMode="numeric" {...field} />
                      </FormControl>
                      <FormDescription>服务器详情 URL 末尾的数字</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="role"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>角色</FormLabel>
                      <FormControl>
                        <select
                          {...field}
                          className="border-input bg-background h-11 w-full rounded-md border px-3 text-sm"
                        >
                          <option value="viewer">viewer（仅查看）</option>
                          <option value="moderator">moderator（踢人）</option>
                          <option value="admin">admin（封禁 / 换图）</option>
                          <option value="owner">owner（服主）</option>
                        </select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="sm:col-span-2">
                  <Button
                    type="submit"
                    disabled={upsert.isPending}
                    size="lg"
                    className="w-full sm:w-auto"
                  >
                    {upsert.isPending ? "提交中…" : "授予权限"}
                  </Button>
                </div>
              </form>
            </Form>
          </CardContent>
        </Card>

        <section className="space-y-3">
          <SectionHeading className="">现有权限（{list.data?.total ?? 0}）</SectionHeading>
          {list.isLoading ? (
            <div className="text-muted-foreground p-8 text-center">加载中…</div>
          ) : (
            <ResponsiveTable
              data={list.data?.items ?? []}
              columns={columns}
              rowKey={(m) => m.id}
              emptyState="尚未授予任何服管权限"
            />
          )}
        </section>

        <ConfirmSheet
          open={pendingDelete !== null}
          onOpenChange={(open) => !open && setPendingDelete(null)}
          title={
            pendingDelete
              ? `删除 ${pendingDelete.user_display_name ?? pendingDelete.user_persona_id ?? pendingDelete.user_username} 在 ${pendingDelete.server_name ?? `#${pendingDelete.server_id}`} 的权限？`
              : "确认删除"
          }
          description="删除后该用户立即失去对此服务器的服管能力"
          confirmText="删除"
          cancelText="取消"
          variant="destructive"
          loading={remove.isPending}
          onConfirm={() => {
            if (pendingDelete) remove.mutate(pendingDelete.id);
          }}
        />
      </main>
    </>
  );
}
