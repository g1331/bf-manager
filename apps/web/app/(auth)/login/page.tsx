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
import { emailLogin, landingPath, localLogin, type SessionUser } from "@/lib/auth";
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
  const [submitting, setSubmitting] = useState(false);
  const [showLocal, setShowLocal] = useState(false);

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
      toast.error(err instanceof ApiException ? err.message : "登录失败，请稍后重试");
    } finally {
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
