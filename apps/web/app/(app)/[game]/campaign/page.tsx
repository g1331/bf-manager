"use client";

/**
 * 行动（Campaign Operations）：EA 当前轮换的行动战役、包含的行动与结束 / 每日重置时间。
 */

import { useQuery } from "@tanstack/react-query";
import { bf1Api } from "@/lib/api/bf1";

function remaining(iso: string): string {
  const minutes = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 60000));
  const d = Math.floor(minutes / 1440);
  const h = Math.floor((minutes % 1440) / 60);
  const m = minutes % 60;
  return d > 0 ? `${d} 天 ${h} 小时` : `${h} 小时 ${m} 分`;
}

export default function CampaignPage() {
  const q = useQuery({ queryKey: ["bf1-campaign"], queryFn: () => bf1Api.getCampaign() });
  const c = q.data;

  return (
    <main className="flex flex-col gap-4 py-6 text-white">
      <header>
        <div className="font-display flex items-center gap-2 text-xs font-medium tracking-[0.2em] text-amber-500 uppercase">
          <span className="h-[2px] w-6 bg-amber-500" />
          Operations
        </div>
        <h1 className="mt-1.5 text-2xl font-bold tracking-wide sm:text-3xl">
          行动{c ? ` · ${c.name}` : ""}
        </h1>
      </header>

      {q.isLoading ? (
        <div className="py-16 text-center text-sm text-white/45">加载中…</div>
      ) : q.isError || !c ? (
        <div className="rounded-sm border border-dashed border-white/15 py-16 text-center text-sm text-white/45">
          {q.isError ? "加载失败，请稍后重试。" : "当前没有进行中的行动。"}
        </div>
      ) : (
        <>
          <p className="max-w-3xl text-sm leading-relaxed text-white/70">{c.description}</p>
          <dl className="grid max-w-3xl grid-cols-2 gap-3">
            <Stat
              label="行动结束"
              value={new Date(c.ends_at).toLocaleString("zh-CN", {
                dateStyle: "medium",
                timeStyle: "short",
              })}
              hint={`剩余 ${remaining(c.ends_at)}`}
            />
            <Stat
              label="每日重置"
              value={new Date(c.daily_reset_at).toLocaleTimeString("zh-CN", { timeStyle: "short" })}
              hint={`还有 ${remaining(c.daily_reset_at)}`}
            />
          </dl>
          <ul className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            {c.operations.map((op) => (
              <li
                key={op.name}
                className="overflow-hidden rounded-sm border border-white/10 bg-black/30"
              >
                {op.image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={op.image_url} alt="" className="aspect-[16/9] w-full object-cover" />
                ) : null}
                <div className="px-3 py-2.5 text-sm font-medium sm:px-4 sm:py-3 sm:text-base">
                  {op.name}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-sm border border-white/10 bg-black/30 px-3 py-3 sm:px-4">
      <dt className="text-xs text-white/45">{label}</dt>
      <dd className="mt-1 text-[15px] font-medium tabular-nums sm:text-lg">{value}</dd>
      <dd className="text-xs text-white/45">{hint}</dd>
    </div>
  );
}
