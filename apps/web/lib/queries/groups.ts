/**
 * 群组的读查询。groupKeys.all() 是「我的群列表」，也是在玩状态的前缀：
 * 失效 all() 会连同 presence 一起刷新，和原先的 ["groups"] 前缀匹配一致。
 */
import { queryOptions } from "@tanstack/react-query";
import { groupsApi } from "@/lib/api/groups";

export const groupKeys = {
  all: () => ["groups"] as const,
  presence: () => ["groups", "presence"] as const,
  detail: (groupId: number) => ["group", groupId] as const,
  invites: (groupId: number) => ["group-invites", groupId] as const,
  /** 不带页码是这个群全部审计页的前缀 */
  audit: (groupId: number) => ["group-audit", groupId] as const,
  auditPage: (groupId: number, page: number) => ["group-audit", groupId, page] as const,
  accounts: (groupId: number) => ["group-accounts", groupId] as const,
  servers: (groupId: number) => ["group-servers", groupId] as const,
  invite: (token: string | null | undefined) => ["group-invite", token] as const,
};

export const groupQueries = {
  list: () =>
    queryOptions({
      queryKey: groupKeys.all(),
      queryFn: ({ signal }) => groupsApi.list({ signal }),
    }),
  presence: () =>
    queryOptions({
      queryKey: groupKeys.presence(),
      queryFn: ({ signal }) => groupsApi.presence({ signal }),
    }),
  detail: (groupId: number) =>
    queryOptions({
      queryKey: groupKeys.detail(groupId),
      queryFn: ({ signal }) => groupsApi.get(groupId, { signal }),
    }),
  invites: (groupId: number) =>
    queryOptions({
      queryKey: groupKeys.invites(groupId),
      queryFn: ({ signal }) => groupsApi.invites(groupId, { signal }),
    }),
  auditPage: (groupId: number, page: number) =>
    queryOptions({
      queryKey: groupKeys.auditPage(groupId, page),
      queryFn: ({ signal }) => groupsApi.audit(groupId, page, { signal }),
    }),
  accounts: (groupId: number) =>
    queryOptions({
      queryKey: groupKeys.accounts(groupId),
      queryFn: ({ signal }) => groupsApi.accounts(groupId, { signal }),
    }),
  servers: (groupId: number) =>
    queryOptions({
      queryKey: groupKeys.servers(groupId),
      queryFn: ({ signal }) => groupsApi.servers(groupId, { signal }),
    }),
  /** 邀请链接预览；token 为空时调用方用 enabled 拦住 */
  invite: (token: string | null | undefined) =>
    queryOptions({
      queryKey: groupKeys.invite(token),
      queryFn: ({ signal }) => groupsApi.lookupInvite(token as string, { signal }),
    }),
};
