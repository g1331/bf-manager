import Link from "next/link";
import { BookOpen, Quote } from "lucide-react";
import { type CodexEntry, codexImage } from "@/lib/bf1/codex/codex";
import {
  type GameMode,
  type MapInfo,
  mapExpansionLabel,
  mapImage,
  mapName,
  modeImage,
  type Tip,
  tipsFor,
} from "@/lib/bf1/codex/battlefield";
import { cn } from "@/lib/utils";

/** 地图卡片：横幅大图，名字压在底部渐变上，悬停浮出金色角标 */
export function MapCard({ map, showExpansion }: { map: MapInfo; showExpansion?: boolean }) {
  const tips = tipsFor(map.id).length;
  return (
    <Link
      href={`/bf1/codex/maps/${map.id}`}
      prefetch={false}
      className="group compact-action block outline-none"
    >
      <div className="codex-frame relative">
        <div className="relative aspect-[1000/636] overflow-hidden bg-black/40 ring-1 ring-white/10 transition-shadow duration-200 group-hover:ring-amber-400/50 group-focus-visible:ring-amber-400/50">
          {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
          <img
            src={mapImage(map.id, 480)}
            srcSet={`${mapImage(map.id, 480)} 480w, ${mapImage(map.id)} 1000w`}
            sizes="(min-width: 640px) 320px, 50vw"
            alt=""
            loading="lazy"
            decoding="async"
            className="size-full object-cover transition-transform duration-500 ease-out group-hover:scale-[1.04] motion-reduce:transition-none"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-transparent" />
          {showExpansion && map.expansion ? (
            <span className="absolute top-2 left-2 border border-amber-400/35 bg-black/70 px-1.5 py-px text-[10px] tracking-wider text-amber-200/90">
              {mapExpansionLabel(map.expansion)}
            </span>
          ) : null}
          <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 p-2.5 sm:p-3">
            <span className="text-[15px] leading-tight font-semibold text-white drop-shadow group-hover:text-amber-200 sm:text-base">
              {mapName(map)}
            </span>
            {tips ? (
              <span className="shrink-0 text-[11px] text-white/55 tabular-nums">{tips} 条贴士</span>
            ) : null}
          </div>
        </div>
      </div>
    </Link>
  );
}

/** 模式卡片：16:9 模式图，下方是名字和游戏内的一句话标题 */
export function ModeCard({ mode }: { mode: GameMode }) {
  return (
    <Link
      href={`/bf1/codex/modes/${mode.id}`}
      prefetch={false}
      className="group compact-action block outline-none"
    >
      <div className="codex-frame relative">
        <div className="relative aspect-[16/9] overflow-hidden bg-black/40 ring-1 ring-white/10 transition-shadow duration-200 group-hover:ring-amber-400/50 group-focus-visible:ring-amber-400/50">
          {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
          <img
            src={modeImage(mode.id, 480)}
            srcSet={`${modeImage(mode.id, 480)} 480w, ${modeImage(mode.id)} 1000w`}
            sizes="(min-width: 640px) 280px, 50vw"
            alt=""
            loading="lazy"
            decoding="async"
            className="size-full object-cover transition-transform duration-500 ease-out group-hover:scale-[1.04] motion-reduce:transition-none"
          />
        </div>
      </div>
      <div className="px-0.5 pt-2.5">
        <div className="text-[15px] leading-snug font-semibold text-white group-hover:text-amber-200">
          {mode.name}
        </div>
        <div className="mt-0.5 line-clamp-1 text-xs text-white/45">
          {mode.header !== mode.name ? mode.header : mode.body}
        </div>
      </div>
    </Link>
  );
}

/** 地图、模式详情页的头图：整宽大图，标题压在左下角 */
export function BattlefieldHero({
  image,
  srcSet,
  eyebrow,
  title,
  subtitle,
}: {
  image: string;
  srcSet: string;
  eyebrow: React.ReactNode;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="relative mt-5 overflow-hidden border border-white/[0.06] bg-black/40 lg:mt-6">
      {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
      <img
        src={image}
        srcSet={srcSet}
        sizes="(min-width: 1152px) 1152px, 100vw"
        alt=""
        className="block aspect-[16/10] w-full object-cover sm:aspect-[16/7] lg:max-h-[520px]"
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/25 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 p-4 sm:p-6 lg:p-8">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs tracking-[0.12em] text-amber-400/90">
          {eyebrow}
        </div>
        <h1 className="mt-1.5 text-2xl leading-tight font-bold tracking-wide drop-shadow sm:text-4xl">
          {title}
        </h1>
        {subtitle ? (
          <p className="mt-1.5 max-w-2xl text-sm text-white/75 sm:text-[15px]">{subtitle}</p>
        ) : null}
      </div>
    </div>
  );
}

/** 小节标题：细金条 + 标题 + 计数 */
export function SectionTitle({ title, count }: { title: string; count?: number }) {
  return (
    <h2 className="flex items-baseline gap-2 text-base font-semibold tracking-wide">
      <span className="h-3.5 w-[3px] self-center bg-amber-500" aria-hidden />
      {title}
      {count != null ? (
        <span className="text-xs font-normal text-white/40 tabular-nums">{count}</span>
      ) : null}
    </h2>
  );
}

/** 「历史背景」：挂在地图、模式上的百科条目全文，配一张竖幅百科图 */
export function CodexStory({ entry, body }: { entry: CodexEntry; body: string }) {
  return (
    <section>
      <SectionTitle title="历史背景" />
      <div className="mt-4 flex gap-4 sm:gap-5">
        <Link
          href={`/bf1/codex/${entry.code}`}
          prefetch={false}
          className="group compact-action hidden w-28 shrink-0 self-start sm:block"
        >
          <div className="codex-frame relative">
            {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
            <img
              src={codexImage(entry.code, 480)}
              alt={entry.name}
              loading="lazy"
              className="block aspect-[640/901] w-full object-cover ring-1 ring-white/10"
            />
          </div>
        </Link>
        <div className="min-w-0">
          <div className="text-[15px] font-semibold text-white/95">{entry.header}</div>
          {entry.subHeader ? (
            <div className="mt-0.5 text-xs text-white/45">{entry.subHeader}</div>
          ) : null}
          <p className="mt-3 text-[15px] leading-[1.9] whitespace-pre-line text-white/80">{body}</p>
          <Link
            href={`/bf1/codex/${entry.code}`}
            prefetch={false}
            className="inline-action mt-3 inline-flex items-center gap-1.5 text-xs text-amber-300/90 hover:text-amber-200"
          >
            <BookOpen className="size-3.5" />
            百科条目「{entry.name}」· 解锁：{entry.unlock}
          </Link>
        </div>
      </div>
    </section>
  );
}

/** 载入画面小贴士：引号开头的一条条短句 */
export function TipList({ tips, className }: { tips: Tip[]; className?: string }) {
  return (
    <ul className={cn("divide-y divide-white/[0.06]", className)}>
      {tips.map((t) => (
        <li key={t.text} className="flex gap-3 py-3 text-sm leading-relaxed text-white/75">
          <Quote className="mt-0.5 size-3.5 shrink-0 text-amber-400/60" aria-hidden />
          <span>{t.text}</span>
        </li>
      ))}
    </ul>
  );
}
