"use client";

import { useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Search, Users, Lock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { bf1Api, type ServerSummary } from "@/lib/api/bf1";

const PAGE_SIZE = 50;

export default function ServerListPage() {
  const params = useParams<{ game: string }>();
  const router = useRouter();
  const [keyword, setKeyword] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const servers = useQuery({
    queryKey: ["bf1-servers", activeQuery],
    queryFn: () => bf1Api.listServers(activeQuery || undefined, 200),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setActiveQuery(keyword.trim());
    setVisibleCount(PAGE_SIZE);
  };

  const allItems = servers.data?.items ?? [];
  const visibleItems = allItems.slice(0, visibleCount);
  const hasMore = visibleCount < allItems.length;

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:px-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold sm:text-3xl">服务器列表</h1>
        <p className="text-muted-foreground text-sm">浏览所有 Battlefield 1 服务器</p>
      </header>

      <form onSubmit={submit} className="flex gap-2">
        <Input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="按服务器名搜索（留空查全部）"
          className="flex-1"
        />
        <Button type="submit" disabled={servers.isFetching} size="lg" className="px-6">
          <Search className="size-4" />
          {servers.isFetching ? "查询中…" : "搜索"}
        </Button>
      </form>

      {servers.isLoading ? (
        <div className="text-muted-foreground p-12 text-center">加载中…</div>
      ) : allItems.length > 0 ? (
        <>
          <section className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {visibleItems.map((s) => (
              <ServerCard
                key={s.server_id}
                server={s}
                onClick={() => s.game_id && router.push(`/${params.game}/server/${s.game_id}`)}
              />
            ))}
          </section>
          <div className="text-muted-foreground flex flex-col items-center gap-2 pt-2 text-sm">
            <span className="tabular-nums">
              已显示 {visibleItems.length} / {allItems.length} 条
            </span>
            {hasMore ? (
              <Button
                variant="outline"
                onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}
                className="px-8"
              >
                加载更多
              </Button>
            ) : null}
          </div>
        </>
      ) : (
        <div className="text-muted-foreground rounded-lg border border-dashed p-12 text-center">
          {servers.data ? "未找到匹配的服务器" : "请先发起搜索"}
        </div>
      )}
    </main>
  );
}

function ServerCard({ server, onClick }: { server: ServerSummary; onClick: () => void }) {
  const fill =
    server.max_player_count > 0
      ? Math.round((server.player_count / server.max_player_count) * 100)
      : 0;
  const mapLabel = server.map_display_name ?? server.map_name;
  const modeLabel = server.mode_display_name ?? server.game_mode;
  const regionLabel = server.region_display_name ?? server.region;
  return (
    <Card
      onClick={onClick}
      className="hover:border-primary active:bg-muted/50 cursor-pointer transition"
    >
      <CardContent className="flex gap-3 p-4">
        {server.map_image_url ? (
          <div className="bg-muted relative h-20 w-32 shrink-0 overflow-hidden rounded">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={server.map_image_url}
              alt={mapLabel ?? ""}
              loading="lazy"
              className="h-full w-full object-cover"
            />
          </div>
        ) : null}
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="flex items-start justify-between gap-2">
            <h3 className="line-clamp-2 flex-1 font-medium" title={server.name}>
              {server.name}
            </h3>
            {server.has_password ? (
              <Lock className="text-muted-foreground size-4 shrink-0" />
            ) : null}
          </div>
          <div className="text-muted-foreground flex flex-wrap gap-x-3 gap-y-1 text-xs">
            {mapLabel ? <span>{mapLabel}</span> : null}
            {modeLabel ? <span>· {modeLabel}</span> : null}
            {regionLabel ? <span>· {regionLabel}</span> : null}
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1 text-sm tabular-nums">
              <Users className="text-muted-foreground size-4" />
              <span className="font-medium">{server.player_count}</span>
              <span className="text-muted-foreground">/ {server.max_player_count}</span>
              {server.queue_count > 0 ? (
                <span className="text-amber-600">+{server.queue_count}</span>
              ) : null}
            </div>
            <div className="bg-muted relative h-1.5 flex-1 overflow-hidden rounded-full">
              <div
                className="bg-primary absolute inset-y-0 left-0 transition-all"
                style={{ width: `${Math.min(fill, 100)}%` }}
              />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
