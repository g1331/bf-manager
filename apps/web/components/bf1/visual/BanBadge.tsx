"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type BanState = "clean" | "hit" | "unknown";
export type BanSource = "bfban" | "bfeac";

interface BanBadgeProps {
  source: BanSource;
  state: BanState;
  size?: "sm" | "md";
}

const SOURCE_META: Record<BanSource, { label: string; logoSrc: string; hitText: string }> = {
  bfban: {
    label: "BFBAN",
    logoSrc: "/bf1/branding/bfban-logo.png",
    hitText: "实锤",
  },
  bfeac: {
    label: "BFEAC",
    logoSrc: "/bf1/branding/bfeac-logo.png",
    hitText: "已封禁",
  },
};

/**
 * BFBAN / BFEAC 状态徽章
 *
 * 复刻 xmbot ban.png 的"圆形 logo + 状态文字"设计，按命中与否分流：
 * - 命中（hit）：暗底 + 红色辉光，状态文字"实锤 / 已封禁"红色高亮，承担警示
 * - 未命中（clean）：不再显示"干净"文字，直接用绿色把品牌名 BFBAN / BFEAC 高亮
 * - 无信息（unknown）：品牌名与"无信息"文字均走弱化灰
 */
export function BanBadge({ source, state, size = "md" }: BanBadgeProps) {
  const meta = SOURCE_META[source];
  const isHit = state === "hit";

  const logoSize = size === "sm" ? 20 : 26;
  const heightClass = size === "sm" ? "h-7" : "h-9";

  // 品牌名配色：clean 态用绿色高亮（替代原"干净"文字），hit 态让位给红色状态词，unknown 态弱化灰
  const labelClass =
    state === "clean" ? "text-emerald-300" : state === "hit" ? "text-white/90" : "text-zinc-300";

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 pr-3 pl-1 font-bold tracking-wider backdrop-blur-md transition-all",
        heightClass,
        isHit ? "bg-black/70 [box-shadow:0_0_14px_rgba(239,68,68,0.55)]" : "bg-black/60",
      )}
      style={{
        clipPath: "polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%)",
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={meta.logoSrc}
        alt={meta.label}
        width={logoSize}
        height={logoSize}
        className="block rounded-full"
      />
      <span className="flex items-baseline gap-1.5 text-xs">
        <span className={cn("tracking-wider", labelClass)}>{meta.label}</span>
        {isHit && (
          <span className="font-black tracking-wider text-red-500 [text-shadow:0_0_8px_rgba(239,68,68,0.95)]">
            {meta.hitText}
          </span>
        )}
        {state === "unknown" && <span className="font-medium text-zinc-400">无信息</span>}
      </span>
    </div>
  );
}
