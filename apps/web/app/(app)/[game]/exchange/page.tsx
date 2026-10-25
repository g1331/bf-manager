"use client";

/**
 * 交换（Scrap Exchange）：每周轮换的皮肤兑换清单，可回看历史各期。
 *
 * 后端每小时问一次 EA，物品有变化即记为新一期；更早的期数来自 umrbot 的旧存档（2022-07 起）。
 * 期数按北京时间日期标识，选中某期即按该日期查询当天生效的清单。
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { bf1Api } from "@/lib/api/bf1";
import { skinRarityFromName, skinRarityHex } from "@/lib/bf1/rarity";
import { cn } from "@/lib/utils";

const RARITY_ORDER: Record<string, number> = { Superior: 0, Enhanced: 1, Standard: 2 };
const RARITY_LABEL: Record<string, string> = {
  Superior: "传奇",
  Enhanced: "精英",
  Standard: "特殊",
};

/** 北京时间的 YYYY-MM-DD */
function cnDate(iso: string): string {
  return new Date(iso).toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" });
}

export default function ExchangePage() {
  const [date, setDate] = useState<string | undefined>();

  const periods = useQuery({
    queryKey: ["bf1-exchange-periods"],
    queryFn: () => bf1Api.getExchangePeriods(),
  });
  const q = useQuery({
    queryKey: ["bf1-exchange", date ?? "latest"],
    queryFn: () => bf1Api.getExchange(date),
  });

  const dates = (periods.data ?? []).map(cnDate);
  const current = q.data ? cnDate(q.data.captured_at) : date;
  const index = current ? dates.indexOf(current) : -1;
  const items = [...(q.data?.items ?? [])].sort(
    (a, b) => (RARITY_ORDER[a.rarity] ?? 9) - (RARITY_ORDER[b.rarity] ?? 9) || b.price - a.price,
  );

  return (
    <main className="flex flex-col gap-4 py-6 text-white">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="font-display flex items-center gap-2 text-xs font-medium tracking-[0.2em] text-amber-500 uppercase">
            <span className="h-[2px] w-6 bg-amber-500" />
            Scrap Exchange
          </div>
          <h1 className="mt-1.5 text-2xl font-bold tracking-wide sm:text-3xl">交换</h1>
        </div>
        {dates.length > 0 ? (
          <div className="flex items-center gap-1.5">
            <PeriodButton
              label="上一期"
              disabled={index < 0 || index >= dates.length - 1}
              onClick={() => setDate(dates[index + 1])}
            >
              <ChevronLeft className="size-4" />
            </PeriodButton>
            <select
              value={index >= 0 ? current : ""}
              onChange={(e) => setDate(e.target.value)}
              aria-label="选择期数"
              className="h-9 rounded-sm border border-white/15 bg-black/40 px-3 text-sm tabular-nums"
            >
              {index < 0 ? <option value="">选择期数</option> : null}
              {dates.map((d, i) => (
                <option key={d + i} value={d}>
                  {d}
                  {i === 0 ? "（当期）" : ""}
                </option>
              ))}
            </select>
            <PeriodButton
              label="下一期"
              disabled={index <= 0}
              onClick={() => setDate(dates[index - 1])}
            >
              <ChevronRight className="size-4" />
            </PeriodButton>
          </div>
        ) : null}
      </header>

      {q.isLoading ? (
        <div className="py-16 text-center text-sm text-white/45">加载中…</div>
      ) : q.isError ? (
        <div className="rounded-sm border border-dashed border-white/15 py-16 text-center text-sm text-white/45">
          暂无交换记录，请稍后重试。
        </div>
      ) : (
        <>
          <p className="text-xs text-white/45">
            {index === 0 ? "当期" : "历史"} · {current} 起 · 共 {items.length} 件
          </p>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
            {items.map((item) => (
              <li
                key={item.key}
                className="flex flex-col overflow-hidden rounded-sm border border-white/10 bg-black/30"
              >
                <div className="flex aspect-[2/1] items-center justify-center bg-white/[0.03] p-3">
                  {item.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={item.image_url}
                      alt=""
                      loading="lazy"
                      className="max-h-full max-w-full object-contain"
                    />
                  ) : null}
                </div>
                <div className="flex flex-1 flex-col gap-0.5 px-3 py-2.5">
                  <span
                    className="truncate text-sm font-medium"
                    style={{ color: skinRarityHex[skinRarityFromName(item.rarity)] }}
                    title={item.name}
                  >
                    {item.name}
                  </span>
                  <span className="truncate text-xs text-white/55" title={item.parent_name ?? ""}>
                    {item.parent_name ?? item.category ?? "—"}
                  </span>
                  <div className="mt-auto flex items-center justify-between pt-1.5 text-xs">
                    <span className="text-white/40">
                      {RARITY_LABEL[item.rarity] ?? item.rarity}
                    </span>
                    <span className="font-medium text-amber-400 tabular-nums">
                      {item.price.toLocaleString("en-US")} 废料
                    </span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}

function PeriodButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex size-9 items-center justify-center rounded-sm border border-white/15 bg-black/40 text-white/70 transition-colors",
        "hover:text-white disabled:opacity-30 disabled:hover:text-white/70",
      )}
    >
      {children}
    </button>
  );
}
