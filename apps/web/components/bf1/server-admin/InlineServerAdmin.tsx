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
import {
  Ban,
  Check,
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
import type { BlazePlayer, MyServerRole } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";

/** 玩家的最小寻址信息：persona_id 为后端实际依据，名字用于展示与确认文案 */
type PlayerRef = Pick<BlazePlayer, "persona_id" | "display_name">;

/** 单人操作种类（与菜单项 / 名单管理项对应） */
type SingleKind = "kick" | "ban" | "unban" | "addVip" | "removeVip" | "addAdmin" | "removeAdmin";
/** 批量操作种类（仅高频的踢 / 封支持批量） */
type BatchKind = "kick" | "ban";

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
  chooseLevel: (levelIndex: number, mapName: string) => void;
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
  | { mode: "level"; levelIndex: number; mapName: string }
  | null;

const DEFAULT_REASON = "violation of rules";

function buildRequest(kind: SingleKind, player: PlayerRef, reason: string): AdminActionRequest {
  const label = player.display_name;
  switch (kind) {
    case "kick":
      return { action: "kick", personaId: player.persona_id, reason, label };
    case "ban":
      return { action: "ban", personaId: player.persona_id, label };
    case "unban":
      return { action: "unban", personaId: player.persona_id, label };
    case "addVip":
      return { action: "addVip", personaId: player.persona_id, label };
    case "removeVip":
      return { action: "removeVip", personaId: player.persona_id, label };
    case "addAdmin":
      return { action: "addAdmin", personaId: player.persona_id, label };
    case "removeAdmin":
      return { action: "removeAdmin", personaId: player.persona_id, label };
  }
}

const SINGLE_VERB: Record<SingleKind, string> = {
  kick: "踢出",
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
    setPending({ mode: "single", kind, player });
  }, []);
  const actBatch = useCallback((kind: BatchKind, players: PlayerRef[]) => {
    if (players.length === 0) return;
    setReason(DEFAULT_REASON);
    setPending({ mode: "batch", kind, players });
  }, []);
  const chooseLevel = useCallback((levelIndex: number, mapName: string) => {
    setPending({ mode: "level", levelIndex, mapName });
  }, []);

  const close = useCallback(() => setPending(null), []);

  const execute = useCallback(async () => {
    if (!pending) return;
    if (pending.mode === "single") {
      const ok = await runSingle(buildRequest(pending.kind, pending.player, reason));
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
    const reqs = pending.players.map((p) => buildRequest(pending.kind, p, reason));
    await runBatch(reqs);
    clear();
    close();
  }, [pending, reason, runSingle, runBatch, clear, close]);

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

  const isKick = pending?.mode !== "level" && pending?.kind === "kick";
  const isBan = pending?.mode !== "level" && pending?.kind === "ban";
  const confirmTitle = !pending
    ? ""
    : pending.mode === "single"
      ? `${SINGLE_VERB[pending.kind]} ${pending.player.display_name}？`
      : pending.mode === "batch"
        ? `${SINGLE_VERB[pending.kind]}选中的 ${pending.players.length} 名玩家？`
        : `切换到 ${pending.mapName}？`;
  // batch 分支须先于 isBan 判断：批量封禁时 isBan 同样为真，若不前置会错误显示单人文案。
  const confirmDescription = !pending
    ? undefined
    : pending.mode === "level"
      ? "切换地图会立即结束当前对局，所有玩家会被移到新地图"
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
        variant={isBan ? "destructive" : "default"}
        loading={loading}
        onConfirm={execute}
      >
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
        "flex size-4 shrink-0 cursor-pointer items-center justify-center rounded-[3px] border transition-colors",
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

/** 玩家行 ⋯ 操作菜单，按角色与玩家当前状态（是否已 VIP / 管理）决定菜单项 */
export function PlayerActionMenu({ player }: { player: BlazePlayer }) {
  const { act, can } = useServerAdmin();
  const ref: PlayerRef = { persona_id: player.persona_id, display_name: player.display_name };

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
          className="inline-flex size-6 items-center justify-center rounded-sm text-white/45 transition-colors hover:bg-white/10 hover:text-white/90"
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

/** 多选批量操作栏：选中玩家后浮现，支持批量踢 / 封 */
export function BatchActionBar({ players }: { players: BlazePlayer[] }) {
  const { canManage, can, selectedCount, clear, actBatch, isSelected } = useServerAdmin();
  if (!canManage || selectedCount === 0) return null;

  const selectedPlayers = players.filter((p) => isSelected(p.persona_id));
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2 rounded-sm border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-sm">
      <span className="font-medium text-amber-100">已选 {selectedCount} 名玩家</span>
      <div className="ml-auto flex items-center gap-2">
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
