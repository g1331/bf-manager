"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { UserX, Ban, MapPin, Plus, ShieldCheck, Star, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmSheet } from "@/components/common/ConfirmSheet";
import { bf1Api, type ServerDetail, type ServerMember, type ServerPlayer } from "@/lib/api/bf1";
import { ApiException } from "@/lib/api-client";

interface AdminPanelProps {
  gameId: number;
  detail: ServerDetail;
}

type PendingAction =
  | { type: "kick"; player: ServerPlayer }
  | { type: "ban"; player: ServerPlayer }
  | { type: "level"; index: number; mapName: string | null }
  | { type: "addVip"; personaId: number }
  | { type: "removeVip"; member: ServerMember }
  | { type: "addAdmin"; personaId: number }
  | { type: "removeAdmin"; member: ServerMember }
  | null;

export function AdminPanel({ gameId, detail }: AdminPanelProps) {
  const qc = useQueryClient();
  const [pending, setPending] = useState<PendingAction>(null);
  const [reason, setReason] = useState("violation of rules");
  const [vipInput, setVipInput] = useState("");
  const [adminInput, setAdminInput] = useState("");
  const [loading, setLoading] = useState(false);

  const close = () => {
    setPending(null);
    setReason("violation of rules");
  };

  const execute = async () => {
    if (!pending) return;
    setLoading(true);
    try {
      if (pending.type === "kick") {
        const res = await bf1Api.adminKick(gameId, pending.player.persona_id, reason);
        toast.success(res.message ?? "已踢出");
      } else if (pending.type === "ban") {
        const res = await bf1Api.adminBan(gameId, pending.player.persona_id);
        toast.success(res.message ?? "已封禁");
      } else if (pending.type === "level") {
        const persisted = detail.summary.persisted_game_id;
        if (!persisted) {
          toast.error("缺少 persisted_game_id，无法换图");
          return;
        }
        const res = await bf1Api.adminChooseLevel(gameId, persisted, pending.index);
        toast.success(res.message ?? "已切换地图");
      } else if (pending.type === "addVip") {
        const res = await bf1Api.adminAddVip(gameId, pending.personaId);
        toast.success(res.message ?? "已添加 VIP");
        setVipInput("");
      } else if (pending.type === "removeVip") {
        const res = await bf1Api.adminRemoveVip(gameId, pending.member.persona_id);
        toast.success(res.message ?? "已移除 VIP");
      } else if (pending.type === "addAdmin") {
        const res = await bf1Api.adminAddAdmin(gameId, pending.personaId);
        toast.success(res.message ?? "已添加管理员");
        setAdminInput("");
      } else if (pending.type === "removeAdmin") {
        const res = await bf1Api.adminRemoveAdmin(gameId, pending.member.persona_id);
        toast.success(res.message ?? "已移除管理员");
      }
      qc.invalidateQueries({ queryKey: ["bf1-server", gameId] });
      close();
    } catch (err) {
      const msg = err instanceof ApiException ? err.message : "操作失败，请稍后重试";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const submitAdd = (kind: "vip" | "admin") => {
    const raw = kind === "vip" ? vipInput : adminInput;
    const personaId = Number(raw.trim());
    if (!Number.isInteger(personaId) || personaId <= 0) {
      toast.error("请输入合法的 persona ID");
      return;
    }
    setPending(kind === "vip" ? { type: "addVip", personaId } : { type: "addAdmin", personaId });
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">玩家管理</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {detail.players.length === 0 ? (
            <p className="text-muted-foreground text-sm">当前无在线玩家</p>
          ) : (
            <ul className="divide-y">
              {detail.players.map((p) => (
                <li key={p.persona_id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{p.display_name}</div>
                    <div className="text-muted-foreground text-xs">
                      {p.is_spectator ? "旁观" : `T${p.team_id ?? "?"}`} · LV{p.rank ?? "—"}
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button
                      variant="outline"
                      size="sm"
                      className="compact-action"
                      onClick={() => setPending({ type: "kick", player: p })}
                    >
                      <UserX className="size-3.5" />
                      踢出
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      className="compact-action"
                      onClick={() => setPending({ type: "ban", player: p })}
                    >
                      <Ban className="size-3.5" />
                      封禁
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">切换地图</CardTitle>
        </CardHeader>
        <CardContent>
          {detail.map_rotation.length === 0 ? (
            <p className="text-muted-foreground text-sm">暂无地图轮换</p>
          ) : (
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {detail.map_rotation.map((m, i) => (
                <li
                  key={`${m.map_name}-${i}`}
                  className="flex items-center justify-between rounded-md border p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{m.map_name ?? "未知"}</div>
                    <div className="text-muted-foreground text-xs">{m.game_mode ?? ""}</div>
                  </div>
                  <Button
                    variant={m.is_current ? "secondary" : "outline"}
                    size="sm"
                    disabled={m.is_current}
                    className="compact-action"
                    onClick={() => setPending({ type: "level", index: i, mapName: m.map_name })}
                  >
                    <MapPin className="size-3.5" />
                    {m.is_current ? "当前" : "切换"}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <MemberManageCard
        title="VIP 名单"
        icon={Star}
        hint="/ 50"
        members={detail.extras.vips}
        inputValue={vipInput}
        onInputChange={setVipInput}
        onAdd={() => submitAdd("vip")}
        onRemove={(m) => setPending({ type: "removeVip", member: m })}
        addLabel="添加 VIP"
        emptyText="暂无 VIP"
      />

      <MemberManageCard
        title="管理员名单"
        icon={ShieldCheck}
        hint="/ 50 · 仅服主可增减"
        members={detail.extras.admins}
        inputValue={adminInput}
        onInputChange={setAdminInput}
        onAdd={() => submitAdd("admin")}
        onRemove={(m) => setPending({ type: "removeAdmin", member: m })}
        addLabel="添加管理员"
        emptyText="暂无管理员"
      />

      <ConfirmSheet
        open={pending !== null}
        onOpenChange={(open) => !open && close()}
        title={
          pending?.type === "kick"
            ? `踢出玩家 ${pending.player.display_name}？`
            : pending?.type === "ban"
              ? `封禁玩家 ${pending.player.display_name}？`
              : pending?.type === "level"
                ? `切换到 ${pending.mapName ?? "此地图"}？`
                : pending?.type === "addVip"
                  ? `添加 VIP #${pending.personaId}？`
                  : pending?.type === "removeVip"
                    ? `移除 VIP ${pending.member.display_name ?? pending.member.persona_id}？`
                    : pending?.type === "addAdmin"
                      ? `添加管理员 #${pending.personaId}？`
                      : pending?.type === "removeAdmin"
                        ? `移除管理员 ${pending.member.display_name ?? pending.member.persona_id}？`
                        : "确认操作"
        }
        description={
          pending?.type === "ban"
            ? "封禁后该玩家无法再次加入服务器，可在 EA 平台或管理员控制台解除"
            : pending?.type === "level"
              ? "切换地图会立即结束当前对局，所有玩家会被移到新地图"
              : pending?.type === "addAdmin"
                ? "管理员可对本服执行踢人、封禁等操作，请确认对方身份"
                : undefined
        }
        confirmText="确认"
        cancelText="取消"
        variant={pending?.type === "ban" ? "destructive" : "default"}
        loading={loading}
        onConfirm={execute}
      >
        {pending?.type === "kick" ? (
          <div className="space-y-2 py-2">
            <Label htmlFor="kick-reason">踢出理由</Label>
            <Input
              id="kick-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={128}
              placeholder="向被踢玩家显示的理由"
            />
          </div>
        ) : null}
      </ConfirmSheet>
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
  emptyText,
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
  emptyText: string;
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
            inputMode="numeric"
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            placeholder="按 persona ID 添加"
            onKeyDown={(e) => {
              if (e.key === "Enter") onAdd();
            }}
          />
          <Button variant="outline" className="shrink-0" onClick={onAdd}>
            <Plus className="size-4" />
            {addLabel}
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
                  移除
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
