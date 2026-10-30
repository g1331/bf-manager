"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Copy, Link2, X } from "lucide-react";
import { cn } from "@/lib/utils";

/** 写剪贴板；非安全上下文（http 内网访问）没有 clipboard API 时退回 execCommand */
async function writeClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:0;left:0;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {}
    ta.remove();
    return ok;
  }
}

/**
 * 复制按钮：结果直接写在按钮上（「已复制」/「复制失败」），1.6 秒后复原，不弹 toast。
 * text 可以是函数，点击时再取值（链接要用当前页面的 origin）。
 */
export function CopyButton({
  text,
  kind,
  label,
  className,
}: {
  text: string | (() => string);
  kind: "text" | "link";
  label: string;
  className?: string;
}) {
  const [state, setState] = useState<"idle" | "ok" | "fail">("idle");
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  const Icon = state === "ok" ? Check : state === "fail" ? X : kind === "link" ? Link2 : Copy;
  return (
    <button
      type="button"
      onClick={async () => {
        const ok = await writeClipboard(typeof text === "function" ? text() : text);
        setState(ok ? "ok" : "fail");
        clearTimeout(timer.current);
        timer.current = setTimeout(() => setState("idle"), 1600);
      }}
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 border px-4 text-sm transition-colors",
        state === "ok"
          ? "border-emerald-400/60 text-emerald-300"
          : state === "fail"
            ? "border-red-400/60 text-red-300"
            : "border-white/20 text-white/80 hover:border-amber-400/70 hover:text-amber-300",
        className,
      )}
    >
      <Icon className="size-4" />
      <span aria-live="polite">
        {state === "ok" ? "已复制" : state === "fail" ? "复制失败" : label}
      </span>
    </button>
  );
}
