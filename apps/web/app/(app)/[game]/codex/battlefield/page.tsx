import type { Metadata } from "next";
import Link from "next/link";
import { BookOpen } from "lucide-react";
import { MapCard, ModeCard } from "@/components/bf1/codex/BattlefieldParts";
import { CodexFootnote, CodexHeader } from "@/components/bf1/codex/CodexHeader";
import { GroupHeading, GroupIndex } from "@/components/bf1/codex/DetailParts";
import {
  FACTIONS,
  factionImage,
  MAP_EXPANSIONS,
  MAPS,
  MODES,
  STORIES,
  type WarStory,
} from "@/lib/bf1/codex/battlefield";
import { codexImage, getCodexEntry } from "@/lib/bf1/codex/codex";

export const metadata: Metadata = {
  title: "战场 · 图鉴",
  description:
    "战地 1 的 10 种模式、32 张多人地图、战争故事与参战阵营：每张地图的历史背景和载入画面小贴士。",
};

const MAP_GROUPS = MAP_EXPANSIONS.map((x) => ({
  ...x,
  maps: MAPS.filter((m) => m.expansion === x.key),
})).filter((g) => g.maps.length);

const MAIN_STORIES = STORIES.filter((s) => s.kind === "story");
const PROLOGUE = STORIES.find((s) => s.kind === "prologue");
const EPILOGUE = STORIES.find((s) => s.kind === "epilogue");

const GROUPS = [
  { id: "modes", title: "模式", count: MODES.length },
  { id: "maps", title: "地图", count: MAPS.length },
  { id: "stories", title: "战争故事", count: MAIN_STORIES.length },
  { id: "factions", title: "阵营", count: FACTIONS.length },
];

export default function BattlefieldPage() {
  return (
    <main className="mx-auto max-w-[1400px] px-4 py-6 text-white sm:py-8">
      <CodexHeader
        active="battlefield"
        intro="战地 1 的玩法、战场和参战各方。地图和模式点开能读到它们背后的历史，以及载入画面里轮播的小贴士。"
      />
      <GroupIndex groups={GROUPS} />

      <div className="mt-8 space-y-14">
        <section>
          <GroupHeading id="modes" title="模式" count={MODES.length} />
          <div className="mt-4 grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-3 sm:gap-x-5 lg:grid-cols-5">
            {MODES.map((m) => (
              <ModeCard key={m.id} mode={m} />
            ))}
          </div>
        </section>

        <section>
          <GroupHeading id="maps" title="地图" count={MAPS.length} />
          <div className="mt-4 space-y-8">
            {MAP_GROUPS.map((g) => (
              <div key={g.key || "base"}>
                <h3
                  id={`maps-${g.key || "base"}`}
                  className="flex scroll-mt-28 items-baseline gap-2 text-sm font-medium text-white/70 lg:scroll-mt-20"
                >
                  {g.label}
                  <span className="text-xs text-white/35 tabular-nums">{g.maps.length}</span>
                </h3>
                <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-[repeat(auto-fill,minmax(240px,1fr))] sm:gap-4">
                  {g.maps.map((m) => (
                    <MapCard key={m.id} map={m} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <GroupHeading id="stories" title="战争故事" count={MAIN_STORIES.length} />
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-white/50">
            单人战役由序章、五个互不相连的战争故事和尾声组成。每一章里都藏着几条百科，打完整个故事还会再解锁一条。
          </p>
          {PROLOGUE ? <StoryBar story={PROLOGUE} label="序章" /> : null}
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            {MAIN_STORIES.map((s, i) => (
              <StoryCard key={s.id} story={s} index={i + 1} />
            ))}
          </div>
          {EPILOGUE ? <StoryBar story={EPILOGUE} label="尾声" /> : null}
        </section>

        <section>
          <GroupHeading id="factions" title="阵营" count={FACTIONS.length} />
          <div className="mt-4 grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {FACTIONS.map((f) => {
              const body = (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
                  <img
                    src={factionImage(f.id)}
                    alt=""
                    width={160}
                    height={160}
                    loading="lazy"
                    className="size-14 object-contain drop-shadow-[0_6px_10px_rgba(0,0,0,0.6)] transition-transform duration-300 group-hover:scale-105 sm:size-16"
                  />
                  <span className="mt-2 text-[13px] leading-snug font-semibold text-white group-hover:text-amber-200 sm:text-sm">
                    {f.name}
                  </span>
                  <span className="mt-0.5 min-h-4 text-[11px] text-white/40">
                    {f.short !== f.name ? f.short : ""}
                  </span>
                  {f.codex ? (
                    <BookOpen
                      className="absolute top-2 right-2 size-3.5 text-white/30 group-hover:text-amber-300"
                      aria-label="有百科条目"
                    />
                  ) : null}
                </>
              );
              const cls =
                "relative flex flex-col items-center border border-white/[0.07] bg-black/30 px-2 py-4 text-center";
              return f.codex ? (
                <Link
                  key={f.id}
                  href={`/bf1/codex/${f.codex}`}
                  prefetch={false}
                  className={`group compact-action ${cls} transition-colors hover:border-amber-400/50`}
                >
                  {body}
                </Link>
              ) : (
                <div key={f.id} className={cls}>
                  {body}
                </div>
              );
            })}
          </div>
        </section>
      </div>

      <CodexFootnote />
    </main>
  );
}

/** 五个战争故事：左边是通关解锁的百科图当封面，右边逐章列出该章解锁的百科 */
function StoryCard({ story, index }: { story: WarStory; index: number }) {
  const finale = story.completion ? getCodexEntry(story.completion) : undefined;
  return (
    <article className="flex gap-4 border border-white/[0.07] bg-black/35 p-3 sm:gap-5 sm:p-4">
      {finale ? (
        <Link
          href={`/bf1/codex/${finale.code}`}
          prefetch={false}
          className="group compact-action w-24 shrink-0 self-start sm:w-32"
          aria-label={`通关解锁的百科：${finale.name}`}
        >
          <div className="codex-frame relative">
            {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
            <img
              src={codexImage(finale.code, 480)}
              alt=""
              loading="lazy"
              className="block aspect-[640/901] w-full object-cover ring-1 ring-white/10"
            />
          </div>
        </Link>
      ) : null}
      <div className="min-w-0 flex-1">
        <div className="font-display text-[11px] tracking-[0.18em] text-amber-400/80 uppercase">
          {String(index).padStart(2, "0")} · {story.en}
        </div>
        <h3 className="mt-0.5 text-lg font-bold tracking-wide">{story.name}</h3>
        <ol className="mt-3 space-y-2.5">
          {story.chapters.map((c, i) => (
            <li key={c.id} className="text-sm">
              <div className="flex items-baseline gap-2">
                <span className="text-[11px] text-white/35 tabular-nums">第 {i + 1} 章</span>
                <span className="font-medium text-white/90">{c.name}</span>
              </div>
              {c.codex.length ? (
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 pl-[3.25rem]">
                  {c.codex.map((code) => {
                    const e = getCodexEntry(code);
                    return e ? (
                      <Link
                        key={code}
                        href={`/bf1/codex/${code}`}
                        prefetch={false}
                        className="inline-action text-xs text-white/50 underline decoration-white/15 underline-offset-[3px] hover:text-amber-200 hover:decoration-amber-300/50"
                      >
                        {e.name}
                      </Link>
                    ) : null;
                  })}
                </div>
              ) : null}
            </li>
          ))}
        </ol>
        {finale ? (
          <div className="mt-3 border-t border-white/[0.06] pt-2.5 text-xs text-white/45">
            通关解锁：
            <Link
              href={`/bf1/codex/${finale.code}`}
              prefetch={false}
              className="inline-action text-amber-300/85 hover:text-amber-200"
            >
              {finale.name}
            </Link>
          </div>
        ) : null}
      </div>
    </article>
  );
}

/** 序章、尾声：一条细横栏 */
function StoryBar({ story, label }: { story: WarStory; label: string }) {
  const finale = story.completion ? getCodexEntry(story.completion) : undefined;
  return (
    <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 border border-white/[0.07] bg-black/30 px-4 py-3 text-sm">
      <span className="text-[11px] tracking-[0.18em] text-amber-400/80">{label}</span>
      <span className="font-semibold">{story.name}</span>
      <span className="font-display text-[11px] tracking-[0.14em] text-white/35 uppercase">
        {story.en}
      </span>
      {finale ? (
        <span className="text-xs text-white/45 sm:ml-auto">
          完成后解锁：
          <Link
            href={`/bf1/codex/${finale.code}`}
            prefetch={false}
            className="inline-action text-amber-300/85 hover:text-amber-200"
          >
            {finale.name}
          </Link>
        </span>
      ) : null}
    </div>
  );
}
