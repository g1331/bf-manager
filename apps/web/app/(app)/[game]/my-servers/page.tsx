"use client";

/**
 * 「我的服务器」：当前登录用户有服管角色（自动识别的服主 / 管理员，或人工授权）的服务器列表。
 *
 * 列表来源是后端按服管角色枚举的 ServerMembership：当用户访问自己作为 EA 服主 / 管理员的服务器
 * 详情时，鉴权层会按 EA 名单识别并落库，此后该服即出现在本页。链接用末次解析到的 gameId 跳详情；
 * gameId 为空（尚未在线时识别）时不可点。与全量「服务器浏览器」分列两个子标签，避免在大列表里找自己的服。
 */

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, MapPin, RotateCw, Server } from "lucide-react";
import { ServerSubTabs } from "@/components/bf1/ServerSubTabs";
import { useSession } from "@/hooks/useSession";
import { bf1Api, type MyServerItem } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

const ROLE_LABEL: Record<MyServerItem["role"], string> = {
  owner: "服主",
  admin: "管理员",
  moderator: "协管",
  viewer: "查看",
};

const ROLE_STYLE: Record<MyServerItem["role"], string> = {
  owner: "bg-amber-500/15 text-amber-300",
  admin: "bg-sky-500/15 text-sky-300",
  moderator: "bg-emerald-500/15 text-emerald-300",
  viewer: "bg-white/10 text-white/60",
};

export default function MyServersPage() {
  const params = useParams<{ game: string }>();
  const router = useRouter();
  const session = useSession();
  const isLoggedIn = !!session.data;

  const q = useQuery({
    queryKey: ["bf1-my-servers"],
    queryFn: () => bf1Api.getMyServers(),
    enabled: isLoggedIn,
  });

  const items = q.data?.items ?? [];

  return (
    <main className="flex flex-col gap-4 py-4 text-white sm:py-6 lg:h-full lg:min-h-0">
      <header className="flex flex-wrap items-end justify-between gap-3 lg:shrink-0">
        <div>
          <div className="font-display flex items-center gap-2 text-xs font-medium tracking-[0.2em] text-amber-500 uppercase">
            <span className="h-[2px] w-6 bg-amber-500" />
            My Servers
          </div>
          <h1 className="mt-1.5 text-2xl font-bold tracking-wide sm:text-3xl">我的服务器</h1>
        </div>
        {isLoggedIn ? (
          <button
            type="button"
            onClick={() => q.refetch()}
            disabled={q.isFetching}
            className="inline-flex items-center gap-1.5 text-sm text-white/55 transition-colors hover:text-white disabled:opacity-50"
          >
            <RotateCw className={cn("size-4", q.isFetching && "animate-spin")} />
            刷新
          </button>
        ) : null}
      </header>

      <ServerSubTabs game={params.game} active="mine" />

      {session.isLoading ? (
        <div className="py-16 text-center text-sm text-white/45">加载中…</div>
      ) : !isLoggedIn ? (
        <EmptyNote text="登录后查看你管理的服务器。">
          <Link
            href={`/login?next=${encodeURIComponent(`/${params.game}/my-servers`)}`}
            className="mt-4 inline-flex h-11 items-center bg-amber-500 px-6 text-[15px] font-semibold text-black transition-colors hover:bg-amber-400"
          >
            登录
          </Link>
        </EmptyNote>
      ) : q.isLoading ? (
        <div className="py-16 text-center text-sm text-white/45">加载中…</div>
      ) : q.isError ? (
        <EmptyNote text="加载失败，请稍后重试。" />
      ) : items.length === 0 ? (
        <EmptyNote text="暂无你管理的服务器。访问你作为服主 / 管理员的服务器详情后，会自动出现在这里。" />
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((s) => (
            <MyServerCard
              key={s.server_pk}
              item={s}
              onOpen={() => s.game_id != null && router.push(`/${params.game}/server/${s.game_id}`)}
            />
          ))}
        </ul>
      )}
    </main>
  );
}

function MyServerCard({ item, onOpen }: { item: MyServerItem; onOpen: () => void }) {
  const clickable = item.game_id != null;
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        disabled={!clickable}
        title={clickable ? undefined : "该服务器当前未在线，暂无法打开详情"}
        className={cn(
          "group flex w-full items-center gap-3 rounded-sm border border-white/10 bg-black/30 px-4 py-3 text-left transition-colors",
          clickable ? "hover:border-white/25 hover:bg-white/[0.06]" : "cursor-default opacity-60",
        )}
      >
        <div className="flex size-10 shrink-0 items-center justify-center rounded-sm bg-white/[0.04]">
          <Server className="size-4 text-white/40" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className="truncate text-[15px] font-medium text-white sm:text-sm"
              title={item.name ?? undefined}
            >
              {item.name ?? `服务器 #${item.server_id}`}
            </span>
            <span
              className={cn("shrink-0 rounded-sm px-1.5 py-0.5 text-[11px]", ROLE_STYLE[item.role])}
            >
              {ROLE_LABEL[item.role]}
            </span>
          </div>
          <div className="mt-1 flex min-w-0 items-center gap-1.5 text-xs text-white/45 tabular-nums">
            <span className="shrink-0">ServerID {item.server_id}</span>
            {item.via_group ? (
              <>
                <span className="text-white/25">·</span>
                <span className="truncate">经群组「{item.via_group}」</span>
              </>
            ) : null}
            {!clickable ? (
              <>
                <span className="text-white/25">·</span>
                <span className="inline-flex items-center gap-1 text-white/40">
                  <MapPin className="size-3" />
                  未在线
                </span>
              </>
            ) : null}
          </div>
        </div>
        {clickable ? (
          <ChevronRight className="size-4 shrink-0 text-white/30 transition-colors group-hover:text-white/70" />
        ) : null}
      </button>
    </li>
  );
}

function EmptyNote({ text, children }: { text: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-sm border border-dashed border-white/15 px-6 py-16 text-center text-sm text-white/45">
      <p>{text}</p>
      {children}
    </div>
  );
}
