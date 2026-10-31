import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight } from "lucide-react";
import {
  BattlefieldHero,
  CodexStory,
  ModeCard,
  SectionTitle,
  TipList,
} from "@/components/bf1/codex/BattlefieldParts";
import { CodexBack, ShareActions } from "@/components/bf1/codex/CodexActions";
import { CodexFootnote } from "@/components/bf1/codex/CodexHeader";
import { Breadcrumbs, DetailPanel, StepNav } from "@/components/bf1/codex/DetailParts";
import {
  type GameMode,
  getMode,
  modeImage,
  modeNeighbors,
  MODES,
  tipsFor,
} from "@/lib/bf1/codex/battlefield";
import { getCodexEntry } from "@/lib/bf1/codex/codex";
import { modeTag } from "@/lib/bf1/codex/tips";
import texts from "@/lib/bf1/codex/data/codex-text.json";

const TEXTS = texts as Record<string, string>;

export const dynamicParams = false;

export function generateStaticParams() {
  return MODES.map((m) => ({ id: m.id }));
}

interface Props {
  params: Promise<{ game: string; id: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const mode = getMode((await params).id);
  if (!mode) return {};
  const description = `战地 1 模式。${mode.header}：${mode.body}`;
  return {
    metadataBase: new URL("https://bfm.umrbotech.com"),
    title: `${mode.name} · 战地 1 模式`,
    description,
    openGraph: { title: mode.name, description, images: [{ url: modeImage(mode.id) }] },
  };
}

export default async function ModePage({ params }: Props) {
  const mode = getMode((await params).id);
  if (!mode) notFound();
  const entry = getCodexEntry(mode.codex);
  // 行动模式没有自己的贴士，沿用闪击行动的（区域、兵力规则相同）
  const tag = modeTag(mode.id);
  const tips = tipsFor(tag);
  const { prev, next } = modeNeighbors(mode.id);
  const others = MODES.filter((m) => m.id !== mode.id);
  const step = (m?: GameMode) =>
    m && {
      href: `/bf1/codex/modes/${m.id}`,
      name: m.name,
      image: modeImage(m.id, 480),
      shape: "card" as const,
    };

  return (
    <main className="mx-auto max-w-6xl px-4 py-4 text-white sm:py-8">
      <CodexBack fallback="/bf1/codex/battlefield#modes" />
      <Breadcrumbs
        items={[
          { label: "图鉴", href: "/bf1/codex" },
          { label: "战场", href: "/bf1/codex/battlefield" },
          { label: "模式", href: "/bf1/codex/battlefield#modes" },
        ]}
      />

      <BattlefieldHero
        image={modeImage(mode.id)}
        srcSet={`${modeImage(mode.id, 480)} 480w, ${modeImage(mode.id)} 1000w`}
        eyebrow={
          <>
            <span>模式</span>
            <span className="font-mono tracking-normal text-white/40">{mode.id}</span>
          </>
        }
        title={mode.name}
        subtitle={mode.header !== mode.name ? mode.header : undefined}
      />

      <div className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <DetailPanel>
          <section>
            <SectionTitle title="玩法" />
            <p className="mt-3 text-[15px] leading-[1.9] whitespace-pre-line text-white/85">
              {mode.body}
            </p>
            {mode.id === "BreakthroughLarge" ? (
              <Link
                href="/bf1/campaign"
                className="mt-4 inline-flex items-center gap-1.5 border border-white/15 px-3 text-sm text-white/80 transition-colors hover:border-amber-400/60 hover:text-amber-300"
              >
                查看当前的行动
                <ArrowRight className="size-4" />
              </Link>
            ) : null}
          </section>
          {entry ? (
            <div className="mt-10">
              <CodexStory entry={entry} body={TEXTS[entry.code] ?? ""} />
            </div>
          ) : null}
          <div className="mt-7 border-t border-white/10 pt-4">
            <ShareActions
              text={`【${mode.name}】战地 1 模式\n${mode.header}：${mode.body}\n\n—— 战地 1 图鉴 · {link}`}
              path={`/bf1/codex/modes/${mode.id}`}
            />
          </div>
        </DetailPanel>

        <aside className="max-w-[42rem] border border-white/[0.07] bg-black/45 p-4 backdrop-blur-sm sm:p-5 lg:p-6">
          <div className="flex items-baseline justify-between gap-3">
            <SectionTitle title="载入贴士" count={tips.length} />
            {tips.length ? (
              <Link
                href={`/bf1/codex/tips?tag=${tag}`}
                prefetch={false}
                className="inline-action text-xs text-white/45 hover:text-amber-300"
              >
                在小贴士里查看
              </Link>
            ) : null}
          </div>
          {tips.length ? (
            <TipList tips={tips} className="mt-2" />
          ) : (
            <p className="mt-3 text-sm leading-relaxed text-white/45">
              游戏数据里没有这个模式专属的载入贴士。
            </p>
          )}
        </aside>
      </div>

      <StepNav prev={step(prev)} next={step(next)} />

      <section className="mt-12">
        <h2 className="text-base font-semibold tracking-wide">其它模式</h2>
        <div className="mt-4 grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-3 sm:gap-x-5 lg:grid-cols-5">
          {others.map((m) => (
            <ModeCard key={m.id} mode={m} />
          ))}
        </div>
      </section>

      <CodexFootnote />
    </main>
  );
}
