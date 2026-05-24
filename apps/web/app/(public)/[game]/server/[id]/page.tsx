"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Users, Lock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";
import { bf1Api, type ServerPlayer, type MapRotationItem } from "@/lib/api/bf1";

export default function ServerDetailPage() {
  const { id, game } = useParams<{ id: string; game: string }>();
  const router = useRouter();
  const gameId = Number(id);

  const detail = useQuery({
    queryKey: ["bf1-server", gameId],
    queryFn: () => bf1Api.getServer(gameId),
    enabled: Number.isFinite(gameId),
  });

  if (detail.isLoading) {
    return <main className="text-muted-foreground p-12 text-center">加载中…</main>;
  }
  if (!detail.data) {
    return <main className="text-destructive p-12 text-center">未找到服务器</main>;
  }

  const { summary, map_rotation, players } = detail.data;

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push(`/${game}/servers`)}
        className="-ml-2 self-start"
      >
        <ArrowLeft className="size-4" />
        返回服务器列表
      </Button>

      <header className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-2xl font-bold sm:text-3xl">{summary.name}</h1>
          {summary.has_password ? <Lock className="text-muted-foreground mt-1 size-5" /> : null}
        </div>
        <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-sm">
          <span className="flex items-center gap-1">
            <Users className="size-4" />
            <span className="tabular-nums">
              {summary.player_count} / {summary.max_player_count}
              {summary.queue_count > 0 ? ` (+${summary.queue_count})` : null}
            </span>
          </span>
          {summary.map_name ? <span>地图: {summary.map_name}</span> : null}
          {summary.game_mode ? <span>模式: {summary.game_mode}</span> : null}
          {summary.region ? <span>区域: {summary.region}</span> : null}
        </div>
        {summary.description ? (
          <Card>
            <CardContent className="p-4 text-sm leading-relaxed whitespace-pre-line">
              {summary.description}
            </CardContent>
          </Card>
        ) : null}
      </header>

      <Tabs defaultValue="players" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="players">玩家列表（{players.length}）</TabsTrigger>
          <TabsTrigger value="rotation">地图轮换（{map_rotation.length}）</TabsTrigger>
        </TabsList>
        <TabsContent value="players">
          <PlayersList players={players} />
        </TabsContent>
        <TabsContent value="rotation">
          <RotationList items={map_rotation} />
        </TabsContent>
      </Tabs>
    </main>
  );
}

function PlayersList({ players }: { players: ServerPlayer[] }) {
  const columns: Column<ServerPlayer>[] = [
    { key: "name", header: "玩家", cell: (p) => p.display_name, isCardTitle: true },
    {
      key: "team",
      header: "队伍",
      cell: (p) => (p.is_spectator ? "旁观" : p.team_id ? `T${p.team_id}` : "—"),
    },
    { key: "rank", header: "等级", cell: (p) => p.rank ?? "—" },
    { key: "id", header: "ID", cell: (p) => p.persona_id },
  ];
  return (
    <ResponsiveTable
      data={players}
      columns={columns}
      rowKey={(p) => p.persona_id}
      emptyState="服务器内暂无玩家数据"
    />
  );
}

function RotationList({ items }: { items: MapRotationItem[] }) {
  if (items.length === 0) {
    return (
      <div className="text-muted-foreground rounded-lg border border-dashed p-8 text-center">
        暂无地图轮换数据
      </div>
    );
  }
  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {items.map((m, i) => (
        <li key={`${m.map_name}-${i}`}>
          <Card className={m.is_current ? "border-primary" : ""}>
            <CardContent className="space-y-1 p-4">
              <div className="flex items-center justify-between">
                <span className="font-medium">{m.map_name ?? "未知地图"}</span>
                {m.is_current ? (
                  <span className="bg-primary text-primary-foreground rounded px-2 py-0.5 text-xs">
                    当前
                  </span>
                ) : null}
              </div>
              {m.game_mode ? (
                <div className="text-muted-foreground text-xs">{m.game_mode}</div>
              ) : null}
            </CardContent>
          </Card>
        </li>
      ))}
    </ul>
  );
}
