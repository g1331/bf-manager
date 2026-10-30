"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "sonner";
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
import { Button } from "@/components/ui/button";
import { AuthCard } from "@/components/auth/AuthCard";
import {
  cancelAccountDeletion,
  emailLogin,
  landingPath,
  localLogin,
  type SessionUser,
} from "@/lib/auth";
import { ApiException } from "@/lib/api-client";
import { safeNextPath } from "@/lib/utils";

const loginSchema = z.object({
  email: z.string().trim().email("请输入正确的邮箱"),
  password: z.string().min(1, "请输入密码"),
});

const localLoginSchema = z.object({
  username: z.string().min(1, "请输入 username"),
  password: z.string().min(1, "请输入密码"),
});

type LoginValues = z.infer<typeof loginSchema>;
type LocalLoginValues = z.infer<typeof localLoginSchema>;

function deletionTime(iso: string | null | undefined): string {
  const at = iso ? new Date(iso) : null;
  return at && !Number.isNaN(at.getTime())
    ? at.toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" })
    : "冷静期结束时";
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="text-muted-foreground p-12 text-sm">加载中…</div>}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const qc = useQueryClient();
  const searchParams = useSearchParams();
  const next = safeNextPath(searchParams.get("next"), "/stats");
  // 绑定 EA 时认领了旧账号：当前会话作废，回到这里用同样的邮箱密码重新登录
  const claimed = searchParams.get("claimed") === "1";
  // 刚申请注销：从「我的主页」跳过来
  const requestedDeletion = searchParams.get("deletion");
  const [submitting, setSubmitting] = useState(false);
  const [showLocal, setShowLocal] = useState(false);
  // 冷静期内用正确的密码登录：提示什么时候删，可以撤销
  const [pending, setPending] = useState<{ values: LoginValues; deleteAt: string | null } | null>(
    null,
  );

  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const localForm = useForm<LocalLoginValues>({
    resolver: zodResolver(localLoginSchema),
    defaultValues: { username: "", password: "" },
  });

  const enter = (user: SessionUser) => {
    qc.setQueryData(["session"], user);
    const greet = user.primary_binding?.display_name ?? user.username;
    toast.success(`欢迎回来，${greet}`);
    router.push(landingPath(user, next));
    router.refresh();
  };

  const onSubmit = async (values: LoginValues) => {
    setSubmitting(true);
    try {
      enter(await emailLogin(values));
    } catch (err) {
      if (err instanceof ApiException && err.code === "ACCOUNT_DELETION_PENDING") {
        const deleteAt = err.details?.delete_at;
        setPending({ values, deleteAt: typeof deleteAt === "string" ? deleteAt : null });
      } else {
        toast.error(err instanceof ApiException ? err.message : "登录失败，请稍后重试");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onCancelDeletion = async () => {
    if (!pending) return;
    setSubmitting(true);
    try {
      const user = await cancelAccountDeletion(pending.values);
      toast.success("已撤销注销");
      enter(user);
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : "撤销失败，请稍后重试");
      setSubmitting(false);
    }
  };

  const onLocalSubmit = async (values: LocalLoginValues) => {
    setSubmitting(true);
    try {
      enter(await localLogin(values));
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : "本地登录失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthCard
      kicker="Sign In"
      title="登录 BF-Manager"
      description="用注册时的邮箱和密码登录。"
      footer={
        <>
          <Link href="/register" className="text-primary underline-offset-4 hover:underline">
            注册账号
          </Link>
          <Link href="/forgot-password" className="underline-offset-4 hover:underline">
            忘记密码
          </Link>
        </>
      }
    >
      {pending ? (
        <div
          role="alert"
          className="border-destructive/40 bg-destructive/10 mb-5 space-y-3 rounded-sm border p-3 text-sm leading-relaxed"
        >
          <p>
            这个账号已申请注销，将在 <strong>{deletionTime(pending.deleteAt)}</strong>{" "}
            删除。现在账号处于冻结状态，撤销后恢复登录；之前吊销的 API Key 不会恢复。
          </p>
          <Button className="w-full" disabled={submitting} onClick={onCancelDeletion}>
            {submitting ? "处理中…" : "撤销注销并登录"}
          </Button>
        </div>
      ) : requestedDeletion !== null ? (
        <div className="mb-5 rounded-sm border border-white/15 bg-white/[0.04] p-3 text-sm leading-relaxed">
          已申请注销，账号将在 <strong>{deletionTime(requestedDeletion)}</strong>{" "}
          删除，确认邮件已发到你的邮箱。改主意的话，在这之前用邮箱和密码登录即可撤销。
        </div>
      ) : null}

      {claimed ? (
        <div className="mb-5 rounded-sm border border-amber-500/30 bg-amber-500/10 p-3 text-sm leading-relaxed text-amber-100">
          旧账号已经认领，原来的服务器权限和操作记录都在。请用刚才设置的邮箱和密码重新登录。
        </div>
      ) : null}

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>邮箱</FormLabel>
                <FormControl>
                  <Input type="email" autoComplete="email" spellCheck={false} {...field} />
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
                <FormLabel>密码</FormLabel>
                <FormControl>
                  <Input type="password" autoComplete="current-password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" size="lg" className="w-full" disabled={submitting}>
            {submitting ? "登录中…" : "登录"}
          </Button>
        </form>
      </Form>

      <div className="text-muted-foreground mt-5 rounded-sm border border-white/10 bg-white/[0.03] p-3 text-sm leading-relaxed">
        以前用 remid 登录过？remid 登录已经停用。用 EA 账号的邮箱
        <Link href="/register" className="text-primary mx-1 underline-offset-4 hover:underline">
          注册
        </Link>
        就能认领旧账号，不需要邀请码，服务器权限和操作记录都会保留。
      </div>

      <div className="mt-6">
        <button
          type="button"
          onClick={() => setShowLocal((v) => !v)}
          className="text-muted-foreground hover:text-foreground text-sm underline-offset-4 hover:underline"
        >
          {showLocal ? "收起本地账号登录" : "使用本地账号登录（仅平台管理员）"}
        </button>
        {showLocal ? (
          <Form {...localForm}>
            <form onSubmit={localForm.handleSubmit(onLocalSubmit)} className="mt-4 space-y-4">
              <FormField
                control={localForm.control}
                name="username"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>username</FormLabel>
                    <FormControl>
                      <Input autoComplete="username" spellCheck={false} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={localForm.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>密码</FormLabel>
                    <FormControl>
                      <Input type="password" autoComplete="current-password" {...field} />
                    </FormControl>
                    <FormDescription>本地账号仅供平台管理员使用。</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button
                type="submit"
                variant="secondary"
                size="lg"
                className="w-full"
                disabled={submitting}
              >
                {submitting ? "登录中…" : "使用本地账号登录"}
              </Button>
            </form>
          </Form>
        ) : null}
      </div>
    </AuthCard>
  );
}
