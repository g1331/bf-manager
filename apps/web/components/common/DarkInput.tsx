"use client";

import * as React from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * 站内统一的深色搜索 / 筛选输入框。
 *
 * 在背景图层上方的深色面板里复用：深底 + 半透明白边 + 白字占位。
 * focus 态刻意克制——关掉基础 `Input` 默认的 `ring-2 ring-offset-2`（在深底上会显出
 * 刺眼的双层外圈），改为 focus 时主色边框高亮，靠 `cn` 的 tailwind-merge 覆盖同组工具类。
 * 默认 `h-9`，调用方可用 className 覆盖高度（如主搜索框传 `h-12` 与按钮等高）。
 */
const DARK_INPUT_CLASS =
  "h-9 border-white/15 bg-black/30 text-white placeholder:text-white/35 transition-colors " +
  "focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:border-primary/70";

export const DarkInput = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <Input ref={ref} className={cn(DARK_INPUT_CLASS, className)} {...props} />
));
DarkInput.displayName = "DarkInput";
