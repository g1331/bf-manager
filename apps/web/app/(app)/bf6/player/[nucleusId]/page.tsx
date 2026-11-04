"use client";

/**
 * BF6 玩家战绩页（作战档案）
 *
 * 首屏是主玩兵种立绘 + K/D 与核心数据，下面是吸顶分区：概览 / 武器 / 载具 / 配备 / 地图 / 模式，
 * 当前分区记在 URL hash。数据都是 EA 的生涯统计，后端缓存 20 分钟。
 */

import { Suspense, useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowLeft } from "lucide-react";
import { SectionNav, useTabHash } from "@/components/bf1/SectionNav";
import { DetailError, DetailNote } from "@/components/bf1/visual/DetailBackground";
import { Bf6Hero } from "@/components/bf6/Bf6Hero";
import { GadgetsTab, VehiclesTab, WeaponsTab } from "@/components/bf6/Bf6Gear";
import { MapsTab, ModesTab } from "@/components/bf6/Bf6Maps";
import { Bf6Overview, type Bf6Tab } from "@/components/bf6/Bf6Overview";
import { PlayerDetailSkeleton } from "@/components/layout/PageSkeleton";
import { useBack } from "@/hooks/useNavigation";
import type { Bf6PlayerStats } from "@/lib/api/bf6";
import { parsePlatform } from "@/lib/bf6/player-link";
import { pushBf6RecentPlayer, useBf6RecentPlayers } from "@/lib/bf6/recent-players";
import { bf6Queries } from "@/lib/queries/bf6";

const TAB_KEYS = ["overview", "weapons", "vehicles", "gadgets", "maps", "modes"] as const;

export default function Bf6PlayerPage() {
  const { nucleusId } = useParams<{ nucleusId: string }>();
  const id = Number(nucleusId);
  const valid = Number.isSafeInteger(id) && id > 0;
  const statsQ = useQuery({ ...bf6Queries.stats(id), enabled: valid });

  if (!valid) return <DetailNote text="无效的玩家 ID" />;
  if (statsQ.isLoading) return <PlayerDetailSkeleton />;
  if (!statsQ.data) {
    return (
      <DetailError
        error={statsQ.error}
        notFoundText="没有找到这个玩家"
        onRetry={() => void statsQ.refetch()}
        retrying={statsQ.isFetching}
      />
    );
  }
  if (!statsQ.data.has_data) return <DetailNote text="EA 没有这名玩家的 BF6 多人战绩" />;
  return (
    // useSearchParams 需要 Suspense 边界
    <Suspense>
      <PlayerView nucleusId={id} stats={statsQ.data} />
    </Suspense>
  );
}

/** 战绩到手后才挂载（纯客户端），分区状态可以直接从 window 读初值 */
function PlayerView({ nucleusId, stats }: { nucleusId: number; stats: Bf6PlayerStats }) {
  const back = useBack("/bf6/players");
  const params = useSearchParams();
  const name = (params.get("name") ?? "").trim();
  const platform = parsePlatform(params.get("platform"));

  // 名字只用来显示：用它重新查一次，ID 对得上才采信；对不上就退回本机最近查看里的记录
  const resolveQ = useQuery({ ...bf6Queries.resolve(name, platform), enabled: name.length > 0 });
  const confirmed = resolveQ.data?.nucleus_id === nucleusId ? resolveQ.data : null;
  const remembered = useBf6RecentPlayers().find((p) => p.nucleus_id === nucleusId);
  const displayName = confirmed?.display_name ?? remembered?.display_name ?? `玩家 ${nucleusId}`;
  const avatarUrl = confirmed?.avatar_url ?? remembered?.avatar_url ?? null;
  const platformNs = confirmed?.platform ?? remembered?.platform ?? null;

  useEffect(() => {
    if (confirmed?.display_name) {
      pushBf6RecentPlayer({
        nucleus_id: confirmed.nucleus_id,
        display_name: confirmed.display_name,
        avatar_url: confirmed.avatar_url,
        platform: confirmed.platform,
      });
    }
  }, [confirmed]);

  const tabs = [
    { key: "overview" as const, label: "概览" },
    { key: "weapons" as const, label: "武器", count: stats.weapons.length },
    { key: "vehicles" as const, label: "载具", count: stats.vehicles.length },
    { key: "gadgets" as const, label: "配备", count: stats.gadgets.length },
    { key: "maps" as const, label: "地图", count: stats.maps.length },
    { key: "modes" as const, label: "模式", count: stats.modes.length },
  ];
  const [tab, setTab] = useTabHash(TAB_KEYS, TAB_KEYS);
  const showTab = (t: Bf6Tab) => {
    setTab(t);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 pt-4 pb-10 sm:px-8 sm:pt-6">
      <button
        type="button"
        onClick={back}
        className="text-bf6-mute hover:text-bf6-fg mb-2 hidden items-center gap-1.5 text-sm transition-colors lg:inline-flex"
      >
        <ArrowLeft className="size-4" />
        返回
      </button>

      <Bf6Hero name={displayName} avatarUrl={avatarUrl} platform={platformNs} stats={stats} />

      <SectionNav tabs={tabs} tab={tab} onTab={setTab} accent="bf6" />

      <motion.div
        key={tab}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
        className="mt-6 sm:mt-8"
      >
        {tab === "overview" && <Bf6Overview stats={stats} onShowTab={showTab} />}
        {tab === "weapons" && <WeaponsTab stats={stats} />}
        {tab === "vehicles" && <VehiclesTab stats={stats} />}
        {tab === "gadgets" && <GadgetsTab stats={stats} />}
        {tab === "maps" && <MapsTab stats={stats} />}
        {tab === "modes" && <ModesTab stats={stats} />}
      </motion.div>

      <p className="border-bf6-line text-bf6-mute mt-10 border-t pt-3.5 text-xs">
        EA 生涯数据 · 更新于 {new Date(stats.fetched_at).toLocaleString("zh-CN", { hour12: false })}
      </p>
    </div>
  );
}
