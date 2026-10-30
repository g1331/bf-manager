/** 群组：成员与角色、邀请链接、服务账号与绑服、群组记录 */
import { api } from "@/lib/api-client";

/** 群主 / 管理员两级，和 tenko v3 的服主 / 管理员一致 */
export type GroupRole = "owner" | "admin";
/** 邀请链接只能由群主发，进群后是管理员 */
export type InviteRole = Exclude<GroupRole, "owner">;

export const ROLE_LABEL: Record<GroupRole, string> = {
  owner: "群主",
  admin: "管理员",
};

export const ROLE_HINT: Record<GroupRole, string> = {
  owner: "添加服务账号、挂服务器、发邀请链接、管理成员",
  admin: "群绑定的服务器上能踢人、换边、封禁、加 V、换图",
};

export interface GroupSummary {
  id: number;
  name: string;
  my_role: GroupRole;
  member_count: number;
  created_at: string;
}

export interface GroupList {
  items: GroupSummary[];
  /** 还能建几个；平台管理员不限，为 null */
  create_left: number | null;
}

export interface GroupMember {
  user_id: number;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  persona_id: number | null;
  role: GroupRole;
  /** 还没绑 EA：在群里没有权限 */
  pending_binding: boolean;
  joined_at: string;
  is_me: boolean;
}

export interface GroupDetail {
  id: number;
  name: string;
  created_at: string;
  my_role: GroupRole;
  members: GroupMember[];
}

export interface GroupInvite {
  id: number;
  role: InviteRole;
  max_uses: number;
  uses: number;
  expires_at: string;
  created_at: string;
  created_by_name: string | null;
}

export interface InviteCreated {
  invite: GroupInvite;
  /** 明文 token，只在创建时返回这一次 */
  token: string;
}

export interface InviteLookup {
  group_name: string;
  role: InviteRole;
  member_count: number;
  inviter_name: string | null;
  expires_at: string;
  uses_left: number;
  /** 能不能拿这个链接注册新账号 */
  can_register: boolean;
}

export interface InviteAccepted {
  group_id: number;
  role: GroupRole;
  already_member: boolean;
}

export interface GroupAuditItem {
  id: number;
  action: string;
  actor_name: string | null;
  target_name: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface GroupAuditPage {
  items: GroupAuditItem[];
  total: number;
  page: number;
  page_size: number;
}

export type GroupAccountStatus = "ok" | "invalid";

/** 群组服务账号：群里绑定的服用它执行服管操作 */
export interface GroupAccount {
  id: number;
  persona_id: number;
  display_name: string | null;
  is_default: boolean;
  /** invalid：连续登录失败，要重新提交凭据 */
  status: GroupAccountStatus;
  last_error: string | null;
  last_verified_at: string | null;
  created_at: string;
}

export interface GroupServer {
  id: number;
  server_id: number;
  /** 末次见到的 gameId，用来跳到服务器页 */
  game_id: number | null;
  name: string | null;
  bound_by_name: string | null;
  bound_via: "owner" | "admin";
  executor: {
    id: number;
    persona_id: number;
    display_name: string | null;
    status: GroupAccountStatus;
  } | null;
  /** revoked：绑定人已不是服主或管理员，群成员在这台服上的权限失效 */
  status: "active" | "revoked";
  status_reason: string | null;
  /** 执行账号的问题：不影响权限，但服管操作会失败 */
  executor_problem: string | null;
  last_verified_at: string | null;
  created_at: string;
}

/** 服主视图：挂着这台服的群 */
export interface ServerGroup {
  group_id: number;
  group_name: string;
  bound_by_name: string | null;
  bound_via: "owner" | "admin";
  status: "active" | "revoked";
  created_at: string;
}

/** 成员在服里的位置：两队、排队、观战 */
export type PresenceSlot = "team1" | "team2" | "queue" | "spectator";

/** 成员所在的服；服务器摘要缓存里没有这台服时只有 game_id 和 slot */
export interface MemberServer {
  game_id: number;
  slot: PresenceSlot;
  name: string | null;
  map_display_name: string | null;
  mode_display_name: string | null;
  player_count: number | null;
  max_player_count: number | null;
}

export interface PresenceMember {
  user_id: number;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  persona_id: number | null;
  role: GroupRole;
  /** 不在任何有人的服里：可能离线，也可能停在主菜单 */
  server: MemberServer | null;
}

export interface GroupPresence {
  /** 最近一轮全服快照的时间；null 表示状态暂不可用 */
  updated_at: string | null;
  groups: { id: number; name: string; members: PresenceMember[] }[];
}

export function accountLabel(a: { display_name: string | null; persona_id: number }): string {
  return a.display_name ?? String(a.persona_id);
}

/** 邀请链接有效期可选值（小时） */
export const INVITE_TTL_OPTIONS = [
  { hours: 1, label: "1 小时" },
  { hours: 24, label: "1 天" },
  { hours: 72, label: "3 天" },
  { hours: 168, label: "7 天" },
] as const;

export const INVITE_MAX_USES = 10;

export function inviteUrl(token: string): string {
  return `${window.location.origin}/invite#token=${token}`;
}

export const groupsApi = {
  list: () => api.get<GroupList>("/groups"),
  /** 我所在各群的其他成员此刻在哪个服（不含自己），右侧好友栏用 */
  presence: () => api.get<GroupPresence>("/groups/presence"),
  create: (name: string) => api.post<GroupDetail>("/groups", { name }),
  get: (id: number) => api.get<GroupDetail>(`/groups/${id}`),
  rename: (id: number, name: string) => api.patch<GroupDetail>(`/groups/${id}`, { name }),
  remove: (id: number) => api.delete<void>(`/groups/${id}`),
  leave: (id: number) => api.post<void>(`/groups/${id}/leave`),
  setRole: (id: number, userId: number, role: GroupRole) =>
    api.patch<GroupDetail>(`/groups/${id}/members/${userId}`, { role }),
  removeMember: (id: number, userId: number) =>
    api.delete<GroupDetail>(`/groups/${id}/members/${userId}`),
  invites: (id: number) => api.get<{ items: GroupInvite[] }>(`/groups/${id}/invites`),
  createInvite: (id: number, body: { role: InviteRole; max_uses: number; ttl_hours: number }) =>
    api.post<InviteCreated>(`/groups/${id}/invites`, body),
  revokeInvite: (id: number, inviteId: number) =>
    api.post<void>(`/groups/${id}/invites/${inviteId}/revoke`),
  audit: (id: number, page: number) =>
    api.get<GroupAuditPage>(`/groups/${id}/audit?page=${page}&page_size=15`),
  accounts: (id: number) => api.get<{ items: GroupAccount[] }>(`/groups/${id}/accounts`),
  addAccountWithCookie: (id: number, body: { remid: string; sid: string }) =>
    api.post<GroupAccount>(`/groups/${id}/accounts/cookie`, body),
  setDefaultAccount: (id: number, accountId: number) =>
    api.post<void>(`/groups/${id}/accounts/${accountId}/default`),
  removeAccount: (id: number, accountId: number) =>
    api.delete<void>(`/groups/${id}/accounts/${accountId}`),
  servers: (id: number) => api.get<{ items: GroupServer[] }>(`/groups/${id}/servers`),
  bindServer: (id: number, body: { game_id: number; account_id?: number }) =>
    api.post<GroupServer>(`/groups/${id}/servers`, body),
  setExecutor: (id: number, bindingId: number, accountId: number) =>
    api.put<GroupServer>(`/groups/${id}/servers/${bindingId}/executor`, {
      account_id: accountId,
    }),
  unbindServer: (id: number, bindingId: number) =>
    api.delete<void>(`/groups/${id}/servers/${bindingId}`),
  recheckServers: (id: number) =>
    api.post<{ items: GroupServer[] }>(`/groups/${id}/servers/recheck`),
  /** 服主视图（BF1）：挂着这台服的群 */
  serverGroups: (gameId: number) =>
    api.get<{ items: ServerGroup[] }>(`/bf1/server-admin/${gameId}/groups`),
  removeServerFromGroup: (gameId: number, groupId: number) =>
    api.delete<void>(`/bf1/server-admin/${gameId}/groups/${groupId}`),
  lookupInvite: (token: string) => api.post<InviteLookup>("/group-invites/lookup", { token }),
  acceptInvite: (token: string) => api.post<InviteAccepted>("/group-invites/accept", { token }),
};

/**
 * 打开邀请链接后要先登录或注册的，token 暂存在当前标签页，回来后接着用。
 * 注册页据此改用群邀请当注册资格。
 */
const PENDING_KEY = "bfm-group-invite";

export interface PendingInvite {
  token: string;
  groupName: string;
}

export function savePendingInvite(invite: PendingInvite): void {
  sessionStorage.setItem(PENDING_KEY, JSON.stringify(invite));
}

export function readPendingInvite(): PendingInvite | null {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY);
    return raw ? (JSON.parse(raw) as PendingInvite) : null;
  } catch {
    return null;
  }
}

export function clearPendingInvite(): void {
  sessionStorage.removeItem(PENDING_KEY);
}
