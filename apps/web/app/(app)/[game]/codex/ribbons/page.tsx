import type { Metadata } from "next";
import { CodexFootnote, CodexHeader } from "@/components/bf1/codex/CodexHeader";
import { GroupHeading, GroupIndex } from "@/components/bf1/codex/DetailParts";
import { expansionLabel } from "@/lib/bf1/codex/codex";
import { groupBy, RIBBONS, ribbonImage } from "@/lib/bf1/codex/collection";

export const metadata: Metadata = {
  title: "勋带 · 图鉴",
  description: "战地 1 全部 47 条勋带：每条的达成条件与奖励分数。",
};

const GROUPS = groupBy(RIBBONS, (r) => r.category).map((g) => ({
  id: `ribbons-${g.key}`,
  title: g.key,
  items: g.items,
}));

export default function RibbonsPage() {
  return (
    <main className="mx-auto max-w-[1400px] px-4 py-6 text-white sm:py-8">
      <CodexHeader
        active="ribbons"
        intro="勋带是单回合内的表现奖励，一回合里达成条件就会在结算时颁发，可以重复获得。"
      />
      <GroupIndex
        groups={GROUPS.map((g) => ({ id: g.id, title: g.title, count: g.items.length }))}
      />
      <div className="mt-8 space-y-10">
        {GROUPS.map((g) => (
          <section key={g.id}>
            <GroupHeading id={g.id} title={`${g.title}勋带`} count={g.items.length} />
            <ul className="mt-4 grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
              {g.items.map((r) => (
                <li
                  key={r.code}
                  className="flex items-center gap-4 border border-white/[0.07] bg-black/35 p-3 backdrop-blur-sm"
                >
                  {/* 原图 256 见方，勋带只占中间一条（x 17–239，y 约 90–167），裁出这一条 */}
                  <div className="relative h-[42px] w-[122px] shrink-0 overflow-hidden">
                    {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
                    <img
                      src={ribbonImage(r.code)}
                      alt={r.name}
                      width={256}
                      height={256}
                      loading="lazy"
                      className="absolute top-[-49px] left-[-9px] h-[141px] w-[141px] max-w-none"
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className="text-[15px] font-semibold">{r.name}</span>
                      {r.expansion ? (
                        <span className="text-[11px] text-amber-300/80">
                          {expansionLabel(r.expansion)}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-0.5 text-sm leading-relaxed text-white/65">{r.description}</p>
                  </div>
                  <span className="font-display shrink-0 self-start text-sm text-amber-300/90 tabular-nums">
                    +{r.score}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      <CodexFootnote />
    </main>
  );
}
