import { cn } from "@/lib/utils";

/**
 * 国旗图标（基于 flag-icons）。
 *
 * 取代 emoji 国旗——Windows 的 Chromium 不渲染彩色 emoji 国旗，只会退化成两个字母。
 * code 接受大写或小写 ISO 3166-1 alpha-2 国家码；为空或非两位时返回 null（不渲染、不占位）。
 * 用方形版（fis，1:1）让小图标在副信息行里紧凑，微圆角呼应全站近直角的视觉基调。
 */
export function CountryFlag({ code, className }: { code: string | null; className?: string }) {
  if (!code || code.length !== 2) return null;
  const cc = code.toLowerCase();
  return (
    <span
      className={cn("fi fis shrink-0 rounded-[1px]", `fi-${cc}`, className)}
      style={{ fontSize: "0.875rem" }}
      role="img"
      aria-label={code.toUpperCase()}
    />
  );
}
