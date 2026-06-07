"use client";

import { useState } from "react";
import Link from "next/link";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { AppRail } from "./AppRail";
import { FriendsRail } from "./FriendsRail";
import { MobileNav } from "./MobileNav";
import { TopTabs } from "./TopTabs";
import { UserMenu } from "./UserMenu";
import { PageTransition } from "./PageTransition";
import { AmbientBackground } from "./AmbientBackground";

/**
 * 应用外壳，复刻经典战地大厅的两级导航布局：
 *   关键思路：整套 UI 作为一个按视口比例（95vw，超宽屏由 200vh 上限收拢）伸缩的「舞台」
 *   在视口里居中，而非把元素逐个钉到屏幕边缘。视口比舞台宽时左右露出战场氛围；
 *   比例变极端时整组元素向中心集中，避免「贴边挤压」。这正是真实大厅在不同宽高比下的行为。
 *
 *   结构：rail 与主区域并列在舞台 flex 容器里；rail 用 sticky h-screen 跟随滚动并
 *   随舞台水平居中而非紧贴视口左缘；战场氛围背景仍铺满视口最底层。
 *   左侧 rail（AppRail）切「游戏 / 模块」，与内容之间靠局部竖线分隔；
 *   顶部横向 tab（TopTabs）切模块内子页，激活刻线与文字等宽且发光、切换时滑动跟随。
 *   移动端将一级导航收进左侧抽屉（MobileNav），二级 tab 单独成行常驻。
 */
export function SidebarLayout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="dark bg-background text-foreground relative min-h-screen">
      {/* BF1 大厅式氛围底层：战场实景铺满视口最底，UI 直接浮于其上 */}
      <AmbientBackground />

      {/* 移动端 Sheet：仅收纳一级模块导航 */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="dark bg-card text-foreground w-64 p-0">
          <SheetTitle className="sr-only">导航菜单</SheetTitle>
          <MobileNav onNavClick={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>

      {/* 舞台容器：比例对照真实 BF1 大厅实测——窗口约 1.9:1 时 UI 仍填到约 95% 宽，
          rail 图标中心落在视口约 5%（贴近左缘），右上厂牌贴到约 97%。故横向恒占 95vw，
          使常规到 2:1 的窗口下 rail / tab / 厂牌的边距与真实大厅一致；只有当窗口比例
          比 2:1 更宽（超宽屏）时，200vh 上限才介入，把整组元素向中心集中、两侧露出
          战场氛围——对应真实大厅在宽高比变极端时「元素集中统一」而非紧贴边缘的行为。 */}
      <div
        className="relative z-10 mx-auto flex min-h-screen"
        style={{ width: "min(95vw, 200vh)" }}
      >
        {/* 桌面端 rail：随舞台容器水平居中，sticky 跟随滚动。
            z-20 让 rail 浮在详情页 `fixed inset-0 z-0` 的全屏背景之上（低于 header 的 z-40），
            否则全屏背景在 DOM 中靠后、同层级会把 rail 盖住。 */}
        <aside className="sticky top-0 z-20 hidden h-screen w-28 shrink-0 lg:block">
          <AppRail />
          {/* 分隔竖线：贯穿整屏高度、与上下边缘接壤，复刻真实大厅 rail 分隔线的全高形态 */}
          <span className="absolute inset-y-0 right-0 w-px bg-white/12" aria-hidden />
        </aside>

        {/* 主内容列 */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* 顶部 Header：纯浮层，无边框、无实色块；桌面端左侧嵌二级 tab，右侧厂牌与账户 */}
          <header className="relative z-40 flex h-32 items-end px-6 pb-3 sm:px-10">
            {/* 移动端汉堡 */}
            <div className="flex items-center pb-1 lg:hidden">
              <Button
                variant="ghost"
                size="icon"
                className="-ml-2"
                onClick={() => setMobileOpen(true)}
                aria-label="打开导航菜单"
              >
                <Menu className="size-5" />
              </Button>
            </div>

            {/* 桌面端二级 tab（带滑动发光指示） */}
            <TopTabs className="hidden lg:flex" animated />

            {/* 右侧：厂牌 logo + 账户 */}
            <div className="ml-auto flex items-end gap-7 pb-1">
              <Link
                href="/stats"
                className="hidden items-center gap-2.5 sm:flex"
                aria-label="BF-Manager 首页"
              >
                <span className="h-7 w-[3px] bg-amber-500" />
                <span className="flex flex-col leading-none">
                  <span className="font-display text-lg font-semibold tracking-[0.22em] text-white uppercase">
                    BF-Manager
                  </span>
                  <span className="font-display mt-1 text-[10px] tracking-[0.4em] text-white/55 uppercase">
                    Battlefield Portal
                  </span>
                </span>
              </Link>
              <UserMenu />
            </div>
          </header>

          {/* 移动端二级 tab：单独成行常驻，可横向滚动；当前路由无 tab 时整行隐藏 */}
          <div className="px-4 empty:hidden lg:hidden">
            <TopTabs />
          </div>

          {/*
           * 页面内容容器：覆盖各页面 main 自带的 `mx-auto`，让内容紧贴 tab 起点向右铺开，
           * 实现「整组元素集中统一」的视觉。错误页（max-w-md）需要保留居中，特判跳过。
           * max-w 由页面各自决定，这里只改对齐方式不改宽度。
           */}
          <div className="[&_main:not(.max-w-md)]:!mr-auto [&_main:not(.max-w-md)]:!ml-0 [&_main:not(.max-w-md)]:!px-6 sm:[&_main:not(.max-w-md)]:!px-10">
            <PageTransition>{children}</PageTransition>
          </div>
        </div>

        {/* 右侧好友 / 派对侧栏：恒定占据展开宽度，主内容据此收窄、为右侧留白；
            悬浮后在这片预留区内原地铺出面板，不挤压也不覆盖主内容；
            社交数据待桌面端客户端接口接入。 */}
        <FriendsRail />
      </div>
    </div>
  );
}
