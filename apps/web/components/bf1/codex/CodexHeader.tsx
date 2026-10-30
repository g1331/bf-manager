import Link from "next/link";
import { cn } from "@/lib/utils";

/** 图鉴的分区。新分区上线时在这里登记，只有一个分区时不显示分区导航 */
const SECTIONS = [{ key: "entries", label: "百科", href: "/bf1/codex" }] as const;

export type CodexSection = (typeof SECTIONS)[number]["key"];

/** 图鉴各分区列表页的页头：标题、一句说明、分区导航 */
export function CodexHeader({ active, intro }: { active: CodexSection; intro: string }) {
  return (
    <header>
      <div className="font-display flex items-center gap-2 text-xs font-medium tracking-[0.2em] text-amber-500 uppercase">
        <span className="h-[2px] w-6 bg-amber-500" />
        Codex
      </div>
      <h1 className="mt-1.5 text-2xl font-bold tracking-wide sm:text-3xl">图鉴</h1>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/55">{intro}</p>
      {SECTIONS.length > 1 ? (
        <nav className="mt-4 flex gap-1 border-b border-white/10">
          {SECTIONS.map((s) => (
            <Link
              key={s.key}
              href={s.href}
              aria-current={s.key === active ? "page" : undefined}
              className={cn(
                "relative px-3 py-2.5 text-[15px] font-semibold tracking-[0.08em] transition-colors",
                s.key === active ? "text-white" : "text-white/45 hover:text-white/80",
              )}
            >
              {s.label}
              {s.key === active ? (
                <span className="absolute inset-x-3 -bottom-px h-0.5 bg-amber-400" />
              ) : null}
            </Link>
          ))}
        </nav>
      ) : null}
    </header>
  );
}

/** 图鉴页底的版权说明 */
export function CodexFootnote() {
  return (
    <p className="mt-16 border-t border-white/[0.07] pt-4 text-xs leading-relaxed text-white/35">
      游戏文字与图片版权归 Electronic Arts 与 DICE 所有，取自战地 1 官方配套服务（Companion），
      本站仅作非商业的纪念与查阅用途。
    </p>
  );
}
