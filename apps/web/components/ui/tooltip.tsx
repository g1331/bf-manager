"use client";

import { type ReactElement, type ReactNode } from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";

/** 全站挂一次：鼠标在相邻图标间移动时，第二个提示不再等延迟 */
export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <TooltipPrimitive.Provider delayDuration={300} skipDelayDuration={300}>
      {children}
    </TooltipPrimitive.Provider>
  );
}

interface TooltipProps {
  /** 提示文字；为空时原样渲染子元素 */
  content: ReactNode;
  /** 唯一子元素，需能接收 ref 和事件（DOM 元素、Link、forwardRef 组件） */
  children: ReactElement;
  side?: "top" | "right" | "bottom" | "left";
  className?: string;
}

/**
 * 桌面端的悬停提示：鼠标悬停或键盘聚焦时出现，触屏上不弹。
 * 只放“看不到也不影响使用”的内容（图标名称、图表数值）；手机上也必须能看到的说明用 InfoHint。
 * 截断文字的全名继续用原生 title。
 */
export function Tooltip({ content, children, side = "top", className }: TooltipProps) {
  if (content == null || content === "") return children;
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          collisionPadding={8}
          className={cn(
            "data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in data-[state=closed]:animate-out data-[state=closed]:fade-out z-50 max-w-[min(18rem,calc(100vw-16px))] border border-white/15 bg-black/90 px-2 py-1 text-xs leading-relaxed font-medium text-white shadow-[0_8px_24px_rgba(0,0,0,0.5)] backdrop-blur-sm",
            className,
          )}
        >
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
