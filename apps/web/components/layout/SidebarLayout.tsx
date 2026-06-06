"use client";

import { useState } from "react";
import Link from "next/link";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { AppSidebar } from "./AppSidebar";
import { UserMenu } from "./UserMenu";

export function SidebarLayout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    // 应用界面统一深色「指挥台」外壳：根节点挂 dark，token 全量切到深色值
    <div className="dark bg-background text-foreground min-h-screen">
      {/* 桌面端固定侧边栏 —— 比内容区略亮一档，形成面板分层 */}
      <aside className="bg-card fixed inset-y-0 left-0 z-30 hidden w-60 border-r lg:block">
        <AppSidebar />
      </aside>

      {/* 移动端 Sheet 侧边栏 */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="dark bg-card text-foreground w-60 p-0">
          <SheetTitle className="sr-only">导航菜单</SheetTitle>
          <AppSidebar onNavClick={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>

      {/* 主区域 */}
      <div className="lg:ml-60">
        {/* 精简 Header */}
        <header className="bg-background/95 sticky top-0 z-40 flex h-14 items-center border-b px-4 backdrop-blur sm:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="mr-2 lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="打开导航菜单"
          >
            <Menu className="size-5" />
          </Button>

          <Link
            href="/dashboard"
            className="font-display text-sm font-semibold tracking-[0.15em] text-white uppercase lg:hidden"
          >
            BF-Manager
          </Link>

          <div className="ml-auto">
            <UserMenu />
          </div>
        </header>

        {/* 页面内容 */}
        {children}
      </div>
    </div>
  );
}
