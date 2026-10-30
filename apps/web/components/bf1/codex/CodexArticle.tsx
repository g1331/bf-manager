import { Fragment } from "react";
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
 * 一条百科的正文排版，阅读层和独立详情页共用。
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
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs tracking-[0.12em] text-amber-400/90">
        <span>{codexKind(entry)}</span>
        {entry.expansion ? (
          <>
            <span className="text-white/25">/</span>
            <span>{expansionLabel(entry.expansion)}</span>
          </>
        ) : null}
        <span className="font-mono tracking-normal text-white/35 uppercase">{entry.code}</span>
      </div>
      <Heading className="mt-2 text-2xl leading-snug font-bold tracking-wide sm:text-[28px]">
        <Highlight text={entry.name} terms={terms} />
      </Heading>
      {entry.header !== entry.name ? (
        <p className="mt-1 text-[15px] text-white/70">
          <Highlight text={entry.header} terms={terms} />
        </p>
      ) : null}
      {entry.subHeader ? (
        <p className="mt-2 text-sm text-white/50 italic">{entry.subHeader}</p>
      ) : null}

      <div className="mt-5 border-l-2 border-amber-400/80 bg-amber-400/[0.06] py-2 pr-3 pl-3">
        <div className="text-[11px] tracking-[0.2em] text-amber-400/80">解锁条件</div>
        <div className="mt-0.5 text-sm text-amber-100/90">
          <Highlight text={entry.unlock} terms={terms} />
        </div>
      </div>

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
