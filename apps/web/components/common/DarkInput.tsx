"use client";

import * as React from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * 站内统一的深色搜索 / 筛选输入框。
 *
 * 在背景图层上方的深色面板里复用：深底 + 半透明白边 + 白字占位。
 * focus 态用柔和的暖白光晕、并带轻微的"太阳式"明暗波动（呼吸感），而非基础 `Input`
 * 默认那圈刺眼的 `ring-2 ring-offset-2` 双层外圈——先靠 `cn` 的 tailwind-merge 用
 * `ring-0 / ring-offset-0` 关掉默认 ring，再挂上 `.dark-input-glow`，由 globals.css 的
 * `.dark-input-glow:focus-visible` 用 keyframes 动画驱动暖光 box-shadow（并尊重
 * prefers-reduced-motion 降级为静态光晕）。默认 `h-9`，调用方可用 className 覆盖高度
 *（如主搜索框传 `h-12` 与按钮等高）。
 */
const DARK_INPUT_CLASS =
  "dark-input-glow h-9 border-white/15 bg-black/30 text-white placeholder:text-white/35 " +
  "transition-[color,border-color] focus-visible:ring-0 focus-visible:ring-offset-0";

export const DarkInput = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <Input ref={ref} className={cn(DARK_INPUT_CLASS, className)} {...props} />
));
DarkInput.displayName = "DarkInput";
