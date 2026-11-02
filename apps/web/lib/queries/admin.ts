/**
 * 平台后台的读查询：概况、EA 号池、服务器授权、用户、API Key、注册设置。
 * adminKeys.memberships() 是授权列表和概况卡片的共同前缀，失效它两处一起刷新。
 */
import { queryOptions } from "@tanstack/react-query";
import { adminApi, type AdminUserFilter } from "@/lib/api/admin";
import { apiKeysApi } from "@/lib/api/api-keys";
import { eaAccountsApi } from "@/lib/api/ea-accounts";
import { membershipsApi } from "@/lib/api/memberships";

export const adminKeys = {
  metrics: () => ["admin-metrics"] as const,
  eaAccounts: () => ["ea-accounts"] as const,
  memberships: () => ["memberships"] as const,
  membershipsOverview: () => ["memberships", "admin-overview"] as const,
  /** 不带参数是全部用户列表页的前缀 */
  users: () => ["admin-users"] as const,
  usersPage: (q: string, only: AdminUserFilter, page: number) =>
    ["admin-users", q, only, page] as const,
  apiKeys: () => ["admin-api-keys"] as const,
  registration: () => ["admin-settings", "registration"] as const,
};

export const adminQueries = {
  metrics: () =>
    queryOptions({
      queryKey: adminKeys.metrics(),
      queryFn: ({ signal }) => adminApi.getMetrics({ signal }),
    }),
  eaAccounts: () =>
    queryOptions({
      queryKey: adminKeys.eaAccounts(),
      queryFn: ({ signal }) => eaAccountsApi.list({ signal }),
    }),
  /** 授权管理页一次拉 200 条 */
  memberships: () =>
    queryOptions({
      queryKey: adminKeys.memberships(),
      queryFn: ({ signal }) => membershipsApi.list({ pageSize: 200 }, { signal }),
    }),
  /** 概况卡片只要总数 */
  membershipsOverview: () =>
    queryOptions({
      queryKey: adminKeys.membershipsOverview(),
      queryFn: ({ signal }) => membershipsApi.list({ pageSize: 1 }, { signal }),
    }),
  usersPage: (q: string, only: AdminUserFilter, page: number, pageSize: number) =>
    queryOptions({
      queryKey: adminKeys.usersPage(q, only, page),
      queryFn: ({ signal }) =>
        adminApi.listUsers({ q: q || undefined, only, page, pageSize }, { signal }),
    }),
  apiKeys: () =>
    queryOptions({
      queryKey: adminKeys.apiKeys(),
      queryFn: ({ signal }) => apiKeysApi.listAll({ signal }),
    }),
  registration: () =>
    queryOptions({
      queryKey: adminKeys.registration(),
      queryFn: ({ signal }) => adminApi.getRegistration({ signal }),
    }),
};
