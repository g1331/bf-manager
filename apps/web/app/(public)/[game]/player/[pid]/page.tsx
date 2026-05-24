"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";
import { bf1Api, type WeaponStat, type VehicleStat, type RecentServer } from "@/lib/api/bf1";
import { formatCount, formatDuration } from "@/lib/utils";

export default function PlayerDetailPage() {
  const { pid } = useParams<{ pid: string }>();
  const personaId = Number(pid);

  const stats = useQuery({
    queryKey: ["bf1-stats", personaId],
    queryFn: () => bf1Api.getStats(personaId),
    enabled: Number.isFinite(personaId),
  });

  const persona = useQuery({
    queryKey: ["bf1-persona", personaId],
    queryFn: () => bf1Api.getPlayer(personaId),
    enabled: Number.isFinite(personaId),
  });

  if (!Number.isFinite(personaId)) {
    return <main className="text-destructive p-6 text-center">无效的 persona ID</main>;
  }

  const displayName =
    persona.data?.display_name ?? (persona.isLoading ? "加载中…" : `Persona ${personaId}`);
  const avatarUrl = persona.data?.avatar_url ?? null;

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6">
      <header className="flex items-center gap-4">
        {avatarUrl ? (
          // EA 头像域不在 next/image remotePatterns 内，用原生 img 避免额外配置
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={avatarUrl}
            alt={displayName}
            className="border-border size-16 shrink-0 rounded-full border object-cover"
          />
        ) : (
          <div className="bg-muted text-muted-foreground border-border flex size-16 shrink-0 items-center justify-center rounded-full border text-xl font-semibold">
            {displayName.slice(0, 1).toUpperCase()}
          </div>
        )}
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="truncate text-2xl font-bold sm:text-3xl">{displayName}</h1>
          <p className="text-muted-foreground text-sm">PID: {personaId}</p>
        </div>
      </header>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="等级" value={stats.data?.summary.rank ?? "—"} loading={stats.isLoading} />
        <StatCard
          label="K/D"
          value={stats.data?.summary.kd?.toFixed(2) ?? "—"}
          loading={stats.isLoading}
        />
        <StatCard
          label="KPM"
          value={stats.data?.summary.kpm?.toFixed(2) ?? "—"}
          loading={stats.isLoading}
        />
        <StatCard
          label="时长"
          value={
            stats.data?.summary.time_played_seconds
              ? formatDuration(stats.data.summary.time_played_seconds)
              : "—"
          }
          loading={stats.isLoading}
        />
      </section>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="overview">概览</TabsTrigger>
          <TabsTrigger value="weapons">武器</TabsTrigger>
          <TabsTrigger value="vehicles">载具</TabsTrigger>
          <TabsTrigger value="servers">最近</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab personaId={personaId} stats={stats.data} loading={stats.isLoading} />
        </TabsContent>
        <TabsContent value="weapons">
          <WeaponsTab personaId={personaId} />
        </TabsContent>
        <TabsContent value="vehicles">
          <VehiclesTab personaId={personaId} />
        </TabsContent>
        <TabsContent value="servers">
          <ServersTab personaId={personaId} />
        </TabsContent>
      </Tabs>
    </main>
  );
}

function StatCard({
  label,
  value,
  loading,
}: {
  label: string;
  value: string | number;
  loading?: boolean;
}) {
  return (
    <Card>
      <CardContent className="space-y-1 p-4">
        <div className="text-muted-foreground text-xs">{label}</div>
        <div className="text-2xl font-bold tabular-nums">{loading ? "…" : value}</div>
      </CardContent>
    </Card>
  );
}

function OverviewTab({
  personaId,
  stats,
  loading,
}: {
  personaId: number;
  stats?: {
    summary: {
      kills: number | null;
      deaths: number | null;
      wins: number | null;
      losses: number | null;
    };
  };
  loading?: boolean;
}) {
  void personaId;
  if (loading) return <div className="text-muted-foreground p-6 text-center">加载中…</div>;
  if (!stats) return <div className="text-muted-foreground p-6 text-center">暂无数据</div>;
  return (
    <Card>
      <CardHeader>
        <CardTitle>生涯综合</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
          <KeyValue label="击杀" value={stats.summary.kills} />
          <KeyValue label="死亡" value={stats.summary.deaths} />
          <KeyValue label="胜场" value={stats.summary.wins} />
          <KeyValue label="负场" value={stats.summary.losses} />
        </dl>
      </CardContent>
    </Card>
  );
}

function KeyValue({ label, value }: { label: string; value: number | null }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium tabular-nums">{value !== null ? formatCount(value) : "—"}</dd>
    </>
  );
}

function WeaponsTab({ personaId }: { personaId: number }) {
  const q = useQuery({
    queryKey: ["bf1-weapons", personaId],
    queryFn: () => bf1Api.getWeapons(personaId),
  });
  if (q.isLoading) return <div className="text-muted-foreground p-6 text-center">加载中…</div>;
  if (!q.data) return null;
  const top = [...q.data.weapons].sort((a, b) => (b.kills ?? 0) - (a.kills ?? 0)).slice(0, 30);

  const columns: Column<WeaponStat>[] = [
    { key: "name", header: "武器", cell: (w) => w.name ?? "—", isCardTitle: true },
    { key: "category", header: "类别", cell: (w) => w.category ?? "—" },
    { key: "kills", header: "击杀", cell: (w) => formatCount(w.kills ?? 0) },
    { key: "headshots", header: "爆头", cell: (w) => formatCount(w.headshots ?? 0) },
    {
      key: "accuracy",
      header: "命中率",
      cell: (w) => (w.accuracy != null ? `${w.accuracy.toFixed(1)}%` : "—"),
    },
  ];

  return (
    <ResponsiveTable
      data={top}
      columns={columns}
      rowKey={(w) => `${w.category}-${w.name}`}
      emptyState="暂无武器数据"
    />
  );
}

function VehiclesTab({ personaId }: { personaId: number }) {
  const q = useQuery({
    queryKey: ["bf1-vehicles", personaId],
    queryFn: () => bf1Api.getVehicles(personaId),
  });
  if (q.isLoading) return <div className="text-muted-foreground p-6 text-center">加载中…</div>;
  if (!q.data) return null;
  const top = [...q.data.vehicles].sort((a, b) => (b.kills ?? 0) - (a.kills ?? 0)).slice(0, 30);

  const columns: Column<VehicleStat>[] = [
    { key: "name", header: "载具", cell: (v) => v.name ?? "—", isCardTitle: true },
    { key: "category", header: "类别", cell: (v) => v.category ?? "—" },
    { key: "kills", header: "击杀", cell: (v) => formatCount(v.kills ?? 0) },
    { key: "destroyed", header: "摧毁", cell: (v) => formatCount(v.destroyed ?? 0) },
  ];

  return (
    <ResponsiveTable
      data={top}
      columns={columns}
      rowKey={(v) => `${v.category}-${v.name}`}
      emptyState="暂无载具数据"
    />
  );
}

function ServersTab({ personaId }: { personaId: number }) {
  const q = useQuery({
    queryKey: ["bf1-recent-servers", personaId],
    queryFn: () => bf1Api.getRecentServers(personaId),
  });
  if (q.isLoading) return <div className="text-muted-foreground p-6 text-center">加载中…</div>;
  if (!q.data) return null;

  const columns: Column<RecentServer>[] = [
    { key: "name", header: "服务器", cell: (s) => s.name, isCardTitle: true },
    { key: "map", header: "地图", cell: (s) => s.map_name ?? "—" },
    { key: "mode", header: "模式", cell: (s) => s.game_mode ?? "—" },
  ];

  return (
    <ResponsiveTable
      data={q.data.servers}
      columns={columns}
      rowKey={(s) => `${s.server_id ?? s.persisted_game_id ?? s.name}`}
      emptyState="暂无最近游玩记录"
    />
  );
}
