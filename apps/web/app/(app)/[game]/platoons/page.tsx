"use client";

/**
 * BF1 战队搜索页
 *
 * 后端调 EA Platoons.findByPartialName：只按战队名匹配（不含简称），关键字至少 3 个字符，最多 10 条。
 * 关键词记在地址栏（?q=），从详情页返回、刷新或分享链接都能看到同一组结果。
 */

import { Suspense, useState } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Loader2, Search, ShieldCheck, X } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { DarkInput } from "@/components/common/DarkInput";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ApiException } from "@/lib/api-client";
import { bf1Api } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

const MIN_QUERY = 3;

export default function PlatoonSearchPage() {
  // useSearchParams 需要 Suspense 边界，否则整页退化为客户端渲染并在构建时报错
  return (
    <Suspense>
      <PlatoonSearch />
    </Suspense>
  );
}

function PlatoonSearch() {
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
    queryKey: ["bf1-platoon-search", q.toLowerCase()],
    queryFn: () => bf1Api.searchPlatoons(q),
    enabled: q.length >= MIN_QUERY,
    staleTime: 5 * 60_000,
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const name = input.trim();
    if (name.length < MIN_QUERY) {
      setHint(`关键字至少 ${MIN_QUERY} 个字符`);
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

  const items = search.data ?? [];

  return (
    <main className="mx-auto max-w-5xl space-y-8 px-4 py-6 text-white sm:px-6 sm:py-10">
      <header>
        <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.3em] text-amber-400 uppercase">
          <span className="h-px w-6 bg-amber-400" />
          Platoons
        </div>
        <h1 className="font-display mt-3 text-4xl font-bold tracking-wide sm:text-5xl">战队</h1>
        <p className="mt-2 text-sm text-white/55">
          按战队名搜索（不支持简称），查看成员和他们正在玩的服务器
        </p>
      </header>

      <Bf1Panel
        variant="transparent"
        cut={20}
        corners={["topLeft", "bottomRight"]}
        className="bg-black/50 p-3 backdrop-blur-sm sm:p-4"
      >
        <form onSubmit={submit} className="flex gap-2 sm:gap-3">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-white/40" />
            <DarkInput
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="战队名"
              aria-label="战队名"
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              autoFocus
              className="h-14 pr-11 pl-12 text-lg"
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
            className="font-display flex h-14 shrink-0 items-center gap-2 bg-amber-500 px-6 text-base font-bold tracking-[0.2em] text-black transition-colors [clip-path:polygon(0_0,100%_0,100%_calc(100%-12px),calc(100%-12px)_100%,0_100%)] hover:bg-amber-400 disabled:opacity-60 sm:px-8"
          >
            {search.isFetching ? <Loader2 className="size-5 animate-spin" /> : null}
            搜索
          </button>
        </form>
        {hint ? <p className="mt-2 px-1 text-xs text-amber-300">{hint}</p> : null}
      </Bf1Panel>

      {q.length < MIN_QUERY ? null : search.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="h-[76px] animate-pulse bg-white/[0.06]" />
          ))}
        </div>
      ) : search.error ? (
        <Notice
          text={
            search.error instanceof ApiException ? search.error.message : "搜索失败，请稍后重试"
          }
          tone="error"
        />
      ) : items.length === 0 ? (
        <Notice text={`没有找到名字包含「${q}」的战队`} />
      ) : (
        <section>
          <div className="mb-3 flex items-baseline justify-between">
            <SectionHeading className="mb-0">搜索结果</SectionHeading>
            <span className="text-xs text-white/45 tabular-nums">
              {/* EA 每次最多返回 10 条，满 10 条说明可能还有更多 */}
              {items.length >= 10
                ? "前 10 个，换个更完整的名字可缩小范围"
                : `${items.length} 个战队`}
            </span>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((p, i) => (
              <motion.li
                key={p.guid}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: Math.min(i, 12) * 0.03 }}
              >
                <Link href={`/${game}/platoon/${p.guid}`} className="group block h-full">
                  <Bf1Panel
                    variant="transparent"
                    cut={14}
                    corners={["bottomRight"]}
                    className="flex h-full items-center gap-3 border-l-2 border-white/10 bg-black/45 px-4 py-3.5 backdrop-blur-sm transition-colors group-hover:border-white/40 group-hover:bg-white/[0.08]"
                  >
                    {p.emblem_url ? (
                      // EA 徽章域不在 next/image remotePatterns 内，用原生 img
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={p.emblem_url}
                        alt=""
                        className="size-11 shrink-0 object-contain"
                        loading="lazy"
                      />
                    ) : (
                      <ShieldCheck className="size-11 shrink-0 p-2 text-white/25" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-semibold text-white">
                        {p.tag ? <span className="text-white/45">[{p.tag}] </span> : null}
                        {p.name ?? p.guid}
                      </div>
                      {p.size != null ? (
                        <div className="mt-0.5 text-xs text-white/50 tabular-nums">{p.size} 人</div>
                      ) : null}
                    </div>
                  </Bf1Panel>
                </Link>
              </motion.li>
            ))}
          </ul>
        </section>
      )}
    </main>
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
