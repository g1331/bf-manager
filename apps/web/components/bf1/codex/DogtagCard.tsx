import Link from "next/link";
import { type Dogtag, DOGTAG_SIDE_LABEL, dogtagImage } from "@/lib/bf1/codex/collection";
import { cn } from "@/lib/utils";
import { Highlight } from "./CodexArticle";

/** 狗牌卡片：圆形金属片放在方形展位里，悬停时微微放大、浮出金色角标 */
export function DogtagCard({
  tag,
  terms,
  compact,
}: {
  tag: Dogtag;
  terms?: string[];
  compact?: boolean;
}) {
  return (
    <Link
      href={`/bf1/codex/dogtags/${tag.id}`}
      prefetch={false}
      className="group compact-action block outline-none"
    >
      <div className="codex-frame relative">
        <div className="flex aspect-square items-center justify-center bg-[radial-gradient(circle_at_50%_40%,rgba(255,236,200,0.07),transparent_70%)]">
          {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
          <img
            src={dogtagImage(tag.id)}
            alt={tag.name}
            width={300}
            height={300}
            loading="lazy"
            decoding="async"
            className="size-[88%] rounded-full drop-shadow-[0_8px_12px_rgba(0,0,0,0.6)] transition-transform duration-300 ease-out group-hover:scale-[1.06] motion-reduce:transition-none"
          />
        </div>
      </div>
      <div className={cn("px-0.5 text-center", compact ? "pt-1.5" : "pt-2")}>
        <div
          className={cn(
            "line-clamp-2 leading-snug font-semibold text-white group-hover:text-amber-200",
            compact ? "text-xs" : "text-[13px] sm:text-sm",
          )}
        >
          <Highlight text={tag.name} terms={terms} />
        </div>
        {compact ? null : (
          <div className="mt-0.5 text-[11px] text-white/40">
            {tag.category} · {DOGTAG_SIDE_LABEL[tag.side]}
          </div>
        )}
      </div>
    </Link>
  );
}
