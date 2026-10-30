"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { AccountNotice } from "./AccountNotice";
import { AppRail } from "./AppRail";
import { FriendsRail } from "./FriendsRail";
import { InstallPrompt } from "./InstallPrompt";
import { MobileAppBar, getDetailRoute } from "./MobileAppBar";
import { MobileNav } from "./MobileNav";
import { MobileTabBar } from "./MobileTabBar";
import { TopTabs } from "./TopTabs";
import { UserMenu } from "./UserMenu";
import { PageTransition } from "./PageTransition";
import { AmbientBackground } from "./AmbientBackground";
import { useTrackNavigation } from "@/hooks/useNavigation";
import { getNavContext, isTabActive } from "@/lib/nav";

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
 *   移动端将一级导航收进左侧抽屉（MobileNav），二级 tab 单独成行常驻；
 *   最常用的五个入口另放在底部标签栏（MobileTabBar），装到桌面的提示条浮在它上方。
 */
export function SidebarLayout({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();
  const detailRoute = getDetailRoute(pathname);
  // 手机端二级 tab 只在当前页属于其中一项时显示；「我的服务器」「我的」这类底部标签栏入口不挂一排没选中的 tab
  const showMobileTabs =
    !detailRoute && getNavContext(pathname).tabs.some((tab) => isTabActive(pathname, tab));
  useTrackNavigation();

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
          战场氛围——对应真实大厅在宽高比变极端时「元素集中统一」而非紧贴边缘的行为。
          手机和平板没有 rail，按 App 的样子铺满整屏，边距交给页面自己。 */}
      <div className="relative z-10 mx-auto flex min-h-screen w-full lg:h-screen lg:w-[min(95vw,200vh)] lg:overflow-hidden">
        {/* 桌面端 rail：随舞台容器水平居中，sticky 跟随滚动。
            z-20 让 rail 浮在详情页 `fixed inset-0 z-0` 的全屏背景之上（低于 header 的 z-40），
            否则全屏背景在 DOM 中靠后、同层级会把 rail 盖住。 */}
        <aside className="sticky top-0 z-20 hidden h-screen w-28 shrink-0 lg:block">
          <AppRail />
          {/* 分隔竖线：贯穿整屏高度、与上下边缘接壤，复刻真实大厅 rail 分隔线的全高形态 */}
          <span className="absolute inset-y-0 right-0 w-px bg-white/12" aria-hidden />
        </aside>

        {/* 主内容列：桌面端固定满高、自身不滚，滚动交给内部页面区，使顶栏与子标签常驻 */}
        <div className="flex min-w-0 flex-1 flex-col lg:min-h-0 lg:overflow-hidden">
          {/* 手机端：吸顶导航栏 + 二级 tab 行（详情页不显示 tab，顶栏换成返回键） */}
          <MobileAppBar onMenu={() => setMobileOpen(true)} />
          {showMobileTabs ? (
            <div className="px-4 lg:hidden">
              <TopTabs />
            </div>
          ) : null}

          {/* 桌面端 Header：纯浮层，无边框、无实色块；左侧嵌二级 tab，右侧厂牌与账户 */}
          <header className="relative z-40 hidden h-20 items-end px-10 pb-3 lg:flex">
            {/* 二级 tab（带滑动发光指示） */}
            <TopTabs animated />

            {/* 右侧：厂牌 logo + 账户 */}
            <div className="ml-auto flex shrink-0 items-end gap-7 pb-1 pl-5">
              <Link
                href="/stats"
                className="flex items-center gap-2.5"
                aria-label="BF-Manager 首页"
              >
                <span className="h-7 w-[3px] bg-amber-500" />
                {/* 窄桌面只留橙色竖条，把宽度让给 tab */}
                <span className="hidden flex-col leading-none min-[1360px]:flex">
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

          {/*
           * 页面内容容器：覆盖各页面 main 自带的 `mx-auto`，让内容紧贴 tab 起点向右铺开，
           * 实现「整组元素集中统一」的视觉。错误页（max-w-md）需要保留居中，特判跳过。
           * max-w 由页面各自决定，这里只改对齐方式不改宽度。
           * 移动端底部留出标签栏的 h-14；底部安全区已由 body 的 padding 留过。
           */}
          <div className="pb-14 lg:flex lg:min-h-0 lg:flex-1 lg:flex-col lg:pb-0 [&_main:not(.max-w-md)]:!mr-auto [&_main:not(.max-w-md)]:!ml-0 [&_main:not(.max-w-md)]:!px-4 sm:[&_main:not(.max-w-md)]:!px-10">
            <AccountNotice />
            <PageTransition>{children}</PageTransition>
          </div>
        </div>

        {/* 右侧好友 / 派对侧栏：默认收起成一条窄边，点开后面板浮在主内容之上 */}
        <FriendsRail />
      </div>

      <MobileTabBar />
      <InstallPrompt />
    </div>
  );
}
