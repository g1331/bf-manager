"use client";

/**
 * 服务器详情「成员名单」tab：管理员 / VIP / 封禁三类名单的查看与维护。
 *
 * 顶部三张容量卡切换名单；搜索框按玩家名或 persona ID 过滤，搜索词跨分类保留，
 * 便于快速确认某玩家身处哪份名单。有对应权限时显示添加入口（按名字或 persona ID
 * 解析）与行内移除按钮，写操作复用 ServerAdminProvider 的 act（统一二次确认 +
 * 缓存失效 + 提示），离线名单维护与在线玩家行内操作走同一条链路。
 *
 * VIP 页另外叠加平台托管的计时信息：每行的剩余时长 / 永久 / 已到期徽标，行动服的待生效
 * 队列，以及 checkvip（「立即生效」）。
 */

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Clock, Plus, Search, X, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Link from "next/link";
import { PlayerAvatar } from "@/components/common/PlayerAvatar";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { useServerAdmin } from "@/components/bf1/server-admin/InlineServerAdmin";
import { VipBadge, formatSpan, vipStatusOf } from "@/components/bf1/server-admin/vip";
import { bf1Api, type ServerExtras, type TimedVipItem, type TimedVipView } from "@/lib/api/bf1";
import { ApiException } from "@/lib/api-client";
import { cn } from "@/lib/utils";

type MemberKind = "admins" | "vips" | "banned";

/** 解析后的操作目标：persona_id 为后端寻址依据，display_name 仅用于确认文案 */
interface ResolvedTarget {
  persona_id: number;
  display_name: string;
}

/**
 * 三类名单的展示文案与操作映射。add / remove 的字面量同时满足
 * useServerAdmin 的操作种类与 can 的授权种类（两侧枚举在这六项上同名）。
 */
const KIND_META: Record<
  MemberKind,
  {
    label: string;
    /** RSP 名单容量上限（管理员 / VIP 50，封禁 200） */
    limit: number;
    addKind: "ban" | "addVip" | "addAdmin";
    removeKind: "unban" | "removeVip" | "removeAdmin";
    addLabel: string;
    removeLabel: string;
    emptyText: string;
  }
> = {
  admins: {
    label: "管理员",
    limit: 50,
    addKind: "addAdmin",
    removeKind: "removeAdmin",
    addLabel: "添加管理员",
    removeLabel: "移除",
    emptyText: "暂无管理员",
  },
  vips: {
    label: "VIP",
    limit: 50,
    addKind: "addVip",
    removeKind: "removeVip",
    addLabel: "添加 VIP",
    removeLabel: "移除",
    emptyText: "暂无 VIP",
  },
  banned: {
    label: "封禁",
    limit: 200,
    addKind: "ban",
    removeKind: "unban",
    addLabel: "封禁",
    removeLabel: "解封",
    emptyText: "暂无封禁记录",
  },
};

const KIND_ORDER: MemberKind[] = ["admins", "vips", "banned"];

/**
 * 把「玩家名或 persona ID」解析为目标 persona。
 * - 纯数字：按 persona ID 精确处理（备选 / 精确路径），顺带取名展示，取名失败也不阻塞；
 * - 否则：按名字检索，优先精确名匹配，唯一结果次之，找不到则返回 null。
 */
async function resolveTarget(raw: string): Promise<ResolvedTarget | null> {
  const input = raw.trim();
  if (!input) return null;
  if (/^\d+$/.test(input)) {
    const id = Number(input);
    try {
      const p = await bf1Api.getPlayer(id);
      return { persona_id: id, display_name: p.display_name };
    } catch {
      return { persona_id: id, display_name: String(id) };
    }
  }
  const res = await bf1Api.searchPlayers(input);
  const exact = res.personas.find((p) => p.display_name.toLowerCase() === input.toLowerCase());
  const hit = exact ?? (res.personas.length === 1 ? res.personas[0] : null);
  return hit ? { persona_id: hit.persona_id, display_name: hit.display_name } : null;
}

export function MembersPanel({
  game,
  gameId,
  extras,
}: {
  game: string;
  gameId: number;
  extras: ServerExtras;
}) {
  const { can, act, canManage } = useServerAdmin();
  const [kind, setKind] = useState<MemberKind>("admins");
  const [search, setSearch] = useState("");
  const [addInput, setAddInput] = useState("");
  const [resolving, setResolving] = useState(false);

  const meta = KIND_META[kind];
  const members = extras[kind];
  const canAdd = can(meta.addKind);
  const canRemove = can(meta.removeKind);
  // RSP 名单不带头像，另行批量查询；查到前显示首字母
  const avatars = useQuery({
    queryKey: ["bf1-avatars", members.map((m) => m.persona_id)],
    queryFn: () => bf1Api.getAvatars(members.map((m) => m.persona_id)),
    enabled: members.length > 0,
    staleTime: 60 * 60_000,
  });

  // 计时信息只对服管可见（查询会用操作者的凭据拉 EA 名单对账）
  const timed = useQuery({
    queryKey: ["bf1-timed-vips", gameId],
    queryFn: () => bf1Api.getTimedVips(gameId),
    enabled: kind === "vips" && canManage,
    staleTime: 15_000,
  });
  const vipView = kind === "vips" ? timed.data : undefined;

  const keyword = search.trim().toLowerCase();
  const filtered = keyword
    ? members.filter(
        (m) =>
          (m.display_name ?? "").toLowerCase().includes(keyword) ||
          String(m.persona_id).includes(keyword),
      )
    : members;

  const switchKind = (next: MemberKind) => {
    setKind(next);
    // 添加输入针对具体名单，切换分类时清空，避免误把目标提交到另一份名单
    setAddInput("");
  };

  const submitAdd = async () => {
    if (resolving || !addInput.trim()) return;
    setResolving(true);
    try {
      const target = await resolveTarget(addInput);
      if (!target) {
        toast.error("未找到该玩家，请检查名字或改用 persona ID");
        return;
      }
      act(meta.addKind, target);
      setAddInput("");
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : "查询玩家失败，请稍后重试");
    } finally {
      setResolving(false);
    }
  };

  return (
    // @container：名单列数按面板自身宽度定，详情页被侧栏裁窄时视口断点测不准
    <div className="@container space-y-5">
      {/* 三份名单的容量卡，同时充当分类切换 */}
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        {KIND_ORDER.map((k) => (
          <KindCard
            key={k}
            label={KIND_META[k].label}
            count={extras[k].length}
            limit={KIND_META[k].limit}
            danger={k === "banned"}
            active={kind === k}
            onClick={() => switchKind(k)}
          />
        ))}
      </div>

      {/* 搜索 + 添加入口（添加入口仅对有对应权限的用户渲染） */}
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-white/35" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`搜索${meta.label}（玩家名或 persona ID）`}
            className="h-9 border-white/15 bg-black/30 pl-9 text-white placeholder:text-white/35"
          />
        </div>
        {canAdd ? (
          <div className="flex gap-2 sm:w-80">
            <Input
              value={addInput}
              onChange={(e) => setAddInput(e.target.value)}
              placeholder="输入玩家名或 persona ID"
              disabled={resolving}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitAdd();
              }}
              className="h-9 border-white/15 bg-black/30 text-white placeholder:text-white/35"
            />
            <Button
              variant="outline"
              className="h-9 shrink-0"
              onClick={submitAdd}
              disabled={resolving || !addInput.trim()}
            >
              <Plus className="size-4" />
              {resolving ? "查询中…" : meta.addLabel}
            </Button>
          </div>
        ) : null}
      </div>

      {vipView ? (
        <VipQueueSection
          gameId={gameId}
          view={vipView}
          keyword={keyword}
          canAdjust={can("addVip")}
          canRemove={can("removeVip")}
          canApply={can("applyVip")}
          onAdjust={(item) =>
            act("addVip", {
              persona_id: item.persona_id,
              display_name: item.display_name ?? String(item.persona_id),
            })
          }
          onRemove={(item) =>
            act("removeVip", {
              persona_id: item.persona_id,
              display_name: item.display_name ?? String(item.persona_id),
            })
          }
        />
      ) : null}

      {keyword ? (
        <p className="text-xs text-white/45 tabular-nums">
          匹配 {filtered.length} / {members.length} 人
        </p>
      ) : null}

      {filtered.length === 0 ? (
        <p className="border border-dashed border-white/10 py-10 text-center text-sm text-white/40">
          {keyword ? `没有匹配「${search.trim()}」的${meta.label}` : meta.emptyText}
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-1.5 @xl:grid-cols-2 @3xl:grid-cols-3">
          {filtered.map((m) => {
            const name = m.display_name ?? String(m.persona_id);
            return (
              <li
                key={m.persona_id}
                className="group flex items-center gap-3 border border-white/[0.06] bg-black/35 px-3 py-2.5 transition-colors hover:border-white/15"
              >
                <PlayerAvatar
                  avatarUrl={m.avatar_url || avatars.data?.[m.persona_id] || null}
                  displayName={name}
                  size="sm"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/${game}/player/${m.persona_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="truncate text-sm text-white hover:underline"
                      title={`${name}（在新标签查看战绩）`}
                    >
                      {name}
                    </Link>
                    {m.platform ? (
                      <span className="shrink-0 border border-white/20 px-1 text-[10px] leading-4 text-white/55">
                        {m.platform.toUpperCase()}
                      </span>
                    ) : null}
                  </div>
                  {vipView ? (
                    <div className="mt-0.5 flex min-w-0">
                      <VipBadge
                        status={vipStatusOf(vipView, m.persona_id)}
                        operation={vipView.operation}
                      />
                    </div>
                  ) : null}
                  <div className="font-mono text-[11px] text-white/40">{m.persona_id}</div>
                </div>
                {kind === "vips" && can("addVip") ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="compact-action shrink-0 px-2.5 opacity-70 group-hover:opacity-100"
                    aria-label={`调整 ${name} 的 VIP`}
                    title="调整时长"
                    onClick={() => act("addVip", { persona_id: m.persona_id, display_name: name })}
                  >
                    <Clock className="size-3.5" />
                  </Button>
                ) : null}
                {canRemove ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className={cn(
                      "compact-action shrink-0 opacity-70 group-hover:opacity-100",
                      kind === "vips" && "px-2.5",
                    )}
                    // VIP 行多一个调整按钮，两个都只留图标，给名字和徽标让出宽度
                    aria-label={kind === "vips" ? `移除 ${name} 的 VIP` : undefined}
                    title={kind === "vips" ? meta.removeLabel : undefined}
                    onClick={() =>
                      act(meta.removeKind, { persona_id: m.persona_id, display_name: name })
                    }
                  >
                    <X className="size-3.5" />
                    {kind === "vips" ? null : meta.removeLabel}
                  </Button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/**
 * VIP 页的计时区：状态栏（名单占用 / 已到期 / 排队）+「立即生效」，以及待生效队列。
 * 普通服只有在出现已到期未移除或排队记录时才显示状态栏（平时到期会自动下掉）。
 */
function VipQueueSection({
  gameId,
  view,
  keyword,
  canAdjust,
  canRemove,
  canApply,
  onAdjust,
  onRemove,
}: {
  gameId: number;
  view: TimedVipView;
  keyword: string;
  canAdjust: boolean;
  canRemove: boolean;
  canApply: boolean;
  onAdjust: (item: TimedVipItem) => void;
  onRemove: (item: TimedVipItem) => void;
}) {
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [restart, setRestart] = useState(false);
  const [applying, setApplying] = useState(false);

  const queue = view.items
    .filter((i) => i.status === "pending")
    .sort((a, b) => (a.queue_position ?? 0) - (b.queue_position ?? 0));
  const expired = view.items.filter((i) => i.expired).length;
  const lastError = view.items.find((i) => i.expired && i.last_error)?.last_error;
  const free = Math.max(view.capacity - view.vip_ids.length + expired, 0);
  const willAdd = Math.min(queue.length, free);
  const empty = view.operation && view.players === 0;
  const shown = keyword
    ? queue.filter(
        (i) =>
          (i.display_name ?? "").toLowerCase().includes(keyword) ||
          String(i.persona_id).includes(keyword),
      )
    : queue;

  if (!view.operation && queue.length === 0 && expired === 0) return null;

  const openApply = () => {
    setRestart(view.operation && view.campaign_start);
    setConfirming(true);
  };

  const apply = async () => {
    setApplying(true);
    try {
      const res = await bf1Api.applyVips(gameId, restart);
      if (res.failures.length === 0) {
        toast.success(res.message);
      } else {
        const first = res.failures[0];
        toast.warning(res.message, {
          description: `${first.display_name ?? (first.persona_id || "重开")}：${first.message}`,
        });
      }
      setConfirming(false);
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : "操作失败，请稍后重试");
    } finally {
      setApplying(false);
      qc.invalidateQueries({ queryKey: ["bf1-timed-vips", gameId] });
      qc.invalidateQueries({ queryKey: ["bf1-server", gameId] });
      qc.invalidateQueries({ queryKey: ["bf1-server-players", gameId] });
    }
  };

  return (
    <div className="space-y-3 border border-white/10 bg-black/30 p-3 sm:p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-white/80 tabular-nums">
            <span>
              名单 {view.vip_ids.length}/{view.capacity}
            </span>
            <span className={expired ? "text-rose-300" : "text-white/45"}>已到期 {expired}</span>
            <span className={queue.length ? "text-sky-200" : "text-white/45"}>
              排队 {queue.length}/{view.queue_limit}
            </span>
          </div>
          <p className="text-xs leading-5 text-white/45">
            {view.operation
              ? "行动服：新加的 VIP 先排队，不扣天数；空服时上下 V 会掉回普通服，所以要在有人时点「立即生效」——先下掉到期的，再按顺序补空位并开始计时。"
              : `普通服的 VIP 到期后每分钟自动下掉；没下掉的可以点「立即生效」重试${lastError ? `（${lastError}）` : ""}。`}
          </p>
        </div>
        {canApply ? (
          <div className="flex shrink-0 flex-col items-stretch gap-1 sm:items-end">
            <Button
              variant="outline"
              className="h-9"
              disabled={empty || (expired === 0 && willAdd === 0)}
              onClick={openApply}
            >
              <Zap className="size-4" />
              立即生效
            </Button>
            {empty ? <span className="text-xs text-rose-300">服里没人，暂时不能生效</span> : null}
          </div>
        ) : null}
      </div>

      {shown.length > 0 ? (
        <ul className="grid grid-cols-1 gap-1.5 @xl:grid-cols-2 @3xl:grid-cols-3">
          {shown.map((item) => {
            const name = item.display_name ?? String(item.persona_id);
            return (
              <li
                key={item.persona_id}
                className="group flex items-center gap-3 border border-sky-400/15 bg-sky-500/[0.04] px-3 py-2"
              >
                <span className="font-display w-6 shrink-0 text-center text-sm text-sky-200 tabular-nums">
                  {item.queue_position}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-white">{name}</div>
                  <div className="truncate text-[11px] text-white/45">
                    待生效 ·{" "}
                    {item.remaining_seconds === null
                      ? "永久"
                      : `剩 ${formatSpan(item.remaining_seconds)}`}
                  </div>
                </div>
                {canAdjust ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="compact-action shrink-0 px-2.5 opacity-70 group-hover:opacity-100"
                    aria-label={`调整 ${name} 的排队时长`}
                    title="调整时长"
                    onClick={() => onAdjust(item)}
                  >
                    <Clock className="size-3.5" />
                  </Button>
                ) : null}
                {canRemove ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="compact-action shrink-0 px-2.5 opacity-70 group-hover:opacity-100"
                    aria-label={`把 ${name} 移出待生效队列`}
                    title="撤销"
                    onClick={() => onRemove(item)}
                  >
                    <X className="size-3.5" />
                  </Button>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}

      <ConfirmSheet
        open={confirming}
        onOpenChange={(open) => !applying && setConfirming(open)}
        title="让 VIP 立即生效？"
        description={`将下掉 ${expired} 个已到期的 VIP，再按排队顺序补上 ${willAdd} 个${
          queue.length > willAdd ? `，剩下 ${queue.length - willAdd} 个继续排队` : ""
        }。补上的从现在开始计时。`}
        confirmText="生效"
        loading={applying}
        onConfirm={apply}
      >
        {view.operation ? (
          <div className="space-y-1.5 py-2">
            <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={restart}
                onChange={(e) => setRestart(e.target.checked)}
                className="accent-primary size-4"
              />
              生效后重开当前地图
            </label>
            <p
              className={cn(
                "text-xs leading-5",
                restart && !view.campaign_start ? "text-destructive" : "text-muted-foreground",
              )}
            >
              {view.campaign_start
                ? "当前是战役第一张图，重开不会丢战役进度。"
                : restart
                  ? "当前不是战役第一张图，重开会丢掉这一战役的进度，建议本战役打完再生效。"
                  : "当前不是战役第一张图，建议本战役打完、换到战役开头后再重开。"}
            </p>
          </div>
        ) : null}
      </ConfirmSheet>
    </div>
  );
}

/** 名单容量卡：人数 / 上限 + 容量条，选中时描金边 */
function KindCard({
  label,
  count,
  limit,
  danger,
  active,
  onClick,
}: {
  label: string;
  count: number;
  limit: number;
  danger: boolean;
  active: boolean;
  onClick: () => void;
}) {
  const share = Math.min(count / limit, 1);
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "relative border px-3 py-3 text-left transition-colors sm:px-4",
        active
          ? "border-amber-400/60 bg-amber-500/[0.08]"
          : "border-white/10 bg-black/30 hover:border-white/25",
      )}
    >
      {active ? <span className="absolute inset-x-0 top-0 h-0.5 bg-amber-400" /> : null}
      <div className={cn("text-xs tracking-wider", active ? "text-amber-300" : "text-white/55")}>
        {label}
      </div>
      <div className="font-display mt-1 flex items-baseline tabular-nums">
        <span className="text-3xl font-bold text-white">{count}</span>
        <span className="ml-1 text-sm text-white/40">/{limit}</span>
      </div>
      <div className="mt-2 h-1 bg-white/10">
        <div
          className={cn("h-full", danger ? "bg-rose-400/80" : "bg-amber-400")}
          style={{ width: `${share * 100}%` }}
        />
      </div>
    </button>
  );
}
