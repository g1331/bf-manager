"use client";

import { Fragment, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { bf1Api, type RoundDetail, type RoundPlayer, type RoundSummary } from "@/lib/api/bf1";
import { classLabel } from "@/components/bf1/player-detail/format";
import { RoundPlayerBreakdown } from "@/components/bf1/rounds/RoundPlayerBreakdown";
import { FACTION_SLUG } from "@/lib/bf1/factions";
import { cn } from "@/lib/utils";
import { TipLine } from "@/components/bf1/codex/TipLine";

export function formatRoundTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatClock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

/** 对局时长；没看到开局的局只知道「至少」这么久 */
export function roundDuration(r: RoundSummary): string {
  const min = Math.max(1, Math.round((r.ended_at - r.started_at) / 60));
  return `${r.observed_start ? "" : "≥ "}${min} 分钟`;
}

/** 服务器详情「对局」分区里选中这一局；用这台服现在的 gameId，重启前的局也能打开 */
export function roundHref(game: string, r: RoundSummary): string {
  return `/${game}/server/${r.server_game_id}?round=${r.id}#rounds`;
}

export function kitLabel(kit: string | null): string {
  if (!kit) return "—";
  return kit === "elite" ? "精英兵" : classLabel(kit);
}

const KIT_ICONS: Record<string, string> = {
  assault: "/bf1/kits/assault.png",
  medic: "/bf1/kits/medic.png",
  support: "/bf1/kits/support.png",
  scout: "/bf1/kits/scout.png",
  tanker: "/bf1/kits/tanker.png",
  pilot: "/bf1/kits/pilot.png",
  cavalry: "/bf1/kits/cavalry.png",
  elite: "/bf1/kits/elite.svg",
};

/**
 * 兵种图标：BF1 游戏内的兵种标志（突击爆炸、医疗十字、支援子弹、侦察瞄准镜、坦克齿轮、
 * 飞行螺旋桨、骑兵马蹄铁），白色单色图放在 public/bf1/kits。精英兵官方没有通用图标，用自绘的
 * 重甲头盔（elite.svg）。
 */
export function KitIcon({ kit, className }: { kit: string | null; className?: string }) {
  const src = kit ? KIT_ICONS[kit] : undefined;
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={kitLabel(kit)}
        title={kitLabel(kit)}
        className={cn("size-4 shrink-0 object-contain opacity-75", className)}
      />
    );
  }
  return (
    <span
      title={kitLabel(kit)}
      className={cn(
        "inline-flex size-4 shrink-0 items-center justify-center text-[9px] leading-none text-white/25",
        className,
      )}
    >
      —
    </span>
  );
}

const STATUS_TAG: Record<RoundPlayer["status"], string | null> = {
  finished: null,
  left: "退出",
  suspect: "存疑",
};

type Team = 1 | 2;

/**
 * 单局详情：上方地图横幅给出两队对阵与胜负，下方两队计分板。战绩是进服前与结算（或退出）后的
 * 生涯差值，中途退出的人没有胜负；「存疑」是增量里混进了别的局，数字仅供参考。
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
    return <div className="py-16 text-center text-sm text-white/40">正在加载对局…</div>;
  }
  if (q.isError || !q.data) {
    return <div className="py-16 text-center text-sm text-white/45">这一局的数据暂时取不到</div>;
  }
  const r = q.data;
  const byTeam = (t: Team) =>
    r.players.filter((p) => p.team === t).sort((a, b) => b.score - a.score);
  const teams = [byTeam(1), byTeam(2)] as const;

  return (
    <section className="min-w-0">
      <RoundBanner r={r} teams={teams} game={game} />
      <TipLine context={{ map: r.map_name, mode: r.game_mode }} className="mt-3" />
      <div className="mt-5 grid grid-cols-1 gap-x-8 gap-y-6 lg:grid-cols-2">
        {([1, 2] as const).map((t) => (
          <TeamBoard
            key={t}
            team={t}
            faction={t === 1 ? r.team1_faction : r.team2_faction}
            won={r.winner == null ? null : r.winner === t}
            players={teams[t - 1]}
            game={game}
            highlight={highlight}
            className={t === 2 ? "lg:border-l lg:border-white/15 lg:pl-8" : undefined}
          />
        ))}
      </div>
      <p className="mt-4 text-[11px] leading-relaxed text-white/35">
        {"战绩是进服前与结算（或退出）后的生涯差值，得分含结算奖励。名字前是在场最久的兵种，" +
          "点一行可看这一局的武器载具和其他数据。中途退出的人没有胜负，「存疑」表示增量里可能混进了别的局。"}
      </p>
    </section>
  );
}

/** 地图横幅：地图图做底，左右两队旗帜与胜负，中间地图、模式与时间 */
function RoundBanner({
  r,
  teams,
  game,
}: {
  r: RoundDetail;
  teams: readonly [RoundPlayer[], RoundPlayer[]];
  game: string;
}) {
  return (
    <div className="relative overflow-hidden border border-white/10 [clip-path:polygon(0_0,100%_0,100%_calc(100%-14px),calc(100%-14px)_100%,0_100%)]">
      {r.map_image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={r.map_image_url}
          alt=""
          className="absolute inset-0 h-full w-full object-cover opacity-45"
        />
      ) : null}
      <div className="absolute inset-0 bg-gradient-to-r from-black/85 via-black/55 to-black/85" />
      <div className="relative grid grid-cols-2 items-start gap-x-4 gap-y-5 px-4 py-5 sm:items-center sm:gap-y-4 sm:px-7 lg:grid-cols-[1fr_auto_1fr]">
        <div className="col-span-2 text-center lg:order-2 lg:col-span-1">
          <div className="font-display text-2xl leading-tight font-bold tracking-wide text-white sm:text-3xl">
            {r.map_display_name ?? r.map_name ?? "未知地图"}
          </div>
          {r.mode_display_name ? (
            <div className="mt-0.5 text-sm font-semibold text-amber-300">{r.mode_display_name}</div>
          ) : null}
          <div className="mt-1.5 text-xs text-white/55 tabular-nums">
            {formatRoundTime(r.started_at)} – {formatClock(r.ended_at)} · {roundDuration(r)}
          </div>
          {r.server_name ? (
            <Link
              href={roundHref(game, r)}
              className="mx-auto mt-1 block max-w-[22rem] truncate text-[11px] text-white/40 hover:text-amber-300"
            >
              {r.server_name}
            </Link>
          ) : null}
          <div className="mt-2 flex flex-wrap justify-center gap-1.5 text-[11px] empty:hidden">
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
        <TeamSide
          faction={r.team1_faction}
          fallback="队伍 1"
          won={r.winner == null ? null : r.winner === 1}
          players={teams[0]}
          className="lg:order-1"
        />
        <TeamSide
          faction={r.team2_faction}
          fallback="队伍 2"
          won={r.winner == null ? null : r.winner === 2}
          players={teams[1]}
          className="lg:order-3"
          alignEnd
        />
      </div>
    </div>
  );
}

/**
 * 阵营旗帜，同时表达胜负（BF1 结算画面的做法）：胜方全彩加金边微光，败方褪成灰色半透明。
 * won 不传或为 null 时按原样显示。
 */
export function FactionFlag({
  faction,
  won,
  className,
}: {
  faction: string | null;
  won?: boolean | null;
  className?: string;
}) {
  const slug = faction ? FACTION_SLUG[faction] : undefined;
  if (!slug) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`/factions/${slug}.png`}
      alt={faction ?? ""}
      className={cn(
        "shrink-0 object-contain",
        won === true &&
          "outline-2 outline-offset-2 outline-amber-400 drop-shadow-[0_0_6px_rgba(251,191,36,0.55)]",
        won === false && "opacity-45 grayscale",
        won == null && "drop-shadow",
        className,
      )}
    />
  );
}

/** 胜负文字：宽字距，胜利琥珀色、失败灰色，不加底色和图标 */
export function ResultTag({ won, className }: { won: boolean | null; className?: string }) {
  if (won == null) return null;
  return (
    <span
      className={cn(
        "text-xs font-extrabold tracking-[0.12em] whitespace-nowrap",
        won ? "text-amber-400" : "text-white/40",
        className,
      )}
    >
      {won ? "胜利" : "失败"}
    </span>
  );
}

function teamTotals(players: RoundPlayer[]) {
  return players.reduce(
    (s, p) => ({ kills: s.kills + p.kills, deaths: s.deaths + p.deaths, score: s.score + p.score }),
    { kills: 0, deaths: 0, score: 0 },
  );
}

function TeamSide({
  faction,
  fallback,
  won,
  players,
  alignEnd,
  className,
}: {
  faction: string | null;
  fallback: string;
  won: boolean | null;
  players: RoundPlayer[];
  alignEnd?: boolean;
  className?: string;
}) {
  const t = teamTotals(players);
  return (
    <div
      className={cn(
        // 手机上两队各占半宽，旗帜、队名、数据竖着叠，居中对齐
        "flex min-w-0 flex-col items-center gap-2 text-center sm:flex-row sm:gap-3 sm:text-left",
        alignEnd && "sm:flex-row-reverse sm:text-right",
        className,
      )}
    >
      <FactionFlag faction={faction} won={won} className="size-12 sm:size-14" />
      <div className="min-w-0">
        <div
          className={cn(
            "flex items-center justify-center gap-2 sm:justify-start",
            alignEnd && "sm:flex-row-reverse",
          )}
        >
          <span
            className={cn(
              "truncate text-base font-bold sm:text-lg",
              won === false ? "text-white/60" : "text-white",
            )}
          >
            {faction ?? fallback}
          </span>
          <ResultTag won={won} />
        </div>
        <div className="mt-0.5 text-xs text-white/55 tabular-nums">
          <span className="block sm:inline">
            {players.length} 人 · 击杀 {t.kills}
          </span>
          <span className="hidden sm:inline"> · </span>
          <span className="block sm:inline">得分 {t.score.toLocaleString("en-US")}</span>
        </div>
      </div>
    </div>
  );
}

function TeamBoard({
  team,
  faction,
  won,
  players,
  game,
  highlight,
  className,
}: {
  team: Team;
  faction: string | null;
  won: boolean | null;
  players: RoundPlayer[];
  game: string;
  highlight?: number;
  className?: string;
}) {
  const t = teamTotals(players);
  return (
    // 两队并排时列容器等高，表格撑满后由占位空行把合计行顶到底，两边合计对齐同一条线
    <div className={cn("flex min-w-0 flex-col", className)}>
      <div className="mb-2 flex items-center gap-2">
        <FactionFlag faction={faction} won={won} className="size-6" />
        <span className="truncate text-sm font-semibold text-white">
          {faction ?? `队伍 ${team}`}
        </span>
        <ResultTag won={won} />
      </div>
      {players.length === 0 ? (
        <div className="border-t border-white/25 py-6 text-center text-xs text-white/35">
          这一队没有算出战绩的玩家
        </div>
      ) : (
        // 窄屏表格横向滚动：明细行按这个容器的可见宽度排版（@container/board），不跟着被截掉。
        // 宽屏不设容器，免得容器的尺寸隔离让两队并排时整块被压窄
        <div className="flex-1 overflow-x-auto max-lg:@container/board lg:overflow-x-visible">
          {/* 只留四列数字并拉开间距，名字列吃满剩余宽度；兵种、在场时长、SPM 放进名字和悬停提示 */}
          <table className="h-full w-full min-w-[24rem] border-collapse text-[13px] tabular-nums lg:min-w-0">
            <colgroup>
              <col className="w-7" />
              <col />
              <col className="w-16" />
              <col className="w-16" />
              <col className="w-[4.5rem]" />
              <col className="w-24" />
            </colgroup>
            <thead>
              <tr className="text-[11px] text-white/50">
                <th className="pb-2 font-medium" />
                <th className="pb-2 pl-2 text-left font-medium">玩家</th>
                <Th>击杀</Th>
                <Th>死亡</Th>
                <Th>K/D</Th>
                <Th>得分</Th>
              </tr>
            </thead>
            <tbody className="border-t border-white/25">
              {players.map((p, i) => (
                <PlayerRow
                  key={p.persona_id}
                  player={p}
                  seq={i + 1}
                  game={game}
                  highlighted={p.persona_id === highlight}
                />
              ))}
              <tr aria-hidden className="h-full">
                <td colSpan={6} />
              </tr>
            </tbody>
            <tfoot>
              <tr className="border-t border-white/20 text-[12.5px] font-semibold text-amber-300/90">
                <td colSpan={2} className="pt-2.5 pl-2">
                  合计
                </td>
                <td className="pt-2.5 pl-4 text-right">{t.kills}</td>
                <td className="pt-2.5 pl-4 text-right">{t.deaths}</td>
                <td className="pt-2.5 pl-4 text-right">
                  {(t.kills / Math.max(t.deaths, 1)).toFixed(2)}
                </td>
                <td className="pt-2.5 pl-4 text-right">{t.score.toLocaleString("en-US")}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="pb-2 pl-4 text-right font-medium whitespace-nowrap">{children}</th>;
}

function PlayerRow({
  player: p,
  seq,
  game,
  highlighted,
}: {
  player: RoundPlayer;
  seq: number;
  game: string;
  highlighted: boolean;
}) {
  // 从玩家页点开时，这个人的明细默认展开
  const [open, setOpen] = useState(highlighted);
  const tag = STATUS_TAG[p.status];
  const minutes = Math.round(p.seconds / 60);
  const hint = [
    p.name ?? String(p.persona_id),
    kitLabel(p.kit),
    minutes ? `在场 ${minutes} 分钟` : null,
    p.spm != null ? `SPM ${p.spm}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Fragment>
      <tr
        onClick={() => setOpen(!open)}
        className={cn(
          "cursor-pointer border-b border-white/[0.06] transition-colors last:border-0 hover:bg-white/[0.05]",
          highlighted && "bg-amber-400/12 hover:bg-amber-400/15",
          open && "border-white/0",
        )}
      >
        <td
          className={cn(
            "py-[7px] pr-1 text-right text-[11px]",
            seq <= 3 ? "font-semibold text-amber-400" : "text-white/35",
          )}
        >
          {seq}
        </td>
        <td className="w-full max-w-0 py-[7px] pl-2">
          <div className="flex min-w-0 items-center gap-2" title={hint}>
            <KitIcon kit={p.kit} />
            <Link
              href={`/${game}/player/${p.persona_id}`}
              onClick={(e) => e.stopPropagation()}
              className={cn(
                "min-w-0 truncate font-medium hover:underline",
                tag ? "text-white/55" : "text-white/90",
              )}
            >
              {p.name ?? p.persona_id}
            </Link>
            {tag ? (
              <span className="shrink-0 rounded-sm bg-white/10 px-1 text-[10px] leading-[1.5] text-white/50">
                {tag}
              </span>
            ) : null}
            <button
              type="button"
              aria-expanded={open}
              aria-label={`${p.name ?? p.persona_id} 的这一局明细`}
              onClick={(e) => {
                e.stopPropagation();
                setOpen(!open);
              }}
              className="ml-auto shrink-0 text-white/25 hover:text-white"
            >
              <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
            </button>
          </div>
        </td>
        <td className="py-[7px] pl-4 text-right text-white/90">{p.kills}</td>
        <td className="py-[7px] pl-4 text-right text-white/60">{p.deaths}</td>
        <td className="py-[7px] pl-4 text-right text-white/75">
          {p.kd != null ? p.kd.toFixed(2) : "—"}
        </td>
        <td className="py-[7px] pl-4 text-right font-semibold text-white">
          {p.score.toLocaleString("en-US")}
        </td>
      </tr>
      {open ? (
        <tr
          className={cn(
            "border-b border-white/[0.06] bg-black/20",
            highlighted && "bg-amber-400/[0.06]",
          )}
        >
          <td colSpan={6} className="p-0">
            <div className="sticky left-0 w-[100cqw] pl-7 lg:static lg:w-auto">
              <RoundPlayerBreakdown player={p} />
            </div>
          </td>
        </tr>
      ) : null}
    </Fragment>
  );
}
