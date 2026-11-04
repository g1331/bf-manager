"use client";

/**
 * BF6 战绩查询页
 *
 * EA 按显示名精确查找，一个名字只对应一个账号，结果是一张卡片，点开进战绩页。
 * 名字和平台记在地址栏（?q=&platform=），从战绩页返回、刷新都能看到同一结果。
 * 没有输入时展示本机「最近查看」。
 */

import { Suspense, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, History, Loader2, Search, X } from "lucide-react";
import { DarkInput } from "@/components/common/DarkInput";
import { PlayerAvatar } from "@/components/common/PlayerAvatar";
import { ApiException } from "@/lib/api-client";
import type { Bf6Platform, Bf6ResolvedPlayer } from "@/lib/api/bf6";
import { bf6PlayerHref, parsePlatform, platformLabel } from "@/lib/bf6/player-link";
import { bf6Queries } from "@/lib/queries/bf6";
import {
  clearBf6RecentPlayers,
  useBf6RecentPlayers,
  type Bf6RecentPlayer,
} from "@/lib/bf6/recent-players";
import { cn } from "@/lib/utils";

const PLATFORMS: { key: Bf6Platform | null; label: string }[] = [
  { key: null, label: "全部平台" },
  { key: "ea", label: "EA" },
  { key: "psn", label: "PlayStation" },
  { key: "xbox", label: "Xbox" },
  { key: "epic", label: "Epic" },
];

export default function Bf6PlayerSearchPage() {
  // useSearchParams 需要 Suspense 边界，否则整页退化为客户端渲染并在构建时报错
  return (
    <Suspense>
      <PlayerSearch />
    </Suspense>
  );
}

function PlayerSearch() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const q = (params.get("q") ?? "").trim();
  const platform = parsePlatform(params.get("platform"));
  const [input, setInput] = useState(q);
  const [inputPlatform, setInputPlatform] = useState<Bf6Platform | null>(platform);

  // 浏览器前进后退改了地址栏时同步输入框（渲染期比对，免去一轮 effect）
  const [synced, setSynced] = useState({ q, platform });
  if (synced.q !== q || synced.platform !== platform) {
    setSynced({ q, platform });
    setInput(q);
    setInputPlatform(platform);
  }

  const resolve = useQuery({ ...bf6Queries.resolve(q, platform), enabled: q.length > 0 });

  const go = (name: string, p: Bf6Platform | null) => {
    const qs = new URLSearchParams();
    if (name) qs.set("q", name);
    if (p) qs.set("platform", p);
    const query = qs.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const name = input.trim();
    if (!name) return;
    if (name === q && inputPlatform === platform) resolve.refetch();
    else go(name, inputPlatform);
  };

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:space-y-8 sm:px-6 sm:py-10">
      <header>
        <div className="text-bf6 flex items-center gap-3 font-mono text-[11px] tracking-[0.25em] uppercase">
          <span className="tracking-[-2px]">▶▶▶▶</span>Battlefield 6 // Career
        </div>
        <h1 className="font-display text-bf6-fg mt-2 text-3xl font-bold tracking-wide sm:mt-3 sm:text-5xl">
          战绩查询
        </h1>
        <p className="text-bf6-mute mt-2 text-sm">
          输入 EA 账号的显示名，需要完整拼写，不区分大小写
        </p>
      </header>

      <div className="bf6-cut border-bf6-line bg-bf6-panel/80 border p-2 [--cut:16px] sm:p-4">
        <form onSubmit={submit} className="flex gap-2 sm:gap-3">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2 text-white/40 sm:left-4" />
            <DarkInput
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="EA 显示名"
              aria-label="EA 显示名"
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              autoFocus
              maxLength={64}
              className="h-12 pr-11 pl-11 sm:h-14 sm:pl-12 sm:text-lg"
            />
            {input ? (
              <button
                type="button"
                onClick={() => {
                  setInput("");
                  go("", inputPlatform);
                }}
                aria-label="清空"
                className="absolute top-1/2 right-3 -translate-y-1/2 p-1 text-white/40 transition-colors hover:text-white"
              >
                <X className="size-4" />
              </button>
            ) : null}
          </div>
          <button
            type="submit"
            disabled={resolve.isFetching}
            className="font-display bg-bf6 hover:bg-bf6-soft flex h-12 shrink-0 items-center gap-2 px-5 text-[15px] font-bold tracking-[0.12em] text-black transition-colors [clip-path:polygon(0_0,100%_0,100%_calc(100%-12px),calc(100%-12px)_100%,0_100%)] disabled:opacity-60 sm:h-14 sm:px-8 sm:text-base sm:tracking-[0.2em]"
          >
            {resolve.isFetching ? <Loader2 className="size-5 animate-spin" /> : null}
            查询
          </button>
        </form>
        <div className="mt-2.5 flex flex-wrap gap-1.5 px-0.5 sm:mt-3">
          {PLATFORMS.map((p) => (
            <button
              key={p.label}
              type="button"
              aria-pressed={inputPlatform === p.key}
              onClick={() => setInputPlatform(p.key)}
              className={cn(
                "border px-2.5 py-1 text-xs transition-colors",
                inputPlatform === p.key
                  ? "border-bf6 bg-bf6/15 text-bf6-soft"
                  : "border-bf6-line-strong text-bf6-mute hover:text-bf6-fg",
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {q ? (
        <Result query={q} data={resolve.data} loading={resolve.isLoading} error={resolve.error} />
      ) : (
        <Recent />
      )}
    </main>
  );
}

function Result({
  query,
  data,
  loading,
  error,
}: {
  query: string;
  data: Bf6ResolvedPlayer | undefined;
  loading: boolean;
  error: Error | null;
}) {
  if (loading) return <div className="h-[84px] animate-pulse bg-white/[0.06]" />;
  if (error || !data) {
    return (
      <div
        className={cn(
          "border px-4 py-8 text-center text-sm",
          error instanceof ApiException && error.status !== 422
            ? "border-red-500/30 bg-red-500/10 text-red-200"
            : "border-bf6-line bg-bf6-panel text-bf6-mute",
        )}
      >
        {error instanceof ApiException ? error.message : `没有找到「${query}」`}
      </div>
    );
  }
  return (
    <PlayerCard
      href={bf6PlayerHref(data)}
      name={data.display_name ?? query}
      avatarUrl={data.avatar_url}
      platform={data.platform}
      note={data.has_current_season_stats ? "本赛季有战绩" : "本赛季暂无战绩"}
    />
  );
}

function PlayerCard({
  href,
  name,
  avatarUrl,
  platform,
  note,
}: {
  href: string;
  name: string;
  avatarUrl: string | null;
  platform: string | null;
  note?: string;
}) {
  const platformName = platformLabel(platform);
  return (
    <Link
      href={href}
      className="group border-bf6-line border-l-bf6 bg-bf6-panel flex items-center gap-3 border border-l-2 px-4 py-3.5 transition-colors hover:bg-white/[0.06]"
    >
      <PlayerAvatar avatarUrl={avatarUrl} displayName={name} size="md" />
      <div className="min-w-0 flex-1">
        <div className="text-bf6-fg truncate font-semibold">{name}</div>
        <div className="text-bf6-mute mt-0.5 flex items-center gap-2 text-xs">
          {platformName ? <span>{platformName}</span> : null}
          {note ? <span>{note}</span> : null}
        </div>
      </div>
      <ChevronRight className="size-4 shrink-0 text-white/30 transition-transform group-hover:translate-x-0.5 group-hover:text-white" />
    </Link>
  );
}

function Recent() {
  const recent = useBf6RecentPlayers();
  if (recent.length === 0) return null;
  return (
    <section>
      <div className="text-bf6-mute mb-3 flex items-center justify-between text-xs">
        <span className="flex items-center gap-2">
          <History className="size-3.5" />
          最近查看
        </span>
        <button
          type="button"
          onClick={clearBf6RecentPlayers}
          className="hover:text-bf6-fg transition-colors"
        >
          清除
        </button>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {recent.map((p: Bf6RecentPlayer) => (
          <li key={p.nucleus_id}>
            <PlayerCard
              href={bf6PlayerHref(p)}
              name={p.display_name}
              avatarUrl={p.avatar_url}
              platform={p.platform}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
