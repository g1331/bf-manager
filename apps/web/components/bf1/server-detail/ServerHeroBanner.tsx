"use client";

import { Bookmark, Clock4, Eye, Lock, SkipForward, UserRound } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { CountUp } from "@/components/bf1/visual/CountUp";
import { CountryFlag } from "@/components/common/CountryFlag";
import type {
  MapRotationItem,
  OperationProgress,
  ServerExtras,
  ServerSummary,
} from "@/lib/api/bf1";
import { pingSiteCountry } from "@/lib/bf1/pingsite";
import { cn } from "@/lib/utils";
import { formatDuration } from "./history";
import { nextMap } from "./operation";
import { OperationTrack } from "./OperationTrack";

/** 槽位条每格代表的人数：64 人服 32 格，32 人服 16 格 */
const PLAYERS_PER_SLOT = 2;

/**
 * 首屏横幅：当前地图实景铺底，左侧服务器名与在线人数，右下角「正在进行」的地图卡。
 * elapsedMinutes 是当前这张图已进行的分钟数（由人数采样推得，没有采样时为 null）。
 * operation 是行动模式进度（来自实时名单的 Blaze ATTR），非行动模式为 null。
 */
export function ServerHeroBanner({
  summary,
  extras,
  rotation,
  elapsedMinutes,
  operation,
}: {
  summary: ServerSummary;
  extras: ServerExtras;
  rotation: MapRotationItem[];
  elapsedMinutes: number | null;
  operation: OperationProgress | null;
}) {
  const mapLabel = summary.map_display_name ?? summary.map_name;
  const modeLabel = summary.mode_display_name ?? summary.game_mode;
  const regionLabel = summary.region_display_name ?? summary.region;
  const cap = Math.max(summary.max_player_count, 1);
  const slots = Math.max(Math.round(cap / PLAYERS_PER_SLOT), 1);
  const filled = Math.round((Math.min(summary.player_count, cap) / cap) * slots);
  const fill = Math.round((summary.player_count / cap) * 100);

  const nm = nextMap(rotation);
  const rotationNext = nm?.kind === "rotation" ? rotation[nm.index] : null;
  const next =
    nm?.kind === "breakthrough"
      ? { label: "攻破后进入", name: nm.map.name, mode: null, image: nm.map.image_url }
      : nm?.kind === "uncertain"
        ? { label: "战役结束后", name: "落点不确定", mode: null, image: null }
        : rotationNext
          ? {
              label: "下一张",
              name: rotationNext.map_display_name ?? rotationNext.map_name,
              mode: rotationNext.mode_display_name,
              image: rotationNext.map_image_url,
            }
          : null;

  return (
    <Bf1Panel
      variant="transparent"
      cut={28}
      corners={["topLeft", "bottomRight"]}
      className="relative overflow-hidden bg-black/40"
    >
      {summary.map_image_url ? (
        // EA CDN 自带缩放与缓存，不走 next/image
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={summary.map_image_url}
          alt=""
          aria-hidden
          className="absolute inset-0 h-full w-full scale-105 object-cover object-center opacity-80"
        />
      ) : null}
      <div className="absolute inset-0 bg-gradient-to-r from-black/95 via-black/75 to-black/10" />
      <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/10 to-black/40" />
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-amber-500/70 via-amber-500/20 to-transparent" />

      <div className="relative grid grid-cols-1 gap-4 p-4 sm:gap-8 sm:p-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-10">
        <div className="flex min-w-0 flex-col">
          {/* 标签行 */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="flex items-center gap-2 pr-1">
              <span className="relative flex size-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400/70" />
                <span className="relative inline-flex size-2 rounded-full bg-amber-400" />
              </span>
              <span className="font-display font-semibold tracking-[0.25em] text-amber-400 uppercase">
                Live
              </span>
            </span>
            {regionLabel ? (
              <Chip>
                <CountryFlag code={summary.country ?? pingSiteCountry(summary.ping_site)} />
                {regionLabel}
              </Chip>
            ) : null}
            {summary.tick_rate ? <Chip>{summary.tick_rate} Hz</Chip> : null}
            {summary.is_official ? <Chip accent>官方服</Chip> : null}
            {summary.is_ranked ? <Chip accent>Ranked</Chip> : null}
            {summary.has_password ? (
              <Chip>
                <Lock className="size-3" />
                密码
              </Chip>
            ) : null}
          </div>

          <h1 className="font-display mt-3 line-clamp-3 text-xl leading-snug font-bold tracking-wide break-all text-white sm:mt-4 sm:text-3xl xl:text-4xl">
            {summary.name}
          </h1>

          <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-white/55">
            {extras.owner?.display_name ? (
              <span className="flex items-center gap-1.5">
                <UserRound className="size-3.5" />
                服主 <span className="text-white/85">{extras.owner.display_name}</span>
              </span>
            ) : null}
            {extras.platoon?.tag ? (
              <span className="flex items-center gap-1.5">
                {extras.platoon.emblem_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={extras.platoon.emblem_url} alt="" className="size-4 object-contain" />
                ) : null}
                战队 <span className="text-white/85">[{extras.platoon.tag}]</span>
              </span>
            ) : null}
            {extras.bookmark_count != null ? (
              <span className="flex items-center gap-1.5 tabular-nums">
                <Bookmark className="size-3.5" />
                {extras.bookmark_count.toLocaleString()} 收藏
              </span>
            ) : null}
          </div>

          {/* 在线人数 */}
          <div className="mt-auto pt-6 sm:pt-8">
            <div className="flex flex-wrap items-end gap-x-8 gap-y-4 sm:gap-x-10">
              <div>
                <div className="text-[11px] tracking-[0.25em] text-amber-400/90 uppercase">
                  在线玩家
                </div>
                <div className="font-display mt-1 flex items-baseline leading-none tabular-nums">
                  <span className="text-6xl font-bold text-amber-400 drop-shadow-[0_0_28px_rgba(245,158,11,0.35)] sm:text-8xl">
                    <CountUp value={summary.player_count} />
                  </span>
                  <span className="ml-2 text-2xl font-semibold text-white/40 sm:text-3xl">
                    /{summary.max_player_count}
                  </span>
                </div>
              </div>
              <div className="flex gap-8 pb-1">
                <Kpi icon={Clock4} label="排队" value={summary.queue_count} />
                <Kpi icon={Eye} label="观战" value={summary.spectator_count} />
              </div>
            </div>
            <div className="mt-5 flex items-center gap-3">
              <div className="flex flex-1 gap-[3px]" aria-hidden>
                {Array.from({ length: slots }, (_, i) => (
                  <span
                    key={i}
                    className={cn("h-2 flex-1", i < filled ? "bg-amber-400" : "bg-white/12")}
                  />
                ))}
              </div>
              <span className="w-10 shrink-0 text-right text-xs text-white/55 tabular-nums">
                {fill}%
              </span>
            </div>
          </div>
        </div>

        {/* 正在进行 */}
        <div className="flex flex-col justify-end lg:items-end lg:text-right">
          <div className="text-[11px] tracking-[0.25em] text-white/50 uppercase">正在进行</div>
          <div className="font-display mt-1 text-3xl leading-tight font-bold text-white drop-shadow-[0_2px_12px_rgba(0,0,0,0.8)] sm:text-5xl">
            {mapLabel ?? "未知地图"}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-white/70 lg:justify-end">
            {modeLabel ? <span className="text-amber-300">{modeLabel}</span> : null}
            {elapsedMinutes != null && elapsedMinutes >= 0 ? (
              <span className="tabular-nums">已进行 {formatDuration(elapsedMinutes)}</span>
            ) : null}
          </div>
          {operation ? <OperationTrack operation={operation} /> : null}
          {next ? (
            <div className="mt-5 flex items-center gap-3 border-t border-white/15 pt-3 lg:flex-row-reverse">
              {next.image ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={next.image}
                  alt=""
                  className="h-10 w-16 shrink-0 object-cover opacity-90 [clip-path:polygon(0_0,100%_0,100%_calc(100%-8px),calc(100%-8px)_100%,0_100%)]"
                />
              ) : null}
              <div className="min-w-0">
                <div className="flex items-center gap-1 text-[11px] text-white/45 lg:justify-end">
                  <SkipForward className="size-3" />
                  {next.label}
                </div>
                <div className="truncate text-sm text-white/85">
                  {next.name}
                  {next.mode ? <span className="ml-1.5 text-white/45">{next.mode}</span> : null}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </Bf1Panel>
  );
}

function Chip({ children, accent }: { children: React.ReactNode; accent?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 border px-2 py-0.5",
        accent
          ? "border-amber-400/40 bg-amber-500/10 text-amber-300"
          : "border-white/15 bg-black/30 text-white/75",
      )}
    >
      {children}
    </span>
  );
}

function Kpi({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[11px] tracking-wider text-white/50">
        <Icon className="size-3" />
        {label}
      </div>
      <div className="font-display mt-1 text-2xl font-bold text-white tabular-nums sm:text-4xl">
        <CountUp value={value} />
      </div>
    </div>
  );
}
