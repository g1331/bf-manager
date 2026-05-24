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
