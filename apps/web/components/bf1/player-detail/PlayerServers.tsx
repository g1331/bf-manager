"use client";

import Link from "next/link";
import { Ban, ChevronRight, Crown, Shield, Star } from "lucide-react";
import { Panel } from "@/components/bf1/player-detail/CareerOverview";
import { RowsSkeleton } from "@/components/layout/PageSkeleton";
import type { PlayerRspServer, PlayerRspServers } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

const ROLES = [
  { key: "owner", label: "拥有的服务器", icon: Crown, tone: "text-amber-300" },
  { key: "admin", label: "管理的服务器", icon: Shield, tone: "text-sky-300" },
  { key: "vip", label: "VIP", icon: Star, tone: "text-emerald-300" },
  { key: "ban", label: "被封禁", icon: Ban, tone: "text-red-400" },
] as const;

export function playerServerCount(data: PlayerRspServers | undefined): number | undefined {
  if (!data) return undefined;
  return ROLES.reduce((n, r) => n + data[r.key].length, 0);
}

function ago(ts: number): string {
  const min = Math.max(0, Math.floor((Date.now() / 1000 - ts) / 60));
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  if (min < 60 * 24) return `${Math.floor(min / 60)} 小时前`;
  return `${Math.floor(min / 60 / 24)} 天前`;
}

/**
 * 天眼查：这个人是哪些私服的服主 / 管理 / VIP，被哪些服封禁。
 * 名单来自平台收录的私服，按间隔轮流刷新，不是 EA 全量，所以页脚写明覆盖范围。
 */
export function PlayerServers({
  game,
  data,
  loading,
  error,
}: {
  game: string;
  data: PlayerRspServers | undefined;
  loading: boolean;
  error: boolean;
}) {
  if (loading) return <RowsSkeleton rows={4} />;
  if (!data)
    return (
      <Panel>
        <div className="py-8 text-center text-sm text-white/40">
          {error ? "加载失败，请稍后重试" : "暂无数据"}
        </div>
      </Panel>
    );

  const groups = ROLES.filter((r) => data[r.key].length > 0);
  const note = `名单来自平台收录的 ${data.tracked_servers} 个私服，每台约 6 小时刷新一次；没有人进过的服查不到。`;
  return (
    <Panel>
      <div className="@container space-y-6">
        {groups.length === 0 ? (
          <div className="py-6 text-center text-sm text-white/40">
            收录的私服里没有这位玩家的服主、管理、VIP 或封禁记录
          </div>
        ) : (
          groups.map((r) => (
            <section key={r.key}>
              <h3 className="mb-2 flex items-center gap-2 text-xs font-bold tracking-[0.04em] text-white/80">
                <r.icon className={cn("size-3.5", r.tone)} />
                {r.label}
                <span className="font-normal tracking-normal text-white/40 tabular-nums">
                  {data[r.key].length}
                </span>
              </h3>
              <ul className="grid grid-cols-1 gap-2 @2xl:grid-cols-2">
                {data[r.key].map((sv) => (
                  <li key={sv.server_id}>
                    <ServerRow game={game} server={sv} banned={r.key === "ban"} />
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
        <p className="text-[11px] leading-relaxed text-white/35">{note}</p>
      </div>
    </Panel>
  );
}

function ServerRow({
  game,
  server,
  banned,
}: {
  game: string;
  server: PlayerRspServer;
  banned: boolean;
}) {
  const live = server.player_count != null;
  return (
    <Link
      href={`/${game}/server/${server.game_id}`}
      className={cn(
        "group relative flex min-h-14 items-center gap-3 overflow-hidden border px-3 py-2.5 transition-colors",
        banned
          ? "border-red-500/25 bg-red-950/25 hover:bg-red-950/40"
          : "border-white/10 bg-white/[0.03] hover:bg-white/[0.07]",
      )}
    >
      {server.map_image_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={server.map_image_url}
          alt=""
          className="h-9 w-16 shrink-0 object-cover opacity-80"
          loading="lazy"
        />
      ) : (
        <div className="h-9 w-16 shrink-0 bg-white/[0.06]" />
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-white">{server.name}</div>
        <div className="mt-0.5 truncate text-xs text-white/45">
          {live ? (
            <span className="text-white/70 tabular-nums">
              {server.player_count}/{server.max_player_count}
              {server.map_display_name ? ` · ${server.map_display_name}` : ""}
            </span>
          ) : (
            "当前无人"
          )}
          <span className="text-white/30"> · 名单 {ago(server.refreshed_at)}</span>
        </div>
      </div>
      <ChevronRight className="size-4 shrink-0 text-white/30 transition-colors group-hover:text-white" />
    </Link>
  );
}
