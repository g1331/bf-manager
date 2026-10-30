"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
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
import { AuthCard, MailSentNotice } from "@/components/auth/AuthCard";
import { useCaptcha } from "@/components/auth/Turnstile";
import { requestPasswordReset } from "@/lib/auth";
import { ApiException } from "@/lib/api-client";

const schema = z.object({ email: z.string().trim().email("请输入正确的邮箱") });

export default function ForgotPasswordPage() {
  const captcha = useCaptcha();
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "" },
  });

  const onSubmit = async ({ email }: z.infer<typeof schema>) => {
    setSubmitting(true);
    try {
      setSent((await requestPasswordReset(email, captcha.token)).message);
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : "提交失败，请稍后重试");
    } finally {
      setSubmitting(false);
      captcha.reset();
    }
  };

  const footer = (
    <>
      <Link href="/login" className="text-primary underline-offset-4 hover:underline">
        返回登录
      </Link>
      <Link href="/register" className="underline-offset-4 hover:underline">
        注册账号
      </Link>
    </>
  );

  return (
    <AuthCard
      kicker="Reset Password"
      title={sent ? "去邮箱查收重置链接" : "找回密码"}
      description={sent ? undefined : "填注册时用的邮箱，我们会发一封重置密码的信。"}
      footer={footer}
    >
      {sent ? (
        <MailSentNotice message={sent}>
          <p className="text-muted-foreground text-sm leading-relaxed">
            链接 1 小时内有效。设置新密码后，其他设备上的登录会全部退出。以前用 remid
            登录、还没设置过邮箱的旧账号收不到这封信，请用 EA 账号邮箱
            <Link href="/register" className="text-primary mx-1 underline-offset-4 hover:underline">
              注册
            </Link>
            认领。
          </p>
        </MailSentNotice>
      ) : (
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
            {captcha.widget}
            <Button
              type="submit"
              size="lg"
              className="w-full"
              disabled={submitting || !captcha.ready}
            >
              {submitting ? "提交中…" : "发送重置链接"}
            </Button>
          </form>
        </Form>
      )}
    </AuthCard>
  );
}
