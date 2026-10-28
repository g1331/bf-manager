"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { SectionHeading } from "@/components/layout/SectionHeading";
import {
  bf1Api,
  type RosterChange,
  type RosterPlayer,
  type RosterSlot,
  type ServerRosterPoint,
} from "@/lib/api/bf1";
import { FACTION_SLUG } from "@/lib/bf1/factions";
import { cn } from "@/lib/utils";

type MapInfo = (mapName: string, mode: string | null) => { name: string; mode: string | null };

const CHANGE_LABEL: Record<RosterChange, string> = {
  joined: "进入",
  left: "退出",
  seated: "进场",
  switched: "换队",
};
const CHANGE_STYLE: Record<RosterChange, string> = {
  joined: "bg-emerald-500/15 text-emerald-300",
  left: "bg-amber-500/15 text-amber-200",
  seated: "bg-teal-500/15 text-teal-300",
  switched: "bg-sky-500/15 text-sky-300",
};
const ROW_STYLE: Partial<Record<RosterChange, string>> = {
  joined: "bg-emerald-500/[0.07]",
  left: "bg-amber-500/[0.07] text-white/55",
};
// 进入的排最前、退出的排最后，一眼看到这一轮的变化
const CHANGE_ORDER: Record<string, number> = {
  joined: 0,
  seated: 1,
  switched: 2,
  none: 3,
  left: 4,
};

function formatStamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** datetime-local 输入框的值（本地时间）↔ unix 秒 */
function toLocalInput(ts: number): string {
  const d = new Date(ts * 1000 - new Date().getTimezoneOffset() * 60_000);
  return d.toISOString().slice(0, 16);
}

/**
 * 服务器快照：全服统计每分钟记一次各服名单（官服也记），这里按时间列出采样点，点开看那一刻两队都有谁、
 * 这一轮谁进谁出谁换队。名单保留 7 天。
 */
export function SnapshotPanel({
  gameId,
  game,
  mapInfo,
}: {
  gameId: number;
  game: string;
  mapInfo: MapInfo;
}) {
  // 跳转时间：从这个时刻往前翻；为空时从最新开始
  const [jumpTo, setJumpTo] = useState<number | null>(null);
  const [changedOnly, setChangedOnly] = useState(true);
  const [selected, setSelected] = useState<number | null>(null);

  const list = useInfiniteQuery({
    queryKey: ["bf1-server-snapshots", gameId, jumpTo],
    queryFn: ({ pageParam }) => bf1Api.getServerSnapshots(gameId, pageParam),
    initialPageParam: jumpTo,
    getNextPageParam: (last) => last.next_before,
    refetchInterval: jumpTo == null ? 60_000 : false,
  });
  const items = useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data]);
  const shown = changedOnly ? items.filter((p) => p.joined || p.left) : items;
  const active = shown.find((p) => p.ts === selected) ?? shown[0] ?? null;

  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="bg-black/45 p-3.5 backdrop-blur-sm sm:p-6"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <SectionHeading className="mb-0">服务器快照</SectionHeading>
        <span className="text-[11px] text-white/40">每分钟记录一次名单 · 保留 7 天</span>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <input
              type="datetime-local"
              aria-label="跳到某个时间"
              value={jumpTo ? toLocalInput(jumpTo) : ""}
              onChange={(e) => {
                const t = Date.parse(e.target.value);
                setJumpTo(Number.isNaN(t) ? null : Math.floor(t / 1000) + 60);
                setSelected(null);
              }}
              className="h-8 min-w-0 flex-1 rounded-sm border border-white/15 bg-white/5 px-2 text-white/85 [color-scheme:dark]"
            />
            <button
              type="button"
              onClick={() => {
                setJumpTo(null);
                setSelected(null);
              }}
              className="h-8 rounded-sm border border-white/15 px-2.5 text-white/70 hover:bg-white/10"
            >
              最新
            </button>
          </div>
          <label className="mt-2 flex items-center gap-2 text-xs text-white/60">
            <input
              type="checkbox"
              checked={changedOnly}
              onChange={(e) => setChangedOnly(e.target.checked)}
              className="accent-amber-400"
            />
            只看有人进出的时刻
          </label>

          <ol className="mt-3 max-h-[640px] space-y-1.5 overflow-y-auto pr-1">
            {shown.map((p) => (
              <SnapshotItem
                key={p.ts}
                point={p}
                mapInfo={mapInfo}
                active={p.ts === active?.ts}
                onClick={() => setSelected(p.ts)}
              />
            ))}
            {!list.isLoading && shown.length === 0 ? (
              <li className="py-8 text-center text-xs text-white/40">
                {list.hasNextPage ? "这段时间没有记录，可以继续往前加载" : "暂无快照"}
              </li>
            ) : null}
          </ol>
          {list.hasNextPage ? (
            <button
              type="button"
              disabled={list.isFetchingNextPage}
              onClick={() => list.fetchNextPage()}
              className="mt-2 h-8 rounded-sm border border-white/15 text-xs text-white/70 hover:bg-white/10 disabled:opacity-50"
            >
              {list.isFetchingNextPage ? "加载中…" : "加载更早的"}
            </button>
          ) : null}
        </aside>

        {active ? (
          <SnapshotRoster gameId={gameId} game={game} point={active} mapInfo={mapInfo} />
        ) : (
          <div className="flex min-h-[240px] items-center justify-center text-sm text-white/40">
            {list.isLoading ? "正在加载快照…" : "选择左侧的一个时刻查看名单"}
          </div>
        )}
      </div>
    </Bf1Panel>
  );
}

function SnapshotItem({
  point,
  mapInfo,
  active,
  onClick,
}: {
  point: ServerRosterPoint;
  mapInfo: MapInfo;
  active: boolean;
  onClick: () => void;
}) {
  const info = point.map_name ? mapInfo(point.map_name, point.game_mode) : null;
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "w-full rounded-sm border px-3 py-2 text-left transition-colors",
          active
            ? "border-amber-400/60 bg-amber-400/10"
            : "border-white/10 bg-white/[0.03] hover:bg-white/[0.07]",
        )}
      >
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="text-white/75 tabular-nums">{formatStamp(point.ts)}</span>
          <span className="flex gap-1.5 tabular-nums">
            {point.joined ? <span className="text-emerald-300">+{point.joined}</span> : null}
            {point.left ? <span className="text-amber-200">−{point.left}</span> : null}
          </span>
        </div>
        <div className="mt-0.5 truncate text-sm font-semibold text-white">
          {info?.name ?? "未知地图"}
        </div>
        <div className="mt-0.5 flex gap-2.5 text-[11px] text-white/50">
          {info?.mode ? <span>{info.mode}</span> : null}
          <span>玩家 {point.players}</span>
          <span>排队 {point.queue}</span>
          <span>观战 {point.spectators}</span>
        </div>
      </button>
    </li>
  );
}

function SnapshotRoster({
  gameId,
  game,
  point,
  mapInfo,
}: {
  gameId: number;
  game: string;
  point: ServerRosterPoint;
  mapInfo: MapInfo;
}) {
  const [keyword, setKeyword] = useState("");
  const snap = useQuery({
    queryKey: ["bf1-server-snapshot", gameId, point.ts],
    queryFn: () => bf1Api.getServerSnapshot(gameId, point.ts),
    // 已经过去的时刻，名单不会再变
    staleTime: Infinity,
  });
  const info = point.map_name ? mapInfo(point.map_name, point.game_mode) : null;

  const groups = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    const by: Record<RosterSlot, RosterPlayer[]> = {
      team1: [],
      team2: [],
      queue: [],
      spectator: [],
    };
    for (const p of snap.data?.roster ?? []) {
      if (kw && !`${p.name ?? ""} ${p.persona_id}`.toLowerCase().includes(kw)) continue;
      by[p.slot].push(p);
    }
    for (const list of Object.values(by)) {
      list.sort(
        (a, b) =>
          CHANGE_ORDER[a.change ?? "none"] - CHANGE_ORDER[b.change ?? "none"] ||
          (a.name ?? "").localeCompare(b.name ?? ""),
      );
    }
    return by;
  }, [snap.data, keyword]);
  // 进入数含新排队的人，他们在下方排队区，单独标出来免得和两队人数对不上
  const queued = snap.data?.roster.filter(
    (p) => p.slot === "queue" && p.change === "joined",
  ).length;

  return (
    <section className="min-w-0">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-white/10 pb-3">
        <div>
          <div className="text-lg font-semibold text-white">{info?.name ?? "未知地图"}</div>
          <div className="text-xs text-white/50">
            {formatStamp(point.ts)}
            {info?.mode ? ` / ${info.mode}` : ""}
          </div>
        </div>
        <div className="flex items-center gap-4 text-center text-xs text-white/50">
          <Stat label="玩家" value={point.players} />
          <Stat label="排队" value={point.queue} />
          <Stat label="观战" value={point.spectators} />
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex gap-2">
          <span className={cn("rounded-sm px-2 py-0.5", CHANGE_STYLE.joined)}>
            进入 {point.joined}
            {queued ? `（排队 ${queued}）` : ""}
          </span>
          <span className={cn("rounded-sm px-2 py-0.5", CHANGE_STYLE.left)}>退出 {point.left}</span>
        </div>
        <label className="flex h-8 items-center gap-1.5 rounded-sm border border-white/15 bg-white/5 px-2 text-white/70">
          <Search className="size-3.5 text-white/40" />
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="筛选名字 / PID"
            className="w-36 bg-transparent outline-none placeholder:text-white/35"
          />
        </label>
      </div>

      {snap.isLoading ? (
        <div className="py-10 text-center text-sm text-white/40">正在加载名单…</div>
      ) : snap.isError ? (
        <div className="py-10 text-center text-sm text-white/45">这个时刻的名单暂时取不到</div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-1 gap-x-8 gap-y-6 lg:grid-cols-2">
            <RosterTable
              title={snap.data?.team1_faction ?? "队伍 1"}
              faction={snap.data?.team1_faction}
              players={groups.team1}
              game={game}
            />
            <RosterTable
              title={snap.data?.team2_faction ?? "队伍 2"}
              faction={snap.data?.team2_faction}
              players={groups.team2}
              game={game}
              className="lg:border-l lg:border-white/15 lg:pl-8"
            />
          </div>
          {groups.queue.length > 0 || groups.spectator.length > 0 ? (
            <div className="mt-6 grid grid-cols-1 gap-x-8 gap-y-6 border-t border-white/10 pt-4 lg:grid-cols-2">
              {groups.queue.length > 0 ? (
                <RosterTable title="排队中" players={groups.queue} game={game} />
              ) : null}
              {groups.spectator.length > 0 ? (
                <RosterTable title="旁观者" players={groups.spectator} game={game} />
              ) : null}
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div>{label}</div>
      <div className="text-base font-semibold text-white tabular-nums">{value}</div>
    </div>
  );
}

function RosterTable({
  title,
  faction,
  players,
  game,
  className,
}: {
  title: string;
  faction?: string | null;
  players: RosterPlayer[];
  game: string;
  className?: string;
}) {
  const present = players.filter((p) => p.change !== "left").length;
  const slug = faction ? FACTION_SLUG[faction] : undefined;
  return (
    <div className={cn("min-w-0", className)}>
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-white">
        {slug ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`/factions/${slug}.png`}
            alt={title}
            className="h-7 w-7 shrink-0 object-contain drop-shadow"
          />
        ) : null}
        {title}
        <span className="rounded-sm bg-white/10 px-1.5 text-[11px] font-normal text-white/70">
          {present} 人
        </span>
      </div>
      {players.length === 0 ? (
        <div className="py-4 text-xs text-white/35">无</div>
      ) : (
        <table className="w-full text-[13px]">
          <tbody>
            {players.map((p, i) => (
              <tr
                key={p.persona_id}
                className={cn(
                  "border-b border-white/[0.06] last:border-0",
                  p.change ? ROW_STYLE[p.change] : undefined,
                )}
              >
                <td className="w-8 py-[5px] pr-1 text-right text-[11px] text-white/35">{i + 1}</td>
                <td className="w-full py-[5px] pl-2 lg:max-w-0">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <Link
                      href={`/${game}/player/${p.persona_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="min-w-0 truncate font-medium hover:underline"
                      title={`${p.name ?? p.persona_id}（在新标签查看战绩）`}
                    >
                      {p.name ?? p.persona_id}
                    </Link>
                    {p.change ? (
                      <span
                        className={cn(
                          "shrink-0 rounded-sm px-1.5 text-[10px]",
                          CHANGE_STYLE[p.change],
                        )}
                      >
                        {CHANGE_LABEL[p.change]}
                      </span>
                    ) : null}
                  </div>
                </td>
                <td className="py-[5px] pl-3 text-right text-[11px] text-white/45 tabular-nums">
                  {p.persona_id}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
