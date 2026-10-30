"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "sonner";
import { ChevronDown } from "lucide-react";
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
import { EaLoginDialog } from "@/components/common/EaLoginFlow";
import { useSession } from "@/hooks/useSession";
import { bindWithCookie, logout } from "@/lib/auth";
import { ApiException } from "@/lib/api-client";

const cookieSchema = z.object({
  remid: z.string().trim().min(10, "remid 看上去不是合法 cookie 值"),
  // sid 留空时由 EA 在登录响应里自动签发新值
  sid: z
    .string()
    .trim()
    .optional()
    .refine((v) => !v || v.length >= 10, "sid 如填写需是合法 cookie 值"),
});

type CookieValues = z.infer<typeof cookieSchema>;

/**
 * 邮箱注册后还没绑 EA 的账号停在这里：两种方式任选，绑上后才能用站内其他功能。
 * 绑的 EA 号如果挂在旧账号（remid 登录时代建的）上，会认领旧账号，当前会话随之作废，
 * 这时送回登录页用同样的邮箱密码重新登录。
 */
export default function BindPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const session = useSession();
  const [flowOpen, setFlowOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // 主动退出、认领后跳登录页时，会话清空不该再触发下面的「未登录」跳转
  const [leaving, setLeaving] = useState(false);
  const user = session.data;

  useEffect(() => {
    if (leaving || session.isLoading || session.isError) return;
    if (!user) router.replace("/login?next=/bind");
    else if (user.status !== "pending_binding") router.replace("/me");
  }, [leaving, session.isLoading, session.isError, user, router]);

  const form = useForm<CookieValues>({
    resolver: zodResolver(cookieSchema),
    defaultValues: { remid: "", sid: "" },
  });

  const finish = (claimed: boolean, name: string | null) => {
    if (claimed) {
      setLeaving(true);
      qc.setQueryData(["session"], null);
      router.replace("/login?claimed=1");
      return;
    }
    toast.success(name ? `已绑定 ${name}` : "EA 账号已绑定");
    qc.invalidateQueries({ queryKey: ["session"] });
    router.replace("/stats");
  };

  const onCookieSubmit = async (values: CookieValues) => {
    setSubmitting(true);
    try {
      const res = await bindWithCookie({ remid: values.remid, sid: values.sid || undefined });
      finish(res.claimed, res.display_name);
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : "绑定失败，请检查 remid / sid");
      setSubmitting(false);
    }
  };

  const onLogout = async () => {
    setLeaving(true);
    await logout().catch(() => {});
    qc.setQueryData(["session"], null);
    router.replace("/login");
  };

  if (!user || user.status !== "pending_binding") {
    return <div className="text-muted-foreground p-12 text-sm">加载中…</div>;
  }

  return (
    <AuthCard
      kicker="Link EA Account"
      title="绑定 EA 账号"
      description={
        <>
          账号 <span className="text-foreground break-all">{user.email}</span> 还没有绑定 EA
          账号。绑定后才能查看自己的战绩、管理服务器。下面两种方式任选一种。
        </>
      }
      footer={
        <button type="button" onClick={onLogout} className="underline-offset-4 hover:underline">
          退出登录
        </button>
      }
    >
      <section className="space-y-3">
        <h2 className="text-sm font-semibold">方式一：用 EA 账号密码登录一次</h2>
        <p className="text-muted-foreground text-sm leading-relaxed">
          在弹窗里输入 EA 账号的邮箱和密码，按提示收验证码。EA 账号密码只用于这一次验证，不会保存。
        </p>
        <Button size="lg" className="w-full" onClick={() => setFlowOpen(true)}>
          用 EA 账号密码绑定
        </Button>
      </section>

      <section className="mt-6 space-y-3 border-t border-white/10 pt-6">
        <h2 className="text-sm font-semibold">方式二：填 remid</h2>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onCookieSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="remid"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>remid</FormLabel>
                  <FormControl>
                    <Input autoComplete="off" spellCheck={false} {...field} />
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
                      placeholder="留空即可"
                      {...field}
                      value={field.value ?? ""}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <details className="group text-xs text-white/55">
              <summary className="flex cursor-pointer list-none items-center gap-1 text-white/70 hover:text-white">
                <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
                怎么获取 remid
              </summary>
              <ol className="mt-2 list-decimal space-y-1 pl-5 leading-relaxed">
                <li>用要绑定的 EA 账号在浏览器登录 ea.com。</li>
                <li>
                  按 F12 打开开发者工具，进入「应用」（Application）→ Cookie →
                  https://accounts.ea.com。
                </li>
                <li>复制 remid 的值。remid 只用来验证这一次，不会保存。</li>
              </ol>
            </details>
            <Button
              type="submit"
              variant="secondary"
              size="lg"
              className="w-full"
              disabled={submitting}
            >
              {submitting ? "验证中…" : "用 remid 绑定"}
            </Button>
          </form>
        </Form>
      </section>

      <EaLoginDialog
        actor="user"
        open={flowOpen}
        onOpenChange={setFlowOpen}
        onSucceeded={(task) => {
          setFlowOpen(false);
          finish(task.result?.claimed ?? false, task.result?.display_name ?? null);
        }}
      />
    </AuthCard>
  );
}
