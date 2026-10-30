"use client";

import { useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { DarkInput } from "@/components/common/DarkInput";
import { cn } from "@/lib/utils";

/**
 * 图鉴列表页的吸顶搜索栏。停在原位时透明、和页头融为一体；吸顶后才铺底色，
 * 并在右侧提示当前筛选和条数，滚到下面也知道自己在看哪一类。按「/」聚焦。
 */
export function StickySearch({
  value,
  onChange,
  onFocus,
  placeholder,
  label,
  summary,
  shortcut = true,
}: {
  value: string;
  onChange: (v: string) => void;
  onFocus?: () => void;
  placeholder: string;
  label: string;
  summary: string;
  /** 页面上有弹层时关掉「/」快捷键 */
  shortcut?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState(false);

  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    // 手机端顶栏 48px；桌面端滚动容器在顶栏下方，哨兵被容器裁掉同样算离开
    const io = new IntersectionObserver(([e]) => setStuck(!e.isIntersecting), {
      rootMargin: "-48px 0px 0px 0px",
    });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!shortcut) return;
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (e.key !== "/" || el.closest("input, textarea, [contenteditable]")) return;
      e.preventDefault();
      input.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shortcut]);

  return (
    <>
      <div ref={sentinel} aria-hidden className="h-px" />
      <div
        className={cn(
          "sticky top-12 z-20 -mx-4 flex items-center gap-4 border-b px-4 py-2.5 transition-[background-color,border-color] duration-200 sm:-mx-10 sm:px-10 lg:top-0",
          stuck
            ? "border-white/[0.07] bg-black/80 backdrop-blur-md"
            : "border-transparent bg-transparent",
        )}
      >
        <div className="relative w-full max-w-2xl">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-white/40" />
          <DarkInput
            ref={input}
            type="search"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={onFocus}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                onChange("");
                e.currentTarget.blur();
              }
            }}
            placeholder={placeholder}
            aria-label={label}
            enterKeyHint="search"
            className="h-11 pr-16 pl-9 [&::-webkit-search-cancel-button]:hidden"
          />
          {value ? (
            <button
              type="button"
              aria-label="清空搜索"
              onClick={() => {
                onChange("");
                input.current?.focus();
              }}
              className="compact-action absolute top-1/2 right-2 flex size-8 -translate-y-1/2 items-center justify-center text-white/50 hover:text-white"
            >
              <X className="size-4" />
            </button>
          ) : (
            <kbd className="pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 border border-white/15 px-1.5 font-mono text-[11px] text-white/40 [@media(hover:hover)]:block">
              /
            </kbd>
          )}
        </div>
        {stuck ? (
          <span className="hidden shrink-0 text-xs text-white/45 tabular-nums sm:block">
            {summary}
          </span>
        ) : null}
      </div>
    </>
  );
}

export function ChipRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-10 shrink-0 text-xs text-white/40">{label}</span>
      <div className="-mr-4 flex min-w-0 flex-1 [scrollbar-width:none] gap-1.5 overflow-x-auto pr-4 sm:mr-0 sm:flex-wrap sm:pr-0 [&::-webkit-scrollbar]:hidden">
        {children}
      </div>
    </div>
  );
}

export function Chip({
  label,
  n,
  active,
  onClick,
}: {
  label: string;
  n: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      disabled={!active && n === 0}
      onClick={onClick}
      className={cn(
        "compact-action flex h-9 shrink-0 items-center gap-1.5 border px-3 text-[13px] whitespace-nowrap transition-colors sm:h-8 sm:px-2.5 sm:text-xs",
        active
          ? "border-white bg-white font-semibold text-black"
          : "border-white/20 text-white/65 hover:border-white/45 hover:text-white disabled:cursor-default disabled:border-white/10 disabled:text-white/25",
      )}
    >
      {label}
      <span className={cn("tabular-nums", active ? "text-black/50" : "text-white/35")}>{n}</span>
    </button>
  );
}

export function Segmented({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (v: string) => void;
}) {
  return (
    <div role="group" aria-label={label} className="flex border border-white/15">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "compact-action h-8 px-2.5 text-xs transition-colors",
            value === o.value ? "bg-white/12 text-white" : "text-white/50 hover:text-white/85",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
