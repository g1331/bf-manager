import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CodexBack } from "@/components/bf1/codex/CodexActions";
import { CodexFootnote } from "@/components/bf1/codex/CodexHeader";
import { Breadcrumbs, DetailPanel, StepNav } from "@/components/bf1/codex/DetailParts";
import { DogtagCard } from "@/components/bf1/codex/DogtagCard";
import { DogtagShare, DogtagStudio } from "@/components/bf1/codex/DogtagStudio";
import { expansionLabel } from "@/lib/bf1/codex/codex";
import {
  DOGTAG_SIDE_LABEL,
  dogtagImage,
  dogtagNeighbors,
  DOGTAGS,
  getDogtag,
  medalImage,
  medalOfDogtag,
} from "@/lib/bf1/codex/collection";

export const dynamicParams = false;

export function generateStaticParams() {
  return DOGTAGS.map((t) => ({ id: t.id }));
}

interface Props {
  params: Promise<{ game: string; id: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const tag = getDogtag((await params).id);
  if (!tag) return {};
  const description = `${tag.category} · ${DOGTAG_SIDE_LABEL[tag.side]}。${tag.description}`;
  return {
    metadataBase: new URL("https://bfm.umrbotech.com"),
    title: `${tag.name} · 战地 1 狗牌`,
    description,
    openGraph: { title: tag.name, description, images: [{ url: dogtagImage(tag.id) }] },
  };
}

export default async function DogtagPage({ params }: Props) {
  const tag = getDogtag((await params).id);
  if (!tag) notFound();
  const { prev, next } = dogtagNeighbors(tag);
  const medal = medalOfDogtag(tag.id);
  const story = tag.category === "进度";
  const siblings = story
    ? []
    : DOGTAGS.filter(
        (t) => t.category === tag.category && t.side === tag.side && t.id !== tag.id,
      ).slice(0, 12);
  const chapters = story
    ? DOGTAGS.filter((t) => t.category === "进度").sort((a, b) => a.index - b.index)
    : [];
  const step = (t: typeof prev) =>
    t && {
      href: `/bf1/codex/dogtags/${t.id}`,
      name: t.name,
      image: dogtagImage(t.id),
      shape: "round" as const,
    };

  return (
    <main className="mx-auto max-w-6xl px-4 py-4 text-white sm:py-8">
      <CodexBack fallback="/bf1/codex/dogtags" />
      <Breadcrumbs
        items={[
          { label: "图鉴", href: "/bf1/codex" },
          { label: "狗牌", href: "/bf1/codex/dogtags" },
          {
            label: tag.category,
            href: `/bf1/codex/dogtags?cat=${encodeURIComponent(tag.category)}`,
          },
        ]}
      />

      <div className="mt-5 grid items-start gap-7 lg:mt-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-10">
        <div className="lg:sticky lg:top-6">
          <DogtagStudio tag={tag} />
        </div>

        <DetailPanel>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs tracking-[0.12em] text-amber-400/90">
            <span>{tag.category}</span>
            <span className="text-white/25">/</span>
            <span>{DOGTAG_SIDE_LABEL[tag.side]}</span>
            {tag.expansion ? (
              <>
                <span className="text-white/25">/</span>
                <span>{expansionLabel(tag.expansion)}</span>
              </>
            ) : null}
            <span className="font-mono tracking-normal text-white/35">{tag.id}</span>
          </div>
          <h1 className="mt-2 text-2xl leading-snug font-bold tracking-wide sm:text-[28px]">
            {tag.name}
          </h1>
          <p className="mt-4 text-[15px] leading-[1.9] text-white/80">{tag.description}</p>

          {story ? (
            <p className="mt-4 border-l-2 border-amber-400/70 bg-amber-400/[0.06] py-2 pr-3 pl-3 text-sm text-amber-100/85">
              「进度」类的 {chapters.length} 枚狗牌描述连起来是一段短篇故事，这是第{" "}
              {chapters.findIndex((t) => t.id === tag.id) + 1} 段，全文在页面下方。
            </p>
          ) : null}

          {medal ? (
            <Link
              href={`/bf1/codex/medals/${medal.code}`}
              className="group mt-6 flex items-center gap-3 border border-white/[0.08] bg-white/[0.03] p-3 transition-colors hover:border-amber-400/50"
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
              <img
                src={medalImage(medal.code)}
                alt=""
                className="size-14 shrink-0 object-contain"
              />
              <span className="min-w-0">
                <span className="block text-[11px] text-white/40">取得这枚勋章时奖励</span>
                <span className="block text-sm font-medium text-white/90 group-hover:text-amber-200">
                  {medal.name}
                </span>
              </span>
            </Link>
          ) : null}

          <div className="mt-7 border-t border-white/10 pt-4">
            <DogtagShare tag={tag} />
          </div>
        </DetailPanel>
      </div>

      <StepNav prev={step(prev)} next={step(next)} />

      {chapters.length ? (
        <section className="mt-12">
          <h2 className="text-base font-semibold tracking-wide">
            整段故事
            <span className="ml-2 text-xs font-normal tracking-wider text-amber-400/75">
              进度 · {chapters.length} 枚
            </span>
          </h2>
          <ol className="mt-4 max-w-3xl border-l border-white/10 bg-black/30">
            {chapters.map((t, i) => {
              const current = t.id === tag.id;
              const body = (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
                  <img
                    src={dogtagImage(t.id)}
                    alt=""
                    loading="lazy"
                    className="size-11 shrink-0 rounded-full sm:size-12"
                  />
                  <span className="min-w-0">
                    <span className="flex items-baseline gap-2 text-sm font-semibold">
                      <span className="font-mono text-xs text-white/35 tabular-nums">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span
                        className={
                          current ? "text-amber-300" : "text-white/90 group-hover:text-amber-200"
                        }
                      >
                        {t.name}
                      </span>
                      <span className="text-[11px] font-normal text-white/35">
                        {DOGTAG_SIDE_LABEL[t.side]}
                      </span>
                    </span>
                    <span className="mt-1 block text-sm leading-relaxed text-white/65">
                      {t.description}
                    </span>
                  </span>
                </>
              );
              return (
                <li key={t.id} className="relative -ml-px">
                  {current ? (
                    <div
                      aria-current="true"
                      className="flex gap-3 border-l-2 border-amber-400 bg-amber-400/[0.06] py-3 pr-3 pl-4"
                    >
                      {body}
                    </div>
                  ) : (
                    <Link
                      href={`/bf1/codex/dogtags/${t.id}`}
                      prefetch={false}
                      className="group flex gap-3 border-l-2 border-transparent py-3 pr-3 pl-4 transition-colors hover:border-white/30 hover:bg-white/[0.03]"
                    >
                      {body}
                    </Link>
                  )}
                </li>
              );
            })}
          </ol>
        </section>
      ) : null}

      {siblings.length ? (
        <section className="mt-12">
          <h2 className="text-base font-semibold tracking-wide">
            同类狗牌
            <span className="ml-2 text-xs font-normal tracking-wider text-amber-400/75">
              {tag.category} · {DOGTAG_SIDE_LABEL[tag.side]}
            </span>
          </h2>
          <div className="mt-4 grid grid-cols-4 gap-x-2 gap-y-4 sm:grid-cols-6 lg:grid-cols-12">
            {siblings.map((t) => (
              <DogtagCard key={t.id} tag={t} compact />
            ))}
          </div>
        </section>
      ) : null}

      <CodexFootnote />
    </main>
  );
}
