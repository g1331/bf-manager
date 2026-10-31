import Link from "next/link";
import { expansionLabel } from "@/lib/bf1/codex/codex";
import { type Medal, medalImage } from "@/lib/bf1/codex/collection";

/** 勋章卡片：透明底的勋章图立在一块微亮的展台上，悬停浮出金色角标 */
export function MedalCard({ medal, size = "md" }: { medal: Medal; size?: "sm" | "md" }) {
  return (
    <Link
      href={`/bf1/codex/medals/${medal.code}`}
      prefetch={false}
      className="group compact-action block outline-none"
    >
      <div className="codex-frame relative">
        <div className="relative flex aspect-square items-center justify-center overflow-hidden bg-[radial-gradient(circle_at_50%_38%,rgba(255,236,200,0.09),rgba(0,0,0,0.35)_70%)] ring-1 ring-white/10 transition-shadow duration-200 group-hover:ring-amber-400/50 group-focus-visible:ring-amber-400/50">
          {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
          <img
            src={medalImage(medal.code)}
            alt={medal.name}
            width={256}
            height={256}
            loading="lazy"
            decoding="async"
            className="size-[86%] object-contain drop-shadow-[0_10px_14px_rgba(0,0,0,0.6)] transition-transform duration-300 ease-out group-hover:-translate-y-1 group-hover:scale-[1.04] motion-reduce:transition-none"
          />
          {medal.expansion ? (
            <span className="absolute top-2 left-2 border border-amber-400/35 bg-black/70 px-1.5 py-px text-[10px] tracking-wider text-amber-200/90">
              {expansionLabel(medal.expansion)}
            </span>
          ) : null}
        </div>
      </div>
      <div className="px-0.5 pt-2.5">
        <div
          className={
            size === "sm"
              ? "text-[13px] leading-snug font-semibold text-white group-hover:text-amber-200"
              : "text-[15px] leading-snug font-semibold text-white group-hover:text-amber-200"
          }
        >
          {medal.name}
        </div>
        <div className="mt-0.5 text-xs text-white/45">
          {medal.stages.length} 个阶段
          {medal.dogtags.length ? ` · 奖励 ${medal.dogtags.length} 枚狗牌` : ""}
        </div>
      </div>
    </Link>
  );
}
