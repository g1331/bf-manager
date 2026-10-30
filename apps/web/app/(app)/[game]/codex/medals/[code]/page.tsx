import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CodexBack, ShareActions } from "@/components/bf1/codex/CodexActions";
import { CodexFootnote } from "@/components/bf1/codex/CodexHeader";
import { Breadcrumbs, DetailPanel, StepNav } from "@/components/bf1/codex/DetailParts";
import { MedalCard } from "@/components/bf1/codex/MedalCard";
import { ObjectViewer } from "@/components/bf1/codex/viewer/ObjectViewer";
import { expansionLabel } from "@/lib/bf1/codex/codex";
import {
  dogtagImage,
  getDogtag,
  getMedal,
  MEDALS,
  medalImage,
  medalNeighbors,
  medalPlainText,
} from "@/lib/bf1/codex/collection";

export const dynamicParams = false;

export function generateStaticParams() {
  return MEDALS.map((m) => ({ code: m.code }));
}

interface Props {
  params: Promise<{ game: string; code: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const medal = getMedal((await params).code);
  if (!medal) return {};
  const description = `${medal.category}勋章。${medal.description} 阶段任务：${medal.stages.map((s) => s.name).join("；")}`;
  return {
    metadataBase: new URL("https://bfm.umrbotech.com"),
    title: `${medal.name} · 战地 1 勋章`,
    description,
    openGraph: { title: medal.name, description, images: [{ url: medalImage(medal.code) }] },
  };
}

export default async function MedalPage({ params }: Props) {
  const medal = getMedal((await params).code);
  if (!medal) notFound();
  const { prev, next } = medalNeighbors(medal.code);
  const dogtags = medal.dogtags.map((id) => getDogtag(id)!).filter(Boolean);
  const siblings = MEDALS.filter((m) => m.category === medal.category && m.code !== medal.code);
  const path = `/bf1/codex/medals/${medal.code}`;

  return (
    <main className="mx-auto max-w-6xl px-4 py-4 text-white sm:py-8">
      <CodexBack fallback="/bf1/codex/medals" />
      <Breadcrumbs
        items={[
          { label: "图鉴", href: "/bf1/codex" },
          { label: "勋章", href: "/bf1/codex/medals" },
          { label: `${medal.category}勋章`, href: `/bf1/codex/medals#medals-${medal.category}` },
        ]}
      />

      <div className="mt-5 grid items-start gap-7 lg:mt-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-10">
        <div className="lg:sticky lg:top-6">
          <ObjectViewer
            subject={{ kind: "medal", image: medalImage(medal.code) }}
            sideLabels={{ front: "正面", back: "背面" }}
            className="aspect-square max-h-[min(70vh,560px)] w-full border border-white/[0.06] bg-black/35"
            fallback={
              // eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp
              <img
                src={medalImage(medal.code)}
                alt={medal.name}
                className="size-3/4 object-contain"
              />
            }
          />
        </div>

        <DetailPanel>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs tracking-[0.12em] text-amber-400/90">
            <span>{medal.category}勋章</span>
            {medal.expansion ? (
              <>
                <span className="text-white/25">/</span>
                <span>{expansionLabel(medal.expansion)}</span>
              </>
            ) : null}
            <span className="font-mono tracking-normal text-white/35 uppercase">{medal.code}</span>
          </div>
          <h1 className="mt-2 text-2xl leading-snug font-bold tracking-wide sm:text-[28px]">
            {medal.name}
          </h1>
          <p className="mt-2 text-[15px] leading-relaxed text-white/75">{medal.description}</p>

          <h2 className="mt-7 text-[11px] tracking-[0.2em] text-amber-400/80">阶段任务</h2>
          <ol className="mt-3 space-y-2">
            {medal.stages.map((s, i) => (
              <li
                key={i}
                className="flex items-start gap-3 border border-white/[0.07] bg-white/[0.03] px-3 py-2.5"
              >
                <span className="font-display flex size-6 shrink-0 items-center justify-center bg-amber-400/15 text-sm text-amber-300">
                  {i + 1}
                </span>
                <span className="text-sm leading-relaxed text-white/85">{s.name}</span>
              </li>
            ))}
          </ol>
          <p className="mt-2 text-xs text-white/40">
            完成全部阶段任务即可获得，奖励 {medal.score.toLocaleString()} 分
          </p>

          {dogtags.length ? (
            <>
              <h2 className="mt-7 text-[11px] tracking-[0.2em] text-amber-400/80">奖励狗牌</h2>
              <div className="mt-3 flex flex-wrap gap-4">
                {dogtags.map((t) => (
                  <Link
                    key={t.id}
                    href={`/bf1/codex/dogtags/${t.id}`}
                    className="group compact-action flex w-24 flex-col items-center gap-1.5 text-center"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
                    <img
                      src={dogtagImage(t.id)}
                      alt={t.name}
                      loading="lazy"
                      className="size-20 rounded-full ring-1 ring-white/10 transition-transform group-hover:scale-105 group-hover:ring-amber-400/60"
                    />
                    <span className="text-xs leading-snug text-white/70 group-hover:text-amber-200">
                      {t.name}
                    </span>
                  </Link>
                ))}
              </div>
            </>
          ) : null}

          <div className="mt-7 border-t border-white/10 pt-4">
            <ShareActions text={medalPlainText(medal, "{link}")} path={path} />
          </div>
        </DetailPanel>
      </div>

      <StepNav
        prev={
          prev && {
            href: `/bf1/codex/medals/${prev.code}`,
            name: prev.name,
            image: medalImage(prev.code),
            shape: "free",
          }
        }
        next={
          next && {
            href: `/bf1/codex/medals/${next.code}`,
            name: next.name,
            image: medalImage(next.code),
            shape: "free",
          }
        }
      />

      {siblings.length ? (
        <section className="mt-12">
          <h2 className="text-base font-semibold tracking-wide">
            同类勋章
            <span className="ml-2 text-xs font-normal tracking-wider text-amber-400/75">
              {medal.category}
            </span>
          </h2>
          <div className="mt-4 grid grid-cols-2 gap-x-3 gap-y-5 sm:grid-cols-[repeat(auto-fill,minmax(128px,1fr))] sm:gap-x-4">
            {siblings.map((m) => (
              <MedalCard key={m.code} medal={m} size="sm" />
            ))}
          </div>
        </section>
      ) : null}

      <CodexFootnote />
    </main>
  );
}
