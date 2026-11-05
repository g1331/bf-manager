"use client";

import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";
import * as Popover from "@radix-ui/react-popover";
import { cn } from "@/lib/utils";

const OPEN_DELAY = 250;
const CLOSE_DELAY = 100;

/** 文字类触发器的虚线下划线，提示这里能点开说明 */
export const HINT_UNDERLINE =
  "underline decoration-white/30 decoration-dotted underline-offset-[3px] hover:decoration-white/70";

interface Props {
  /** 气泡里的说明 */
  content: ReactNode;
  /** 触发区域里显示的内容（标签、徽标等），整块可点 */
  children: ReactNode;
  className?: string;
  side?: "top" | "right" | "bottom" | "left";
  /** 触发器的可访问名称；触发器文字本身说不清指的是什么时传 */
  label?: string;
}

/**
 * 手机上也要看得到的说明。鼠标悬停弹出，点按（触屏、鼠标、键盘）切换。
 * 只在桌面锦上添花的提示用 ui/tooltip；这里给“看不到就读不懂”的说明用。
 *
 * 触发器和气泡上的点击不往外冒泡：它们常放在可点开的表格行里，
 * 而 React 合成事件会穿过 Portal 冒到行上。
 */
export function InfoHint({ content, children, className, side = "top", label }: Props) {
  const [open, setOpen] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  // 悬停打开后再点一下，是想把气泡留住而不是关掉
  const hoverOpened = useRef(false);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const schedule = (next: boolean, delay: number) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      hoverOpened.current = next;
      setOpen(next);
    }, delay);
  };
  const onEnter = (e: PointerEvent) => {
    if (e.pointerType !== "mouse") return;
    if (open) window.clearTimeout(timer.current);
    else schedule(true, OPEN_DELAY);
  };
  const onLeave = (e: PointerEvent) => {
    if (e.pointerType !== "mouse") return;
    if (open && !hoverOpened.current) return; // 点开的不随鼠标离开关闭
    schedule(false, CLOSE_DELAY);
  };

  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        window.clearTimeout(timer.current);
        hoverOpened.current = false;
        setOpen(next);
      }}
    >
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label={label}
          onPointerEnter={onEnter}
          onPointerLeave={onLeave}
          onClick={(e) => {
            e.stopPropagation();
            if (open && hoverOpened.current) {
              e.preventDefault(); // 跳过 Radix 的开关切换
              hoverOpened.current = false;
            }
          }}
          className={cn("inline-action cursor-help text-left", className)}
        >
          {children}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side={side}
          sideOffset={6}
          collisionPadding={12}
          // 打开和关闭都不挪焦点：焦点从不进气泡，关闭时也就不该被拉回触发器，
          // 否则鼠标移开自动关闭时会把用户正在输入的框的焦点抢走
          onOpenAutoFocus={(e) => e.preventDefault()}
          onCloseAutoFocus={(e) => e.preventDefault()}
          onPointerEnter={onEnter}
          onPointerLeave={onLeave}
          onClick={(e) => e.stopPropagation()}
          className="data-[state=open]:animate-in data-[state=open]:fade-in data-[state=closed]:animate-out data-[state=closed]:fade-out z-50 max-w-[min(18rem,calc(100vw-24px))] border border-white/15 bg-black/90 px-2.5 py-1.5 text-xs leading-relaxed font-normal text-white shadow-[0_8px_24px_rgba(0,0,0,0.5)] backdrop-blur-sm outline-none"
        >
          {content}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
