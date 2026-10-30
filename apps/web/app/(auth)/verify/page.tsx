"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "sonner";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { AuthCard } from "@/components/auth/AuthCard";
import { confirmMatches, confirmMismatch, newPasswordFields } from "@/components/auth/password";
import {
  confirmVerification,
  landingPath,
  lookupVerification,
  type VerificationInfo,
} from "@/lib/auth";
import { ApiException } from "@/lib/api-client";

const schema = z.object(newPasswordFields).refine(confirmMatches, confirmMismatch);
type Values = z.infer<typeof schema>;

const COPY: Record<
  string,
  { kicker: string; title: string; description: string; submit: string; done: string }
> = {
  register_ea: {
    kicker: "Sign Up",
    title: "完成注册",
    description: "设置登录密码，注册就完成了，EA 账号会同时绑定好。以后用这个邮箱和密码登录。",
    submit: "完成注册",
    done: "注册完成",
  },
  register_plain: {
    kicker: "Sign Up",
    title: "完成注册",
    description: "设置登录密码。下一步再绑定一个 EA 账号，就可以开始使用了。",
    submit: "设置密码",
    done: "邮箱已验证，下一步绑定 EA 账号",
  },
  claim: {
    kicker: "Claim Account",
    title: "认领旧账号",
    description: "设置登录密码后，旧账号的服务器权限和操作记录都会保留，以后用这个邮箱和密码登录。",
    submit: "认领账号",
    done: "旧账号已认领",
  },
  reset: {
    kicker: "Reset Password",
    title: "设置新密码",
    description: "设置后，其他设备上的登录会全部退出。",
    submit: "保存新密码",
    done: "密码已重置",
  },
  set_email: {
    kicker: "Verify Email",
    title: "验证登录邮箱",
    description: "设置登录密码后，以后用这个邮箱和密码登录。",
    submit: "验证并设置密码",
    done: "登录邮箱已设置",
  },
};

function copyFor(info: VerificationInfo) {
  if (info.kind === "register")
    return COPY[info.mode === "plain" ? "register_plain" : "register_ea"];
  return COPY[info.kind];
}

/** 从 #token=… 里取出 token 后立刻把它从地址栏抹掉，免得截图、分享时带出去 */
function useHashToken(): string | null | undefined {
  const [token, setToken] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    const value = new URLSearchParams(window.location.hash.slice(1)).get("token");
    if (value) window.history.replaceState(null, "", window.location.pathname);
    // 只在挂载时从地址栏读一次，读完就清掉 hash。开发模式下 effect 会跑两遍，
    // 第二遍 hash 已经清空，不能把第一遍读到的 token 覆盖成 null
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setToken((prev) => prev ?? value);
  }, []);
  return token;
}

export default function VerifyPage() {
  const token = useHashToken();
  const info = useQuery({
    queryKey: ["verification", token],
    queryFn: () => lookupVerification(token as string),
    enabled: !!token,
    retry: false,
    staleTime: Infinity,
  });

  if (token === undefined || (token && info.isLoading)) {
    return <div className="text-muted-foreground p-12 text-sm">正在检查链接…</div>;
  }
  if (!token || info.isError || !info.data) {
    const message =
      info.error instanceof ApiException ? info.error.message : "链接无效或已过期，请重新申请";
    return (
      <AuthCard kicker="Link Expired" title="链接用不了了">
        <p className="text-muted-foreground text-sm leading-relaxed">
          {message}。链接只能用一次，新申请的链接会让旧的失效，请打开最近一封信里的链接。
        </p>
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <Button asChild variant="outline">
            <Link href="/register">重新注册</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/forgot-password">找回密码</Link>
          </Button>
        </div>
      </AuthCard>
    );
  }
  return <SetPasswordForm token={token} info={info.data} />;
}

function SetPasswordForm({ token, info }: { token: string; info: VerificationInfo }) {
  const router = useRouter();
  const qc = useQueryClient();
  const copy = copyFor(info);
  const [submitting, setSubmitting] = useState(false);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirm: "" },
  });

  const onSubmit = async ({ password }: Values) => {
    setSubmitting(true);
    try {
      const user = await confirmVerification(token, password);
      qc.setQueryData(["session"], user);
      toast.success(copy.done);
      router.replace(landingPath(user, info.kind === "set_email" ? "/me" : "/stats"));
      router.refresh();
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : "提交失败，请稍后重试");
      setSubmitting(false);
    }
  };

  return (
    <AuthCard kicker={copy.kicker} title={copy.title} description={copy.description}>
      <dl className="mb-5 space-y-2 rounded-sm border border-white/10 bg-white/[0.03] p-3 text-sm">
        <div className="flex gap-3">
          <dt className="text-muted-foreground w-16 shrink-0">邮箱</dt>
          <dd className="min-w-0 break-all">{info.email}</dd>
        </div>
        {info.persona_name ? (
          <div className="flex gap-3">
            <dt className="text-muted-foreground w-16 shrink-0">EA 账号</dt>
            <dd className="min-w-0 font-medium break-all">{info.persona_name}</dd>
          </div>
        ) : null}
      </dl>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
          {/* 让浏览器把邮箱和新密码一起存进密码管理器 */}
          <input type="email" autoComplete="username" value={info.email} readOnly hidden />
          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{info.kind === "reset" ? "新密码" : "登录密码"}</FormLabel>
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
          <Button type="submit" size="lg" className="w-full" disabled={submitting}>
            {submitting ? "提交中…" : copy.submit}
          </Button>
        </form>
      </Form>
    </AuthCard>
  );
}
