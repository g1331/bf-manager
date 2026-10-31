import type { Metadata } from "next";
import { CodexFootnote, CodexHeader } from "@/components/bf1/codex/CodexHeader";
import { GroupHeading, GroupIndex } from "@/components/bf1/codex/DetailParts";
import { assignmentImage, ASSIGNMENTS, groupBy } from "@/lib/bf1/codex/collection";

export const metadata: Metadata = {
  title: "勤务 · 图鉴",
  description: "战地 1 全部 41 个勤务小任务：每项的全部达成条件与解锁前置。",
};

const GROUP_INTRO: Record<string, string> = {
  初来乍到: "新兵入门的 5 个任务，完成其中 3 个就会开放「保持专注」。",
  保持专注: "兵种和载具专精，多数分基本、老鸟两级，老鸟级要先完成基本级。",
  晋升阶级:
    "完成 5 个保持专注小任务后开放，其中有以七宗罪命名的七个「之证」；最后 5 项要先完成对应的「之证」。",
};

const GROUPS = groupBy(ASSIGNMENTS, (a) => a.group).map((g, i) => ({
  id: `assignments-${i + 1}`,
  title: g.key,
  items: g.items,
}));

export default function AssignmentsPage() {
  return (
    <main className="mx-auto max-w-[1400px] px-4 py-6 text-white sm:py-8">
      <CodexHeader
        active="assignments"
        intro="勤务小任务要把列出的条件全部完成才算达成，后面的任务需要先完成前置任务才会开放。"
      />
      <GroupIndex
        groups={GROUPS.map((g) => ({ id: g.id, title: g.title, count: g.items.length }))}
      />
      <div className="mt-8 space-y-12">
        {GROUPS.map((g) => (
          <section key={g.id}>
            <GroupHeading id={g.id} title={g.title} count={g.items.length} />
            {GROUP_INTRO[g.title] ? (
              <p className="mt-1.5 text-sm text-white/45">{GROUP_INTRO[g.title]}</p>
            ) : null}
            <div className="mt-4 grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
              {g.items.map((a) => (
                <article
                  key={a.code}
                  id={a.code}
                  className="scroll-mt-28 border border-white/[0.07] bg-black/35 p-4 backdrop-blur-sm lg:scroll-mt-20"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex size-12 shrink-0 items-center justify-center bg-white/[0.05] ring-1 ring-white/10">
                      {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
                      <img
                        src={assignmentImage(a.image)}
                        alt=""
                        width={256}
                        height={256}
                        loading="lazy"
                        className="size-9 object-contain"
                      />
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-[15px] font-semibold">{a.name}</h3>
                      {a.description ? (
                        <p className="mt-0.5 text-xs text-white/45">
                          {a.requires.length === 1 ? (
                            // 前置只有一项时整句可点，跳到那张卡片
                            <a
                              href={`#${a.requires[0]}`}
                              className="inline-action underline decoration-white/20 underline-offset-4 hover:text-amber-200"
                            >
                              {a.description}
                            </a>
                          ) : (
                            a.description
                          )}
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <ol className="mt-3 space-y-1.5 border-t border-white/[0.06] pt-3">
                    {a.criteria.map((c, i) => (
                      <li key={i} className="flex gap-2.5 text-sm leading-relaxed text-white/75">
                        <span className="mt-[7px] size-1.5 shrink-0 bg-amber-400/70" aria-hidden />
                        {c}
                      </li>
                    ))}
                  </ol>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>
      <CodexFootnote />
    </main>
  );
}
