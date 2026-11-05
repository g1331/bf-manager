"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import * as Popover from "@radix-ui/react-popover";
import { CalendarDays, Search, User, X } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { Tooltip } from "@/components/ui/tooltip";
import { SectionHeading } from "@/components/layout/SectionHeading";
import {
  FactionFlag,
  RoundDetailView,
  formatRoundTime,
  roundDuration,
} from "@/components/bf1/rounds/RoundDetailView";
import {
  DayBar,
  RoundCalendar,
  dayKey,
  dayRange,
  localTz,
} from "@/components/bf1/rounds/RoundCalendar";
import { ApiException } from "@/lib/api-client";
import type { RoundDay, RoundSummary } from "@/lib/api/bf1";
import { bf1Queries, type RoundsFilter } from "@/lib/queries/bf1";
import { cn } from "@/lib/utils";

/**
 * 服务器对局：每局结算时把在服玩家的生涯和进服时对比，算出这一局各人的战绩。服重启前后的实例
 * 合在一起列，保留 90 天。顶上可按日期（月历）和玩家筛选；一排地图卡片按结束时间从新到旧选局，
 * 下方整宽显示计分板。
 */
export function RoundsPanel({ gameId, game }: { gameId: number; game: string }) {
  // 从玩家对局等处带着 ?round= 跳进来时直接选中那一局（组件只在客户端挂载，可直接读 window）
  const [linked] = useState(() => {
    const v = Number(new URLSearchParams(window.location.search).get("round"));
    return Number.isSafeInteger(v) && v > 0 ? v : null;
  });
  const [selected, setSelected] = useState<number | null>(linked);
  const [day, setDay] = useState<string | null>(null);
  const [player, setPlayer] = useState<string | null>(null);
  const [tz] = useState(localTz);

  const calendar = useQuery({
    ...bf1Queries.serverRoundDays(gameId, tz, player),
    placeholderData: keepPreviousData,
    retry: (count, err) => !(err instanceof ApiException && err.status === 404) && count < 2,
    refetchInterval: 120_000,
  });
  // 换人时占位的是上一个人的日历，不能拿它的 personaId 去筛
  const resolved = player && !calendar.isPlaceholderData ? calendar.data?.player : null;
  const notFound =
    player != null && calendar.error instanceof ApiException && calendar.error.status === 404;
  const filter = useMemo<RoundsFilter>(
    () => ({
      ...(day ? dayRange(day) : {}),
      ...(resolved ? { player: resolved.persona_id } : {}),
    }),
    [day, resolved],
  );
  const live = !day || day === dayKey(new Date());
  const list = useInfiniteQuery({
    ...bf1Queries.serverRounds(gameId, filter),
    enabled: !player || resolved != null,
    placeholderData: keepPreviousData,
    refetchInterval: live ? 60_000 : false,
  });
  // 名字还没对上人（查找中或查无此人）时，列表里留着的是筛选前的局，不能显示
  const waiting = player != null && resolved == null;
  const items = useMemo(
    () => (waiting ? [] : (list.data?.pages.flatMap((p) => p.items) ?? [])),
    [list.data, waiting],
  );
  // 选中的局可能比已加载的更早，不在卡片里也照样显示计分板
  const activeId = selected ?? items[0]?.id ?? null;
  const select = (id: number) => {
    // 换筛选时占位的是上一组卡片，这时选中的局可能不在新结果里
    if (list.isPlaceholderData) return;
    setSelected(id);
    window.history.replaceState(null, "", `?round=${id}#rounds`);
  };
  const filtered = day != null || player != null;
  const pickDay = (d: string | null) => {
    setDay(d);
    setSelected(null);
  };

  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="bg-black/45 p-4 backdrop-blur-sm sm:p-6"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <SectionHeading className="mb-0">对局</SectionHeading>
        <span className="text-[11px] text-white/40">由每局前后的生涯差值算出 · 保留 90 天</span>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <DayPicker
          day={day}
          days={calendar.data?.days ?? []}
          loading={calendar.isLoading}
          onSelect={pickDay}
        />
        <PlayerFilter
          key={player ?? ""}
          value={player}
          resolvedName={resolved ? (resolved.name ?? String(resolved.persona_id)) : null}
          notFound={notFound}
          onChange={(q) => {
            setPlayer(q);
            setSelected(null);
          }}
        />
      </div>
      {day ? (
        <div className="mt-3 max-w-md">
          <DayBar day={day} days={calendar.data?.days ?? []} onSelect={pickDay} />
        </div>
      ) : null}

      {items.length === 0 ? (
        <div className="flex min-h-[240px] items-center justify-center text-sm text-white/40">
          {notFound
            ? "没找到这个玩家，请填完整名字或 PID"
            : list.isLoading || (waiting && !calendar.isError)
              ? "正在加载对局…"
              : list.isError || calendar.isError
                ? "对局加载失败，请稍后重试"
                : filtered
                  ? "没有符合条件的对局"
                  : "还没有记录到对局，每局结束后一两分钟出现在这里"}
        </div>
      ) : (
        <div
          aria-busy={list.isPlaceholderData}
          className={cn(list.isPlaceholderData && "pointer-events-none opacity-60")}
        >
          <ol className="-mx-1 mt-4 flex snap-x gap-2 overflow-x-auto px-1 pb-2">
            {items.map((r) => (
              <RoundCard
                key={r.id}
                round={r}
                active={r.id === activeId}
                scrollIntoView={r.id === linked}
                onClick={() => select(r.id)}
              />
            ))}
            {list.hasNextPage ? (
              <li className="shrink-0">
                <button
                  type="button"
                  disabled={list.isFetchingNextPage}
                  onClick={() => list.fetchNextPage()}
                  className="h-full w-24 rounded-sm border border-dashed border-white/20 text-xs text-white/60 hover:bg-white/10 disabled:opacity-50"
                >
                  {list.isFetchingNextPage ? "加载中…" : "更早的对局"}
                </button>
              </li>
            ) : null}
          </ol>
          {activeId != null ? (
            <div className="mt-4">
              <RoundDetailView roundId={activeId} game={game} highlight={resolved?.persona_id} />
            </div>
          ) : null}
        </div>
      )}
    </Bf1Panel>
  );
}

/** 「日期」按钮，点开是对局月历；选中的那天由下面的日期条显示 */
function DayPicker({
  day,
  days,
  loading,
  onSelect,
}: {
  day: string | null;
  days: RoundDay[];
  loading: boolean;
  onSelect: (day: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className={cn(
            "compact-action flex h-11 shrink-0 items-center gap-1.5 rounded-sm border px-3 text-[13px] sm:h-8 sm:text-xs",
            open || day ? "border-amber-400/50 text-amber-200" : "border-white/15 text-white/70",
            "hover:bg-white/10",
          )}
        >
          <CalendarDays className="size-4" />
          日期
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          collisionPadding={8}
          className="z-50 w-[min(18rem,calc(100vw-16px))] border border-white/15 bg-[#14161a]/95 p-3 shadow-[0_8px_24px_rgba(0,0,0,0.5)] backdrop-blur-sm"
        >
          <RoundCalendar
            days={days}
            selected={day}
            loading={loading}
            onSelect={(d) => {
              onSelect(d);
              setOpen(false);
            }}
          />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** 按玩家筛：回车提交完整名字或 PID；筛上之后显示成可清除的标签 */
function PlayerFilter({
  value,
  resolvedName,
  notFound,
  onChange,
}: {
  value: string | null;
  resolvedName: string | null;
  notFound: boolean;
  onChange: (q: string | null) => void;
}) {
  const [text, setText] = useState(value ?? "");
  if (value && resolvedName)
    return (
      <span className="flex h-11 max-w-full min-w-0 items-center gap-1 rounded-sm border border-amber-400/50 pl-3 text-[13px] text-amber-200 sm:h-8 sm:text-xs">
        <User className="size-3.5 shrink-0" />
        <span className="truncate">{resolvedName}</span>
        <button
          type="button"
          aria-label="不按玩家筛选"
          onClick={() => onChange(null)}
          className="compact-action flex h-full w-9 shrink-0 items-center justify-center text-white/60 hover:text-white sm:w-7"
        >
          <X className="size-3.5" />
        </button>
      </span>
    );
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        onChange(text.trim() || null);
      }}
      className={cn(
        "flex h-11 min-w-0 flex-1 items-center gap-1.5 rounded-sm border bg-white/5 px-3 text-[13px] text-white/70 sm:h-8 sm:max-w-64 sm:px-2 sm:text-xs",
        notFound ? "border-red-400/60" : "border-white/15",
      )}
    >
      <Search className="size-3.5 shrink-0 text-white/40" />
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        enterKeyHint="search"
        aria-label="按玩家筛选"
        placeholder="玩家名 / PID，回车筛选"
        className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-white/35"
      />
    </form>
  );
}

function RoundCard({
  round: r,
  active,
  scrollIntoView,
  onClick,
}: {
  round: RoundSummary;
  active: boolean;
  scrollIntoView: boolean;
  onClick: () => void;
}) {
  const winner = r.winner === 1 ? r.team1_faction : r.winner === 2 ? r.team2_faction : null;
  const ref = useRef<HTMLLIElement>(null);
  // 跳进来的那一局可能排在横条后面，挂载时滚到它
  useEffect(() => {
    if (scrollIntoView) ref.current?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [scrollIntoView]);
  return (
    <li ref={ref} className="shrink-0 snap-start">
      <button
        type="button"
        onClick={onClick}
        aria-pressed={active}
        className={cn(
          "relative block h-[4.5rem] w-48 overflow-hidden rounded-sm border text-left transition-colors",
          active ? "border-amber-400" : "border-white/10 hover:border-white/30",
        )}
      >
        {r.map_image_url ? (
          <img
            src={r.map_image_url}
            alt=""
            loading="lazy"
            className={cn(
              "absolute inset-0 h-full w-full object-cover transition-opacity",
              active ? "opacity-55" : "opacity-30",
            )}
          />
        ) : null}
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 to-black/30" />
        {active ? <span className="absolute inset-x-0 bottom-0 h-0.5 bg-amber-400" /> : null}
        {winner ? (
          <Tooltip content={`${winner} 胜`}>
            <span className="absolute right-2.5 bottom-2 z-10 flex">
              <FactionFlag faction={winner} won className="size-6" />
            </span>
          </Tooltip>
        ) : null}
        <div className="relative flex h-full flex-col justify-between px-2.5 py-1.5">
          <div className="flex items-center justify-between gap-2 text-[11px] text-white/70 tabular-nums">
            <span>{formatRoundTime(r.ended_at)}</span>
            <span className="text-white/50">{roundDuration(r)}</span>
          </div>
          <div>
            <div className="truncate text-sm font-semibold text-white">
              {r.map_display_name ?? r.map_name ?? "未知地图"}
            </div>
            <div className="flex gap-2 pr-10 text-[11px] text-white/55">
              {r.mode_display_name ? (
                <span className="truncate text-amber-300/80">{r.mode_display_name}</span>
              ) : null}
              <span className="shrink-0">{r.player_count} 人</span>
              {!r.settled ? <span className="shrink-0">未打完</span> : null}
            </div>
          </div>
        </div>
      </button>
    </li>
  );
}
