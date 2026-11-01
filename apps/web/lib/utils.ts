import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** 合并 Tailwind class，处理冲突 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** 秒数 → "1h 23m"（分钟数请用 server-detail/history 的 formatMinutes） */
export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

/**
 * 登录后跳转目标只接受站内路径，防止 `?next=https://evil.example` 这类开放重定向。
 * 先要求以单个 `/` 开头，再按 URL 规范解析一遍，挡住 `//host`、`/\host`、夹带制表符等浏览器会归一成外站的写法。
 */
export function safeNextPath(raw: string | null | undefined, fallback: string): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) {
    return fallback;
  }
  const base = "http://same-origin.invalid";
  try {
    const url = new URL(raw, base);
    if (url.origin !== base) return fallback;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return fallback;
  }
}
