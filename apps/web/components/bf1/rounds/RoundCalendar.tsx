"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { Tooltip } from "@/components/ui/tooltip";
import type { RoundDay } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

/** 对局保留 90 天，日历最早只翻到这么久以前 */
const RETENTION_DAYS = 90;
const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

/** 浏览器所在时区的 UTC 偏移（分钟，东正西负），后端按它给日期分组 */
export function localTz(): number {
  return -new Date().getTimezoneOffset();
}

/** 本地日期 → YYYY-MM-DD */
export function dayKey(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${String(d.getDate()).padStart(2, "0")}`;
}

function parseDay(key: string): Date {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** 某一天在本地时区的 [since, until)，unix 秒 */
export function dayRange(key: string): { since: number; until: number } {
  const d = parseDay(key);
  const next = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1);
  return { since: d.getTime() / 1000, until: next.getTime() / 1000 };
}

/** 11 月 3 日 周一；不是今年的带上年份 */
export function dayTitle(key: string): string {
  const d = parseDay(key);
  const year = d.getFullYear() === new Date().getFullYear() ? "" : `${d.getFullYear()} 年 `;
  return `${year}${d.getMonth() + 1} 月 ${d.getDate()} 日 周${WEEKDAYS[(d.getDay() + 6) % 7]}`;
}

/** 一天的概况：12 局 · 7 胜 · 230 杀（胜场击杀只有玩家日历有） */
export function daySummary(d: RoundDay): string {
  const parts = [`${d.rounds} 局`];
  if (d.wins != null) parts.push(`${d.wins} 胜`);
  if (d.kills != null) parts.push(`${d.kills} 杀`);
  return parts.join(" · ");
}

function monthStart(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

/**
 * 对局月历：每格一天，颜色深浅表示当天局数，没有对局的日子不能点。选中的日子再点一次取消。
 * 周一在前；最早翻到保留期开始的那个月。
 */
export function RoundCalendar({
  days,
  selected,
  onSelect,
  loading = false,
  className,
}: {
  days: RoundDay[];
  selected: string | null;
  onSelect: (day: string | null) => void;
  loading?: boolean;
  className?: string;
}) {
  const today = new Date();
  const todayKey = dayKey(today);
  const earliest = new Date(
    today.getFullYear(),
    today.getMonth(),
    today.getDate() - RETENTION_DAYS,
  );
  const earliestKey = dayKey(earliest);
  const [month, setMonth] = useState(() => monthStart(selected ? parseDay(selected) : today));
  // 选中的日子换到别的月份时（翻前一天 / 后一天），月历跟过去；渲染期同步，不用 effect
  const [shownFor, setShownFor] = useState(selected);
  if (selected !== shownFor) {
    setShownFor(selected);
    if (selected) setMonth(monthStart(parseDay(selected)));
  }

  const byDay = useMemo(() => new Map(days.map((d) => [d.day, d])), [days]);
  const max = useMemo(() => Math.max(1, ...days.map((d) => d.rounds)), [days]);
  const total = days.reduce((n, d) => n + d.rounds, 0);

  const canPrev = month > monthStart(earliest);
  const canNext = month < monthStart(today);
  const lead = (month.getDay() + 6) % 7;
  const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells: (Date | null)[] = [
    ...Array.from({ length: lead }, () => null),
    ...Array.from(
      { length: count },
      (_, i) => new Date(month.getFullYear(), month.getMonth(), i + 1),
    ),
  ];
  while (cells.length % 7) cells.push(null);

  const shift = (n: number) => setMonth(new Date(month.getFullYear(), month.getMonth() + n, 1));
  const navButton =
    "compact-action flex size-8 items-center justify-center rounded-sm text-white/60 hover:bg-white/10 hover:text-white disabled:pointer-events-none disabled:opacity-25";

  return (
    <div className={cn("w-full select-none", className)}>
      <div className="flex items-center justify-between">
        <button
          type="button"
          aria-label="上个月"
          disabled={!canPrev}
          onClick={() => shift(-1)}
          className={navButton}
        >
          <ChevronLeft className="size-4" />
        </button>
        <span className="text-sm font-semibold text-white/85 tabular-nums">
          {month.getFullYear()} 年 {month.getMonth() + 1} 月
        </span>
        <button
          type="button"
          aria-label="下个月"
          disabled={!canNext}
          onClick={() => shift(1)}
          className={navButton}
        >
          <ChevronRight className="size-4" />
        </button>
      </div>

      <div className="mt-2 grid grid-cols-7 gap-1 text-center">
        {WEEKDAYS.map((w) => (
          <span key={w} className="pb-0.5 text-[10px] text-white/35">
            {w}
          </span>
        ))}
        {cells.map((d, i) => {
          if (!d) return <span key={`blank-${i}`} />;
          const key = dayKey(d);
          const info = byDay.get(key);
          const n = info?.rounds ?? 0;
          const inRange = key >= earliestKey && key <= todayKey;
          const active = key === selected;
          const level = n ? Math.min(4, Math.ceil((n / max) * 4)) : 0;
          const cell = (
            <button
              key={key}
              type="button"
              disabled={!n}
              aria-pressed={active}
              aria-label={`${dayTitle(key)}${info ? `，${daySummary(info)}` : "，没有对局"}`}
              onClick={() => onSelect(active ? null : key)}
              className={cn(
                "compact-action relative flex aspect-square min-h-0 flex-col items-center justify-center rounded-sm border text-xs tabular-nums transition-colors",
                !inRange && "opacity-30",
                level === 0 && "border-transparent text-white/30",
                level === 1 && "border-transparent bg-amber-400/15 text-white/80",
                level === 2 && "border-transparent bg-amber-400/30 text-white/90",
                level === 3 && "border-transparent bg-amber-400/50 text-white",
                level === 4 && "border-transparent bg-amber-400/75 font-semibold text-black",
                n > 0 && !active && "hover:border-white/50",
                key === todayKey && !active && "border-white/35",
                active && "border-amber-300 ring-1 ring-amber-300",
                loading && "animate-pulse",
              )}
            >
              <span className="leading-none">{d.getDate()}</span>
              {n ? (
                <span
                  className={cn(
                    "mt-0.5 text-[9px] leading-none",
                    level === 4 ? "text-black/65" : "text-white/55",
                  )}
                >
                  {n}
                </span>
              ) : null}
            </button>
          );
          return info ? (
            <Tooltip key={key} content={`${dayTitle(key)} · ${daySummary(info)}`}>
              {cell}
            </Tooltip>
          ) : (
            cell
          );
        })}
      </div>

      <p className="mt-2 text-[11px] text-white/40 tabular-nums">
        {loading
          ? "加载中…"
          : total
            ? `近 ${RETENTION_DAYS} 天 ${total} 局 · ${days.length} 天有对局`
            : "没有对局"}
      </p>
    </div>
  );
}

/**
 * 选中某一天后列表顶上的一条：日期、当天概况，前后翻到相邻有对局的日子，或回到全部。
 */
export function DayBar({
  day,
  days,
  onSelect,
}: {
  day: string;
  days: RoundDay[];
  onSelect: (day: string | null) => void;
}) {
  const i = days.findIndex((d) => d.day === day);
  const info = i >= 0 ? days[i] : null;
  // days 按日期升序：前一个是更早的有对局的日子
  const prev = i > 0 ? days[i - 1].day : null;
  const next = i >= 0 && i + 1 < days.length ? days[i + 1].day : null;
  const nav =
    "compact-action flex size-8 items-center justify-center rounded-sm text-white/60 hover:bg-white/10 hover:text-white disabled:pointer-events-none disabled:opacity-25";
  return (
    <div className="flex items-center gap-1 rounded-sm border border-amber-400/30 bg-amber-400/[0.07] py-1 pr-1 pl-3">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-white">{dayTitle(day)}</div>
        {info ? (
          <div className="text-[11px] text-white/55 tabular-nums">{daySummary(info)}</div>
        ) : null}
      </div>
      <button
        type="button"
        aria-label="更早一天"
        disabled={!prev}
        onClick={() => prev && onSelect(prev)}
        className={nav}
      >
        <ChevronLeft className="size-4" />
      </button>
      <button
        type="button"
        aria-label="更晚一天"
        disabled={!next}
        onClick={() => next && onSelect(next)}
        className={nav}
      >
        <ChevronRight className="size-4" />
      </button>
      <button type="button" aria-label="看全部日期" onClick={() => onSelect(null)} className={nav}>
        <X className="size-4" />
      </button>
    </div>
  );
}
