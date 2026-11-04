"use client";

/**
 * 一键卡行动：私服没有行动模式选项，服主或管理员用这个工具把服务器「抽」成 24 图行动并锚定。
 *
 * 公开工具，不要求登录：服主或管理员填 remid + sid（登录用户可直接用主绑定账号，或借用本站号池里
 * 是这台服管理员的平台账号）。凭据只随请求发给后端、只在任务内存里用，不存本地也不落库；任务 id 和
 * 查看令牌存在 localStorage，刷新或关掉页面后回来还能看进度。
 *
 * 选好账号后按收录的私服名单列出它是服主或管理员的服，点一下就检查；名单只覆盖有人进过的服，
 * 所以 gameId 也能直接填。
 */

import { Suspense, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, X } from "lucide-react";
import { toast } from "sonner";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { DarkInput } from "@/components/common/DarkInput";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { useSession } from "@/hooks/useSession";
import { ApiException } from "@/lib/api-client";
import {
  cardApi,
  type CardAccountServers,
  type CardCredentials,
  type CardJob,
  type CardJobStatus,
  type CardPrecheck,
  type CardServer,
} from "@/lib/api/bf1";
import { bf1Keys, bf1Queries } from "@/lib/queries/bf1";
import { mapLabel, modeLabel } from "@/lib/bf1/catalog";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "bfm:bf1-card-job";
const POLL_MS = 2000;
const PANEL_STYLE = { background: "rgba(12,12,15,0.72)" };

const STATUS: Record<CardJobStatus, { label: string; cls: string }> = {
  running: { label: "进行中", cls: "bg-sky-500/15 text-sky-300" },
  succeeded: { label: "已完成", cls: "bg-emerald-500/15 text-emerald-300" },
  failed: { label: "失败", cls: "bg-red-500/15 text-red-300" },
  cancelled: { label: "已停止", cls: "bg-white/10 text-white/75" },
  interrupted: { label: "已中断", cls: "bg-amber-500/15 text-amber-200" },
};
const EVENT_STYLE: Record<string, string> = {
  info: "bg-white/10 text-white/80",
  round: "bg-sky-500/15 text-sky-300",
  warn: "bg-amber-500/15 text-amber-200",
  error: "bg-red-500/15 text-red-300",
  success: "bg-emerald-500/15 text-emerald-300",
};
const EVENT_LABEL: Record<string, string> = {
  info: "进度",
  round: "抽图",
  warn: "注意",
  error: "出错",
  success: "完成",
};

interface StoredJob {
  id: number;
  token: string | null;
}

// 上次的任务存在 localStorage：服务端渲染时为空，挂载后读到本机记录
const storeListeners = new Set<() => void>();

function readStored(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStored(job: StoredJob | null): void {
  try {
    if (job) localStorage.setItem(STORAGE_KEY, JSON.stringify(job));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // 隐私模式 / 存储已满时只是刷新后看不到上次的任务
  }
  storeListeners.forEach((l) => l());
}

function useStoredJob(): StoredJob | null {
  const raw = useSyncExternalStore(
    (l) => {
      storeListeners.add(l);
      return () => storeListeners.delete(l);
    },
    readStored,
    () => null,
  );
  return useMemo(() => {
    try {
      return raw ? (JSON.parse(raw) as StoredJob) : null;
    } catch {
      return null;
    }
  }, [raw]);
}

function errText(e: unknown): string {
  return e instanceof ApiException ? e.message : "请求失败，请稍后重试";
}

function duration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return s >= 60 ? `${Math.floor(s / 60)} 分 ${s % 60} 秒` : `${s} 秒`;
}

export default function CardOperationPage() {
  // useSearchParams 需要 Suspense 边界
  return (
    <Suspense>
      <CardOperation />
    </Suspense>
  );
}

function CardOperation() {
  const params = useSearchParams();
  const session = useSession();
  const binding = session.data?.primary_binding ?? null;
  const qc = useQueryClient();

  // 未手动切换时，登录且有主绑定就默认用绑定账号；平台账号只给登录用户
  const [credMode, setCredMode] = useState<CredMode | null>(null);
  const loggedIn = session.data != null;
  const canUseBinding = binding != null && !binding.is_frozen;
  const modes: { v: CredMode; label: string }[] = [
    ...(canUseBinding
      ? [{ v: "binding" as const, label: `绑定账号 ${binding.display_name ?? binding.persona_id}` }]
      : []),
    ...(loggedIn ? [{ v: "pool" as const, label: "平台账号" }] : []),
    { v: "manual", label: "填写 remid / sid" },
  ];
  const mode: CredMode = credMode && modes.some((m) => m.v === credMode) ? credMode : modes[0].v;
  const [remid, setRemid] = useState("");
  const [sid, setSid] = useState("");
  const [gameId, setGameId] = useState(params.get("gameId") ?? "");
  // 从列表点选的服（按稳定的 serverId 认，gameId 定位后可能变）
  const [picked, setPicked] = useState<number | null>(null);
  const [check, setCheck] = useState<CardPrecheck | null>(null);
  const [confirm, setConfirm] = useState<"card" | "anchor" | null>(null);
  const stored = useStoredJob();

  const creds: CardCredentials = {
    remid: remid.trim(),
    sid: sid.trim(),
    use_binding: mode === "binding",
    use_pool: mode === "pool",
  };
  const credsReady = mode !== "manual" || (creds.remid !== "" && creds.sid !== "");
  const gid = Number(gameId.trim());
  const gidValid = Number.isInteger(gid) && gid > 0;

  // 绑定账号和平台账号不用登录 EA 就能查，切过去自动列；手填的要登录一次，点「识别账号」才查
  const autoServers = useQuery({
    queryKey: ["bf1-card-servers", mode, session.data?.id ?? null],
    queryFn: () => cardApi.servers(creds),
    enabled: mode !== "manual" && loggedIn,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const identify = useMutation({ mutationFn: () => cardApi.servers(creds) });
  const servers = mode === "manual" ? identify : autoServers;

  const remember = writeStored;

  const job = useQuery({
    ...bf1Queries.cardJob(stored),
    enabled: stored != null,
    refetchInterval: (q) => (q.state.data?.status === "running" ? POLL_MS : false),
    retry: (count, e) => !(e instanceof ApiException && [403, 404].includes(e.status)) && count < 2,
  });
  const setJob = (j: CardJob) => qc.setQueryData(bf1Keys.cardJob(j.id), j);

  const precheck = useMutation({
    mutationFn: (g: number) => cardApi.precheck(g, creds),
    onSuccess: setCheck,
    onError: (e) => {
      setCheck(null);
      toast.error(errText(e));
    },
  });

  // 没人的服不在快照里，列表记的 gameId 可能是重启前的，先问一次当前的
  const locate = useMutation({
    mutationFn: (s: CardServer) =>
      s.player_count != null
        ? Promise.resolve({ game_id: s.game_id })
        : cardApi.locate(s.server_id),
    onSuccess: ({ game_id }) => {
      setGameId(String(game_id));
      precheck.mutate(game_id);
    },
    onError: (e) => toast.error(errText(e)),
  });

  const start = useMutation({
    mutationFn: (kind: "card" | "anchor") => cardApi.start(gid, kind, creds),
    onSuccess: ({ job: j, token }) => {
      setConfirm(null);
      setCheck(null);
      setJob(j);
      remember({ id: j.id, token });
    },
    onError: (e) => {
      setConfirm(null);
      toast.error(errText(e));
    },
  });

  const cancel = useMutation({
    mutationFn: () => cardApi.cancel(stored!.id, stored!.token),
    onSuccess: setJob,
    onError: (e) => toast.error(errText(e)),
  });

  const restore = useMutation({
    mutationFn: () => cardApi.restore(stored!.id, stored!.token, creds),
    onSuccess: (j) => {
      setJob(j);
      toast.success("已恢复原设置");
    },
    onError: (e) => toast.error(errText(e)),
  });

  const running = job.data?.status === "running";

  return (
    <main className="flex max-w-3xl flex-col gap-4 py-6 text-white">
      <header>
        <div className="font-display flex items-center gap-2 text-xs font-medium tracking-[0.2em] text-amber-500 uppercase">
          <span className="h-[2px] w-6 bg-amber-500" />
          Card Operation
        </div>
        <h1 className="mt-1.5 text-2xl font-bold tracking-wide sm:text-3xl">一键卡行动</h1>
        <p className="mt-2 text-sm leading-relaxed text-white/65">
          私服没有行动模式选项。这个工具把轮换换成无效地图，反复唤醒服务器，直到 EA 随机分到 24
          图行动，再把轮换锚定成同一批地图，之后改设置也不会掉回征服。需要这台服的服主或管理员账号。
        </p>
      </header>

      {stored ? (
        <JobPanel
          query={job}
          onCancel={() => cancel.mutate()}
          cancelling={cancel.isPending}
          onRestore={() => {
            if (!credsReady) {
              toast.error("先在下面填好账号的 remid 和 sid");
              return;
            }
            restore.mutate();
          }}
          restoring={restore.isPending}
          onClear={() => remember(null)}
        />
      ) : null}

      <Bf1Panel cut={14} className="p-4 sm:p-6" style={PANEL_STYLE}>
        <SectionHeading className="mb-0">服主或管理员账号</SectionHeading>
        {modes.length > 1 ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {modes.map((o) => (
              <button
                key={o.v}
                type="button"
                onClick={() => {
                  setCredMode(o.v);
                  setCheck(null);
                }}
                className={cn(
                  "compact-action px-3 py-1.5 text-xs ring-1 transition-colors",
                  mode === o.v
                    ? "bg-white font-semibold text-black ring-white"
                    : "text-white/65 ring-white/15 hover:text-white",
                )}
              >
                {o.label}
              </button>
            ))}
          </div>
        ) : null}
        {mode !== "manual" ? null : (
          <>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5 text-xs text-white/60">
                remid
                <DarkInput
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  value={remid}
                  onChange={(e) => {
                    setRemid(e.target.value);
                    setCheck(null);
                    identify.reset();
                  }}
                  placeholder="EA 账号的 remid"
                  className="h-11"
                />
              </label>
              <label className="flex flex-col gap-1.5 text-xs text-white/60">
                sid
                <DarkInput
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  value={sid}
                  onChange={(e) => {
                    setSid(e.target.value);
                    setCheck(null);
                    identify.reset();
                  }}
                  placeholder="EA 账号的 sid"
                  className="h-11"
                />
              </label>
            </div>
            <details className="group mt-3 text-xs text-white/55">
              <summary className="inline-action flex cursor-pointer list-none items-center gap-1 text-white/70 hover:text-white">
                <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
                怎么获取 remid 和 sid
              </summary>
              <ol className="mt-2 list-decimal space-y-1 pl-5 leading-relaxed">
                <li>用服主或管理员的 EA 账号在浏览器登录 ea.com。</li>
                <li>
                  按 F12 打开开发者工具，进入「应用」（Application）→ Cookie →
                  https://accounts.ea.com。
                </li>
                <li>
                  复制 remid 和 sid 两项的值。用过 BF1 服管工具的，也可以在它的 config.json 里找到。
                </li>
              </ol>
            </details>
          </>
        )}
        <p className="mt-3 text-xs leading-relaxed text-white/45">
          {mode === "pool"
            ? "用本站号池里是这台服服主或管理员的账号操作，需要你在本站对这台服有管理员权限。"
            : "凭据只用于这次操作，不会保存。卡服期间会用这个账号登录游戏服务，这个账号正在玩的话会被挤下线。"}
        </p>
      </Bf1Panel>

      <Bf1Panel cut={14} className="p-4 sm:p-6" style={PANEL_STYLE}>
        <SectionHeading className="mb-0">服务器</SectionHeading>
        <AccountServers
          mode={mode}
          result={servers.data}
          loading={servers.isPending && (mode === "manual" ? identify.isPending : loggedIn)}
          error={servers.isError ? errText(servers.error) : null}
          selected={picked}
          locating={locate.isPending}
          onIdentify={() => {
            if (!credsReady) toast.error("请先填写账号的 remid 和 sid");
            else identify.mutate();
          }}
          onPick={(s) => {
            setPicked(s.server_id);
            setGameId(String(s.game_id));
            setCheck(null);
            locate.mutate(s);
          }}
        />
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!credsReady) toast.error("请先填写账号的 remid 和 sid");
            else if (!gidValid) toast.error("请填写服务器的 gameId（数字）");
            else precheck.mutate(gid);
          }}
        >
          <DarkInput
            inputMode="numeric"
            value={gameId}
            onChange={(e) => {
              setGameId(e.target.value);
              setPicked(null);
              setCheck(null);
            }}
            placeholder="gameId，服务器详情页地址里的数字"
            className="h-11 min-w-0 flex-1"
          />
          <button
            type="submit"
            disabled={precheck.isPending || locate.isPending}
            className="h-11 shrink-0 bg-white px-5 text-sm font-semibold text-black transition-colors hover:bg-white/85 disabled:opacity-50"
          >
            {precheck.isPending || locate.isPending ? "检查中…" : "检查"}
          </button>
        </form>

        {check ? (
          <PrecheckView
            check={check}
            busy={start.isPending || running}
            onCard={() => setConfirm("card")}
            onAnchor={() => setConfirm("anchor")}
          />
        ) : null}
      </Bf1Panel>

      <ConfirmSheet
        open={confirm != null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm === "anchor" ? "锚定当前行动图池？" : "开始卡行动？"}
        description={
          confirm === "anchor"
            ? "会把轮换改成当前 24 张图、模式统一为空中突击（AA0），名称、简介、密码和规则保持不变。服里没人时会先用这个账号进服。"
            : "开始前会保存当前设置，失败或停止后可以一键恢复。"
        }
        confirmText={confirm === "anchor" ? "开始锚定" : "开始卡行动"}
        loading={start.isPending}
        onConfirm={() => {
          if (confirm) start.mutate(confirm);
        }}
      >
        {confirm === "card" ? (
          <ul className="text-foreground list-disc space-y-1.5 pl-5 text-sm">
            <li>原轮换会被覆盖，卡完是 24 图行动，地图顺序随机。</li>
            <li>运行期间这个账号会反复进出服务器，正在玩的话会被挤下线。</li>
            <li>一般几分钟，最长 30 分钟；卡完要尽快有人进服，空服太久可能掉回征服。</li>
          </ul>
        ) : null}
      </ConfirmSheet>
    </main>
  );
}

type CredMode = "binding" | "pool" | "manual";

const ROLE_LABEL: Record<string, string> = { owner: "服主", admin: "管理员" };

function AccountServers({
  mode,
  result,
  loading,
  error,
  selected,
  locating,
  onIdentify,
  onPick,
}: {
  mode: CredMode;
  result: CardAccountServers | undefined;
  loading: boolean;
  error: string | null;
  /** 选中的 serverId */
  selected: number | null;
  locating: boolean;
  onIdentify: () => void;
  onPick: (server: CardServer) => void;
}) {
  if (mode === "manual" && !result && !loading && !error) {
    return (
      <button
        type="button"
        onClick={onIdentify}
        className="compact-action mt-3 h-9 bg-white/[0.08] px-4 text-xs font-semibold text-white/85 ring-1 ring-white/15 transition-colors hover:bg-white hover:text-black"
      >
        识别账号，列出它管理的服
      </button>
    );
  }
  if (loading) {
    return <p className="mt-3 text-xs text-white/50">正在查这个账号管理的服…</p>;
  }
  if (error) {
    return <p className="mt-3 text-xs text-red-300/80">{error}</p>;
  }
  if (!result) return null;
  if (result.servers.length === 0) {
    return (
      <p className="mt-3 text-xs leading-relaxed text-white/50">
        {mode === "pool"
          ? "平台账号能管的服里，没有你在本站有管理员权限的。"
          : "收录的私服里没找到这个账号是服主或管理员的服。"}
        没人进过的服不在收录范围，可以直接填 gameId。
      </p>
    );
  }
  return (
    <ul className="mt-3 divide-y divide-white/[0.06] ring-1 ring-white/10">
      {result.servers.map((s) => {
        const live = s.player_count != null;
        return (
          <li key={s.server_id}>
            <button
              type="button"
              onClick={() => onPick(s)}
              disabled={locating}
              className={cn(
                "flex min-h-11 w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-white/[0.06] disabled:cursor-wait",
                selected === s.server_id && "bg-white/[0.08]",
              )}
            >
              <span className="min-w-0 flex-1 truncate text-sm text-white/90">{s.name}</span>
              <span className="shrink-0 text-xs text-white/50 tabular-nums">
                {live ? `${s.player_count}/${s.max_player_count ?? "?"} 人` : "当前没人"}
              </span>
              <span className="shrink-0 bg-white/10 px-1.5 py-px text-[11px] text-white/70">
                {ROLE_LABEL[s.role] ?? s.role}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function PrecheckView({
  check: c,
  busy,
  onCard,
  onAnchor,
}: {
  check: CardPrecheck;
  busy: boolean;
  onCard: () => void;
  onAnchor: () => void;
}) {
  const canManage = c.is_owner || c.is_admin;
  const rows: { ok: boolean; text: string }[] = [
    {
      ok: canManage,
      text: c.is_owner
        ? `这个账号是服主（${c.owner_name || c.owner_id}）`
        : c.is_admin
          ? "这个账号是管理员"
          : `这个账号不是服主或管理员，服主是 ${c.owner_name || c.owner_id}`,
    },
    {
      ok: c.occupied === 0,
      text:
        c.occupied === 0
          ? "服务器没人，可以抽图"
          : `服里有 ${c.occupied} 人，抽图需要空服${c.is_operation ? "；当前已是行动，可以直接锚定" : ""}`,
    },
  ];
  const canCard = canManage && c.occupied === 0 && !c.running_job_id;
  const canAnchor = canManage && c.is_operation && !c.running_job_id;

  return (
    <div className="mt-4 space-y-3">
      <div>
        <div className="text-base font-semibold break-all">{c.server_name}</div>
        <div className="mt-0.5 text-xs text-white/50">
          当前 {c.mode ? modeLabel(c.mode) : "未知模式"}
          {c.map_name ? ` · ${mapLabel(c.map_name)}` : ""} · 轮换 {c.map_count} 张图 ·{" "}
          {c.soldier_max} 人服
        </div>
      </div>
      <ul className="space-y-1.5 text-sm">
        {rows.map((r) => (
          <li key={r.text} className="flex items-start gap-2">
            {r.ok ? (
              <Check className="mt-0.5 size-4 shrink-0 text-emerald-400" />
            ) : (
              <X className="mt-0.5 size-4 shrink-0 text-red-400" />
            )}
            <span className={r.ok ? "text-white/80" : "text-white/70"}>{r.text}</span>
          </li>
        ))}
        {c.is_operation ? (
          <li className="text-xs text-white/50">
            这台服已经是 24 图行动。轮换没锚定过的话，用「手动锚定」补上即可，不用重新抽。
          </li>
        ) : null}
        {c.auto_switch_enabled ? (
          <li className="text-xs text-amber-200/80">这台服开着自动换图，卡行动期间会暂停。</li>
        ) : null}
        {c.running_job_id ? (
          <li className="text-xs text-amber-200/80">
            这台服已经有一个任务在跑（#{c.running_job_id}）。
          </li>
        ) : null}
      </ul>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!canCard || busy}
          onClick={onCard}
          className="h-11 bg-amber-500 px-5 text-sm font-semibold text-black transition-colors hover:bg-amber-400 disabled:opacity-40"
        >
          开始卡行动
        </button>
        <button
          type="button"
          disabled={!canAnchor || busy}
          onClick={onAnchor}
          className="h-11 bg-white/[0.08] px-5 text-sm font-semibold text-white/85 ring-1 ring-white/15 transition-colors hover:bg-white hover:text-black disabled:opacity-40 disabled:hover:bg-white/[0.08] disabled:hover:text-white/85"
        >
          手动锚定
        </button>
      </div>
    </div>
  );
}

function JobPanel({
  query,
  onCancel,
  cancelling,
  onRestore,
  restoring,
  onClear,
}: {
  query: ReturnType<typeof useQuery<CardJob>>;
  onCancel: () => void;
  cancelling: boolean;
  onRestore: () => void;
  restoring: boolean;
  onClear: () => void;
}) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  const j = query.data;
  const running = j?.status === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(t);
  }, [running]);

  if (!j) {
    return (
      <Bf1Panel cut={14} className="p-4 sm:p-6" style={PANEL_STYLE}>
        <div className="flex items-center justify-between gap-3 text-sm text-white/55">
          {query.isError ? `上次的任务读取失败：${errText(query.error)}` : "正在读取上次的任务…"}
          {query.isError ? (
            <button type="button" onClick={onClear} className="compact-action text-xs underline">
              不再显示
            </button>
          ) : null}
        </div>
      </Bf1Panel>
    );
  }

  const st = STATUS[j.status];
  const elapsed = (j.finished_at ?? now) - j.started_at;
  return (
    <Bf1Panel cut={14} className="p-4 sm:p-6" style={PANEL_STYLE}>
      <div className="flex flex-wrap items-center gap-2">
        <SectionHeading className="mb-0">
          {j.kind === "anchor" ? "手动锚定" : "卡行动"}
        </SectionHeading>
        <span className={cn("px-1.5 py-px text-[11px] font-semibold", st.cls)}>{st.label}</span>
        {!running ? (
          <button
            type="button"
            onClick={onClear}
            className="compact-action ml-auto text-xs text-white/45 hover:text-white"
          >
            关闭
          </button>
        ) : null}
      </div>
      <div className="mt-2 text-sm break-all text-white/80">
        <Link href={`/bf1/server/${j.game_id}`} className="inline-action hover:underline">
          {j.server_name || j.game_id}
        </Link>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        {j.kind === "card" ? (
          <div>
            <dt className="text-xs text-white/45">已抽</dt>
            <dd className="mt-0.5 font-semibold tabular-nums">
              {j.attempts} / {j.max_attempts} 轮
            </dd>
          </div>
        ) : null}
        <div>
          <dt className="text-xs text-white/45">用时</dt>
          <dd className="mt-0.5 font-semibold tabular-nums">{duration(elapsed)}</dd>
        </div>
        <div>
          <dt className="text-xs text-white/45">操作账号</dt>
          <dd className="mt-0.5 truncate font-semibold">{j.persona_name || j.persona_id}</dd>
        </div>
      </dl>
      {j.message ? <p className="mt-3 text-sm text-white/80">{j.message}</p> : null}
      {j.status === "succeeded" && j.result_maps?.length ? (
        <div className="mt-3 text-xs leading-relaxed text-white/55">
          图池顺序：{j.result_maps.map((m, i) => `${i + 1}.${mapLabel(m)}`).join("  ")}
          <div className="mt-1">
            想按战役顺序推进，可以在服务器详情页开「自动换图」（需要在本站绑定服主或管理员账号）。
          </div>
        </div>
      ) : null}
      {j.restored_at ? (
        <p className="mt-2 text-xs text-emerald-300/80">
          已于 {new Date(j.restored_at * 1000).toLocaleString("zh-CN")} 恢复原设置
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {running ? (
          <button
            type="button"
            disabled={cancelling}
            onClick={onCancel}
            className="h-11 bg-white/[0.08] px-5 text-sm font-semibold text-white/85 ring-1 ring-white/15 transition-colors hover:bg-white hover:text-black disabled:opacity-50"
          >
            {cancelling ? "停止中…" : "停止"}
          </button>
        ) : null}
        {j.can_restore && !j.restored_at && j.status !== "succeeded" ? (
          <button
            type="button"
            disabled={restoring}
            onClick={onRestore}
            className="h-11 bg-white px-5 text-sm font-semibold text-black transition-colors hover:bg-white/85 disabled:opacity-50"
          >
            {restoring ? "恢复中…" : "恢复原设置"}
          </button>
        ) : null}
      </div>

      {j.events.length ? (
        <ul className="mt-4 max-h-80 divide-y divide-white/[0.06] overflow-y-auto text-sm">
          {j.events.map((e, i) => (
            <li key={`${e.ts}-${i}`} className="flex gap-3 py-2">
              <span className="w-16 shrink-0 text-xs text-white/40 tabular-nums">
                {new Date(e.ts * 1000).toLocaleTimeString("zh-CN", { hour12: false })}
              </span>
              <span
                className={cn(
                  "h-fit shrink-0 px-1.5 py-px text-[11px] font-semibold",
                  EVENT_STYLE[e.kind] ?? EVENT_STYLE.info,
                )}
              >
                {EVENT_LABEL[e.kind] ?? e.kind}
              </span>
              <span className="text-white/80">{e.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </Bf1Panel>
  );
}
