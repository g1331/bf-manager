"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Ban, Plus, ShieldCheck, Star, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { bf1Api, type ServerDetail, type ServerMember } from "@/lib/api/bf1";
import { ApiException } from "@/lib/api-client";
import { useServerAdmin } from "@/components/bf1/server-admin/InlineServerAdmin";

interface AdminPanelProps {
  detail: ServerDetail;
}

type TargetKind = "ban" | "addVip" | "addAdmin";

/** 解析后的操作目标：persona_id 为后端寻址依据，display_name 仅用于确认文案 */
interface ResolvedTarget {
  persona_id: number;
  display_name: string;
}

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

/**
 * 服管「管理」tab：离线、按名字的名单管理控制台。
 *
 * 在线玩家的踢出 / 封禁 / 加 V / 下 V 已内联到玩家列表每一行，换图已内联到地图轮换，
 * 因此这里只保留无法在列表里就地完成的离线操作：按名字封禁 / 解封、VIP 与管理员名单维护。
 * 所有写操作复用 Provider 的 act（统一二次确认 + 双键缓存失效 + 提示）。
 */
export function AdminPanel({ detail }: AdminPanelProps) {
  const { can, act } = useServerAdmin();
  const { extras } = detail;
  const [banInput, setBanInput] = useState("");
  const [vipInput, setVipInput] = useState("");
  const [adminInput, setAdminInput] = useState("");
  const [resolving, setResolving] = useState(false);

  const submit = async (kind: TargetKind, raw: string, clear: () => void) => {
    if (resolving) return;
    setResolving(true);
    try {
      const target = await resolveTarget(raw);
      if (!target) {
        toast.error("未找到该玩家，请检查名字或改用 persona ID");
        return;
      }
      act(kind, target);
      clear();
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : "查询玩家失败，请稍后重试");
    } finally {
      setResolving(false);
    }
  };

  const toRef = (m: ServerMember): ResolvedTarget => ({
    persona_id: m.persona_id,
    display_name: m.display_name ?? String(m.persona_id),
  });

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">
        在线玩家的踢出 / 封禁 / 加 V / 下 V 请在「玩家列表」里就地操作，换图请在「地图轮换」里操作。
        此处用于离线、按名字维护封禁与名单。
      </p>

      {can("ban") ? (
        <MemberManageCard
          title="封禁名单"
          icon={Ban}
          hint="按名字或 ID 封禁"
          members={extras.banned}
          inputValue={banInput}
          onInputChange={setBanInput}
          onAdd={() => submit("ban", banInput, () => setBanInput(""))}
          onRemove={(m) => act("unban", toRef(m))}
          addLabel="封禁"
          removeLabel="解封"
          emptyText="暂无封禁记录"
          adding={resolving}
        />
      ) : null}

      {can("addVip") ? (
        <MemberManageCard
          title="VIP 名单"
          icon={Star}
          hint="/ 50"
          members={extras.vips}
          inputValue={vipInput}
          onInputChange={setVipInput}
          onAdd={() => submit("addVip", vipInput, () => setVipInput(""))}
          onRemove={(m) => act("removeVip", toRef(m))}
          addLabel="添加 VIP"
          removeLabel="移除"
          emptyText="暂无 VIP"
          adding={resolving}
        />
      ) : null}

      {can("addAdmin") ? (
        <MemberManageCard
          title="管理员名单"
          icon={ShieldCheck}
          hint="/ 50 · 仅服主可增减"
          members={extras.admins}
          inputValue={adminInput}
          onInputChange={setAdminInput}
          onAdd={() => submit("addAdmin", adminInput, () => setAdminInput(""))}
          onRemove={(m) => act("removeAdmin", toRef(m))}
          addLabel="添加管理员"
          removeLabel="移除"
          emptyText="暂无管理员"
          adding={resolving}
        />
      ) : null}
    </div>
  );
}

function MemberManageCard({
  title,
  icon: Icon,
  hint,
  members,
  inputValue,
  onInputChange,
  onAdd,
  onRemove,
  addLabel,
  removeLabel,
  emptyText,
  adding,
}: {
  title: string;
  icon: React.ElementType;
  hint: string;
  members: ServerMember[];
  inputValue: string;
  onInputChange: (v: string) => void;
  onAdd: () => void;
  onRemove: (m: ServerMember) => void;
  addLabel: string;
  removeLabel: string;
  emptyText: string;
  adding: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="size-4" />
          {title}
          <span className="text-muted-foreground text-xs font-normal tabular-nums">
            {members.length} {hint}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            placeholder="输入玩家名或 persona ID"
            disabled={adding}
            onKeyDown={(e) => {
              if (e.key === "Enter") onAdd();
            }}
          />
          <Button variant="outline" className="shrink-0" onClick={onAdd} disabled={adding}>
            <Plus className="size-4" />
            {adding ? "查询中…" : addLabel}
          </Button>
        </div>
        {members.length === 0 ? (
          <p className="text-muted-foreground text-sm">{emptyText}</p>
        ) : (
          <ul className="divide-y">
            {members.map((m) => (
              <li key={m.persona_id} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{m.display_name ?? "—"}</div>
                  <div className="text-muted-foreground text-xs tabular-nums">
                    ID {m.persona_id}
                    {m.platform ? ` · ${m.platform.toUpperCase()}` : ""}
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="compact-action shrink-0"
                  onClick={() => onRemove(m)}
                >
                  <X className="size-3.5" />
                  {removeLabel}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
