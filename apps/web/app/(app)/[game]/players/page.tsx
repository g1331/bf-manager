"use client";

/**
 * BF1 战绩查询页
 *
 * 关键词记在地址栏（?q=），从详情页返回、刷新或分享链接都能看到同一组结果。
 * 没有关键词时展示「我的账号」（已绑定 EA 账号时）与本机「最近查看」，一键回到常看的玩家。
 */

import { Suspense, useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ChevronRight, History, Loader2, Search, UserRound, X } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { DarkInput } from "@/components/common/DarkInput";
import { PlayerAvatar } from "@/components/common/PlayerAvatar";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { useSession } from "@/hooks/useSession";
import { ApiException } from "@/lib/api-client";
import { bf1Api, type PersonaBrief } from "@/lib/api/bf1";
import { clearRecentPlayers, useRecentPlayers } from "@/lib/bf1/recent-players";
import { cn } from "@/lib/utils";
import { TipLine } from "@/components/bf1/codex/TipLine";

const MIN_QUERY = 2;

export default function PlayerSearchPage() {
  // useSearchParams 需要 Suspense 边界，否则整页退化为客户端渲染并在构建时报错
  return (
    <Suspense>
      <PlayerSearch />
    </Suspense>
  );
}

function PlayerSearch() {
  const { game } = useParams<{ game: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const q = (useSearchParams().get("q") ?? "").trim();
  const [input, setInput] = useState(q);
  const [hint, setHint] = useState<string | null>(null);

  // 浏览器前进后退改了 ?q= 时同步输入框（渲染期比对，免去一轮 effect）
  const [syncedQ, setSyncedQ] = useState(q);
  if (syncedQ !== q) {
    setSyncedQ(q);
    setInput(q);
  }

  const search = useQuery({
    queryKey: ["bf1-player-search", q.toLowerCase()],
    queryFn: () => bf1Api.searchPlayers(q),
    enabled: q.length >= MIN_QUERY,
    staleTime: 5 * 60_000,
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const name = input.trim();
    if (name.length < MIN_QUERY) {
      setHint(`昵称至少 ${MIN_QUERY} 个字符`);
      return;
    }
    setHint(null);
    if (name === q) search.refetch();
    else router.replace(`${pathname}?q=${encodeURIComponent(name)}`);
  };

  const clear = () => {
    setInput("");
    setHint(null);
    router.replace(pathname);
  };

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-6 text-white sm:space-y-8 sm:px-6 sm:py-10">
      <header>
        <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.3em] text-amber-400 uppercase">
          <span className="h-px w-6 bg-amber-400" />
          Career
        </div>
        <h1 className="font-display mt-2 text-3xl font-bold tracking-wide sm:mt-3 sm:text-5xl">
          战绩查询
        </h1>
        <p className="mt-2 text-sm text-white/55">
          输入 EA 昵称查找 Battlefield 1 玩家，支持模糊匹配、不区分大小写
        </p>
      </header>

      <Bf1Panel
        variant="transparent"
        cut={20}
        corners={["topLeft", "bottomRight"]}
        className="bg-black/50 p-2 backdrop-blur-sm sm:p-4"
      >
        <form onSubmit={submit} className="flex gap-2 sm:gap-3">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2 text-white/40 sm:left-4" />
            <DarkInput
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="EA 昵称"
              aria-label="EA 昵称"
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              autoFocus
              className="h-12 pr-11 pl-11 sm:h-14 sm:pl-12 sm:text-lg"
            />
            {input ? (
              <button
                type="button"
                onClick={clear}
                aria-label="清空"
                className="absolute top-1/2 right-3 -translate-y-1/2 p-1 text-white/40 transition-colors hover:text-white"
              >
                <X className="size-4" />
              </button>
            ) : null}
          </div>
          <button
            type="submit"
            disabled={search.isFetching}
            className="font-display flex h-12 shrink-0 items-center gap-2 bg-amber-500 px-5 text-[15px] font-bold tracking-[0.12em] text-black transition-colors [clip-path:polygon(0_0,100%_0,100%_calc(100%-12px),calc(100%-12px)_100%,0_100%)] hover:bg-amber-400 disabled:opacity-60 sm:h-14 sm:px-8 sm:text-base sm:tracking-[0.2em]"
          >
            {search.isFetching ? <Loader2 className="size-5 animate-spin" /> : null}
            查询
          </button>
        </form>
        {hint ? <p className="mt-2 px-1 text-xs text-amber-300">{hint}</p> : null}
      </Bf1Panel>

      {q.length >= MIN_QUERY ? (
        <Results
          game={game}
          query={q}
          personas={search.data?.personas}
          loading={search.isLoading}
          error={search.error}
        />
      ) : (
        <Shortcuts game={game} />
      )}
    </main>
  );
}

/* ----------------------------- 搜索结果 ----------------------------- */

function Results({
  game,
  query,
  personas,
  loading,
  error,
}: {
  game: string;
  query: string;
  personas: PersonaBrief[] | undefined;
  loading: boolean;
  error: Error | null;
}) {
  if (loading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="h-[76px] animate-pulse bg-white/[0.06]" />
        ))}
      </div>
    );
  }
  if (error) {
    return (
      <Notice
        text={error instanceof ApiException ? error.message : "查询失败，请稍后重试"}
        tone="error"
      />
    );
  }
  if (!personas || personas.length === 0) {
    return (
      <>
        <Notice text={`没有找到昵称包含「${query}」的玩家`} />
        <TipLine className="mt-3" />
      </>
    );
  }

  // 精确匹配（不区分大小写）排最前
  const lower = query.toLowerCase();
  const sorted = [...personas].sort(
    (a, b) =>
      Number(b.display_name.toLowerCase() === lower) -
      Number(a.display_name.toLowerCase() === lower),
  );

  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between">
        <SectionHeading className="mb-0">搜索结果</SectionHeading>
        <span className="text-xs text-white/45 tabular-nums">{personas.length} 个匹配</span>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {sorted.map((p, i) => (
          <motion.li
            key={p.persona_id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: Math.min(i, 12) * 0.03 }}
          >
            <PlayerCard
              game={game}
              personaId={p.persona_id}
              name={p.display_name}
              avatarUrl={p.avatar_url}
              exact={p.display_name.toLowerCase() === lower}
              hours={p.time_played_hours}
            />
          </motion.li>
        ))}
      </ul>
    </section>
  );
}

function PlayerCard({
  game,
  personaId,
  name,
  avatarUrl,
  exact,
  hours,
  tag,
}: {
  game: string;
  personaId: number;
  name: string;
  avatarUrl: string | null;
  exact?: boolean;
  hours?: number | null;
  tag?: string;
}) {
  return (
    <Link href={`/${game}/player/${personaId}`} className="group block h-full">
      <Bf1Panel
        variant="transparent"
        cut={14}
        corners={["bottomRight"]}
        className={cn(
          "flex h-full items-center gap-3 border-l-2 bg-black/45 px-4 py-3.5 backdrop-blur-sm transition-colors group-hover:bg-white/[0.08]",
          exact ? "border-amber-400" : "border-white/10 group-hover:border-white/40",
        )}
      >
        <PlayerAvatar avatarUrl={avatarUrl} displayName={name} size="md" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-semibold text-white">{name}</span>
            {exact ? (
              <span className="shrink-0 bg-amber-400 px-1 text-[10px] leading-4 font-bold text-black">
                精确匹配
              </span>
            ) : null}
            {tag ? (
              <span className="shrink-0 border border-white/20 px-1 text-[10px] leading-4 text-white/60">
                {tag}
              </span>
            ) : null}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-xs text-white/45 tabular-nums">
            PID {personaId}
            {/* 同名消歧：仅当结果出现重名时后端回填 time_played_hours，帮你区分真号与空号 */}
            {hours != null ? (
              <span className={hours > 0 ? "text-emerald-300" : "text-red-300"}>
                {hours > 0 ? `BF1 ${hours} 小时` : "未玩过 BF1"}
              </span>
            ) : null}
          </div>
        </div>
        <ChevronRight className="size-4 shrink-0 text-white/30 transition-transform group-hover:translate-x-0.5 group-hover:text-white" />
      </Bf1Panel>
    </Link>
  );
}

function Notice({ text, tone }: { text: string; tone?: "error" }) {
  return (
    <div
      className={cn(
        "border px-4 py-8 text-center text-sm",
        tone === "error"
          ? "border-red-500/30 bg-red-500/10 text-red-200"
          : "border-white/10 bg-black/40 text-white/55",
      )}
    >
      {text}
    </div>
  );
}

/* ----------------------------- 空态快捷入口 ----------------------------- */

function Shortcuts({ game }: { game: string }) {
  const session = useSession();
  const mine = session.data?.primary_binding ?? null;
  const recent = useRecentPlayers();

  if (!mine && recent.length === 0) return null;

  return (
    <div className="space-y-8">
      {mine ? (
        <section>
          <div className="mb-3 flex items-center gap-2 text-xs text-white/50">
            <UserRound className="size-3.5" />
            我的账号
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <PlayerCard
              game={game}
              personaId={mine.persona_id}
              name={mine.display_name ?? `Persona ${mine.persona_id}`}
              avatarUrl={mine.avatar_url}
              tag="已绑定"
            />
          </div>
        </section>
      ) : null}
      {recent.length > 0 ? (
        <section>
          <div className="mb-3 flex items-center justify-between text-xs text-white/50">
            <span className="flex items-center gap-2">
              <History className="size-3.5" />
              最近查看
            </span>
            <button
              type="button"
              onClick={clearRecentPlayers}
              className="transition-colors hover:text-white"
            >
              清除
            </button>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {recent.map((p) => (
              <li key={p.persona_id}>
                <PlayerCard
                  game={game}
                  personaId={p.persona_id}
                  name={p.display_name}
                  avatarUrl={p.avatar_url}
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
