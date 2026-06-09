"use client";

import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { bf1Api, type MyServerRole } from "@/lib/api/bf1";
import { ApiException } from "@/lib/api-client";

/**
 * 单条服管操作请求。label 为人类可读名称（玩家名 / 地图名），仅用于聚合提示文案。
 * persona_id 为后端实际寻址依据，名字仅是展示与解析入口。
 */
export type AdminActionRequest =
  | { action: "kick"; personaId: number; reason: string; label: string }
  | { action: "move"; personaId: number; teamId: number; label: string }
  | { action: "ban"; personaId: number; label: string }
  | { action: "unban"; personaId: number; label: string }
  | { action: "addVip"; personaId: number; label: string }
  | { action: "removeVip"; personaId: number; label: string }
  | { action: "addAdmin"; personaId: number; label: string }
  | { action: "removeAdmin"; personaId: number; label: string }
  | { action: "chooseLevel"; levelIndex: number; label: string };

interface BatchOutcome {
  ok: number;
  failed: { label: string; message: string }[];
}

function describeError(err: unknown): string {
  return err instanceof ApiException ? err.message : "操作失败，请稍后重试";
}

/**
 * 内联服管操作的共享执行器。集中处理：
 * - 按 action 分发到对应的 bf1Api 方法；
 * - 成功 / 失败的 toast 提示；
 * - 双键缓存失效（服务器详情 ["bf1-server"] 与实时名单 ["bf1-server-players"]），
 *   两者都可能因踢人 / 封禁 / 改名单而变化，缺一会导致 UI 与服务器实际状态不一致。
 */
export function useServerAdminActions(gameId: number) {
  const qc = useQueryClient();
  const [loading, setLoading] = useState(false);

  const invalidate = useCallback(() => {
    qc.invalidateQueries({ queryKey: ["bf1-server", gameId] });
    qc.invalidateQueries({ queryKey: ["bf1-server-players", gameId] });
  }, [qc, gameId]);

  const callApi = useCallback(
    (req: AdminActionRequest) => {
      switch (req.action) {
        case "kick":
          return bf1Api.adminKick(gameId, req.personaId, req.reason);
        case "move":
          return bf1Api.adminMove(gameId, req.personaId, req.teamId);
        case "ban":
          return bf1Api.adminBan(gameId, req.personaId);
        case "unban":
          return bf1Api.adminUnban(gameId, req.personaId);
        case "addVip":
          return bf1Api.adminAddVip(gameId, req.personaId);
        case "removeVip":
          return bf1Api.adminRemoveVip(gameId, req.personaId);
        case "addAdmin":
          return bf1Api.adminAddAdmin(gameId, req.personaId);
        case "removeAdmin":
          return bf1Api.adminRemoveAdmin(gameId, req.personaId);
        case "chooseLevel":
          return bf1Api.adminChooseLevel(gameId, req.levelIndex);
      }
    },
    [gameId],
  );

  /** 单条操作：执行 + 单次 toast + 失效，返回是否成功。 */
  const runSingle = useCallback(
    async (req: AdminActionRequest): Promise<boolean> => {
      setLoading(true);
      try {
        const res = await callApi(req);
        toast.success(res.message ?? "操作成功");
        invalidate();
        return true;
      } catch (err) {
        toast.error(describeError(err));
        return false;
      } finally {
        setLoading(false);
      }
    },
    [callApi, invalidate],
  );

  /** 批量操作：逐条执行，聚合为单次 toast + 单次失效，避免刷屏与重复请求。 */
  const runBatch = useCallback(
    async (reqs: AdminActionRequest[]): Promise<BatchOutcome> => {
      setLoading(true);
      const failed: { label: string; message: string }[] = [];
      let ok = 0;
      try {
        for (const req of reqs) {
          try {
            await callApi(req);
            ok += 1;
          } catch (err) {
            failed.push({ label: req.label, message: describeError(err) });
          }
        }
      } finally {
        invalidate();
        setLoading(false);
      }
      if (failed.length === 0) {
        toast.success(`已对 ${ok} 名玩家执行操作`);
      } else if (ok === 0) {
        toast.error(`全部 ${failed.length} 项失败：${failed[0].message}`);
      } else {
        toast.warning(`成功 ${ok} 项，失败 ${failed.length} 项`);
      }
      return { ok, failed };
    },
    [callApi, invalidate],
  );

  return { loading, runSingle, runBatch, invalidate };
}

/**
 * 查询当前登录用户对该服务器的角色，用于 gating 内联服管入口。
 * enabled 由调用方控制（仅登录态才查），未登录或无权限时返回的 role 为空。
 */
export function useMyServerRole(gameId: number, enabled: boolean) {
  return useQuery<MyServerRole>({
    queryKey: ["bf1-my-server-role", gameId],
    queryFn: () => bf1Api.getMyServerRole(gameId),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}
