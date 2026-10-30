/**
 * 审计日志 API 客户端
 */
import { api } from "@/lib/api-client";

export interface AuditLogItem {
  id: number;
  user_id: number | null;
  acting_persona_id: number;
  game: string;
  server_id: number | null;
  /** 群组操作（game 为 "group"）记在哪个群 */
  group_id: number | null;
  action: string;
  target_persona_id: number | null;
  payload: Record<string, unknown>;
  result: "success" | "failure" | string;
  error_code: string | null;
  error_message: string | null;
  ip: string | null;
  user_agent: string | null;
  created_at: string;
}

/** 群组操作的审计记录：game 固定为 "group"，不对应某个游戏的服务器或玩家页 */
export const GROUP_AUDIT_GAME = "group";

export const GROUP_ACTION_LABEL: Record<string, string> = {
  group_create: "建群",
  group_rename: "改群名",
  group_delete: "删除群",
  group_member_join: "加入群",
  group_member_role: "调整群角色",
  group_member_remove: "移出群成员",
  group_owner_inherit: "接任群主",
  group_member_account_deleted: "成员注销账号",
  group_leave: "退出群",
  group_invite_create: "发群邀请链接",
  group_invite_revoke: "作废群邀请链接",
};

/** 站点设置的审计记录：game 固定为 "site" */
export const SITE_AUDIT_GAME = "site";

export const SITE_ACTION_LABEL: Record<string, string> = {
  site_registration_mode: "切换注册方式",
  user_freeze: "冻结账号",
  user_unfreeze: "解冻账号",
  account_delete_request: "申请注销",
  account_delete_cancel: "撤销注销",
  account_delete: "删除账号",
};

/** 审计列表“游戏”一列：群组、站点操作不属于某个游戏 */
export function auditGameLabel(game: string): string {
  if (game === GROUP_AUDIT_GAME) return "群组";
  if (game === SITE_AUDIT_GAME) return "站点";
  return game.toUpperCase();
}

export interface AuditLogPage {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ListAuditLogsParams {
  game?: string;
  serverId?: number;
  action?: string;
  page?: number;
  pageSize?: number;
}

export const auditApi = {
  list: (params: ListAuditLogsParams = {}) => {
    const qs = new URLSearchParams();
    if (params.game) qs.set("game", params.game);
    if (params.serverId !== undefined) qs.set("server_id", String(params.serverId));
    if (params.action) qs.set("action", params.action);
    qs.set("page", String(params.page ?? 1));
    qs.set("page_size", String(params.pageSize ?? 20));
    return api.get<AuditLogPage>(`/audit-logs?${qs.toString()}`);
  },
};
