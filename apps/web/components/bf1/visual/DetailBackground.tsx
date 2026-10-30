"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { QueryErrorState } from "@/components/common/ErrorState";
import { FALLBACK_GRADIENT } from "@/lib/bf1/background";
import { cn } from "@/lib/utils";

/**
 * 详情页全屏背景：挂载时整体淡入，盖住全站轮换背景；图片下载完再淡入，换图时新旧交叉淡化。
 * grayscale 用于被反作弊平台标记的玩家，整页褪色。
 */
export function DetailBackground({
  url,
  grayscale = false,
}: {
  url: string | null;
  grayscale?: boolean;
}) {
  const reduceMotion = useReducedMotion();
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!url) return;
    const img = new Image();
    img.onload = () => setLoadedUrl(url);
    img.src = url;
    return () => {
      img.onload = null;
    };
  }, [url]);

  const shownUrl = url ? loadedUrl : null;
  const fade = { duration: reduceMotion ? 0 : 0.8, ease: "easeInOut" } as const;

  return (
    <motion.div
      className={cn("pointer-events-none fixed inset-0 z-0", grayscale && "grayscale")}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={fade}
    >
      <div className="absolute inset-0" style={{ background: FALLBACK_GRADIENT }} />
      <AnimatePresence>
        {shownUrl ? (
          <motion.div
            key={shownUrl}
            className="absolute inset-0 scale-110 bg-cover bg-center bg-no-repeat blur-[2px]"
            style={{ backgroundImage: `url(${shownUrl})` }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={fade}
          />
        ) : null}
      </AnimatePresence>
      <div className="absolute inset-0 bg-black/55" />
      <div className="absolute inset-0 bg-gradient-to-b from-black/75 via-black/35 to-black/90" />
    </motion.div>
  );
}

/** 详情页的整页提示（无效 ID、加载失败等），沿用同一背景 */
export function DetailNote({ text }: { text: string }) {
  return (
    <div className="relative min-h-screen w-full overflow-hidden text-white">
      <DetailBackground url={null} />
      <div className="relative z-10 flex min-h-screen items-center justify-center px-4">
        <span className="text-sm text-white/60">{text}</span>
      </div>
    </div>
  );
}

/** 详情页主数据加载失败：按错误类别给文案，可重试的给重试按钮，本站内部错误附编号与反馈入口 */
export function DetailError({
  error,
  notFoundText,
  onRetry,
  retrying,
  children,
}: {
  error: unknown;
  notFoundText: string;
  onRetry: () => void;
  retrying: boolean;
  /** 主数据失败时仍能给出的内容，排在错误提示下方 */
  children?: React.ReactNode;
}) {
  return (
    <div className="relative min-h-screen w-full overflow-hidden text-white">
      <DetailBackground url={null} />
      <div className="relative z-10 flex min-h-screen flex-col items-center justify-center gap-6 px-4 py-8">
        <QueryErrorState
          error={error}
          notFoundText={notFoundText}
          onRetry={onRetry}
          retrying={retrying}
        />
        {children ? <div className="w-full max-w-3xl">{children}</div> : null}
      </div>
    </div>
  );
}
