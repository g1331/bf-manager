"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
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
import { AuthCard, MailSentNotice } from "@/components/auth/AuthCard";
import { useAuthConfig, useCaptcha } from "@/components/auth/Turnstile";
import { register, type RegisterMode } from "@/lib/auth";
import { clearPendingInvite, type PendingInvite, readPendingInvite } from "@/lib/api/groups";
import { ApiException } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const schema = z.object({
  email: z.string().trim().email("请输入正确的邮箱"),
  invite_code: z.string().trim().max(32),
});

type Values = z.infer<typeof schema>;

const MODES: { value: RegisterMode; label: string }[] = [
  { value: "ea", label: "EA 账号邮箱" },
  { value: "plain", label: "其他邮箱" },
];

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="text-muted-foreground p-12 text-sm">加载中…</div>}>
      <RegisterForm />
    </Suspense>
  );
}

function RegisterForm() {
  const searchParams = useSearchParams();
  const config = useAuthConfig();
  const captcha = useCaptcha();
  const [mode, setMode] = useState<RegisterMode>("ea");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState<{
    message: string;
    mode: RegisterMode;
    claimOnly: boolean;
  } | null>(null);
  // 从群邀请链接点过来的：用链接代替邀请码
  const [groupInvite, setGroupInvite] = useState<PendingInvite | null>(null);
  const registrationMode = config.data?.registration_mode ?? "invite";
  // 暂停注册：只剩用 EA 邮箱认领旧账号这一条路
  const closed = registrationMode === "closed";
  const inviteRequired = registrationMode === "invite" && !groupInvite;

  useEffect(() => {
    // sessionStorage 只能在浏览器里读
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setGroupInvite(readPendingInvite());
  }, []);

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", invite_code: searchParams.get("invite") ?? "" },
  });

  const onSubmit = async (values: Values) => {
    setSubmitting(true);
    try {
      const res = await register(
        closed
          ? { email: values.email, mode: "ea" }
          : groupInvite
            ? { email: values.email, mode, group_invite_token: groupInvite.token }
            : {
                email: values.email,
                mode,
                invite_code: (inviteRequired && values.invite_code) || undefined,
              },
        captcha.token,
      );
      setSent({ message: res.message, mode: closed ? "ea" : mode, claimOnly: closed });
      // 群邀请已经跟着验证信走了，完成注册时自动进群；页面状态留着，换邮箱重新提交还能用
      if (groupInvite && !closed) clearPendingInvite();
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : "提交失败，请稍后重试");
    } finally {
      setSubmitting(false);
      captcha.reset();
    }
  };

  const footer = (
    <>
      <span>
        已有账号？
        <Link href="/login" className="text-primary underline-offset-4 hover:underline">
          登录
        </Link>
      </span>
      <Link href="/forgot-password" className="underline-offset-4 hover:underline">
        忘记密码
      </Link>
    </>
  );

  // 注册方式没拿到之前不画表单，免得暂停注册时先闪一下完整的注册表单
  if (!config.data) {
    return (
      <AuthCard kicker="Sign Up" title="注册 BF-Manager" footer={footer}>
        {config.isError ? (
          <div className="space-y-4 py-4 text-center text-sm">
            <p className="text-muted-foreground">读取注册设置失败，请稍后重试。</p>
            <Button
              variant="outline"
              className="w-full"
              disabled={config.isFetching}
              onClick={() => void config.refetch()}
            >
              {config.isFetching ? "重试中…" : "重试"}
            </Button>
          </div>
        ) : (
          <div className="text-muted-foreground py-8 text-center text-sm">加载中…</div>
        )}
      </AuthCard>
    );
  }

  if (sent?.claimOnly) {
    return (
      <AuthCard kicker="Claim Account" title="去邮箱查收认领信" footer={footer}>
        <MailSentNotice message={sent.message}>
          <ul className="text-muted-foreground list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
            <li>
              这个邮箱对应的 EA 账号以前用 remid
              登录过本站的话，会收到认领信，打开链接设置密码就能用回旧账号。链接 4 小时内有效。
            </li>
            <li>一直没收到？确认填的是 EA 账号的登录邮箱。新账号要等重新开放注册。</li>
          </ul>
          <Button variant="outline" className="w-full" onClick={() => setSent(null)}>
            换个邮箱重新提交
          </Button>
        </MailSentNotice>
      </AuthCard>
    );
  }

  if (closed) {
    return (
      <AuthCard kicker="Sign Up" title="暂停注册" footer={footer}>
        <div className="mb-5 rounded-sm border border-amber-500/30 bg-amber-500/10 p-3 text-sm leading-relaxed text-amber-100">
          现在暂停注册新账号，已有账号照常登录。
        </div>
        <p className="text-muted-foreground mb-5 text-sm leading-relaxed">
          以前用 remid 登录过的老用户，填 EA 账号（EA App /
          Origin）的登录邮箱就能认领旧账号，服务器权限和操作记录都会保留。
        </p>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>EA 账号邮箱</FormLabel>
                  <FormControl>
                    <Input type="email" autoComplete="email" spellCheck={false} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {captcha.widget}
            <Button
              type="submit"
              size="lg"
              className="w-full"
              disabled={submitting || !captcha.ready}
            >
              {submitting ? "提交中…" : "发送认领信"}
            </Button>
          </form>
        </Form>
      </AuthCard>
    );
  }

  if (sent) {
    return (
      <AuthCard kicker="Sign Up" title="去邮箱查收验证信" footer={footer}>
        <MailSentNotice message={sent.message}>
          <ul className="text-muted-foreground list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
            <li>打开信里的链接设置密码，注册就完成了。链接 4 小时内有效。</li>
            {sent.mode === "ea" ? (
              <li>
                一直没收到？确认填的是 EA 账号的登录邮箱；用的是旧邮箱收不到信的话，可以
                <button
                  type="button"
                  className="text-primary mx-1 underline-offset-4 hover:underline"
                  onClick={() => {
                    setMode("plain");
                    setSent(null);
                  }}
                >
                  用其他邮箱注册
                </button>
                。
              </li>
            ) : (
              <li>注册后还要绑定一个 EA 账号才能开始使用。</li>
            )}
          </ul>
          <Button variant="outline" className="w-full" onClick={() => setSent(null)}>
            换个邮箱重新提交
          </Button>
        </MailSentNotice>
      </AuthCard>
    );
  }

  return (
    <AuthCard kicker="Sign Up" title="注册 BF-Manager" footer={footer}>
      <div
        role="radiogroup"
        aria-label="注册方式"
        className="mb-4 grid grid-cols-2 rounded-sm border border-white/10 bg-white/[0.03] p-1"
      >
        {MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            role="radio"
            aria-checked={mode === m.value}
            onClick={() => setMode(m.value)}
            className={cn(
              "h-11 rounded-[2px] text-sm font-medium transition-colors",
              mode === m.value
                ? "bg-amber-500 text-black"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {m.label}
          </button>
        ))}
      </div>

      <p className="text-muted-foreground mb-5 text-sm leading-relaxed">
        {mode === "ea"
          ? "填 EA 账号（EA App / Origin）的登录邮箱。我们据此找到你的 EA 账号，验证信能打开，就同时证明了邮箱和 EA 账号都是你的，不用再另外绑定。以前用 remid 登录过的，用这个方式认领旧账号。"
          : "用任意邮箱注册。注册后还要填一次 remid，或用 EA 账号密码登录一次，把 EA 账号绑上才能开始使用。"}
      </p>

      {groupInvite ? (
        <div className="mb-5 rounded-sm border border-amber-500/30 bg-amber-500/10 p-3 text-sm leading-relaxed text-amber-100">
          正在通过群组「{groupInvite.groupName}」的邀请链接注册，不需要邀请码，完成注册后自动进群。
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground ml-1 underline underline-offset-4"
            onClick={() => {
              clearPendingInvite();
              setGroupInvite(null);
            }}
          >
            不用这个链接
          </button>
        </div>
      ) : null}

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{mode === "ea" ? "EA 账号邮箱" : "邮箱"}</FormLabel>
                <FormControl>
                  <Input type="email" autoComplete="email" spellCheck={false} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          {inviteRequired ? (
            <FormField
              control={form.control}
              name="invite_code"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>邀请码</FormLabel>
                  <FormControl>
                    <Input
                      autoComplete="off"
                      spellCheck={false}
                      placeholder="XXXX-XXXX"
                      className="font-mono uppercase"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    {mode === "ea"
                      ? "向已注册的朋友要一个。认领旧账号不需要邀请码。"
                      : "向已注册的朋友要一个。"}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          ) : null}
          {captcha.widget}
          <Button
            type="submit"
            size="lg"
            className="w-full"
            disabled={submitting || !captcha.ready}
          >
            {submitting ? "提交中…" : "发送验证信"}
          </Button>
        </form>
      </Form>
    </AuthCard>
  );
}
