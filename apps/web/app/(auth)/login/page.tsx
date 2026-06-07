"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { localLogin, login } from "@/lib/auth";
import { ApiException } from "@/lib/api-client";

const loginSchema = z.object({
  remid: z.string().min(10, "remid 看上去不是合法 cookie 值"),
  // sid 留空时由 EA 在登录响应里自动 Set-Cookie 出新值，所以前端也设为可选
  sid: z
    .string()
    .optional()
    .refine((v) => !v || v.length >= 10, "sid 如填写需是合法 cookie 值"),
});

const localLoginSchema = z.object({
  username: z.string().min(1, "请输入 username"),
  password: z.string().min(1, "请输入密码"),
});

type LoginValues = z.infer<typeof loginSchema>;
type LocalLoginValues = z.infer<typeof localLoginSchema>;

export default function LoginPage() {
  return (
    // 登录页统一深色战地外壳：与首页、应用内深色基调连贯，消除此前浅色卡片导致的「哗白」突兀
    <div className="dark text-foreground relative flex min-h-screen flex-col bg-black">
      {/* 战地背景：静态大图 + 渐变遮罩压暗，保证表单文字与输入框可读。
          用 absolute inset-0 置于内容流首位，靠 DOM 顺序压在底层，避免 -z-10 被父背景遮挡 */}
      <div className="absolute inset-0" aria-hidden>
        {/* EA 素材域不在 next/image remotePatterns 内，且为静态首屏图，用原生 img */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/bf1/backgrounds/general/general-3.jpg"
          alt=""
          className="h-full w-full object-cover object-center"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black via-black/85 to-black/55" />
        <div className="absolute inset-0 bg-gradient-to-r from-black/70 to-transparent" />
      </div>

      <header className="flex items-center justify-between px-6 py-6 sm:px-10">
        <Link
          href="/"
          className="font-display text-base font-semibold tracking-[0.2em] text-white uppercase"
        >
          BF-Manager
        </Link>
        <Link
          href="/"
          className="text-sm tracking-wide text-white/60 uppercase transition-colors hover:text-white"
        >
          返回首页
        </Link>
      </header>

      <Suspense
        fallback={
          <main className="text-muted-foreground flex flex-1 items-center justify-center p-12 text-sm">
            加载中…
          </main>
        }
      >
        <LoginForm />
      </Suspense>
    </div>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") ?? "/stats";
  const [submitting, setSubmitting] = useState(false);
  const [showLocal, setShowLocal] = useState(false);

  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { remid: "", sid: "" },
  });

  const localForm = useForm<LocalLoginValues>({
    resolver: zodResolver(localLoginSchema),
    defaultValues: { username: "", password: "" },
  });

  const onSubmit = async (values: LoginValues) => {
    setSubmitting(true);
    try {
      const user = await login(values);
      const greet = user.primary_binding?.display_name ?? user.username;
      toast.success(`欢迎回来，${greet}`);
      router.push(next);
      router.refresh();
    } catch (err) {
      const msg =
        err instanceof ApiException ? err.message : "登录失败，请检查 remid / sid 是否正确";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const onLocalSubmit = async (values: LocalLoginValues) => {
    setSubmitting(true);
    try {
      const user = await localLogin(values);
      toast.success(`欢迎回来，${user.username}`);
      router.push(next);
      router.refresh();
    } catch (err) {
      const msg = err instanceof ApiException ? err.message : "本地登录失败";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="flex flex-1 items-center justify-center px-4 py-8 sm:py-12">
      <Card className="bg-card/80 w-full max-w-md border-white/10 shadow-2xl backdrop-blur-md">
        <CardHeader>
          <div className="font-display mb-1 flex items-center gap-2 text-xs font-medium tracking-[0.2em] text-amber-500 uppercase">
            <span className="h-[2px] w-6 bg-amber-500" />
            Sign In
          </div>
          <CardTitle>登录 BF-Manager</CardTitle>
          <CardDescription>
            使用 EA 账号的 Cookie 登录。一般只需要填 <strong>remid</strong>，sid 留空即可—— EA
            会在登录过程里自动签发新的 sid。两个 Cookie 都能在浏览器中访问{" "}
            <a
              href="https://accounts.ea.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              accounts.ea.com
            </a>{" "}
            后从开发者工具的 Cookies 面板获取。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
              <FormField
                control={form.control}
                name="remid"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>remid</FormLabel>
                    <FormControl>
                      <Input
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="EA 长效 Cookie，通常 2 年有效"
                        {...field}
                      />
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
                    <FormLabel>sid（可选）</FormLabel>
                    <FormControl>
                      <Input
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="留空即可，EA 会自动签发新的 sid"
                        {...field}
                        value={field.value ?? ""}
                      />
                    </FormControl>
                    <FormDescription>
                      凭据通过 AES-256-GCM 加密存储，永远不会出现在任何 API 响应中。
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" size="lg" className="w-full" disabled={submitting}>
                {submitting ? "登录中…" : "登录"}
              </Button>
            </form>
          </Form>

          <div className="mt-6 border-t pt-4">
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
                        <FormDescription>
                          本地账号由部署者通过 CLI 创建：
                          <code className="bg-muted ml-1 rounded px-1 py-0.5 text-xs">
                            python -m app.cli create-admin
                          </code>
                        </FormDescription>
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
        </CardContent>
      </Card>
    </main>
  );
}
