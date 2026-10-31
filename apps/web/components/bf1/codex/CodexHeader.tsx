import Link from "next/link";
import { CODEX_ENTRIES } from "@/lib/bf1/codex/codex";
import { MAPS } from "@/lib/bf1/codex/battlefield";
import { ASSIGNMENTS, DOGTAGS, MEDALS, RIBBONS } from "@/lib/bf1/codex/collection";
import { cn } from "@/lib/utils";

/** 图鉴的分区。新分区上线时在这里登记（服务端组件，计数直接取数据，不进客户端包） */
const SECTIONS = [
  { key: "entries", label: "百科", count: CODEX_ENTRIES.length, href: "/bf1/codex" },
  // 战场的计数取多人地图数
  { key: "battlefield", label: "战场", count: MAPS.length, href: "/bf1/codex/battlefield" },
  { key: "medals", label: "勋章", count: MEDALS.length, href: "/bf1/codex/medals" },
  { key: "ribbons", label: "勋带", count: RIBBONS.length, href: "/bf1/codex/ribbons" },
  { key: "assignments", label: "勤务", count: ASSIGNMENTS.length, href: "/bf1/codex/assignments" },
  { key: "dogtags", label: "狗牌", count: DOGTAGS.length, href: "/bf1/codex/dogtags" },
] as const;

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
      <nav
        aria-label="图鉴分区"
        className="-mx-4 mt-4 flex [scrollbar-width:none] gap-1 overflow-x-auto border-b border-white/10 px-4 sm:mx-0 sm:px-0 [&::-webkit-scrollbar]:hidden"
      >
        {SECTIONS.map((s) => (
          <Link
            key={s.key}
            href={s.href}
            aria-current={s.key === active ? "page" : undefined}
            className={cn(
              "relative flex shrink-0 items-baseline gap-1.5 px-3 py-2.5 text-[15px] font-semibold tracking-[0.08em] transition-colors",
              s.key === active ? "text-white" : "text-white/45 hover:text-white/80",
            )}
          >
            {s.label}
            <span
              className={cn(
                "text-[11px] font-medium tracking-normal tabular-nums",
                s.key === active ? "text-amber-400" : "text-white/30",
              )}
            >
              {s.count}
            </span>
            {s.key === active ? (
              <span className="absolute inset-x-3 -bottom-px h-0.5 bg-amber-400" />
            ) : null}
          </Link>
        ))}
      </nav>
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
