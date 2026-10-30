"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { MailSentNotice } from "@/components/auth/AuthCard";
import { useCaptcha } from "@/components/auth/Turnstile";
import { confirmMatches, confirmMismatch, newPasswordFields } from "@/components/auth/password";
import {
  changePassword,
  createInviteCode,
  type InviteCodeItem,
  type InviteStatus,
  listInviteCodes,
  logoutAll,
  requestSetEmail,
  revokeInviteCode,
  type SessionUser,
} from "@/lib/auth";
import { ApiException } from "@/lib/api-client";
import { cn } from "@/lib/utils";

function errorText(err: unknown, fallback: string) {
  return err instanceof ApiException ? err.message : fallback;
}

/** 旧账号补登录邮箱：remid 登录停用后，不设邮箱的话会话过期就只能重新认领 */
export function SetEmailCard() {
  const captcha = useCaptcha();
  const [sent, setSent] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const schema = z.object({ email: z.string().trim().email("请输入正确的邮箱") });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "" },
  });

  const onSubmit = async ({ email }: z.infer<typeof schema>) => {
    setSubmitting(true);
    try {
      setSent((await requestSetEmail(email, captcha.token)).message);
    } catch (err) {
      toast.error(errorText(err, "提交失败，请稍后重试"));
    } finally {
      setSubmitting(false);
      captcha.reset();
    }
  };

  return (
    <section className="rounded-sm border border-amber-500/40 bg-amber-500/[0.07] p-4 sm:p-5">
      <h2 className="font-semibold text-amber-100">设置登录邮箱</h2>
      <p className="text-muted-foreground mt-1 text-sm leading-relaxed">
        remid 登录已经停用。这个账号是用 remid
        登录时建的，还没有登录邮箱。填一个邮箱，打开验证信设置密码，以后就用邮箱和密码登录；服务器权限和操作记录都不变。
      </p>
      {sent ? (
        <div className="mt-4">
          <MailSentNotice message={sent}>
            <Button variant="outline" size="sm" onClick={() => setSent(null)}>
              换个邮箱
            </Button>
          </MailSentNotice>
        </div>
      ) : (
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="mt-4 space-y-3">
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Input
                      type="email"
                      autoComplete="email"
                      placeholder="邮箱"
                      spellCheck={false}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {captcha.widget}
            <Button
              type="submit"
              disabled={submitting || !captcha.ready}
              className="w-full sm:w-auto"
            >
              {submitting ? "提交中…" : "发送验证信"}
            </Button>
          </form>
        </Form>
      )}
    </section>
  );
}

const passwordSchema = z
  .object({ current: z.string().min(1, "请输入当前密码"), ...newPasswordFields })
  .refine(confirmMatches, confirmMismatch);
type PasswordValues = z.infer<typeof passwordSchema>;

function ChangePasswordDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const form = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current: "", password: "", confirm: "" },
  });
  const mutation = useMutation({
    mutationFn: (v: PasswordValues) => changePassword(v.current, v.password),
    onSuccess: () => {
      toast.success("密码已修改，其他设备上的登录已退出");
      form.reset();
      onOpenChange(false);
    },
    onError: (err) => toast.error(errorText(err, "修改失败，请稍后重试")),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="dark text-foreground w-[calc(100%-2rem)] rounded-lg sm:max-w-md">
        <DialogHeader>
          <DialogTitle>修改密码</DialogTitle>
          <DialogDescription>
            改完后其他设备上的登录会全部退出，这台设备保持登录。
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit((v) => mutation.mutate(v))} className="space-y-4">
            <FormField
              control={form.control}
              name="current"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>当前密码</FormLabel>
                  <FormControl>
                    <Input type="password" autoComplete="current-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>新密码</FormLabel>
                  <FormControl>
                    <Input
                      type="password"
                      autoComplete="new-password"
                      placeholder="至少 8 位"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="confirm"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>再输一次</FormLabel>
                  <FormControl>
                    <Input type="password" autoComplete="new-password" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" className="w-full" disabled={mutation.isPending}>
              {mutation.isPending ? "保存中…" : "保存新密码"}
            </Button>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

/** 账号与安全：登录邮箱、改密码、退出所有设备 */
export function SecuritySection({ user }: { user: SessionUser }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [pwOpen, setPwOpen] = useState(false);
  const logoutAllMutation = useMutation({
    mutationFn: logoutAll,
    onSuccess: () => {
      qc.setQueryData(["session"], null);
      toast.success("已退出所有设备");
      router.replace("/login");
    },
    onError: (err) => toast.error(errorText(err, "操作失败，请稍后重试")),
  });
  // 旧账号没有密码；本地管理员有密码但可能没邮箱
  const hasPassword = user.status !== "legacy";

  return (
    <section>
      <SectionHeading>账号与安全</SectionHeading>
      <div className="border-border divide-border divide-y rounded-sm border">
        <div className="flex items-center justify-between gap-3 p-3">
          <div className="min-w-0">
            <div className="text-muted-foreground text-xs">登录邮箱</div>
            <div className="truncate text-sm">{user.email ?? "未设置"}</div>
          </div>
        </div>
        {hasPassword ? (
          <div className="flex items-center justify-between gap-3 p-3">
            <div className="min-w-0">
              <div className="text-sm">登录密码</div>
              <div className="text-muted-foreground text-xs">
                忘了当前密码可以退出后在登录页找回
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => setPwOpen(true)}>
              修改
            </Button>
          </div>
        ) : null}
        <div className="flex items-center justify-between gap-3 p-3">
          <div className="min-w-0">
            <div className="text-sm">退出所有设备</div>
            <div className="text-muted-foreground text-xs">
              怀疑账号被别人登录时用，包括这台设备
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={logoutAllMutation.isPending}
            onClick={() => {
              if (window.confirm("确定退出所有设备上的登录吗？")) logoutAllMutation.mutate();
            }}
          >
            全部退出
          </Button>
        </div>
      </div>
      <ChangePasswordDialog open={pwOpen} onOpenChange={setPwOpen} />
    </section>
  );
}

const INVITE_STATUS: Record<InviteStatus, { label: string; className: string }> = {
  unused: { label: "可用", className: "bg-amber-500 text-black" },
  used: { label: "已使用", className: "bg-secondary text-secondary-foreground" },
  expired: { label: "已过期", className: "bg-muted text-muted-foreground" },
  revoked: { label: "已作废", className: "bg-muted text-muted-foreground" },
};

function inviteLink(code: string) {
  return `${window.location.origin}/register?invite=${encodeURIComponent(code)}`;
}

async function copyText(text: string, done: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(done);
  } catch {
    toast.error("复制失败，请手动选中复制");
  }
}

function InviteRow({
  item,
  onRevoke,
  revoking,
}: {
  item: InviteCodeItem;
  onRevoke: (id: number) => void;
  revoking: boolean;
}) {
  const status = INVITE_STATUS[item.status];
  const usable = item.status === "unused";
  return (
    <li className="border-border flex flex-wrap items-center justify-between gap-x-3 gap-y-2 rounded-sm border p-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "font-mono text-base tracking-wider",
              !usable && "text-muted-foreground line-through",
            )}
          >
            {item.code}
          </span>
          <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-semibold", status.className)}>
            {status.label}
          </span>
        </div>
        <div className="text-muted-foreground mt-0.5 text-xs">
          {item.used_at
            ? `${new Date(item.used_at).toLocaleString("zh-CN")} 使用`
            : `${new Date(item.expires_at).toLocaleString("zh-CN")} 过期`}
        </div>
      </div>
      {usable ? (
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => copyText(inviteLink(item.code), "注册链接已复制，邀请码已填在里面")}
          >
            <Copy className="size-3.5" />
            复制链接
          </Button>
          <Button variant="ghost" size="sm" disabled={revoking} onClick={() => onRevoke(item.id)}>
            作废
          </Button>
        </div>
      ) : null}
    </li>
  );
}

/** 邀请码：注册要邀请码时才显示 */
export function InviteSection({ canCreate }: { canCreate: boolean }) {
  const qc = useQueryClient();
  const invites = useQuery({ queryKey: ["invite-codes"], queryFn: listInviteCodes });
  const update = (data: Awaited<ReturnType<typeof listInviteCodes>>) =>
    qc.setQueryData(["invite-codes"], data);
  const create = useMutation({
    mutationFn: createInviteCode,
    onSuccess: (data) => {
      update(data);
      toast.success("邀请码已生成");
    },
    onError: (err) => toast.error(errorText(err, "生成失败，请稍后重试")),
  });
  const revoke = useMutation({
    mutationFn: revokeInviteCode,
    onSuccess: update,
    onError: (err) => toast.error(errorText(err, "操作失败，请稍后重试")),
  });

  if (!invites.data?.invite_required) return null;
  const { items, quota_left } = invites.data;
  const exhausted = quota_left !== null && quota_left <= 0;

  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <SectionHeading className="mb-0">邀请码</SectionHeading>
        {canCreate ? (
          <Button
            size="sm"
            disabled={create.isPending || exhausted}
            onClick={() => create.mutate()}
          >
            生成邀请码
          </Button>
        ) : null}
      </div>
      <p className="text-muted-foreground mb-3 text-sm leading-relaxed">
        新用户注册要填邀请码。每个邀请码只能用一次，7 天内有效
        {quota_left !== null ? `，你还能生成 ${quota_left} 个` : ""}
        {canCreate ? "。" : "。绑定 EA 账号后才能生成。"}
      </p>
      {items.length === 0 ? (
        <p className="text-muted-foreground text-sm">还没有生成过邀请码。</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <InviteRow
              key={item.id}
              item={item}
              revoking={revoke.isPending}
              onRevoke={(id) => revoke.mutate(id)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
