"use client";

import { useEffect, useRef, useState } from "react";
import { UsersRound, UserPlus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSession } from "@/hooks/useSession";

/**
 * 右侧好友 / 派对侧栏，默认收起：
 *   收起时只占一条窄边，顶部留一个图标入口，主内容尽量铺开；
 *   点击入口后面板从舞台右缘滑出，浮在主内容之上，不挤压布局。
 *   点面板外、按 Esc 或点关闭按钮都会收起。面板与内容之间不画竖线分隔——大厅本身没有这条线。
 *
 * 当前为占位形态，好友 / 派对数据尚未接入，不伪造任何社交数据。
 */
export function FriendsRail() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLElement>(null);
  const session = useSession();
  const isLoggedIn = !!session.data;

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <aside ref={rootRef} className="sticky top-0 z-50 hidden h-screen w-14 shrink-0 lg:block">
      {/* 收起态：入口贴顶部 header 行、紧邻账户区，作为右上角社交入口 */}
      <div className="flex justify-center pt-6">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={cn(
            "flex size-9 items-center justify-center rounded-full transition-colors hover:text-white",
            open ? "text-white" : "text-white/55",
          )}
          aria-label="好友与派对"
          aria-expanded={open}
          aria-controls="friends-panel"
          title="好友与派对"
        >
          <UsersRound className="size-5" />
        </button>
      </div>

      {/* 展开态：从舞台右缘滑出、浮在主内容之上；舞台 overflow-hidden 会裁掉收起时移出的部分 */}
      <div
        id="friends-panel"
        className={cn(
          "absolute inset-y-0 right-0 w-72 bg-black/80 backdrop-blur-md transition-[opacity,translate] duration-300",
          open ? "translate-x-0 opacity-100" : "pointer-events-none translate-x-full opacity-0",
        )}
        aria-hidden={!open}
        inert={!open}
      >
        <ExpandedPanel isLoggedIn={isLoggedIn} onClose={() => setOpen(false)} />
      </div>
    </aside>
  );
}

/** 展开态：派对 + 在线 / 离线好友区；当前为占位说明，待数据接入后填充。 */
function ExpandedPanel({ isLoggedIn, onClose }: { isLoggedIn: boolean; onClose: () => void }) {
  return (
    <div className="flex h-full flex-col px-5 pt-6">
      <div className="flex h-9 items-center gap-2.5">
        <UsersRound className="size-5 text-white/70" />
        <span className="font-display text-sm font-semibold tracking-[0.18em] text-white/85 uppercase">
          好友与派对
        </span>
        <button
          type="button"
          onClick={onClose}
          className="-mr-2 ml-auto flex size-9 items-center justify-center rounded-full text-white/55 transition-colors hover:text-white"
          aria-label="收起好友与派对"
        >
          <X className="size-5" />
        </button>
      </div>

      <span className="mt-4 h-px bg-white/10" aria-hidden />

      {/* 占位区：派对 / 好友数据待接入，先说明来源，不伪造任何列表 */}
      <div className="mt-10 flex flex-col items-center gap-3 text-center">
        <UserPlus className="size-7 text-white/25" />
        <p className="text-sm leading-relaxed text-white/45">
          {isLoggedIn ? "好友与派对功能尚未接入。" : "登录后可在此查看派对与好友。"}
        </p>
      </div>
    </div>
  );
}
