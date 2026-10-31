import { Fragment } from "react";
import { SquareCheck } from "lucide-react";
import { type CodexEntry, codexKind, expansionLabel } from "@/lib/bf1/codex/codex";
import { splitByTerms } from "@/lib/bf1/codex/search";
import { cn } from "@/lib/utils";

/** 把搜索词标成琥珀底；没有搜索词时原样输出 */
export function Highlight({ text, terms }: { text: string; terms?: string[] }) {
  if (!terms?.length) return <>{text}</>;
  return (
    <>
      {splitByTerms(text, terms).map((part, i) =>
        i % 2 ? (
          <mark key={i} className="bg-amber-400/25 px-px text-amber-200">
            {part}
          </mark>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

/**
 * 一条百科的正文排版，阅读层和独立详情页共用。版式照游戏里的百科：
 * 小字分类、细体大标题、打勾的卡其色解锁条件，再接正文。
 * body 为 undefined 表示正文还在加载（列表页按需拉取），显示几行占位。
 */
export function CodexArticle({
  entry,
  body,
  terms,
  as: Heading = "h2",
  className,
}: {
  entry: CodexEntry;
  body: string | undefined;
  terms?: string[];
  as?: "h1" | "h2";
  className?: string;
}) {
  return (
    <article className={cn("text-white", className)}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs tracking-[0.18em] text-white/55">
        <span>{codexKind(entry)}</span>
        {entry.expansion ? (
          <>
            <span className="text-white/25">/</span>
            <span>{expansionLabel(entry.expansion)}</span>
          </>
        ) : null}
        <span className="font-mono tracking-normal text-white/30 uppercase">{entry.code}</span>
      </div>
      <Heading className="mt-2 text-[26px] leading-snug font-normal tracking-wide sm:text-[32px]">
        <Highlight text={entry.name} terms={terms} />
      </Heading>
      {entry.header !== entry.name ? (
        <p className="mt-1 text-[15px] text-white/65">
          <Highlight text={entry.header} terms={terms} />
        </p>
      ) : null}
      {entry.subHeader ? (
        <p className="mt-2 text-sm text-white/45 italic">{entry.subHeader}</p>
      ) : null}

      <p className="text-codex-light mt-4 flex items-start gap-2 text-sm leading-relaxed">
        <SquareCheck className="mt-[3px] size-4 shrink-0" aria-hidden />
        <span title="解锁条件">
          <span className="sr-only">解锁条件：</span>
          <Highlight text={entry.unlock} terms={terms} />
        </span>
      </p>

      <div className="mt-5 space-y-3 text-[15px] leading-[1.9] text-white/80">
        {body == null ? (
          <div className="space-y-2.5 pt-1" aria-label="正文加载中">
            {[100, 96, 100, 88, 60].map((w, i) => (
              <div
                key={i}
                className="h-3.5 animate-pulse bg-white/[0.07]"
                style={{ width: `${w}%` }}
              />
            ))}
          </div>
        ) : (
          body
            .split(/\n+/)
            .filter(Boolean)
            .map((p, i) => (
              <p key={i}>
                <Highlight text={p} terms={terms} />
              </p>
            ))
        )}
      </div>
    </article>
  );
}
