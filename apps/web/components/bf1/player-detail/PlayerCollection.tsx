"use client";

import Link from "next/link";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { RowsSkeleton } from "@/components/layout/PageSkeleton";
import type { CollectionDogtag, CollectionMedal, PlayerCollection } from "@/lib/api/bf1";
import {
  DOGTAGS,
  dogtagImage,
  getDogtag,
  groupBy,
  MEDALS,
  medalImage,
} from "@/lib/bf1/codex/collection";
import { cn } from "@/lib/utils";
import { Panel } from "./CareerOverview";

const MEDAL_GROUPS = groupBy(MEDALS, (m) => m.category);
const DOGTAG_GROUPS = groupBy(DOGTAGS, (t) => t.category);

/** 收藏分区：佩戴的狗牌、勋章墙、狗牌墙；没拿到的置灰，点开进图鉴 */
export function PlayerCollectionView({
  data,
  loading,
  error,
}: {
  data: PlayerCollection | undefined;
  loading: boolean;
  error: boolean;
}) {
  if (loading) return <RowsSkeleton rows={6} />;
  if (error || !data)
    return (
      <Panel>
        <div className="py-8 text-center text-sm text-white/45">收藏数据暂时读不到</div>
      </Panel>
    );
  const medals = new Map(data.medals.map((m) => [m.code, m]));
  const dogtags = new Map(data.dogtags.map((t) => [t.id, t]));
  const equipped = data.equipped.map(getDogtag).filter((t) => t != null);
  return (
    <div className="space-y-4 sm:space-y-6">
      {equipped.length ? (
        <Panel>
          <SectionHeading className="mb-4">佩戴的狗牌</SectionHeading>
          <div className="flex flex-wrap gap-6">
            {equipped.map((t) => (
              <Link
                key={t.id}
                href={`/bf1/codex/dogtags/${t.id}`}
                prefetch={false}
                className="group compact-action flex items-center gap-3"
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
                <img
                  src={dogtagImage(t.id)}
                  alt=""
                  width={300}
                  height={300}
                  className="size-20 rounded-full drop-shadow-[0_8px_12px_rgba(0,0,0,0.6)] sm:size-24"
                />
                <span className="text-sm font-semibold text-white group-hover:text-amber-200">
                  {t.name}
                </span>
              </Link>
            ))}
          </div>
        </Panel>
      ) : null}

      <Panel>
        <Heading
          title="勋章"
          got={data.medals.filter((m) => m.unlocked).length}
          total={MEDALS.length}
        />
        <div className="space-y-4">
          {MEDAL_GROUPS.map((g) => (
            <div key={g.key}>
              <div className="mb-1.5 text-[11px] text-white/45">{g.key}</div>
              <ul className="grid grid-cols-[repeat(auto-fill,minmax(3.5rem,1fr))] gap-2 sm:grid-cols-[repeat(auto-fill,minmax(4.5rem,1fr))]">
                {g.items.map((m) => (
                  <li key={m.code}>
                    <MedalTile code={m.code} name={m.name} state={medals.get(m.code)} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Panel>

      <Panel>
        <Heading
          title="狗牌"
          got={data.dogtags.filter((t) => t.unlocked).length}
          total={DOGTAGS.length}
        />
        <div className="space-y-4">
          {DOGTAG_GROUPS.map((g) => (
            <div key={g.key}>
              <div className="mb-1.5 text-[11px] text-white/45">{g.key}</div>
              <ul className="grid grid-cols-[repeat(auto-fill,minmax(2.5rem,1fr))] gap-1.5 sm:grid-cols-[repeat(auto-fill,minmax(3.25rem,1fr))] sm:gap-2">
                {g.items.map((t) => (
                  <li key={t.id}>
                    <DogtagTile id={t.id} name={t.name} state={dogtags.get(t.id)} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function Heading({ title, got, total }: { title: string; got: number; total: number }) {
  return (
    <div className="mb-4 flex items-baseline justify-between gap-3">
      <SectionHeading>{title}</SectionHeading>
      <span className="text-xs text-white/45 tabular-nums">
        {got} / {total}
      </span>
    </div>
  );
}

function MedalTile({
  code,
  name,
  state,
}: {
  code: string;
  name: string;
  state: CollectionMedal | undefined;
}) {
  const done = state?.unlocked ?? false;
  const partial = !done && state && state.stages_done > 0;
  const label = done
    ? `${name}，已解锁`
    : partial
      ? `${name}，未解锁，${state.stages_done} / ${state.stages_total} 阶段`
      : `${name}，未解锁`;
  return (
    <Link
      href={`/bf1/codex/medals/${code}`}
      prefetch={false}
      title={label}
      aria-label={label}
      className="group compact-action block"
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
      <img
        src={medalImage(code)}
        alt=""
        width={256}
        height={256}
        loading="lazy"
        decoding="async"
        className={cn(
          "aspect-square w-full object-contain transition-opacity group-hover:opacity-100",
          done ? "" : "opacity-30 grayscale",
        )}
      />
      <div className="h-4 text-center text-[10px] text-white/50 tabular-nums">
        {partial ? `${state.stages_done}/${state.stages_total}` : ""}
      </div>
    </Link>
  );
}

function DogtagTile({
  id,
  name,
  state,
}: {
  id: string;
  name: string;
  state: CollectionDogtag | undefined;
}) {
  const done = state?.unlocked ?? false;
  const ratio =
    state?.acquired != null && state.needed ? Math.min(state.acquired / state.needed, 1) : null;
  const label = done
    ? `${name}，已解锁`
    : ratio != null
      ? `${name}，未解锁，${state?.acquired} / ${state?.needed}`
      : `${name}，未解锁`;
  return (
    <Link
      href={`/bf1/codex/dogtags/${id}`}
      prefetch={false}
      title={label}
      aria-label={label}
      className="group compact-action block"
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
      <img
        src={dogtagImage(id)}
        alt=""
        width={300}
        height={300}
        loading="lazy"
        decoding="async"
        className={cn(
          "aspect-square w-full rounded-full transition-opacity group-hover:opacity-100",
          done ? "" : "opacity-25 grayscale",
        )}
      />
      {ratio != null && ratio > 0 ? (
        <div className="mx-1 mt-1 h-0.5 bg-white/10">
          <div className="h-full bg-amber-400/70" style={{ width: `${ratio * 100}%` }} />
        </div>
      ) : null}
    </Link>
  );
}
