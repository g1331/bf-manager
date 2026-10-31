import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  BattlefieldHero,
  CodexStory,
  MapCard,
  SectionTitle,
  TipList,
} from "@/components/bf1/codex/BattlefieldParts";
import { CodexBack, ShareActions } from "@/components/bf1/codex/CodexActions";
import { CodexFootnote } from "@/components/bf1/codex/CodexHeader";
import { Breadcrumbs, DetailPanel, StepNav } from "@/components/bf1/codex/DetailParts";
import {
  getMap,
  type MapInfo,
  mapExpansionLabel,
  mapImage,
  mapName,
  mapNeighbors,
  MAPS,
  tipsFor,
} from "@/lib/bf1/codex/battlefield";
import { getCodexEntry } from "@/lib/bf1/codex/codex";
import texts from "@/lib/bf1/codex/data/codex-text.json";

const TEXTS = texts as Record<string, string>;

export const dynamicParams = false;

export function generateStaticParams() {
  return MAPS.map((m) => ({ id: m.id }));
}

interface Props {
  params: Promise<{ game: string; id: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const map = getMap((await params).id);
  if (!map) return {};
  const name = mapName(map);
  const entry = getCodexEntry(map.codex);
  const description = `战地 1 地图 · ${mapExpansionLabel(map.expansion)}。${
    entry ? TEXTS[entry.code].slice(0, 90) : ""
  }`;
  return {
    metadataBase: new URL("https://bfm.umrbotech.com"),
    title: `${name} · 战地 1 地图`,
    description,
    openGraph: { title: name, description, images: [{ url: mapImage(map.id) }] },
  };
}

export default async function MapPage({ params }: Props) {
  const map = getMap((await params).id);
  if (!map) notFound();
  const name = mapName(map);
  const entry = getCodexEntry(map.codex);
  const tips = tipsFor(map.id);
  const { prev, next } = mapNeighbors(map.id);
  const siblings = MAPS.filter((m) => m.expansion === map.expansion && m.id !== map.id);
  const xp = mapExpansionLabel(map.expansion);
  const step = (m?: MapInfo) =>
    m && {
      href: `/bf1/codex/maps/${m.id}`,
      name: mapName(m),
      image: mapImage(m.id, 480),
      shape: "card" as const,
    };
  const share = [
    `【${name}】战地 1 地图 · ${xp}`,
    entry ? `历史背景：${entry.header}` : "",
    tips.length ? `载入贴士：${tips[0].text}` : "",
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <main className="mx-auto max-w-6xl px-4 py-4 text-white sm:py-8">
      <CodexBack fallback="/bf1/codex/battlefield#maps" />
      <Breadcrumbs
        items={[
          { label: "图鉴", href: "/bf1/codex" },
          { label: "战场", href: "/bf1/codex/battlefield" },
          { label: "地图", href: `/bf1/codex/battlefield#maps-${map.expansion || "base"}` },
        ]}
      />

      <BattlefieldHero
        image={mapImage(map.id)}
        srcSet={`${mapImage(map.id, 480)} 480w, ${mapImage(map.id)} 1000w`}
        eyebrow={
          <>
            <span>地图</span>
            <span className="text-white/25">/</span>
            <span>{xp}</span>
            <span className="font-mono tracking-normal text-white/40">{map.id}</span>
          </>
        }
        title={name}
        subtitle={entry && entry.header !== name ? entry.header : undefined}
      />

      <div className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <DetailPanel>
          {entry ? <CodexStory entry={entry} body={TEXTS[entry.code] ?? ""} /> : null}
          <div className="mt-7 border-t border-white/10 pt-4">
            <ShareActions
              text={`${share}\n\n—— 战地 1 图鉴 · {link}`}
              path={`/bf1/codex/maps/${map.id}`}
            />
          </div>
        </DetailPanel>

        <aside className="max-w-[42rem] border border-white/[0.07] bg-black/45 p-4 backdrop-blur-sm sm:p-5 lg:p-6">
          <div className="flex items-baseline justify-between gap-3">
            <SectionTitle title="载入贴士" count={tips.length} />
            {tips.length ? (
              <Link
                href={`/bf1/codex/tips?tag=${map.id}`}
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
              游戏数据里没有这张地图专属的载入贴士。
            </p>
          )}
        </aside>
      </div>

      <StepNav prev={step(prev)} next={step(next)} />

      {siblings.length ? (
        <section className="mt-12">
          <h2 className="text-base font-semibold tracking-wide">
            同一资料片
            <span className="ml-2 text-xs font-normal tracking-wider text-amber-400/75">{xp}</span>
          </h2>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4">
            {siblings.map((m) => (
              <MapCard key={m.id} map={m} />
            ))}
          </div>
        </section>
      ) : null}

      <CodexFootnote />
    </main>
  );
}
