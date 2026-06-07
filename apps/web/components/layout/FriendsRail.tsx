"use client";

import { useState } from "react";
import { UsersRound, UserPlus } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSession } from "@/hooks/useSession";

/**
 * 右侧好友 / 派对侧栏，复刻经典战地大厅右侧那条可伸缩的社交面板：
 *   侧栏恒定占据展开所需的宽度，主内容据此收窄、为右侧让出一片预留空白——
 *   这正是大厅主体内容本身就给右侧留白的形态。未悬浮时图标贴在预留区右缘、
 *   左侧留白即为间距；鼠标悬浮后在这片预留区内原地铺出深色面板，既不挤压
 *   也不覆盖主内容。面板与内容之间不画竖线分隔——大厅本身没有这条线。
 *
 * 当前为占位形态。好友 / 派对数据需玩家登录后经桌面端客户端接口接入，接入前
 * 仅展示占位说明，不伪造任何社交数据；折叠 / 展开行为先行实现，待数据链路
 * 接通后直接在展开区填充派对与好友列表即可。
 */
export function FriendsRail() {
  const [open, setOpen] = useState(false);
  const session = useSession();
  const isLoggedIn = !!session.data;

  return (
    <aside
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocusCapture={() => setOpen(true)}
      onBlurCapture={() => setOpen(false)}
      className="sticky top-0 z-30 hidden h-screen w-72 shrink-0 lg:block"
    >
      {/* 收拢态：入口贴顶部 header 行、紧邻账户区，作为右上角社交入口；
          左侧大片留白即主内容预留的右侧空间 */}
      <div
        className={cn(
          "flex h-full flex-col items-end pt-[6.5rem] pr-6 transition-opacity duration-300",
          open ? "pointer-events-none opacity-0" : "opacity-100",
        )}
      >
        <button
          type="button"
          className="flex items-center gap-2 text-white/55 transition-colors hover:text-white"
          aria-label="好友与派对"
        >
          <UsersRound className="size-5" />
          <span className="text-sm font-medium tracking-wide">好友</span>
        </button>
      </div>

      {/* 展开态：在预留宽度内原地铺出深色面板，不挤压、也不覆盖主内容 */}
      <div
        className={cn(
          "absolute inset-0 bg-black/70 backdrop-blur-sm transition-opacity duration-300",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        aria-hidden={!open}
      >
        <ExpandedPanel isLoggedIn={isLoggedIn} />
      </div>
    </aside>
  );
}

/** 展开态：派对 + 在线 / 离线好友区；当前为占位说明，待数据接入后填充。 */
function ExpandedPanel({ isLoggedIn }: { isLoggedIn: boolean }) {
  return (
    <div className="flex h-full flex-col px-5 pt-[18vh]">
      <div className="flex items-center gap-2.5">
        <UsersRound className="size-5 text-white/70" />
        <span className="font-display text-sm font-semibold tracking-[0.18em] text-white/85 uppercase">
          好友与派对
        </span>
      </div>

      <span className="mt-4 h-px bg-white/10" aria-hidden />

      {/* 占位区：派对 / 好友数据待接入，先说明来源，不伪造任何列表 */}
      <div className="mt-10 flex flex-col items-center gap-3 text-center">
        <UserPlus className="size-7 text-white/25" />
        <p className="text-sm leading-relaxed text-white/45">
          {isLoggedIn
            ? "好友与派对功能尚未接入，后续将通过桌面端客户端读取派对与在线 / 离线好友。"
            : "登录后可在此查看派对与好友。"}
        </p>
      </div>
    </div>
  );
}
