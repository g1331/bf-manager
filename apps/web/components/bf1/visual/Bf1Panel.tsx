"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * BF1 风格切角面板基础组件
 *
 * 复刻 BF1 游戏内 HUD 的平行四边形面板：
 * - 默认顶部左 + 底部右切角（最常见的 stat / weapon 模板形态）
 * - 半透明灰色 + 背景模糊
 * - 通过 corners 任意组合四角切法，支持其他子模板形态
 */

export type Bf1PanelVariant = "default" | "dark" | "transparent";
export type Bf1PanelCorner = "topLeft" | "topRight" | "bottomLeft" | "bottomRight";

export interface Bf1PanelProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: Bf1PanelVariant;
  cut?: number;
  corners?: Bf1PanelCorner[];
}

const VARIANT_CLASS: Record<Bf1PanelVariant, string> = {
  default: "bg-[rgba(122,122,122,0.85)] backdrop-blur-sm shadow-[2px_2px_5px_rgba(0,0,0,0.5)]",
  dark: "bg-[rgba(22,22,24,0.6)] backdrop-blur-md",
  transparent: "",
};

function buildClipPath(cut: number, corners: Bf1PanelCorner[]): string {
  const tl = corners.includes("topLeft");
  const tr = corners.includes("topRight");
  const br = corners.includes("bottomRight");
  const bl = corners.includes("bottomLeft");
  const pts: string[] = [];
  if (tl) pts.push(`0 ${cut}px`, `${cut}px 0`);
  else pts.push("0 0");
  if (tr) pts.push(`calc(100% - ${cut}px) 0`, `100% ${cut}px`);
  else pts.push("100% 0");
  if (br) pts.push(`100% calc(100% - ${cut}px)`, `calc(100% - ${cut}px) 100%`);
  else pts.push("100% 100%");
  if (bl) pts.push(`${cut}px 100%`, `0 calc(100% - ${cut}px)`);
  else pts.push("0 100%");
  return `polygon(${pts.join(", ")})`;
}

export function Bf1Panel({
  variant = "default",
  cut = 32,
  corners = ["topLeft", "bottomRight"],
  className,
  style,
  children,
  ...rest
}: Bf1PanelProps) {
  const clipPath = buildClipPath(cut, corners);
  return (
    <div {...rest} className={cn(VARIANT_CLASS[variant], className)} style={{ clipPath, ...style }}>
      {children}
    </div>
  );
}
