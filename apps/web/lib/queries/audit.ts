/**
 * 操作记录（audit-logs）的读查询。三个视图共用 auditKeys.all() 前缀，写操作后失效它就能一起刷新。
 */
import { queryOptions } from "@tanstack/react-query";
import { auditApi } from "@/lib/api/audit";

/** 后台操作记录页的筛选框原值；空串表示不限 */
export interface AuditFilters {
  game?: string;
  serverId?: string;
  action?: string;
}

export const auditKeys = {
  all: () => ["audit-logs"] as const,
  mine: (page: number) => ["audit-logs", "me", page] as const,
  server: (gameId: number, page: number) => ["audit-logs", "server", gameId, page] as const,
  admin: (filters: AuditFilters, page: number) => ["audit-logs", "admin", filters, page] as const,
};

export const auditQueries = {
  /** 「我的」页：自己的操作，每页 10 条 */
  mine: (page: number) =>
    queryOptions({
      queryKey: auditKeys.mine(page),
      queryFn: ({ signal }) => auditApi.list({ page, pageSize: 10 }, { signal }),
    }),
  /** 服务器页：这台服上的操作，每页 20 条 */
  server: (gameId: number, page: number) =>
    queryOptions({
      queryKey: auditKeys.server(gameId, page),
      queryFn: ({ signal }) => auditApi.list({ serverId: gameId, page, pageSize: 20 }, { signal }),
    }),
  admin: (filters: AuditFilters, page: number) =>
    queryOptions({
      queryKey: auditKeys.admin(filters, page),
      queryFn: ({ signal }) =>
        auditApi.list(
          {
            game: filters.game || undefined,
            serverId: filters.serverId ? Number(filters.serverId) : undefined,
            action: filters.action || undefined,
            page,
            pageSize: 20,
          },
          { signal },
        ),
    }),
};
