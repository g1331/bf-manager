"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { bf1Api } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";
import { usePageState } from "@/hooks/useNavigation";
import { useNowSeconds } from "@/components/bf1/server-detail/history";

const WINDOWS = [
  { days: 1, label: "近 24 小时" },
  { days: 7, label: "近 7 天" },
] as const;

/** 秒 → 「12 小时 5 分」/「42 分钟」 */
function fmtDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h} 小时 ${m} 分` : `${m} 分钟`;
}

function fmtAgo(ts: number, now: number): string {
  const min = Math.floor((now - ts) / 60);
  if (min < 60) return `${Math.max(min, 1)} 分钟前`;
  if (min < 24 * 60) return `${Math.floor(min / 60)} 小时前`;
  return `${Math.floor(min / 1440)} 天前`;
}

/**
 * 服务器排行：由每分钟的名单快照算出每人在这台服两队里待了多久（排队、观战不算），
 * 服务器重启前后的各个实例按 serverId 合并计算（真官服没有持久身份，只算当前实例）。名单只保留 7 天。
 */
export function LeaderboardPanel({ gameId, game }: { gameId: number; game: string }) {
  const [days, setDays] = usePageState<number>("server-leaderboard-days", 7);
  const board = useQuery({
    queryKey: ["bf1-server-leaderboard", gameId, days],
    queryFn: () => bf1Api.getServerLeaderboard(gameId, days),
    staleTime: 60_000,
  });
  const items = board.data?.items ?? [];
  const now = useNowSeconds();

  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="bg-black/45 p-4 backdrop-blur-sm sm:p-6"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <SectionHeading className="mb-0">常客排行</SectionHeading>
        <div className="flex items-center gap-3">
          {board.data ? (
            <span className="text-[11px] text-white/40 tabular-nums">
              共 {board.data.total_players} 人上过场 · 按在队时长
            </span>
          ) : null}
          <div className="flex border border-white/15 text-xs">
            {WINDOWS.map((w) => (
              <button
                key={w.days}
                type="button"
                onClick={() => setDays(w.days)}
                className={cn(
                  "compact-action h-9 px-3 transition-colors sm:h-7 sm:px-2.5",
                  days === w.days ? "bg-amber-400 text-black" : "text-white/65 hover:bg-white/10",
                )}
              >
                {w.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm sm:min-w-[560px]">
          <thead>
            <tr className="border-b border-white/10 text-left text-[11px] text-white/45">
              <th className="w-10 py-2 font-normal">#</th>
              <th className="py-2 font-normal">玩家</th>
              <th className="py-2 text-right font-normal">在队时长</th>
              {/* 手机上这三列并进玩家名下面一行，表格不再横向滚动 */}
              <th className="hidden py-2 text-right font-normal sm:table-cell">活跃天数</th>
              <th className="hidden py-2 text-right font-normal sm:table-cell">进服次数</th>
              <th className="hidden py-2 text-right font-normal sm:table-cell">最近在服</th>
            </tr>
          </thead>
          <tbody>
            {items.map((p, i) => (
              <tr key={p.persona_id} className="border-b border-white/5 hover:bg-white/[0.04]">
                <td
                  className={cn(
                    "py-2 font-semibold tabular-nums",
                    i < 3 ? "text-amber-300" : "text-white/45",
                  )}
                >
                  {i + 1}
                </td>
                <td className="w-full max-w-0 py-2.5 sm:w-auto sm:max-w-[16rem] sm:py-2">
                  <Link
                    href={`/${game}/player/${p.persona_id}`}
                    className="block truncate text-[15px] text-white hover:text-amber-300 sm:inline sm:text-sm"
                  >
                    {p.name ?? p.persona_id}
                  </Link>
                  <div className="mt-0.5 truncate text-xs text-white/45 tabular-nums sm:hidden">
                    活跃 {p.days} 天 · 进服 {p.joins} 次 ·{" "}
                    {p.online ? (
                      <span className="text-emerald-300">在服</span>
                    ) : (
                      fmtAgo(p.last_seen, now)
                    )}
                  </div>
                </td>
                <td className="py-2 pl-3 text-right whitespace-nowrap text-white tabular-nums">
                  {fmtDuration(p.seconds)}
                </td>
                <td className="hidden py-2 text-right text-white/70 tabular-nums sm:table-cell">
                  {p.days}
                </td>
                <td className="hidden py-2 text-right text-white/70 tabular-nums sm:table-cell">
                  {p.joins}
                </td>
                <td className="hidden py-2 text-right text-xs tabular-nums sm:table-cell">
                  {p.online ? (
                    <span className="text-emerald-300">在服</span>
                  ) : (
                    <span className="text-white/50">{fmtAgo(p.last_seen, now)}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!board.isLoading && items.length === 0 ? (
          <p className="py-10 text-center text-xs text-white/40">
            {board.isError ? "排行加载失败，请稍后重试" : "这段时间没有记录"}
          </p>
        ) : null}
        {board.isLoading ? (
          <p className="py-10 text-center text-xs text-white/40">正在统计…</p>
        ) : null}
      </div>
    </Bf1Panel>
  );
}
