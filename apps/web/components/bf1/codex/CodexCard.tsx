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
 * 百科卡片：平面卡面 + 发丝线边框，悬停时随指针轻微倾斜、浮出金色角标和一道反光。
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
            className="relative overflow-hidden rounded-[2px] bg-white/[0.04] shadow-[0_14px_28px_-16px_rgba(0,0,0,0.9)] ring-1 ring-white/12 transition-shadow duration-200 group-hover:ring-amber-400/60 group-focus-visible:ring-amber-400/60"
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
              <span className="absolute top-2 left-2 border border-amber-400/35 bg-black/70 px-1.5 py-px text-[10px] tracking-wider text-amber-200/90">
                {expansionLabel(entry.expansion)}
              </span>
            ) : null}
            <div
              aria-hidden
              className="codex-glare pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
            />
          </div>
        </div>
      </div>

      <div className="px-0.5 pt-2.5">
        <div className="flex items-center gap-2 text-[11px] tracking-wider text-amber-400/75">
          <span className="truncate">{codexKind(entry)}</span>
          <span className="ml-auto font-mono tracking-normal text-white/30 uppercase">
            {entry.code}
          </span>
        </div>
        <div className="mt-0.5 text-[15px] leading-snug font-semibold text-white transition-colors group-hover:text-amber-200 group-focus-visible:text-amber-200">
          <Highlight text={entry.name} terms={terms} />
        </div>
        {entry.header !== entry.name ? (
          <div className="mt-0.5 truncate text-xs text-white/50">
            <Highlight text={entry.header} terms={terms} />
          </div>
        ) : null}
        {snippet ? (
          <p className={cn("mt-1.5 line-clamp-3 text-xs leading-relaxed text-white/55")}>
            <Highlight text={snippet} terms={terms} />
          </p>
        ) : null}
      </div>
    </Link>
  );
});
