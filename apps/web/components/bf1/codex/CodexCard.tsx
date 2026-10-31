"use client";

import { memo, useRef } from "react";
import Link from "next/link";
import {
  type CodexEntry,
  CODEX_IMAGE_HEIGHT,
  CODEX_IMAGE_WIDTH,
  codexImage,
  codexKind,
  codexSrcSet,
  expansionLabel,
} from "@/lib/bf1/codex/codex";
import { cn } from "@/lib/utils";
import { Highlight } from "./CodexArticle";

/** 只有精确指针（鼠标、触控板）且没开「减弱动效」时才做倾斜；触屏上倾斜会和滚动打架 */
function canTilt(): boolean {
  return (
    typeof window !== "undefined" &&
    matchMedia("(hover: hover) and (pointer: fine)").matches &&
    !matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * 百科卡片：照游戏里的样子，圆角卡面、名字压在图上、卡其色底边；悬停时随指针轻微倾斜、浮出金色角标和一道反光。
 * 本身是指向独立详情页的链接：普通点击由 onOpen 拦下打开阅读层，
 * 新标签页打开、复制链接、爬虫都走真实地址。
 */
export const CodexCard = memo(function CodexCard({
  entry,
  terms,
  snippet,
  sizes,
  onOpen,
}: {
  entry: CodexEntry;
  terms?: string[];
  snippet?: string;
  /** img sizes，按当前网格密度给，让浏览器挑 480 还是 640 宽 */
  sizes: string;
  onOpen?: (code: string) => void;
}) {
  const tilt = useRef<HTMLDivElement>(null);

  return (
    <Link
      href={`/bf1/codex/${entry.code}`}
      prefetch={false}
      className="group compact-action block outline-none"
      onClick={(e) => {
        if (!onOpen || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        onOpen(entry.code);
      }}
      onPointerMove={(e) => {
        const el = tilt.current;
        if (!el || e.pointerType !== "mouse" || !canTilt()) return;
        const r = el.getBoundingClientRect();
        const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
        const y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
        el.dataset.live = "true";
        el.style.setProperty("--rx", `${(0.5 - y) * 14}deg`);
        el.style.setProperty("--ry", `${(x - 0.5) * 18}deg`);
        el.style.setProperty("--gx", `${x * 100}%`);
        el.style.setProperty("--gy", `${y * 100}%`);
      }}
      onPointerLeave={() => {
        const el = tilt.current;
        if (!el) return;
        el.dataset.live = "false";
        el.style.setProperty("--rx", "0deg");
        el.style.setProperty("--ry", "0deg");
      }}
    >
      <div ref={tilt} className="codex-tilt">
        <div className="codex-frame relative">
          <div
            className="group-hover:ring-codex/70 group-focus-visible:ring-codex/70 @container relative overflow-hidden rounded-[6px] bg-white/[0.04] shadow-[0_14px_28px_-16px_rgba(0,0,0,0.9)] ring-1 ring-white/10 transition-shadow duration-200"
            style={{ aspectRatio: `${CODEX_IMAGE_WIDTH} / ${CODEX_IMAGE_HEIGHT}` }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp，已按宽度出两档 */}
            <img
              src={codexImage(entry.code, 480)}
              srcSet={codexSrcSet(entry.code)}
              sizes={sizes}
              alt={entry.name}
              width={CODEX_IMAGE_WIDTH}
              height={CODEX_IMAGE_HEIGHT}
              loading="lazy"
              decoding="async"
              draggable={false}
              className="block size-full object-cover"
            />
            {entry.expansion ? (
              <span className="text-codex-light absolute top-2 left-2 rounded-sm bg-black/65 px-1.5 py-px text-[10px] tracking-wider">
                {expansionLabel(entry.expansion)}
              </span>
            ) : null}
            <CodexPlate entry={entry} terms={terms} />
            <div
              aria-hidden
              className="codex-glare pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
            />
          </div>
        </div>
      </div>

      {entry.header !== entry.name || snippet ? (
        <div className="px-0.5 pt-2">
          {entry.header !== entry.name ? (
            <div className="truncate text-xs text-white/50">
              <Highlight text={entry.header} terms={terms} />
            </div>
          ) : null}
          {snippet ? (
            <p className={cn("mt-1 line-clamp-3 text-xs leading-relaxed text-white/55")}>
              <Highlight text={snippet} terms={terms} />
            </p>
          ) : null}
        </div>
      ) : null}
    </Link>
  );
});

/**
 * 游戏里百科卡的卡面：底部压暗，卡其色的分类和名字直接叠在图上，最下面一道卡其色底边。
 * 字号跟着卡片宽度走（容器查询），网格小卡和详情页大图共用；父元素需要 relative + @container。
 * 名字已经由图片 alt 读出，这层对读屏隐藏，免得读两遍。
 */
export function CodexPlate({
  entry,
  terms,
  className,
}: {
  entry: CodexEntry;
  terms?: string[];
  className?: string;
}) {
  return (
    <div
      aria-hidden
      className={cn("pointer-events-none absolute inset-0 flex flex-col justify-end", className)}
    >
      <div className="absolute inset-x-0 bottom-0 h-3/5 bg-gradient-to-t from-black/90 via-black/50 to-transparent" />
      <div className="relative px-[7%] pb-[6%] [text-shadow:0_1px_6px_rgb(0_0_0/0.6)]">
        <div className="text-codex/90 truncate text-[10px] leading-tight tracking-wider @[12rem]:text-xs @[18rem]:text-sm @[24rem]:text-base">
          {codexKind(entry)}
        </div>
        <div className="text-codex group-hover:text-codex-light group-focus-visible:text-codex-light mt-0.5 line-clamp-2 text-[13px] leading-snug font-medium transition-colors @[9rem]:text-[15px] @[12rem]:text-lg @[18rem]:text-2xl @[18rem]:leading-tight @[24rem]:text-[28px]">
          <Highlight text={entry.name} terms={terms} />
        </div>
      </div>
      <div className="bg-codex relative h-[3px] @[18rem]:h-1.5" />
    </div>
  );
}
