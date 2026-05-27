"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Users, Lock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";
import { AdminPanel } from "@/components/bf1/AdminPanel";
import { useSession } from "@/hooks/useSession";
import {
  bf1Api,
  type ServerPlayer,
  type MapRotationItem,
  type ServerExtras,
  type ServerMember,
} from "@/lib/api/bf1";

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

  const { summary, map_rotation, players, extras } = detail.data;
  return (
    <ServerDetailView
      gameId={gameId}
      game={game}
      summary={summary}
      map_rotation={map_rotation}
      players={players}
      extras={extras}
      detail={detail.data}
      routerPush={router.push}
    />
  );
}

function ServerDetailView({
  gameId,
  game,
  summary,
  map_rotation,
  players,
  extras,
  detail,
  routerPush,
}: {
  gameId: number;
  game: string;
  summary: import("@/lib/api/bf1").ServerSummary;
  map_rotation: MapRotationItem[];
  players: ServerPlayer[];
  extras: ServerExtras;
  detail: import("@/lib/api/bf1").ServerDetail;
  routerPush: (path: string) => void;
}) {
  const session = useSession();
  const isLoggedIn = !!session.data;
  const memberCount = extras.admins.length + extras.vips.length + extras.banned.length;

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => routerPush(`/${game}/servers`)}
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
          {summary.map_display_name || summary.map_name ? (
            <span>地图: {summary.map_display_name ?? summary.map_name}</span>
          ) : null}
          {summary.mode_display_name || summary.game_mode ? (
            <span>模式: {summary.mode_display_name ?? summary.game_mode}</span>
          ) : null}
          {summary.region_display_name || summary.region ? (
            <span>区域: {summary.region_display_name ?? summary.region}</span>
          ) : null}
        </div>
        {summary.description ? (
          <Card>
            <CardContent className="p-4 text-sm leading-relaxed whitespace-pre-line">
              {summary.description}
            </CardContent>
          </Card>
        ) : null}
      </header>

      <ServerInfoCard extras={extras} />

      <Tabs defaultValue="players" className="w-full">
        <TabsList className={`grid w-full ${isLoggedIn ? "grid-cols-4" : "grid-cols-3"}`}>
          <TabsTrigger value="players">玩家列表（{players.length}）</TabsTrigger>
          <TabsTrigger value="rotation">地图轮换（{map_rotation.length}）</TabsTrigger>
          <TabsTrigger value="members">成员名单（{memberCount}）</TabsTrigger>
          {isLoggedIn ? <TabsTrigger value="admin">管理</TabsTrigger> : null}
        </TabsList>
        <TabsContent value="players">
          <PlayersList players={players} />
        </TabsContent>
        <TabsContent value="rotation">
          <RotationList items={map_rotation} />
        </TabsContent>
        <TabsContent value="members">
          <MembersPanel extras={extras} />
        </TabsContent>
        {isLoggedIn ? (
          <TabsContent value="admin">
            <AdminPanel gameId={gameId} detail={detail} />
          </TabsContent>
        ) : null}
      </Tabs>
    </main>
  );
}

function ServerInfoCard({ extras }: { extras: ServerExtras }) {
  const hasOwner = !!extras.owner?.persona_id;
  const hasIds = !!(extras.game_id || extras.server_id || extras.persisted_game_id);
  const hasLifecycle =
    !!extras.lifecycle.created_at || !!extras.lifecycle.expires_at || !!extras.lifecycle.updated_at;
  const hasPlatoon = !!extras.platoon?.name;
  if (!hasOwner && !hasIds && !hasLifecycle && !hasPlatoon && extras.bookmark_count == null) {
    return null;
  }
  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <h2 className="text-sm font-semibold">服务器信息</h2>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          {extras.owner?.display_name ? (
            <InfoRow label="服主">
              <span>{extras.owner.display_name}</span>
              {extras.owner.persona_id ? (
                <span className="text-muted-foreground ml-2 text-xs tabular-nums">
                  #{extras.owner.persona_id}
                </span>
              ) : null}
              {extras.owner.platform ? (
                <span className="bg-muted ml-2 rounded px-1.5 py-0.5 text-xs">
                  {extras.owner.platform.toUpperCase()}
                </span>
              ) : null}
            </InfoRow>
          ) : null}
          {extras.bookmark_count != null ? (
            <InfoRow label="收藏">
              <span className="tabular-nums">{extras.bookmark_count}</span>
            </InfoRow>
          ) : null}
          {extras.game_id ? (
            <InfoRow label="GameID">
              <span className="font-mono text-xs tabular-nums">{extras.game_id}</span>
            </InfoRow>
          ) : null}
          {extras.server_id ? (
            <InfoRow label="ServerID">
              <span className="font-mono text-xs tabular-nums">{extras.server_id}</span>
            </InfoRow>
          ) : null}
          {extras.persisted_game_id ? (
            <InfoRow label="PersistID">
              <span className="font-mono text-xs break-all">{extras.persisted_game_id}</span>
            </InfoRow>
          ) : null}
          {extras.lifecycle.created_at ? (
            <InfoRow label="创建时间">
              <span className="tabular-nums">{formatDateTime(extras.lifecycle.created_at)}</span>
            </InfoRow>
          ) : null}
          {extras.lifecycle.updated_at ? (
            <InfoRow label="更新时间">
              <span className="tabular-nums">{formatDateTime(extras.lifecycle.updated_at)}</span>
            </InfoRow>
          ) : null}
          {extras.lifecycle.expires_at ? (
            <InfoRow label="到期时间">
              <span className="tabular-nums">{formatDateTime(extras.lifecycle.expires_at)}</span>
            </InfoRow>
          ) : null}
        </dl>
        {extras.platoon?.name ? (
          <div className="bg-muted/40 rounded-md border p-3 text-sm">
            <div className="mb-1 font-medium">
              战队 [{extras.platoon.tag ?? "—"}] {extras.platoon.name}
              {extras.platoon.size != null ? (
                <span className="text-muted-foreground ml-2 text-xs">{extras.platoon.size} 人</span>
              ) : null}
            </div>
            {extras.platoon.description ? (
              <p className="text-muted-foreground text-xs leading-relaxed whitespace-pre-line">
                {extras.platoon.description}
              </p>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="text-muted-foreground w-20 shrink-0 text-xs">{label}</dt>
      <dd className="flex-1">{children}</dd>
    </div>
  );
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function MembersPanel({ extras }: { extras: ServerExtras }) {
  return (
    <div className="space-y-4">
      <MemberSection title="管理员" hint="/ 50" members={extras.admins} />
      <MemberSection title="VIP" hint="/ 50" members={extras.vips} />
      <MemberSection title="封禁名单" hint="/ 200" members={extras.banned} />
    </div>
  );
}

function MemberSection({
  title,
  hint,
  members,
}: {
  title: string;
  hint: string;
  members: ServerMember[];
}) {
  const columns: Column<ServerMember>[] = [
    {
      key: "name",
      header: title,
      cell: (m) => m.display_name ?? "—",
      isCardTitle: true,
    },
    {
      key: "platform",
      header: "平台",
      cell: (m) => (m.platform ? m.platform.toUpperCase() : "—"),
    },
    { key: "id", header: "Persona ID", cell: (m) => m.persona_id },
  ];
  return (
    <section>
      <div className="text-muted-foreground mb-2 flex items-baseline gap-2 text-xs">
        <span className="font-medium">{title}</span>
        <span className="tabular-nums">
          {members.length} {hint}
        </span>
      </div>
      <ResponsiveTable
        data={members}
        columns={columns}
        rowKey={(m) => m.persona_id}
        emptyState={`暂无${title}`}
      />
    </section>
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
      {items.map((m, i) => {
        const mapLabel = m.map_display_name ?? m.map_name ?? "未知地图";
        const modeLabel = m.mode_display_name ?? m.game_mode;
        return (
          <li key={`${m.map_name}-${i}`}>
            <Card className={`overflow-hidden ${m.is_current ? "border-primary" : ""}`}>
              {m.map_image_url ? (
                <div className="bg-muted relative aspect-[16/9] w-full">
                  {/* EA CDN 自带缩放与缓存，故不走 next/image；
                      如未来切换需要在 next.config.js 的 images.remotePatterns 加白名单。 */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={m.map_image_url}
                    alt={mapLabel}
                    loading="lazy"
                    className="h-full w-full object-cover"
                  />
                </div>
              ) : null}
              <CardContent className="space-y-1 p-4">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{mapLabel}</span>
                  {m.is_current ? (
                    <span className="bg-primary text-primary-foreground rounded px-2 py-0.5 text-xs">
                      当前
                    </span>
                  ) : null}
                </div>
                {modeLabel ? (
                  <div className="text-muted-foreground text-xs">{modeLabel}</div>
                ) : null}
              </CardContent>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}
