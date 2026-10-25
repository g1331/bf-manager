"use client";

import { Fragment } from "react";
import { motion } from "framer-motion";
import { Clock4, Copy, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { BanBadge } from "@/components/bf1/visual/BanBadge";
import { PlayerAvatar } from "@/components/common/PlayerAvatar";
import type { BanStatus, PlayerPlatoon, PlayerStatsSummary } from "@/lib/api/bf1";
import { rarityByRank, rarityHex } from "@/lib/bf1/rarity";
import { cn } from "@/lib/utils";
import { classLabel, fmtFixed, fmtFull, fmtHours, fmtPct, isKnownClass, winRate } from "./format";

/**
 * 首屏横幅：左侧身份（头像、战队、昵称、等级、在线与封禁状态）与生涯核心数字，
 * 右侧最佳兵种立绘。被反作弊平台标记时顶部加红色警示条，身份区褪色。
 */
export function PlayerHeroBanner({
  personaId,
  displayName,
  avatarUrl,
  summary,
  online,
  onlineServer,
  ban,
  platoon,
}: {
  personaId: number;
  displayName: string;
  avatarUrl: string | null;
  summary: PlayerStatsSummary;
  online: boolean | null;
  onlineServer: string | null;
  ban: BanStatus | undefined;
  platoon: PlayerPlatoon | null;
}) {
  const banned = ban?.bfban === "hit" || ban?.bfeac === "hit";
  const best = isKnownClass(summary.best_class) ? summary.best_class : null;
  const rate = winRate(summary.wins, summary.losses);

  const copyPid = () => {
    navigator.clipboard.writeText(String(personaId)).then(
      () => toast.success("已复制 PID"),
      () => toast.error("复制失败"),
    );
  };

  return (
    <Bf1Panel
      variant="transparent"
      cut={28}
      corners={["topLeft", "bottomRight"]}
      // 立绘列按横幅自身宽度（@container）显隐：页面可用宽度被侧栏裁剪，视口断点测不准（#48）
      className="@container relative overflow-hidden bg-black/55 backdrop-blur-sm"
    >
      <div className="absolute inset-0 bg-gradient-to-r from-black/80 via-black/40 to-transparent" />
      <div
        className={cn(
          "absolute inset-x-0 top-0 h-px bg-gradient-to-r to-transparent",
          banned ? "from-red-500/80 via-red-500/30" : "from-amber-500/70 via-amber-500/20",
        )}
      />

      {best ? (
        <motion.img
          src={`/bf1/soldiers/portraits/${best}.png`}
          alt=""
          aria-hidden
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className={cn(
            "pointer-events-none absolute right-6 bottom-0 hidden h-[92%] max-h-[22rem] object-contain object-bottom [filter:drop-shadow(0_8px_18px_rgba(0,0,0,0.9))] select-none @4xl:block @6xl:right-16",
            banned && "grayscale",
          )}
        />
      ) : null}

      <div className="relative p-6 sm:p-8 @4xl:pr-[20rem] @6xl:pr-[26rem]">
        {banned ? <BanWarning ban={ban} /> : null}

        {/* 状态行 */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <OnlineChip online={online} server={onlineServer} />
          <BanBadge
            source="bfban"
            state={ban?.bfban ?? "unknown"}
            size="sm"
            href={ban?.bfban_url}
          />
          <BanBadge
            source="bfeac"
            state={ban?.bfeac ?? "unknown"}
            size="sm"
            href={ban?.bfeac_url}
          />
        </div>

        {/* 身份 */}
        <div className={cn("mt-5 flex items-center gap-4 sm:gap-6", banned && "grayscale")}>
          <PlayerAvatar
            avatarUrl={avatarUrl}
            displayName={displayName}
            size="lg"
            online={online ?? false}
          />
          <div className="min-w-0">
            {platoon?.tag || platoon?.name ? (
              <div className="mb-1 flex items-center gap-2 text-xs text-white/55">
                {platoon.emblem_url ? (
                  // EA 徽章域不在 next/image remotePatterns 内
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={platoon.emblem_url} alt="" className="size-5 object-contain" />
                ) : null}
                <span className="truncate">
                  {platoon.name ?? platoon.tag}
                  {platoon.size != null ? ` · ${platoon.size} 人` : ""}
                </span>
                {platoon.verified ? <span className="text-amber-300/90">已认证</span> : null}
              </div>
            ) : null}
            <h1 className="font-display flex flex-wrap items-baseline gap-x-3 text-3xl leading-tight font-bold tracking-wide break-all sm:text-4xl @6xl:text-5xl">
              {platoon?.tag ? <span className="text-white/45">[{platoon.tag}]</span> : null}
              <span>{displayName}</span>
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-white/55">
              <RankBadge rank={summary.rank} />
              <span className="flex items-center gap-1.5 tabular-nums">
                <Clock4 className="size-3.5" />
                {fmtHours(summary.time_played_seconds)}
              </span>
              <button
                type="button"
                onClick={copyPid}
                className="flex items-center gap-1.5 tabular-nums transition-colors hover:text-white"
                title="复制 PID"
              >
                PID {personaId}
                <Copy className="size-3" />
              </button>
            </div>
          </div>
        </div>

        {/* 核心数字 */}
        <div className="mt-8 flex flex-wrap items-end gap-x-10 gap-y-5">
          <div>
            <div className="text-[11px] tracking-[0.25em] text-amber-400/90 uppercase">K / D</div>
            <div className="font-display mt-1 text-7xl leading-none font-bold text-amber-400 tabular-nums drop-shadow-[0_0_28px_rgba(245,158,11,0.35)] sm:text-8xl">
              {fmtFixed(summary.kd)}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-4 pb-1 sm:grid-cols-4">
            <Kpi label="KPM" value={fmtFixed(summary.kpm)} />
            <Kpi label="SPM" value={summary.sps != null ? fmtFull(summary.sps * 60) : "—"} />
            <Kpi label="胜率" value={fmtPct(rate)} />
            <Kpi label="技巧值" value={fmtFull(summary.skill)} />
          </div>
        </div>

        {best ? (
          <div className="mt-6 flex items-center gap-3 border-t border-white/10 pt-4 text-xs text-white/55 @4xl:hidden">
            {/* 窄屏不放立绘，用一行文字交代最佳兵种 */}
            最佳兵种 <span className="font-semibold text-white">{classLabel(best)}</span>
          </div>
        ) : null}
      </div>

      {best ? (
        <div className="absolute right-6 bottom-5 hidden text-right @4xl:block @6xl:right-16">
          <div className="text-[11px] tracking-[0.25em] text-white/50 uppercase">最佳兵种</div>
          <div className="font-display text-3xl font-bold text-white drop-shadow-[0_2px_12px_rgba(0,0,0,0.9)]">
            {classLabel(best)}
          </div>
        </div>
      ) : null}
    </Bf1Panel>
  );
}

function RankBadge({ rank }: { rank: number | null }) {
  const color = rarityHex[rarityByRank(rank)];
  return (
    <span
      className="font-display border px-1.5 py-px text-sm font-bold tabular-nums"
      style={{ color, borderColor: `${color}66` }}
    >
      Lv. {rank ?? "—"}
    </span>
  );
}

function OnlineChip({ online, server }: { online: boolean | null; server: string | null }) {
  if (online) {
    return (
      <span className="inline-flex max-w-full items-center gap-2 border border-emerald-400/40 bg-emerald-500/10 px-2 py-0.5 text-emerald-300 sm:max-w-[26rem]">
        <span className="relative flex size-2 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/70" />
          <span className="relative inline-flex size-2 rounded-full bg-emerald-400" />
        </span>
        <span className="truncate">{server ? `正在游戏 · ${server}` : "在线"}</span>
      </span>
    );
  }
  // null 表示在线状态查询失败、无法判定，标注「未知」而非误判离线
  return (
    <span className="inline-flex items-center gap-2 border border-white/15 bg-black/30 px-2 py-0.5 text-white/60">
      <span className="inline-block size-2 rounded-full bg-zinc-500" />
      {online == null ? "状态未知" : "离线"}
    </span>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] tracking-wider text-white/50">{label}</div>
      <div className="font-display mt-1 text-3xl font-bold text-white tabular-nums">{value}</div>
    </div>
  );
}

function BanWarning({ ban }: { ban: BanStatus | undefined }) {
  const sources: { label: string; url: string | null }[] = [];
  if (ban?.bfban === "hit") sources.push({ label: "BFBAN", url: ban.bfban_url });
  if (ban?.bfeac === "hit") sources.push({ label: "BFEAC", url: ban.bfeac_url });
  return (
    <div className="mb-5 flex items-center gap-2 bg-red-600/90 px-4 py-2 text-sm font-bold text-white [box-shadow:0_0_18px_rgba(239,68,68,0.5)] [clip-path:polygon(8px_0,100%_0,calc(100%-8px)_100%,0_100%)]">
      <ShieldAlert className="size-4 shrink-0" />
      <span>
        该账号已被反作弊平台标记（
        {sources.map((s, i) => (
          <Fragment key={s.label}>
            {i > 0 && " / "}
            {s.url ? (
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="underline underline-offset-2 hover:text-red-100"
              >
                {s.label}
              </a>
            ) : (
              s.label
            )}
          </Fragment>
        ))}
        ）
      </span>
    </div>
  );
}
