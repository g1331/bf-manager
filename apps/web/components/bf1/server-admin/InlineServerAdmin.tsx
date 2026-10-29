"use client";

/**
 * 内联服管：把踢出 / 封禁 / 加 V / 下 V 等操作直接做到实时玩家列表的每一行与多选批量栏上。
 *
 * 设计：
 * - 用 React Context 承载「当前用户对本服的角色、选择集、确认与执行」，玩家行与批量栏作为
 *   消费方，避免逐层透传一堆 props；
 * - 未包裹 Provider 时 useServerAdmin 返回安全默认值（canManage=false、操作均为 no-op），
 *   因此纯展示用途（如 mock 预览）的 ServerPlayersView 不依赖 Provider 也能渲染；
 * - 角色仅用于 gating UI（是否渲染入口、菜单项是否出现），真正鉴权以后端 require_role 为准。
 */

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  Ban,
  Check,
  Clock,
  Minus,
  MoreHorizontal,
  ShieldCheck,
  ShieldMinus,
  Star,
  StarOff,
  UserX,
  X,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { useSession } from "@/hooks/useSession";
import {
  useMyServerRole,
  useServerAdminActions,
  type AdminActionRequest,
} from "@/hooks/useServerAdminActions";
import { canDo, hasAnyServerAdmin, type ServerAdminAction } from "@/lib/bf1/server-admin-authz";
import { bf1Api, type BlazePlayer, type MyServerRole, type VipGrantOptions } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";
import {
  VipDurationPicker,
  formatExpiry,
  formatSpan,
  isPermanentVip,
  isValidDays,
  vipStatusOf,
  type VipStatus,
} from "@/components/bf1/server-admin/vip";

/**
 * 玩家的最小寻址信息：persona_id 为后端实际依据，名字用于展示与确认文案。
 * team 是玩家当前所在队伍的 Blaze TIDX（0/1），仅换边需要；离线名单管理（按名解析）无队伍
 * 概念，故设为可选。
 */
type PlayerRef = Pick<BlazePlayer, "persona_id" | "display_name"> & { team?: number };

/** 单人操作种类（与菜单项 / 名单管理项对应） */
type SingleKind =
  "kick" | "move" | "ban" | "unban" | "addVip" | "removeVip" | "addAdmin" | "removeAdmin";
/** 批量操作种类（高频的踢 / 换边 / 封，以及给服内玩家批量加 N 天 V） */
type BatchKind = "kick" | "move" | "ban" | "addVip";

interface ServerAdminContextValue {
  /** 是否拥有任意服管权限，决定是否渲染服管入口（选择列 / ⋯ 菜单 / 批量栏） */
  canManage: boolean;
  /** 单个操作的细粒度授权判断 */
  can: (action: ServerAdminAction) => boolean;
  role: MyServerRole | undefined;
  // ——— 多选 ———
  isSelected: (personaId: number) => boolean;
  toggle: (personaId: number) => void;
  selectMany: (personaIds: number[], on: boolean) => void;
  clear: () => void;
  selectedCount: number;
  // ——— 操作（触发二次确认） ———
  act: (kind: SingleKind, player: PlayerRef) => void;
  actBatch: (kind: BatchKind, players: PlayerRef[]) => void;
  /** restart：换到当前地图（重开）；warning：确认框里额外显示的警告，并改用警示样式 */
  chooseLevel: (
    levelIndex: number,
    mapName: string,
    opts?: { restart?: boolean; warning?: string },
  ) => void;
  loading: boolean;
}

const NOOP = () => {};
const DEFAULT_CTX: ServerAdminContextValue = {
  canManage: false,
  can: () => false,
  role: undefined,
  isSelected: () => false,
  toggle: NOOP,
  selectMany: NOOP,
  clear: NOOP,
  selectedCount: 0,
  act: NOOP,
  actBatch: NOOP,
  chooseLevel: NOOP,
  loading: false,
};

const ServerAdminContext = createContext<ServerAdminContextValue>(DEFAULT_CTX);

export function useServerAdmin(): ServerAdminContextValue {
  return useContext(ServerAdminContext);
}

type Pending =
  | { mode: "single"; kind: SingleKind; player: PlayerRef }
  | { mode: "batch"; kind: BatchKind; players: PlayerRef[] }
  | { mode: "level"; levelIndex: number; mapName: string; restart?: boolean; warning?: string }
  | null;

const DEFAULT_REASON = "violation of rules";

function buildRequest(
  kind: SingleKind,
  player: PlayerRef,
  reason: string,
  vip?: VipGrantOptions,
): AdminActionRequest {
  const label = player.display_name;
  switch (kind) {
    case "kick":
      return { action: "kick", personaId: player.persona_id, reason, label };
    case "move":
      // 换边总是 toggle 到对面：传玩家当前队伍号（0/1），后端 +1 转 RSP 源队伍号。
      // team 在换边场景必来自实时名单（对阵玩家 team 必为 0/1），?? 0 仅作类型兜底。
      return { action: "move", personaId: player.persona_id, teamId: player.team ?? 0, label };
    case "ban":
      return { action: "ban", personaId: player.persona_id, label };
    case "unban":
      return { action: "unban", personaId: player.persona_id, label };
    case "addVip":
      return { action: "addVip", personaId: player.persona_id, label, vip };
    case "removeVip":
      return { action: "removeVip", personaId: player.persona_id, label };
    case "addAdmin":
      return { action: "addAdmin", personaId: player.persona_id, label };
    case "removeAdmin":
      return { action: "removeAdmin", personaId: player.persona_id, label };
  }
}

/**
 * 加 V 时长的默认值：新加的默认永久（与 v3 不带天数的 -vip 一致），已有期限的默认再加 7 天，
 * 批量加 V 默认 7 天（对应 v3「谁在玩」回复 v 天数）。
 */
function defaultVipDays(status: VipStatus, batch: boolean): number | null {
  if (batch) return 7;
  if (isPermanentVip(status)) return null;
  return status.kind === "timed" || status.kind === "pending" ? 7 : null;
}

/** 单人加 V / 改期确认框的标题动词 */
function vipVerb(status: VipStatus): string {
  return status.kind === "none" ? "添加 VIP" : "调整 VIP";
}

/** 加 V / 下 V 确认框的说明，按服务器类型和玩家当前的 VIP 状态给出实际效果 */
function vipDescription(
  kind: "addVip" | "removeVip",
  status: VipStatus,
  days: number | null,
  operation: boolean,
): string {
  if (kind === "removeVip") {
    if (status.kind === "pending") return "从待生效队列撤掉，不会动 EA 名单";
    return operation
      ? "行动服：先标记为到期，下次在 VIP 名单里点「立即生效」时才会真正下掉（空服上下 V 会掉回普通服）"
      : "立即从 EA 名单移除";
  }
  if (status.kind === "timed" && status.item.expired) {
    return days === null
      ? "已到期还没下掉，改为永久 VIP"
      : `已到期还没下掉，从现在起算 ${days} 天；只改记录，不动 EA 名单`;
  }
  if (status.kind === "timed") {
    const exp = status.item.expires_at ? `，目前 ${formatExpiry(status.item.expires_at)} 到期` : "";
    return days === null
      ? `改为永久 VIP${exp}`
      : `在现有期限上${days > 0 ? "增加" : "减少"} ${Math.abs(days)} 天${exp}；只改记录，不动 EA 名单`;
  }
  if (status.kind === "pending") {
    const left =
      status.item.remaining_seconds === null
        ? "永久"
        : `剩 ${formatSpan(status.item.remaining_seconds)}`;
    const where = `该玩家在待生效队列里（${left}，第 ${status.item.queue_position ?? "?"} 位）`;
    if (status.item.remaining_seconds === null && days !== null) {
      return `${where}，确认后改为排队 ${days} 天的限时 VIP`;
    }
    return `${where}，只调整排队时长，不动 EA 名单`;
  }
  if (status.kind === "permanent") {
    return days === null
      ? "该玩家已经是永久 VIP"
      : `该玩家目前是永久 VIP，确认后会改为 ${days} 天的限时 VIP，${
          operation ? "到期后下次「立即生效」时下掉" : "到期自动下掉"
        }`;
  }
  if (operation) {
    return "行动服：先加入待生效队列，排队期间不扣天数；在 VIP 名单里点「立即生效」后才会真正加上";
  }
  return days === null ? "永久 VIP，不会自动下掉" : `立即加上，${days} 天后自动下掉`;
}

const SINGLE_VERB: Record<SingleKind, string> = {
  kick: "踢出",
  move: "换边",
  ban: "封禁",
  unban: "解封",
  addVip: "添加 VIP",
  removeVip: "移除 VIP",
  addAdmin: "添加管理员",
  removeAdmin: "移除管理员",
};

export function ServerAdminProvider({ gameId, children }: { gameId: number; children: ReactNode }) {
  const session = useSession();
  const isLoggedIn = !!session.data;
  const roleQuery = useMyServerRole(gameId, isLoggedIn);
  const role = roleQuery.data;
  const { loading, runSingle, runBatch } = useServerAdminActions(gameId);

  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [pending, setPending] = useState<Pending>(null);
  const [reason, setReason] = useState(DEFAULT_REASON);
  // undefined 表示还没手动选过，取 defaultVipDays；NaN 表示自定义输入不合法
  const [vipDays, setVipDays] = useState<number | null | undefined>(undefined);

  const canManage = hasAnyServerAdmin(role);
  const can = useCallback((action: ServerAdminAction) => canDo(action, role), [role]);

  const isSelected = useCallback((id: number) => selected.has(id), [selected]);
  const toggle = useCallback((id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  const selectMany = useCallback((ids: number[], on: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (on) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }, []);
  const clear = useCallback(() => setSelected(new Set()), []);

  const act = useCallback((kind: SingleKind, player: PlayerRef) => {
    setReason(DEFAULT_REASON);
    setVipDays(undefined);
    setPending({ mode: "single", kind, player });
  }, []);
  const actBatch = useCallback((kind: BatchKind, players: PlayerRef[]) => {
    if (players.length === 0) return;
    setReason(DEFAULT_REASON);
    setVipDays(undefined);
    setPending({ mode: "batch", kind, players });
  }, []);
  const chooseLevel = useCallback(
    (levelIndex: number, mapName: string, opts?: { restart?: boolean; warning?: string }) => {
      setPending({ mode: "level", levelIndex, mapName, ...opts });
    },
    [],
  );

  const close = useCallback(() => setPending(null), []);

  // VIP 操作要知道服务器类型和玩家现有的 VIP 状态（永久 / 限时 / 排队）
  const vipKind =
    pending &&
    pending.mode !== "level" &&
    (pending.kind === "addVip" || pending.kind === "removeVip")
      ? pending.kind
      : null;
  const timedVips = useQuery({
    queryKey: ["bf1-timed-vips", gameId],
    queryFn: () => bf1Api.getTimedVips(gameId),
    enabled: vipKind !== null && canManage,
    staleTime: 15_000,
  });
  const vipView = timedVips.data;
  const singleVipStatus = useMemo<VipStatus>(
    () =>
      pending?.mode === "single"
        ? vipStatusOf(vipView, pending.player.persona_id)
        : { kind: "none" },
    [pending, vipView],
  );
  // 有剩余期限的才能填负数缩短；已到期的改期从现在起算
  const canShortenVip =
    (singleVipStatus.kind === "pending" && !isPermanentVip(singleVipStatus)) ||
    (singleVipStatus.kind === "timed" && !singleVipStatus.item.expired);
  const effectiveVipDays =
    vipDays === undefined ? defaultVipDays(singleVipStatus, pending?.mode === "batch") : vipDays;
  const vipDaysValid = isValidDays(effectiveVipDays, canShortenVip);

  const vipOptions = useCallback(
    (status: VipStatus, player: PlayerRef): VipGrantOptions => ({
      days: effectiveVipDays,
      displayName: player.display_name,
      allowPermanentToTimed: isPermanentVip(status) && effectiveVipDays !== null,
    }),
    [effectiveVipDays],
  );

  const execute = useCallback(async () => {
    if (!pending) return;
    if (pending.mode === "single") {
      const vip =
        pending.kind === "addVip" ? vipOptions(singleVipStatus, pending.player) : undefined;
      const ok = await runSingle(buildRequest(pending.kind, pending.player, reason, vip));
      if (ok) close();
      return;
    }
    if (pending.mode === "level") {
      const ok = await runSingle({
        action: "chooseLevel",
        levelIndex: pending.levelIndex,
        label: pending.mapName,
      });
      if (ok) close();
      return;
    }
    // 批量加 V 跳过永久 VIP（与 v3 一致），其余在现有期限上加
    const players =
      pending.kind === "addVip"
        ? pending.players.filter((p) => !isPermanentVip(vipStatusOf(vipView, p.persona_id)))
        : pending.players;
    const reqs = players.map((p) =>
      buildRequest(
        pending.kind,
        p,
        reason,
        pending.kind === "addVip" ? vipOptions({ kind: "none" }, p) : undefined,
      ),
    );
    await runBatch(reqs);
    clear();
    close();
  }, [pending, reason, runSingle, runBatch, clear, close, vipOptions, singleVipStatus, vipView]);

  const value = useMemo<ServerAdminContextValue>(
    () => ({
      canManage,
      can,
      role,
      isSelected,
      toggle,
      selectMany,
      clear,
      selectedCount: selected.size,
      act,
      actBatch,
      chooseLevel,
      loading,
    }),
    [
      canManage,
      can,
      role,
      isSelected,
      toggle,
      selectMany,
      clear,
      selected.size,
      act,
      actBatch,
      chooseLevel,
      loading,
    ],
  );

  // 换图提示要看行动进度：复用详情页已预取的实时名单，只在打开换图确认时才可能补拉
  const players = useQuery({
    queryKey: ["bf1-server-players", gameId],
    queryFn: () => bf1Api.getServerPlayers(gameId),
    staleTime: 15_000,
    enabled: pending?.mode === "level",
  });
  const op = players.data?.operation;
  const opSectors = op?.maps[op.map_index]?.sectors;
  const levelDescription =
    op?.state === "waiting"
      ? "现在是开局前，适合换图；所有玩家会被移到新地图"
      : op && opSectors
        ? `当前对局正在进行（区域 ${Math.min(op.sectors_taken + 1, opSectors)}/${opSectors}），换图会立即结束这一局，建议等到开局前再换`
        : "切换地图会立即结束当前对局，所有玩家会被移到新地图";

  const isKick = pending?.mode !== "level" && pending?.kind === "kick";
  const isAddVip = vipKind === "addVip";
  const isMove = pending?.mode !== "level" && pending?.kind === "move";
  const isBan = pending?.mode !== "level" && pending?.kind === "ban";
  const confirmTitle = !pending
    ? ""
    : pending.mode === "single"
      ? `${pending.kind === "addVip" ? vipVerb(singleVipStatus) : SINGLE_VERB[pending.kind]} ${pending.player.display_name}？`
      : pending.mode === "batch"
        ? pending.kind === "addVip"
          ? `给选中的 ${pending.players.length} 名玩家加 V？`
          : `${SINGLE_VERB[pending.kind]}选中的 ${pending.players.length} 名玩家？`
        : `${pending.restart ? "重开" : "切换到"} ${pending.mapName}？`;
  // isMove / batch 分支须先于 isBan 判断：批量时对应 kind 的标志同样为真，若不前置会错误回退到
  // 单人 / 通用文案。换边无论单人或批量都要提示 forceKill 会强制阵亡一次。
  const confirmDescription = !pending
    ? undefined
    : pending.mode === "level"
      ? [pending.warning, levelDescription].filter(Boolean).join("。")
      : vipKind && pending.mode === "batch"
        ? vipView?.operation
          ? "行动服：没在名单里的先加入待生效队列，已有期限的在原期限上加；永久 VIP 跳过"
          : "没在名单里的立即加上，已有期限的在原期限上加；永久 VIP 跳过"
        : vipKind && pending.mode === "single"
          ? vipDescription(vipKind, singleVipStatus, effectiveVipDays, !!vipView?.operation)
          : isMove
            ? pending.mode === "batch"
              ? "换边会强制玩家阵亡一次后移到对方阵营；将对所有选中玩家依次执行，部分失败不会中断其余项"
              : "换边会强制玩家阵亡一次后移到对方阵营"
            : pending.mode === "batch"
              ? "将对所有选中玩家依次执行，部分失败不会中断其余项"
              : isBan
                ? "封禁后该玩家无法再次加入服务器，可在管理后台或 EA 平台解除"
                : pending.kind === "addAdmin"
                  ? "管理员可对本服执行踢人、封禁等操作，请确认对方身份"
                  : undefined;

  return (
    <ServerAdminContext.Provider value={value}>
      {children}
      <ConfirmSheet
        open={pending !== null}
        onOpenChange={(open) => !open && close()}
        title={confirmTitle}
        description={confirmDescription}
        confirmText="确认"
        cancelText="取消"
        variant={
          isBan || (pending?.mode === "level" && pending.warning) ? "destructive" : "default"
        }
        loading={loading}
        // VIP 操作要先拿到服务器类型和玩家现有状态（永久 / 限时 / 排队），否则文案和参数都可能不对
        confirmDisabled={(isAddVip && !vipDaysValid) || (vipKind !== null && timedVips.isPending)}
        onConfirm={execute}
      >
        {isAddVip && pending?.mode !== "level" ? (
          <VipDurationPicker
            key={pending?.mode === "single" ? pending.player.persona_id : "batch"}
            value={effectiveVipDays}
            onChange={setVipDays}
            allowNegative={canShortenVip}
            label={canShortenVip ? "在现有期限上增加（自定义可填负数缩短）" : "VIP 时长"}
          />
        ) : null}
        {isKick ? (
          <div className="space-y-2 py-2">
            <Label htmlFor="inline-kick-reason">踢出理由</Label>
            <Input
              id="inline-kick-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={128}
              placeholder="向被踢玩家显示的理由"
            />
          </div>
        ) : null}
      </ConfirmSheet>
    </ServerAdminContext.Provider>
  );
}

/* --------------------------- 玩家行内联控件 --------------------------- */

/**
 * 暗色主题自定义复选框：用切角方块 + 图标替代原生白框，与战地暗色面板统一。
 * 半选态（indeterminate）用 Minus 图标表示，避免依赖原生 DOM indeterminate 属性。
 */
function SelectBox({
  checked,
  indeterminate = false,
  onToggle,
  label,
}: {
  checked: boolean;
  indeterminate?: boolean;
  onToggle: () => void;
  label: string;
}) {
  const active = checked || indeterminate;
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={indeterminate ? "mixed" : checked}
      aria-label={label}
      onClick={onToggle}
      className={cn(
        "compact-action flex size-4 shrink-0 cursor-pointer items-center justify-center rounded-[3px] border transition-colors",
        active
          ? "border-amber-500 bg-amber-500 text-black"
          : "border-white/30 bg-white/5 hover:border-white/55",
      )}
    >
      {indeterminate ? (
        <Minus className="size-3" strokeWidth={3} />
      ) : checked ? (
        <Check className="size-3" strokeWidth={3} />
      ) : null}
    </button>
  );
}

/** 单行选择框，仅在有服管权限时由调用方渲染 */
export function PlayerSelectCheckbox({ player }: { player: PlayerRef }) {
  const { isSelected, toggle } = useServerAdmin();
  return (
    <SelectBox
      checked={isSelected(player.persona_id)}
      onToggle={() => toggle(player.persona_id)}
      label={`选择 ${player.display_name}`}
    />
  );
}

/** 表头「全选本队」选择框：全选中实心、部分选中半选态 */
export function TeamSelectAllCheckbox({ players }: { players: PlayerRef[] }) {
  const { isSelected, selectMany } = useServerAdmin();
  const ids = players.map((p) => p.persona_id);
  const selectedCount = ids.filter((id) => isSelected(id)).length;
  const allSelected = ids.length > 0 && selectedCount === ids.length;
  const someSelected = selectedCount > 0 && !allSelected;
  return (
    <SelectBox
      checked={allSelected}
      indeterminate={someSelected}
      onToggle={() => selectMany(ids, !allSelected)}
      label="全选本队玩家"
    />
  );
}

function isInTeam(player: BlazePlayer): boolean {
  return player.team === 0 || player.team === 1;
}

/** 玩家行 ⋯ 操作菜单，按角色与玩家当前状态（是否已 VIP / 管理）决定菜单项 */
export function PlayerActionMenu({ player }: { player: BlazePlayer }) {
  const { act, can } = useServerAdmin();
  const ref: PlayerRef = {
    persona_id: player.persona_id,
    display_name: player.display_name,
    team: player.team,
  };

  // 暗色玻璃风菜单项的统一基类（focus 态用半透明白底，覆盖组件默认的浅色 accent）。
  const itemCls = "cursor-pointer gap-2 focus:bg-white/10 focus:text-white";

  const items: ReactNode[] = [];
  if (can("kick")) {
    items.push(
      <DropdownMenuItem key="kick" className={itemCls} onSelect={() => act("kick", ref)}>
        <UserX className="size-3.5" />
        踢出
      </DropdownMenuItem>,
    );
  }
  // 排队 / 旁观玩家不在任何一队（TIDX 65535），没有换边可言
  if (can("move") && isInTeam(player)) {
    items.push(
      <DropdownMenuItem key="move" className={itemCls} onSelect={() => act("move", ref)}>
        <ArrowLeftRight className="size-3.5" />
        换边
      </DropdownMenuItem>,
    );
  }
  if (can("ban")) {
    items.push(
      <DropdownMenuItem
        key="ban"
        onSelect={() => act("ban", ref)}
        className={cn(itemCls, "text-red-400 focus:bg-red-500/15 focus:text-red-300")}
      >
        <Ban className="size-3.5" />
        封禁
      </DropdownMenuItem>,
    );
  }

  const vipItems: ReactNode[] = [];
  if (player.is_vip && can("addVip")) {
    vipItems.push(
      <DropdownMenuItem key="adjustVip" className={itemCls} onSelect={() => act("addVip", ref)}>
        <Clock className="size-3.5" />
        调整 VIP
      </DropdownMenuItem>,
    );
  }
  if (player.is_vip && can("removeVip")) {
    vipItems.push(
      <DropdownMenuItem key="removeVip" className={itemCls} onSelect={() => act("removeVip", ref)}>
        <StarOff className="size-3.5" />下 V
      </DropdownMenuItem>,
    );
  } else if (!player.is_vip && can("addVip")) {
    vipItems.push(
      <DropdownMenuItem key="addVip" className={itemCls} onSelect={() => act("addVip", ref)}>
        <Star className="size-3.5" />加 V
      </DropdownMenuItem>,
    );
  }
  if (player.is_admin && can("removeAdmin")) {
    vipItems.push(
      <DropdownMenuItem
        key="removeAdmin"
        className={itemCls}
        onSelect={() => act("removeAdmin", ref)}
      >
        <ShieldMinus className="size-3.5" />
        移除管理
      </DropdownMenuItem>,
    );
  } else if (!player.is_admin && can("addAdmin")) {
    vipItems.push(
      <DropdownMenuItem key="addAdmin" className={itemCls} onSelect={() => act("addAdmin", ref)}>
        <ShieldCheck className="size-3.5" />
        设为管理
      </DropdownMenuItem>,
    );
  }

  if (items.length === 0 && vipItems.length === 0) return null;

  return (
    // modal={false}：避免下拉关闭与确认弹窗（Dialog）同时争夺焦点 / 锁 body 指针事件，
    // 否则从菜单项打开确认框后页面会出现短暂不可点击。
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`管理 ${player.display_name}`}
          className="compact-action inline-flex size-6 items-center justify-center rounded-sm text-white/45 transition-colors hover:bg-white/10 hover:text-white/90"
        >
          <MoreHorizontal className="size-4" />
        </button>
      </DropdownMenuTrigger>
      {/* 暗色玻璃面板，与详情页 Bf1Panel / 半透明黑底统一，覆盖组件默认浅色 popover */}
      <DropdownMenuContent
        align="end"
        className="min-w-[8rem] border-white/10 bg-neutral-900/95 text-white/90 shadow-xl backdrop-blur-md"
      >
        {items}
        {items.length > 0 && vipItems.length > 0 ? (
          <DropdownMenuSeparator className="bg-white/10" />
        ) : null}
        {vipItems}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** 玩家行尾部 actions 单元格内容：复选框 + ⋯ 菜单 */
export function PlayerRowActions({ player }: { player: BlazePlayer }) {
  return (
    <div className="flex items-center justify-end gap-1.5">
      <PlayerSelectCheckbox player={player} />
      <PlayerActionMenu player={player} />
    </div>
  );
}

/** 多选批量操作栏：选中玩家后浮现，支持批量踢 / 换边 / 封 / 加 V */
export function BatchActionBar({ players }: { players: BlazePlayer[] }) {
  const { canManage, can, selectedCount, clear, actBatch, isSelected } = useServerAdmin();
  if (!canManage || selectedCount === 0) return null;

  const selectedPlayers = players.filter((p) => isSelected(p.persona_id));
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2 rounded-sm border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-sm">
      <span className="font-medium text-amber-100">已选 {selectedCount} 名玩家</span>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        {can("kick") ? (
          <Button
            variant="outline"
            size="sm"
            className="compact-action"
            onClick={() => actBatch("kick", selectedPlayers)}
          >
            <UserX className="size-3.5" />
            批量踢出
          </Button>
        ) : null}
        {can("move") ? (
          <Button
            variant="outline"
            size="sm"
            className="compact-action"
            onClick={() => actBatch("move", selectedPlayers.filter(isInTeam))}
          >
            <ArrowLeftRight className="size-3.5" />
            批量换边
          </Button>
        ) : null}
        {can("addVip") ? (
          <Button
            variant="outline"
            size="sm"
            className="compact-action"
            onClick={() => actBatch("addVip", selectedPlayers)}
          >
            <Star className="size-3.5" />
            批量加 V
          </Button>
        ) : null}
        {can("ban") ? (
          <Button
            variant="destructive"
            size="sm"
            className="compact-action"
            onClick={() => actBatch("ban", selectedPlayers)}
          >
            <Ban className="size-3.5" />
            批量封禁
          </Button>
        ) : null}
        <Button variant="ghost" size="sm" className="compact-action" onClick={clear}>
          <X className="size-3.5" />
          取消选择
        </Button>
      </div>
    </div>
  );
}
