/**
 * 登录态与「我的」页面的读查询：登录态、注册配置、EA 绑定、邀请码、API Key、验证链接。
 * 用法同 bf1Queries：useQuery({ ...accountQueries.session(), staleTime })，失效 / 写缓存用 accountKeys。
 */
import { queryOptions } from "@tanstack/react-query";
import { apiKeysApi } from "@/lib/api/api-keys";
import {
  getAuthConfig,
  getSession,
  listInviteCodes,
  listMyBindings,
  lookupVerification,
} from "@/lib/auth";

export const accountKeys = {
  session: () => ["session"] as const,
  authConfig: () => ["auth-config"] as const,
  eaBindings: () => ["my-ea-bindings"] as const,
  inviteCodes: () => ["invite-codes"] as const,
  apiKeys: () => ["my-api-keys"] as const,
  verification: (token: string | null | undefined) => ["verification", token] as const,
};

export const accountQueries = {
  session: () =>
    queryOptions({
      queryKey: accountKeys.session(),
      queryFn: ({ signal }) => getSession({ signal }),
    }),
  authConfig: () =>
    queryOptions({
      queryKey: accountKeys.authConfig(),
      queryFn: ({ signal }) => getAuthConfig({ signal }),
    }),
  eaBindings: () =>
    queryOptions({
      queryKey: accountKeys.eaBindings(),
      queryFn: ({ signal }) => listMyBindings({ signal }),
    }),
  inviteCodes: () =>
    queryOptions({
      queryKey: accountKeys.inviteCodes(),
      queryFn: ({ signal }) => listInviteCodes({ signal }),
    }),
  apiKeys: () =>
    queryOptions({
      queryKey: accountKeys.apiKeys(),
      queryFn: ({ signal }) => apiKeysApi.listMine({ signal }),
    }),
  /** token 为空时调用方用 enabled 拦住，queryFn 不会执行 */
  verification: (token: string | null | undefined) =>
    queryOptions({
      queryKey: accountKeys.verification(token),
      queryFn: ({ signal }) => lookupVerification(token as string, { signal }),
    }),
};
