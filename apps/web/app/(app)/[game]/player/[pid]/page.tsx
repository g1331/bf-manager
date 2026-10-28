"use client";

/**
 * BF1 玩家战绩详情页
 *
 * 版式与服务器详情页一致：全屏模糊背景 + 首屏横幅 + 吸顶分区导航（状态记在 URL hash）。
 * 概览一屏看完生涯：战斗、团队贡献、兵种、常用装备；武器 / 载具分区是可排序的排行列表。
 * 武器 / 载具进页即在后台拉取（概览的常用装备要用），最近服务器切到该分区时再拉。
 */

import { useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { SectionNav, useTabHash } from "@/components/bf1/SectionNav";
import { DetailBackground, DetailNote } from "@/components/bf1/visual/DetailBackground";
import { CareerOverview, Panel } from "@/components/bf1/player-detail/CareerOverview";
import {
  EquipmentTable,
  isUsed,
  type GearColumn,
} from "@/components/bf1/player-detail/EquipmentTable";
import { PlayerHeroBanner } from "@/components/bf1/player-detail/PlayerHeroBanner";
import { PlayerRounds } from "@/components/bf1/player-detail/PlayerRounds";
import { fmtFixed, fmtFull, perMinute } from "@/components/bf1/player-detail/format";
import { PlayerDetailSkeleton, RowsSkeleton } from "@/components/layout/PageSkeleton";
import {
  bf1Api,
  type PlayerStatsDetail,
  type RecentServer,
  type VehicleStat,
  type WeaponStat,
} from "@/lib/api/bf1";
import { pickBackgroundUrl } from "@/lib/bf1/background";
import { pushRecentPlayer } from "@/lib/bf1/recent-players";
import { useBack } from "@/hooks/useNavigation";
import { formatDuration } from "@/lib/utils";

const TAB_KEYS = ["overview", "weapons", "vehicles", "rounds", "recent"] as const;

const fmtPctValue = (v: number | null) => (v == null ? "—" : `${v.toFixed(1)}%`);
const fmtTime = (v: number | null) => (v == null ? "—" : formatDuration(v));

const WEAPON_COLUMNS: GearColumn<WeaponStat>[] = [
  { key: "kills", label: "击杀", value: (w) => w.kills, format: fmtFull },
  {
    key: "kpm",
    label: "KPM",
    value: (w) => perMinute(w.kills, w.time_seconds),
    format: (v) => fmtFixed(v),
  },
  { key: "accuracy", label: "命中率", value: (w) => w.accuracy, format: fmtPctValue },
  {
    key: "headshot",
    label: "爆头率",
    value: (w) => (w.kills && w.headshots != null ? (w.headshots / w.kills) * 100 : null),
    format: fmtPctValue,
  },
  { key: "time", label: "时长", value: (w) => w.time_seconds, format: fmtTime },
];

const VEHICLE_COLUMNS: GearColumn<VehicleStat>[] = [
  { key: "kills", label: "击杀", value: (v) => v.kills, format: fmtFull },
  {
    key: "kpm",
    label: "KPM",
    value: (v) => perMinute(v.kills, v.time_seconds),
    format: (v) => fmtFixed(v),
  },
  { key: "destroyed", label: "摧毁", value: (v) => v.destroyed, format: fmtFull },
  { key: "time", label: "时长", value: (v) => v.time_seconds, format: fmtTime },
];

export default function Bf1PlayerPage() {
  const { game, pid } = useParams<{ game: string; pid: string }>();
  const personaId = Number(pid);
  const enabled = Number.isFinite(personaId) && personaId > 0;

  const statsQ = useQuery({
    queryKey: ["bf1-stats", personaId],
    queryFn: () => bf1Api.getStats(personaId),
    enabled,
  });

  if (!enabled) return <DetailNote text="无效的玩家 ID" />;
  if (statsQ.isLoading) return <PlayerDetailSkeleton />;
  if (!statsQ.data) return <DetailNote text="加载玩家战绩失败，请稍后重试" />;
  return <PlayerDetailView game={game} personaId={personaId} stats={statsQ.data} />;
}

/** 战绩到手后才挂载（纯客户端），分区状态可以直接从 window 读初值 */
function PlayerDetailView({
  game,
  personaId,
  stats,
}: {
  game: string;
  personaId: number;
  stats: PlayerStatsDetail;
}) {
  const { summary, soldiers } = stats;
  // 回到真正来的那一页（战队、服务器排行、带搜索词的战绩查询等），直接打开时退到战绩查询
  const back = useBack(`/${game}/players`);

  const playerQ = useQuery({
    queryKey: ["bf1-player", personaId],
    queryFn: () => bf1Api.getPlayer(personaId),
  });
  const onlineQ = useQuery({
    queryKey: ["bf1-online", personaId],
    queryFn: () => bf1Api.getOnline(personaId),
  });
  const platoonQ = useQuery({
    queryKey: ["bf1-platoon", personaId],
    queryFn: () => bf1Api.getPlatoon(personaId),
  });
  const displayName = playerQ.data?.display_name || summary.display_name || `Persona ${personaId}`;
  const banQ = useQuery({
    queryKey: ["bf1-ban", personaId, playerQ.data?.display_name],
    queryFn: () => bf1Api.getBan(personaId, playerQ.data?.display_name),
    enabled: !!playerQ.data,
  });
  const weaponsQ = useQuery({
    queryKey: ["bf1-weapons", personaId],
    queryFn: () => bf1Api.getWeapons(personaId),
  });
  const vehiclesQ = useQuery({
    queryKey: ["bf1-vehicles", personaId],
    queryFn: () => bf1Api.getVehicles(personaId),
  });

  const weapons = weaponsQ.data?.weapons;
  const vehicles = vehiclesQ.data?.vehicles;
  const usedCount = (list: (WeaponStat | VehicleStat)[] | undefined) => list?.filter(isUsed).length;

  const tabs = [
    { key: "overview" as const, label: "概览" },
    { key: "weapons" as const, label: "武器", count: usedCount(weapons) },
    { key: "vehicles" as const, label: "载具", count: usedCount(vehicles) },
    { key: "rounds" as const, label: "对局" },
    { key: "recent" as const, label: "最近" },
  ];
  const [tab, setTab] = useTabHash(TAB_KEYS, TAB_KEYS);

  const recentQ = useQuery({
    queryKey: ["bf1-recent", personaId],
    queryFn: () => bf1Api.getRecentServers(personaId),
    enabled: tab === "recent",
  });

  const player = playerQ.data;
  useEffect(() => {
    if (player) {
      pushRecentPlayer({
        persona_id: player.persona_id,
        display_name: player.display_name,
        avatar_url: player.avatar_url,
      });
    }
  }, [player]);

  const ban = banQ.data;
  const banned = ban?.bfban === "hit" || ban?.bfeac === "hit";

  return (
    <div className="relative min-h-screen w-full text-white">
      <DetailBackground url={pickBackgroundUrl(personaId, null)} grayscale={banned} />

      <div className="relative z-10 max-w-[1600px] px-3 py-4 sm:px-10 sm:py-8">
        <button
          type="button"
          onClick={back}
          className="mb-4 inline-flex items-center gap-1.5 text-sm text-white/55 transition-colors hover:text-white"
        >
          <ArrowLeft className="size-4" />
          返回
        </button>

        <PlayerHeroBanner
          personaId={personaId}
          displayName={displayName}
          avatarUrl={player?.avatar_url ?? null}
          summary={summary}
          online={onlineQ.data?.is_online ?? null}
          onlineServer={onlineQ.data?.server_name ?? null}
          onlineGameId={onlineQ.data?.game_id ?? null}
          ban={ban}
          platoon={platoonQ.data ?? null}
          game={game}
        />

        <SectionNav tabs={tabs} tab={tab} onTab={setTab} />

        <motion.div
          key={tab}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="mt-6"
        >
          {tab === "overview" && (
            <CareerOverview
              summary={summary}
              soldiers={soldiers}
              weapons={weapons}
              vehicles={vehicles}
              onShowAll={(t) => {
                setTab(t);
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
            />
          )}
          {tab === "weapons" && (
            <EquipmentTable
              items={weapons ?? []}
              loading={weaponsQ.isLoading}
              columns={WEAPON_COLUMNS}
              placeholder="搜索武器名 / 皮肤名…"
              emptyText="暂无武器数据"
            />
          )}
          {tab === "vehicles" && (
            <EquipmentTable
              items={vehicles ?? []}
              loading={vehiclesQ.isLoading}
              columns={VEHICLE_COLUMNS}
              placeholder="搜索载具名 / 皮肤名…"
              emptyText="暂无载具数据"
            />
          )}
          {tab === "rounds" && <PlayerRounds personaId={personaId} game={game} />}
          {tab === "recent" && (
            <RecentServers
              game={game}
              servers={recentQ.data?.servers ?? []}
              loading={recentQ.isLoading}
            />
          )}
        </motion.div>
      </div>
    </div>
  );
}

/** 最近游玩的服务器：上游按时间倒序给出，不带时间戳；有服务器 ID 的可直接跳详情 */
function RecentServers({
  game,
  servers,
  loading,
}: {
  game: string;
  servers: RecentServer[];
  loading: boolean;
}) {
  if (loading) return <RowsSkeleton rows={5} />;
  if (servers.length === 0)
    return (
      <Panel>
        <div className="py-8 text-center text-sm text-white/40">暂无最近游玩记录</div>
      </Panel>
    );
  return (
    <Panel>
      <ol className="divide-y divide-white/[0.06]">
        {servers.map((sv, i) => {
          const body = (
            <>
              <span
                className={`font-display w-6 shrink-0 text-center text-sm font-bold tabular-nums ${i === 0 ? "text-amber-400" : "text-white/30"}`}
              >
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-white">{sv.name}</div>
                <div className="mt-0.5 text-xs text-white/50">
                  {sv.map_name ?? "未知地图"}
                  {sv.game_mode ? (
                    <span className="text-amber-300/80"> · {sv.game_mode}</span>
                  ) : null}
                </div>
              </div>
              {sv.server_id != null ? (
                <ChevronRight className="size-4 shrink-0 text-white/30 transition-colors group-hover:text-white" />
              ) : null}
            </>
          );
          const key = `${sv.server_id ?? sv.persisted_game_id ?? sv.name}-${i}`;
          return (
            <li key={key}>
              {sv.server_id != null ? (
                <Link
                  href={`/${game}/server/${sv.server_id}`}
                  className="group flex items-center gap-4 px-1 py-3.5 transition-colors hover:bg-white/[0.04]"
                >
                  {body}
                </Link>
              ) : (
                <div className="flex items-center gap-4 px-1 py-3.5">{body}</div>
              )}
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}
