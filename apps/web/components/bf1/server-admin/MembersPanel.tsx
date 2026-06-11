"use client";

/**
 * 服务器详情「成员名单」tab：管理员 / VIP / 封禁三类名单的查看与维护。
 *
 * 子级分类 chips 切换名单；搜索框按玩家名或 persona ID 过滤，搜索词跨分类保留，
 * 便于快速确认某玩家身处哪份名单。有对应权限时显示添加入口（按名字或 persona ID
 * 解析）与行内移除按钮，写操作复用 ServerAdminProvider 的 act（统一二次确认 +
 * 双键缓存失效 + 提示），离线名单维护与在线玩家行内操作走同一条链路。
 */

import { useState } from "react";
import { toast } from "sonner";
import { Plus, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ResponsiveTable, type Column } from "@/components/common/ResponsiveTable";
import { useServerAdmin } from "@/components/bf1/server-admin/InlineServerAdmin";
import { bf1Api, type ServerExtras, type ServerMember } from "@/lib/api/bf1";
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

export function MembersPanel({ extras }: { extras: ServerExtras }) {
  const { can, act } = useServerAdmin();
  const [kind, setKind] = useState<MemberKind>("admins");
  const [search, setSearch] = useState("");
  const [addInput, setAddInput] = useState("");
  const [resolving, setResolving] = useState(false);

  const meta = KIND_META[kind];
  const members = extras[kind];
  const canAdd = can(meta.addKind);
  const canRemove = can(meta.removeKind);

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

  const columns: Column<ServerMember>[] = [
    {
      key: "name",
      header: "玩家",
      cell: (m) => m.display_name ?? "—",
      isCardTitle: true,
    },
    {
      key: "platform",
      header: "平台",
      cell: (m) => (m.platform ? m.platform.toUpperCase() : "—"),
    },
    { key: "id", header: "Persona ID", cell: (m) => m.persona_id },
    ...(canRemove
      ? ([
          {
            key: "actions",
            header: "操作",
            className: "w-24 text-right",
            cell: (m: ServerMember) => (
              <Button
                variant="outline"
                size="sm"
                className="compact-action"
                onClick={() =>
                  act(meta.removeKind, {
                    persona_id: m.persona_id,
                    display_name: m.display_name ?? String(m.persona_id),
                  })
                }
              >
                <X className="size-3.5" />
                {meta.removeLabel}
              </Button>
            ),
          },
        ] satisfies Column<ServerMember>[])
      : []),
  ];

  return (
    <div className="space-y-4">
      {/* 分类 chips：带「当前数 / 容量上限」计数 */}
      <div className="flex flex-wrap gap-1.5">
        {KIND_ORDER.map((k) => (
          <KindChip
            key={k}
            label={`${KIND_META[k].label} ${extras[k].length}/${KIND_META[k].limit}`}
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

      {keyword ? (
        <p className="text-xs text-white/45 tabular-nums">
          匹配 {filtered.length} / {members.length} 人
        </p>
      ) : null}

      <ResponsiveTable
        data={filtered}
        columns={columns}
        rowKey={(m) => m.persona_id}
        emptyState={keyword ? `没有匹配「${search.trim()}」的${meta.label}` : meta.emptyText}
      />
    </div>
  );
}

/** 分类切换 chip，沿用武器 / 载具过滤条的样式语言（白底高亮 + 细描边） */
function KindChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "border px-2.5 py-1 text-xs tracking-wide tabular-nums transition-colors",
        active
          ? "border-white bg-white font-semibold text-black"
          : "border-white/20 text-white/60 hover:border-white/45 hover:text-white",
      )}
    >
      {label}
    </button>
  );
}
