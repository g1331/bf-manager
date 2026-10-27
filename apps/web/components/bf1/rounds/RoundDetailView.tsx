"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { bf1Api, type RoundPlayer, type RoundSummary } from "@/lib/api/bf1";
import { classLabel, isKnownClass } from "@/components/bf1/player-detail/format";
import { FACTION_SLUG } from "@/lib/bf1/factions";
import { cn } from "@/lib/utils";

export function formatRoundTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** 对局时长；没看到开局的局只知道「至少」这么久 */
export function roundDuration(r: RoundSummary): string {
  const min = Math.max(1, Math.round((r.ended_at - r.started_at) / 60));
  return `${r.observed_start ? "" : "≥ "}${min} 分钟`;
}

export function kitLabel(kit: string | null): string {
  if (!kit) return "—";
  return kit === "elite" ? "精英兵" : classLabel(kit);
}

export function KitIcon({ kit, className }: { kit: string | null; className?: string }) {
  if (!isKnownClass(kit)) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`/bf1/soldiers/${kit}.png`}
      alt={kitLabel(kit)}
      title={kitLabel(kit)}
      className={cn("size-4 shrink-0 object-contain opacity-80", className)}
    />
  );
}

const STATUS_BADGE: Record<RoundPlayer["status"], string | null> = {
  finished: null,
  left: "中途退出",
  suspect: "存疑",
};

/**
 * 单局详情：两队各人这一局的击杀、死亡、得分等。战绩是进出服时的生涯差值，中途退出的人没有胜负；
 * 「存疑」是增量里混进了别的局（如刚从别的服过来、那边的结算晚到），数字仅供参考。
 */
export function RoundDetailView({
  roundId,
  game,
  highlight,
}: {
  roundId: number;
  game: string;
  highlight?: number;
}) {
  const q = useQuery({
    queryKey: ["bf1-round", roundId],
    queryFn: () => bf1Api.getRound(roundId),
    // 对局结束后不会再变
    staleTime: Infinity,
  });
  if (q.isLoading) {
    return <div className="py-10 text-center text-sm text-white/40">正在加载对局…</div>;
  }
  if (q.isError || !q.data) {
    return <div className="py-10 text-center text-sm text-white/45">这一局的数据暂时取不到</div>;
  }
  const r = q.data;
  const teams = [1, 2] as const;
  const faction = (t: 1 | 2) => (t === 1 ? r.team1_faction : r.team2_faction);

  return (
    <section className="min-w-0">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-white/10 pb-3">
        <div className="min-w-0">
          <div className="text-lg font-semibold text-white">
            {r.map_display_name ?? r.map_name ?? "未知地图"}
          </div>
          <div className="truncate text-xs text-white/50">
            {formatRoundTime(r.started_at)} – {formatRoundTime(r.ended_at)} · {roundDuration(r)}
            {r.mode_display_name ? ` · ${r.mode_display_name}` : ""}
          </div>
          {r.server_name ? (
            <Link
              href={`/${game}/server/${r.game_id}`}
              className="mt-0.5 block truncate text-xs text-white/40 hover:text-amber-300"
            >
              {r.server_name}
            </Link>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-1.5 text-[11px]">
          {!r.settled ? (
            <span className="rounded-sm bg-white/10 px-2 py-0.5 text-white/60">未打完</span>
          ) : null}
          {!r.observed_start ? (
            <span
              className="rounded-sm bg-white/10 px-2 py-0.5 text-white/60"
              title="开始统计时这一局已经开打，开局后很快退出的人可能不全"
            >
              中途接手统计
            </span>
          ) : null}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-x-8 gap-y-6 xl:grid-cols-2">
        {teams.map((t) => (
          <TeamTable
            key={t}
            title={faction(t) ?? `队伍 ${t}`}
            faction={faction(t)}
            won={r.winner == null ? null : r.winner === t}
            players={r.players.filter((p) => p.team === t)}
            game={game}
            highlight={highlight}
            className={t === 2 ? "xl:border-l xl:border-white/15 xl:pl-8" : undefined}
          />
        ))}
      </div>
      <p className="mt-4 text-[11px] leading-relaxed text-white/35">
        战绩是进服前与结算（或退出）后的生涯差值；时长按各兵种在场时间计。中途退出的人没有胜负，
        「存疑」表示增量里可能混进了别的局。
      </p>
    </section>
  );
}

function TeamTable({
  title,
  faction,
  won,
  players,
  game,
  highlight,
  className,
}: {
  title: string;
  faction: string | null;
  won: boolean | null;
  players: RoundPlayer[];
  game: string;
  highlight?: number;
  className?: string;
}) {
  const slug = faction ? FACTION_SLUG[faction] : undefined;
  const sum = (k: "kills" | "deaths" | "score") => players.reduce((n, p) => n + p[k], 0);
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
        <span className="truncate">{title}</span>
        {won != null ? (
          <span
            className={cn(
              "rounded-sm px-1.5 text-[11px] font-semibold",
              won ? "bg-amber-400 text-black" : "bg-white/10 text-white/60",
            )}
          >
            {won ? "胜" : "负"}
          </span>
        ) : null}
        <span className="ml-auto text-[11px] font-normal text-white/45 tabular-nums">
          {players.length} 人 · 击杀 {sum("kills")} · 得分 {sum("score").toLocaleString("en-US")}
        </span>
      </div>
      {players.length === 0 ? (
        <div className="py-4 text-xs text-white/35">无</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[420px] text-[13px]">
            <thead>
              <tr className="border-b border-white/10 text-left text-[11px] text-white/40">
                <th className="w-7 py-1.5 font-normal" />
                <th className="py-1.5 font-normal">玩家</th>
                <th className="py-1.5 text-right font-normal">击杀</th>
                <th className="py-1.5 text-right font-normal">死亡</th>
                <th className="py-1.5 text-right font-normal">得分</th>
                <th className="py-1.5 text-right font-normal">SPM</th>
                <th className="py-1.5 text-right font-normal">KD</th>
              </tr>
            </thead>
            <tbody>
              {players.map((p, i) => (
                <tr
                  key={p.persona_id}
                  className={cn(
                    "border-b border-white/[0.06] last:border-0",
                    p.persona_id === highlight && "bg-amber-400/10",
                    p.status !== "finished" && "text-white/55",
                  )}
                >
                  <td className="py-[5px] pr-1 text-right text-[11px] text-white/35 tabular-nums">
                    {i + 1}
                  </td>
                  <td className="max-w-0 py-[5px] pl-2">
                    <div className="flex min-w-0 items-center gap-1.5">
                      <KitIcon kit={p.kit} />
                      <Link
                        href={`/${game}/player/${p.persona_id}`}
                        className="min-w-0 truncate font-medium hover:underline"
                        title={`${p.name ?? p.persona_id} · ${kitLabel(p.kit)}`}
                      >
                        {p.name ?? p.persona_id}
                      </Link>
                      {STATUS_BADGE[p.status] ? (
                        <span className="shrink-0 rounded-sm bg-white/10 px-1.5 text-[10px] text-white/55">
                          {STATUS_BADGE[p.status]}
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="py-[5px] pl-2 text-right tabular-nums">{p.kills}</td>
                  <td className="py-[5px] pl-2 text-right tabular-nums">{p.deaths}</td>
                  <td className="py-[5px] pl-2 text-right tabular-nums">
                    {p.score.toLocaleString("en-US")}
                  </td>
                  <td className="py-[5px] pl-2 text-right text-white/70 tabular-nums">
                    {p.spm ?? "—"}
                  </td>
                  <td className="py-[5px] pl-2 text-right text-white/70 tabular-nums">
                    {p.kd != null ? p.kd.toFixed(2) : p.kills ? "∞" : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
