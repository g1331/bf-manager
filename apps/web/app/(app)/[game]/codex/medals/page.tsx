import type { Metadata } from "next";
import { CodexFootnote, CodexHeader } from "@/components/bf1/codex/CodexHeader";
import { GroupHeading, GroupIndex } from "@/components/bf1/codex/DetailParts";
import { MedalCard } from "@/components/bf1/codex/MedalCard";
import { groupBy, MEDALS } from "@/lib/bf1/codex/collection";

export const metadata: Metadata = {
  title: "勋章 · 图鉴",
  description: "战地 1 全部 60 枚勋章：每枚的阶段任务与奖励狗牌，可以 3D 旋转查看。",
};

const GROUPS = groupBy(MEDALS, (m) => m.category).map((g) => ({
  id: `medals-${g.key}`,
  title: g.key,
  items: g.items,
}));

export default function MedalsPage() {
  return (
    <main className="mx-auto max-w-[1400px] px-4 py-6 text-white sm:py-8">
      <CodexHeader
        active="medals"
        intro="每枚勋章都要连续完成几个阶段任务才能拿到，部分还会奖励专属狗牌。点开可以把勋章拿在手里转着看。"
      />
      <GroupIndex
        groups={GROUPS.map((g) => ({ id: g.id, title: g.title, count: g.items.length }))}
      />
      <div className="mt-8 space-y-12">
        {GROUPS.map((g) => (
          <section key={g.id}>
            <GroupHeading id={g.id} title={`${g.title}勋章`} count={g.items.length} />
            <div className="mt-4 grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-[repeat(auto-fill,minmax(168px,1fr))] sm:gap-x-5 sm:gap-y-8">
              {g.items.map((m) => (
                <MedalCard key={m.code} medal={m} />
              ))}
            </div>
          </section>
        ))}
      </div>
      <CodexFootnote />
    </main>
  );
}
