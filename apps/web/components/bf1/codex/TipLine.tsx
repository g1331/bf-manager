"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useReducedMotion } from "framer-motion";
import { ChevronRight, RefreshCw } from "lucide-react";
import type { Tip } from "@/lib/bf1/codex/battlefield";
import { markSeen, pickTip, readSeen, type TipContext, tipPool } from "@/lib/bf1/codex/tips";
import { cn } from "@/lib/utils";

/** 贴士数据单独成块，第一次渲染 TipLine 时才拉，之后整站共用这一份 */
let tipsPromise: Promise<Tip[]> | null = null;
function loadTips(): Promise<Tip[]> {
  tipsPromise ??= import("@/lib/bf1/codex/data/tips.json").then((m) => m.default as Tip[]);
  return tipsPromise;
}

const ROTATE_MS = 15_000;

/**
 * 游戏载入画面那样的一行小贴士：按地图、模式挑内容，每次进来都不一样。
 * rotate 打开后每 15 秒换一条（页面在后台或开启「减少动态效果」时不换）。
 * 随机内容只在客户端抽，服务端渲染一行占位，避免水合不一致。
 */
export function TipLine({
  context = {},
  rotate = false,
  variant = "bar",
  className,
}: {
  context?: TipContext;
  rotate?: boolean;
  /** bar：带底色的独立一行；bare：没有边框底色，放在骨架屏、空状态里 */
  variant?: "bar" | "bare";
  className?: string;
}) {
  const { map, mode } = context;
  const [pool, setPool] = useState<Tip[]>([]);
  const [tip, setTip] = useState<Tip>();
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    let alive = true;
    loadTips().then((tips) => {
      if (!alive) return;
      const p = tipPool(tips, { map, mode });
      const t = pickTip(p, readSeen());
      setPool(p);
      setTip(t);
      if (t) markSeen(t.text);
    });
    return () => {
      alive = false;
    };
  }, [map, mode]);

  const next = useCallback(() => {
    setTip((cur) => {
      const t = pickTip(pool, readSeen(), cur?.text);
      if (t) markSeen(t.text);
      return t;
    });
  }, [pool]);

  useEffect(() => {
    if (!rotate || reduceMotion || pool.length < 2) return;
    const id = setInterval(() => {
      if (!document.hidden) next();
    }, ROTATE_MS);
    return () => clearInterval(id);
  }, [rotate, reduceMotion, pool.length, next]);

  // 抽到的是这张图的专属贴士时，「全部」直接跳到这张图的筛选
  const scoped = !!map && pool.some((t) => t.tags.includes(map));
  const href = scoped ? `/bf1/codex/tips?tag=${map}` : "/bf1/codex/tips";

  return (
    // 手机上分两行：标签和按钮一行，正文占满整宽；宽屏回到一行
    <div
      className={cn(
        "grid grid-cols-[1fr_auto] items-center gap-x-3 sm:flex",
        variant === "bar" &&
          "border border-white/[0.07] bg-black/45 pr-1.5 pl-3 backdrop-blur-sm sm:py-1.5 sm:pl-4",
        className,
      )}
    >
      <span className="font-display row-start-1 shrink-0 text-[11px] font-semibold tracking-[0.2em] text-amber-400/90">
        贴士
      </span>
      <p
        key={tip?.text}
        aria-live={rotate ? "off" : "polite"}
        className="motion-safe:animate-in motion-safe:fade-in col-span-2 row-start-2 min-w-0 flex-1 pr-1.5 pb-3 text-[13px] leading-relaxed text-white/75 duration-500 sm:py-1 sm:pr-0 sm:text-sm"
      >
        {tip?.text ?? " "}
      </p>
      <div className="row-start-1 flex shrink-0 items-center justify-self-end">
        <button
          type="button"
          onClick={next}
          disabled={pool.length < 2}
          aria-label="换一条贴士"
          title="换一条"
          className="compact-action flex size-11 items-center justify-center text-white/45 transition-colors hover:text-amber-300 disabled:opacity-0 sm:size-8"
        >
          <RefreshCw className="size-3.5" />
        </button>
        <Link
          href={href}
          prefetch={false}
          aria-label="查看全部小贴士"
          className="compact-action flex size-11 items-center justify-center gap-0.5 text-xs whitespace-nowrap text-white/45 transition-colors hover:text-amber-300 sm:h-8 sm:w-auto sm:pr-1.5 sm:pl-1"
        >
          <span className="hidden sm:inline">全部</span>
          <ChevronRight className="size-3.5" />
        </Link>
      </div>
    </div>
  );
}
