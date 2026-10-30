import type { ReactNode } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface AuthCardProps {
  kicker: string;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  /** 卡片底部的次要链接（注册 / 登录 / 找回密码之间互相跳转） */
  footer?: ReactNode;
}

/** 登录系页面的表单卡片。手机端不套卡片，表单直接铺在页面上，像 App 的登录页 */
export function AuthCard({ kicker, title, description, children, footer }: AuthCardProps) {
  return (
    <Card className="sm:bg-card/80 w-full max-w-md border-0 bg-transparent shadow-none sm:border sm:border-white/10 sm:shadow-2xl sm:backdrop-blur-md">
      <CardHeader className="px-0 pt-0 sm:p-6">
        <div className="font-display mb-1 flex items-center gap-2 text-xs font-medium tracking-[0.2em] text-amber-500 uppercase">
          <span className="h-[2px] w-6 bg-amber-500" />
          {kicker}
        </div>
        <CardTitle className="text-2xl sm:text-lg">{title}</CardTitle>
        {description ? (
          <CardDescription className="pt-1 leading-relaxed sm:pt-0">{description}</CardDescription>
        ) : null}
      </CardHeader>
      <CardContent className="px-0 sm:px-6">
        {children}
        {footer ? (
          <div className="text-muted-foreground mt-6 flex flex-wrap gap-x-4 gap-y-2 border-t border-white/10 pt-4 text-sm">
            {footer}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** 发信类请求提交后的结果：不论邮箱是否存在都显示同一句话 */
export function MailSentNotice({ message, children }: { message: string; children?: ReactNode }) {
  return (
    <div className="space-y-4">
      <div className="rounded-sm border border-amber-500/30 bg-amber-500/10 p-4 text-sm leading-relaxed text-amber-100">
        {message}
      </div>
      {children}
    </div>
  );
}
