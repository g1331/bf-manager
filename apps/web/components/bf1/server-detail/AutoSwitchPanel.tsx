"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Minus, Plus, X } from "lucide-react";
import { toast } from "sonner";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { SectionHeading } from "@/components/layout/SectionHeading";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { ApiException } from "@/lib/api-client";
import {
  bf1Api,
  type AutoSwitchItem,
  type AutoSwitchPlan,
  type MapRotationItem,
  type OperationMap,
} from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

const CONFIRM_SECONDS = 5;
const LOOP_OPTIONS = [
  { value: 1, label: "1 轮" },
  { value: 2, label: "2 轮" },
  { value: 3, label: "3 轮" },
  { value: 0, label: "一直循环" },
];
const EVENT_STYLE: Record<string, string> = {
  ok: "bg-emerald-500/15 text-emerald-300",
  switch: "bg-sky-500/15 text-sky-300",
  retry: "bg-sky-500/15 text-sky-300",
  manual: "bg-amber-500/15 text-amber-200",
  start: "bg-white/10 text-white/80",
  stop: "bg-white/10 text-white/80",
  finished: "bg-white/10 text-white/80",
  error: "bg-red-500/15 text-red-300",
  conflict: "bg-red-500/15 text-red-300",
};
const EVENT_LABEL: Record<string, string> = {
  ok: "正常",
  switch: "换图",
  retry: "重试",
  manual: "人工切图",
  start: "开始",
  stop: "关闭",
  finished: "跑完",
  error: "出错",
  conflict: "冲突",
};

function describeError(err: unknown): string {
  return err instanceof ApiException ? err.message : "操作失败，请稍后重试";
}

/**
 * 行动服自动换图：管理员编排轮换（整个战役或单张图，每项可打多次，整轮可循环），开启后
 * 后端每 5 秒检查一次，在一局结束时按编排换图。默认关闭，开启前弹窗确认并倒数 5 秒。
 */
export function AutoSwitchPanel({
  gameId,
  rotation,
  canEdit,
}: {
  gameId: number;
  rotation: MapRotationItem[];
  canEdit: boolean;
}) {
  const qc = useQueryClient();
  const key = ["bf1-auto-switch", gameId];
  const view = useQuery({
    queryKey: key,
    queryFn: () => bf1Api.getAutoSwitch(gameId),
    refetchInterval: (q) => (q.state.data?.enabled ? 10_000 : false),
  });

  // 图池里的行动地图：代号 → 名称 / 封面，以及所属战役
  const maps = useMemo(() => {
    const byCode = new Map<string, OperationMap & { operation: OperationMap[] }>();
    for (const m of rotation) {
      if (!m.map_name || !m.operation) continue;
      const self = m.operation.find((o) => o.map_name === m.map_name);
      if (self) byCode.set(m.map_name, { ...self, operation: m.operation });
    }
    return byCode;
  }, [rotation]);
  const operationStarts = [...maps.values()].filter(
    (m) => m.operation.length > 1 && m.operation[0].map_name === m.map_name,
  );

  const [draft, setDraft] = useState<AutoSwitchPlan | null>(null);
  const saved = view.data?.plan ?? { items: [], loops: 0 };
  const plan = draft ?? saved;
  const dirty = draft !== null;
  const edit = (next: AutoSwitchPlan) => setDraft(next);
  const setItem = (i: number, patch: Partial<AutoSwitchItem>) =>
    edit({ ...plan, items: plan.items.map((it, j) => (j === i ? { ...it, ...patch } : it)) });
  const move = (i: number, delta: number) => {
    const items = [...plan.items];
    const [it] = items.splice(i, 1);
    items.splice(i + delta, 0, it);
    edit({ ...plan, items });
  };

  const onSuccess = (data: Awaited<ReturnType<typeof bf1Api.getAutoSwitch>>) => {
    qc.setQueryData(key, data);
    setDraft(null);
  };
  const save = useMutation({
    mutationFn: () => bf1Api.saveAutoSwitchPlan(gameId, plan),
    onSuccess: (data) => {
      onSuccess(data);
      toast.success("编排已保存");
    },
    onError: (e) => toast.error(describeError(e)),
  });
  const toggle = useMutation({
    mutationFn: (on: boolean) =>
      on ? bf1Api.enableAutoSwitch(gameId) : bf1Api.disableAutoSwitch(gameId),
    onSuccess: (data) => {
      onSuccess(data);
      setConfirmOpen(false);
      toast.success(data.enabled ? "自动换图已开启" : "自动换图已关闭");
    },
    onError: (e) => toast.error(describeError(e)),
  });

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [countdown, setCountdown] = useState(CONFIRM_SECONDS);
  useEffect(() => {
    if (!confirmOpen) return;
    const timer = setInterval(() => setCountdown((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(timer);
  }, [confirmOpen]);

  if (view.isLoading) {
    return <div className="py-8 text-center text-sm text-white/40">加载中…</div>;
  }
  if (view.isError) {
    return (
      <div className="py-8 text-center text-sm text-white/40">{describeError(view.error)}</div>
    );
  }
  const v = view.data!;
  const name = (code: string) => maps.get(code)?.name ?? code;
  const current = v.plan.items[v.cursor];

  return (
    <div className="space-y-6">
      {/* 状态与开关 */}
      <Bf1Panel
        variant="transparent"
        cut={20}
        corners={["topLeft", "bottomRight"]}
        className="bg-black/45 p-3.5 backdrop-blur-sm sm:p-6"
      >
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
          <SectionHeading className="mb-0">自动换图</SectionHeading>
          {v.enabled ? (
            <span className="inline-flex items-center gap-1.5 bg-emerald-500/15 px-2 py-0.5 text-xs font-semibold text-emerald-300">
              <span className="size-1.5 animate-pulse rounded-full bg-emerald-400" />
              运行中
            </span>
          ) : (
            <span className="bg-white/10 px-2 py-0.5 text-xs text-white/60">已关闭</span>
          )}
          {canEdit ? (
            <button
              type="button"
              disabled={toggle.isPending || (!v.enabled && (dirty || v.plan.items.length === 0))}
              title={
                !v.enabled && dirty
                  ? "先保存编排"
                  : !v.enabled && v.plan.items.length === 0
                    ? "先添加并保存编排"
                    : undefined
              }
              onClick={() => {
                if (v.enabled) return toggle.mutate(false);
                setCountdown(CONFIRM_SECONDS);
                setConfirmOpen(true);
              }}
              className={cn(
                "ml-auto inline-flex h-9 items-center px-4 text-sm font-semibold transition-colors disabled:opacity-40",
                v.enabled
                  ? "bg-white/[0.08] text-white/85 ring-1 ring-white/15 hover:bg-white hover:text-black"
                  : "bg-emerald-500 text-black hover:bg-emerald-400",
              )}
            >
              {v.enabled ? "关闭自动换图" : "开启自动换图"}
            </button>
          ) : null}
        </div>
        <div className="mt-3 text-sm text-white/70">
          {v.enabled && current ? (
            <>
              正在进行编排第 {v.cursor + 1} 项「{name(current.map)}
              {current.scope === "operation" ? " 战役" : ""}」· 第 {v.done + 1}/{current.repeat} 次
              · 第 {v.loop}
              {v.plan.loops ? `/${v.plan.loops}` : ""} 轮
              {v.pending_map ? (
                <span className="text-sky-300"> · 正在换到「{name(v.pending_map)}」</span>
              ) : null}
            </>
          ) : (
            "默认关闭。开启后每局结束时按下面的编排换图；有人手动换到编排里的图会被跟随。"
          )}
        </div>
        {v.enabled_by ? (
          <div className="mt-1 text-xs text-white/40">
            由 {v.enabled_by} 开启
            {v.enabled_at ? ` · ${new Date(v.enabled_at * 1000).toLocaleString("zh-CN")}` : ""}
            ，换图使用其绑定的 EA 账号执行，审计里记为「自动换图」
          </div>
        ) : null}
      </Bf1Panel>

      {/* 编排 */}
      <Bf1Panel cut={20} className="p-3.5 sm:p-6" style={{ background: "rgba(12,12,15,0.72)" }}>
        <div className="flex flex-wrap items-center gap-3">
          <SectionHeading className="mb-0">轮换编排</SectionHeading>
          <span className="text-xs text-white/40">
            「战役」打完整个战役算一次，「单图」打完这一局算一次
          </span>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs">
          <span className="text-white/60">整轮循环</span>
          <div className="inline-flex ring-1 ring-white/15">
            {LOOP_OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                disabled={!canEdit}
                onClick={() => edit({ ...plan, loops: o.value })}
                className={cn(
                  "compact-action px-3 py-1.5 transition-colors",
                  plan.loops === o.value
                    ? "bg-white font-semibold text-black"
                    : "text-white/65 enabled:hover:text-white",
                )}
              >
                {o.label}
              </button>
            ))}
          </div>
          {canEdit && dirty ? (
            <div className="ml-auto flex gap-2">
              <button
                type="button"
                onClick={() => setDraft(null)}
                className="compact-action h-8 px-3 text-white/70 ring-1 ring-white/15 hover:bg-white/10"
              >
                还原
              </button>
              <button
                type="button"
                disabled={save.isPending}
                onClick={() => save.mutate()}
                className="compact-action h-8 bg-amber-400 px-4 font-semibold text-black hover:bg-amber-300 disabled:opacity-50"
              >
                保存编排
              </button>
            </div>
          ) : null}
        </div>

        <ol className="mt-3 space-y-1.5">
          {plan.items.length === 0 ? (
            <li className="py-6 text-center text-sm text-white/40">
              还没有编排，从下方图池添加战役或单张图
            </li>
          ) : null}
          {plan.items.map((it, i) => {
            const info = maps.get(it.map);
            const chain = it.scope === "operation" && info ? info.operation : info ? [info] : [];
            const active = v.enabled && !dirty && i === v.cursor;
            return (
              <li
                key={`${it.map}-${i}`}
                className={cn(
                  "flex flex-wrap items-center gap-3 px-3 py-2 ring-1",
                  active
                    ? "bg-amber-400/[0.07] ring-amber-400/70"
                    : "bg-white/[0.04] ring-white/[0.06]",
                )}
              >
                <span className="w-5 text-xs font-bold text-white/40 tabular-nums">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div className="flex shrink-0 gap-1">
                  {chain.map((m) =>
                    m.image_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        key={m.map_name}
                        src={m.image_url}
                        alt=""
                        className="h-7 w-12 object-cover"
                      />
                    ) : null,
                  )}
                </div>
                <span
                  className={cn(
                    "px-1.5 text-[10px] ring-1",
                    it.scope === "operation"
                      ? "text-white/70 ring-white/25"
                      : "text-sky-200 ring-sky-400/60",
                  )}
                >
                  {it.scope === "operation" ? "战役" : "单图"}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm">
                  {chain.map((m) => m.name).join(" → ") || it.map}
                  {active ? (
                    <span className="ml-2 bg-amber-400 px-1.5 text-[10px] font-bold text-black">
                      进行中
                    </span>
                  ) : null}
                </span>
                <div
                  className="inline-flex items-center text-xs tabular-nums ring-1 ring-white/15"
                  title="打几次再进入下一项"
                >
                  <button
                    type="button"
                    aria-label="减少次数"
                    disabled={!canEdit || it.repeat <= 1}
                    onClick={() => setItem(i, { repeat: it.repeat - 1 })}
                    className="compact-action grid size-7 place-items-center text-white/60 enabled:hover:bg-white enabled:hover:text-black disabled:opacity-30"
                  >
                    <Minus className="size-3" />
                  </button>
                  <span className="w-12 text-center">
                    {active ? `${v.done + 1}/${it.repeat}` : `× ${it.repeat}`}
                  </span>
                  <button
                    type="button"
                    aria-label="增加次数"
                    disabled={!canEdit || it.repeat >= 9}
                    onClick={() => setItem(i, { repeat: it.repeat + 1 })}
                    className="compact-action grid size-7 place-items-center text-white/60 enabled:hover:bg-white enabled:hover:text-black disabled:opacity-30"
                  >
                    <Plus className="size-3" />
                  </button>
                </div>
                {canEdit ? (
                  <div className="flex gap-1">
                    <IconButton label="上移" disabled={i === 0} onClick={() => move(i, -1)}>
                      <ArrowUp className="size-3.5" />
                    </IconButton>
                    <IconButton
                      label="下移"
                      disabled={i === plan.items.length - 1}
                      onClick={() => move(i, 1)}
                    >
                      <ArrowDown className="size-3.5" />
                    </IconButton>
                    <IconButton
                      label="移除"
                      onClick={() => edit({ ...plan, items: plan.items.filter((_, j) => j !== i) })}
                    >
                      <X className="size-3.5" />
                    </IconButton>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>

        {canEdit ? (
          <div className="mt-5 space-y-3">
            <PoolRow
              title="添加战役"
              entries={operationStarts.map((m) => ({
                key: m.map_name,
                image: m.image_url,
                label: m.operation.map((o) => o.name).join(" → "),
                onAdd: () =>
                  edit({
                    ...plan,
                    items: [...plan.items, { map: m.map_name, scope: "operation", repeat: 1 }],
                  }),
              }))}
            />
            <PoolRow
              title="添加单张图"
              entries={[...maps.values()].map((m) => ({
                key: m.map_name,
                image: m.image_url,
                label:
                  m.operation.length > 1
                    ? `${m.name}（第 ${m.operation.findIndex((o) => o.map_name === m.map_name) + 1} 张）`
                    : `${m.name}（单图行动）`,
                onAdd: () =>
                  edit({
                    ...plan,
                    items: [...plan.items, { map: m.map_name, scope: "map", repeat: 1 }],
                  }),
              }))}
            />
          </div>
        ) : null}
      </Bf1Panel>

      {/* 执行记录 */}
      <Bf1Panel cut={20} className="p-3.5 sm:p-6" style={{ background: "rgba(12,12,15,0.72)" }}>
        <SectionHeading className="mb-0">执行记录</SectionHeading>
        {v.events.length === 0 ? (
          <div className="py-6 text-center text-sm text-white/40">还没有记录</div>
        ) : (
          <ul className="mt-3 divide-y divide-white/[0.06] text-sm">
            {v.events.map((e, i) => (
              <li key={`${e.ts}-${i}`} className="flex gap-3 py-2">
                <span className="w-16 shrink-0 text-xs text-white/40 tabular-nums">
                  {new Date(e.ts * 1000).toLocaleTimeString("zh-CN", { hour12: false })}
                </span>
                <span
                  className={cn(
                    "h-fit shrink-0 px-1.5 py-px text-[11px] font-semibold",
                    EVENT_STYLE[e.kind] ?? EVENT_STYLE.start,
                  )}
                >
                  {EVENT_LABEL[e.kind] ?? e.kind}
                </span>
                <span className="text-white/80">{e.message}</span>
              </li>
            ))}
          </ul>
        )}
      </Bf1Panel>

      <ConfirmSheet
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="开启自动换图？"
        description="开启后，每局结束时会按编排自动换图，由你绑定的 EA 账号执行，审计里记为「自动换图」。换图失败、编排跑完，或检测到别的切图机器人时会自动关闭。"
        confirmText={countdown > 0 ? `确认开启（${countdown}）` : "确认开启"}
        confirmDisabled={countdown > 0}
        loading={toggle.isPending}
        onConfirm={() => toggle.mutate(true)}
      >
        <div className="text-foreground text-sm">
          共 {v.plan.items.length} 项，
          {v.plan.loops ? `跑 ${v.plan.loops} 轮后停止` : "一直循环"}。
        </div>
      </ConfirmSheet>
    </div>
  );
}

function IconButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="compact-action grid size-7 place-items-center text-white/60 ring-1 ring-white/10 enabled:hover:bg-white enabled:hover:text-black disabled:opacity-30"
    >
      {children}
    </button>
  );
}

function PoolRow({
  title,
  entries,
}: {
  title: string;
  entries: { key: string; image: string | null; label: string; onAdd: () => void }[];
}) {
  if (entries.length === 0) return null;
  return (
    <div>
      <div className="mb-2 text-xs text-white/45">{title}</div>
      <div className="flex flex-wrap gap-1.5">
        {entries.map((e) => (
          <button
            key={e.key}
            type="button"
            onClick={e.onAdd}
            className="compact-action inline-flex h-8 items-center gap-2 bg-white/[0.05] pr-2.5 text-xs text-white/80 ring-1 ring-white/10 transition-colors hover:bg-white hover:text-black"
          >
            {e.image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={e.image} alt="" className="h-full w-12 object-cover" />
            ) : null}
            <Plus className="size-3" />
            {e.label}
          </button>
        ))}
      </div>
    </div>
  );
}
