"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { ChevronLeft, ChevronRight, ExternalLink, X } from "lucide-react";
import {
  type CodexEntry,
  CODEX_IMAGE_HEIGHT,
  CODEX_IMAGE_WIDTH,
  codexImage,
  codexPlainText,
} from "@/lib/bf1/codex/codex";
import { CodexArticle } from "./CodexArticle";
import { CopyButton } from "./CopyButton";
import { ZoomableImage } from "./ZoomableImage";

/**
 * 百科阅读层：在列表上方铺满屏幕，左边大图可放大，右边正文可复制，← → 在当前筛选结果里翻页。
 * 桌面端图文左右并排、各自不超出一屏；手机端改为上图下文整页滚动，翻页和关闭按钮固定在上下两条栏里。
 */
export function CodexReader({
  list,
  index,
  texts,
  terms,
  onIndex,
  onClose,
}: {
  list: CodexEntry[];
  index: number;
  texts: Record<string, string> | undefined;
  terms: string[];
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const entry = list[index];
  const scroller = useRef<HTMLDivElement>(null);
  const textCol = useRef<HTMLDivElement>(null);
  const total = list.length;
  const go = (step: number) => onIndex((index + step + total) % total);

  useEffect(() => {
    scroller.current?.scrollTo({ top: 0 });
    textCol.current?.scrollTo({ top: 0 });
    // 预取前后两张大图，翻页时不用等
    for (const n of [list[index + 1], list[index - 1]]) {
      if (n) new Image().src = codexImage(n.code);
    }
  }, [list, index]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!entry) return null;
  const body = texts?.[entry.code];
  const link = () => `${window.location.origin}/bf1/codex/${entry.code}`;

  return (
    <DialogPrimitive.Root open onOpenChange={(open) => !open && onClose()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="data-[state=open]:animate-in data-[state=open]:fade-in-0 fixed inset-0 z-50 bg-[#0a0907] lg:bg-black/85 lg:backdrop-blur-md" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          onOpenAutoFocus={(e) => e.preventDefault()}
          className="data-[state=open]:animate-in data-[state=open]:fade-in-0 fixed inset-0 z-50 flex flex-col text-white outline-none"
        >
          <DialogPrimitive.Title className="sr-only">{entry.name}</DialogPrimitive.Title>

          {/* 手机顶栏：关闭、位置、独立页面 */}
          <div className="flex h-12 shrink-0 items-center border-b border-white/[0.07] px-1.5 lg:hidden">
            <DialogPrimitive.Close
              aria-label="关闭"
              className="flex size-11 items-center justify-center text-white/80"
            >
              <X className="size-5" />
            </DialogPrimitive.Close>
            <span className="flex-1 text-center text-sm text-white/55 tabular-nums">
              {index + 1} / {total}
            </span>
            <Link
              href={`/bf1/codex/${entry.code}`}
              aria-label="在独立页面打开"
              className="flex size-11 items-center justify-center text-white/70"
            >
              <ExternalLink className="size-[18px]" />
            </Link>
          </div>

          {/* 手机上整块滚动；桌面上图文并排各占一屏，点空白处关闭 */}
          <div
            ref={scroller}
            onPointerDown={(e) => {
              if (e.target === e.currentTarget) onClose();
            }}
            className="min-h-0 flex-1 overflow-y-auto overscroll-contain lg:grid lg:grid-cols-[auto_minmax(320px,440px)] lg:items-center lg:justify-center lg:gap-12 lg:overflow-hidden lg:px-20 lg:py-12"
          >
            <div
              key={entry.code}
              className="animate-in fade-in-0 flex flex-col items-center gap-2 px-6 pt-5 duration-200 lg:p-0"
            >
              <ZoomableImage
                src={codexImage(entry.code)}
                alt={entry.name}
                width={CODEX_IMAGE_WIDTH}
                height={CODEX_IMAGE_HEIGHT}
                priority
                className="codex-reader-image w-full max-w-[400px] rounded-[2px] shadow-[0_30px_60px_-24px_#000] ring-1 ring-white/15"
              />
              <p className="text-[11px] text-white/40">
                <span className="hidden lg:inline">点击放大 2 倍，移动鼠标看细节，滚轮微调</span>
                <span className="lg:hidden">点按放大，拖动看细节</span>
              </p>
            </div>

            <div
              key={`${entry.code}-text`}
              className="animate-in fade-in-0 flex min-h-0 flex-col px-5 pt-6 pb-8 duration-200 lg:max-h-[min(calc(100dvh-6rem),901px)] lg:p-0"
            >
              <div ref={textCol} className="min-h-0 flex-1 lg:overflow-y-auto lg:pr-3">
                <CodexArticle entry={entry} body={body} terms={terms} />
              </div>
              <div className="mt-6 flex flex-wrap gap-2 border-t border-white/10 pt-4">
                <CopyButton
                  kind="text"
                  label="复制正文"
                  text={() => codexPlainText(entry, body ?? "", link())}
                  className="flex-1"
                />
                <CopyButton kind="link" label="复制链接" text={link} className="flex-1" />
                <Link
                  href={`/bf1/codex/${entry.code}`}
                  className="hidden h-10 items-center gap-1.5 border border-white/20 px-3 text-sm text-white/70 transition-colors hover:border-white/45 hover:text-white lg:inline-flex"
                >
                  <ExternalLink className="size-4" />
                  独立页面
                </Link>
              </div>
            </div>
          </div>

          {/* 手机底栏：上一条 / 下一条 */}
          <div className="flex shrink-0 gap-px border-t border-white/10 pb-[env(safe-area-inset-bottom)] lg:hidden">
            <MobileStep
              entry={list[(index - 1 + total) % total]}
              dir="prev"
              onClick={() => go(-1)}
            />
            <MobileStep entry={list[(index + 1) % total]} dir="next" onClick={() => go(1)} />
          </div>

          {/* 桌面：关闭与左右翻页 */}
          <DialogPrimitive.Close
            aria-label="关闭"
            className="fixed top-5 right-5 hidden size-11 items-center justify-center border border-white/15 bg-black/50 text-white/80 transition-colors hover:border-white/40 hover:text-white lg:flex"
          >
            <X className="size-5" />
          </DialogPrimitive.Close>
          <NavButton side="left" onClick={() => go(-1)} />
          <NavButton side="right" onClick={() => go(1)} />
          <div className="fixed bottom-4 left-6 hidden items-center gap-3 text-xs text-white/45 lg:flex">
            <span className="text-sm text-white/70 tabular-nums">
              {index + 1} / {total}
            </span>
            <span>← → 翻页 · Esc 关闭</span>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function NavButton({ side, onClick }: { side: "left" | "right"; onClick: () => void }) {
  const Icon = side === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={side === "left" ? "上一条" : "下一条"}
      className={`fixed top-1/2 hidden size-12 -translate-y-1/2 items-center justify-center border border-white/15 bg-black/50 text-white/75 transition-colors hover:border-amber-400/60 hover:text-amber-300 lg:flex ${side === "left" ? "left-5" : "right-5"}`}
    >
      <Icon className="size-6" />
    </button>
  );
}

function MobileStep({
  entry,
  dir,
  onClick,
}: {
  entry: CodexEntry | undefined;
  dir: "prev" | "next";
  onClick: () => void;
}) {
  const next = dir === "next";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex h-14 min-w-0 flex-1 items-center gap-1.5 px-3 text-left active:bg-white/5 ${next ? "flex-row-reverse text-right" : ""}`}
    >
      {next ? (
        <ChevronRight className="size-5 shrink-0 text-white/60" />
      ) : (
        <ChevronLeft className="size-5 shrink-0 text-white/60" />
      )}
      <span className="min-w-0">
        <span className="block text-[11px] text-white/40">{next ? "下一条" : "上一条"}</span>
        <span className="block truncate text-sm text-white/85">{entry?.name}</span>
      </span>
    </button>
  );
}
