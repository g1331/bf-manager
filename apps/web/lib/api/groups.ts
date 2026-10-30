/** 群组：成员与角色、邀请链接、群组记录 */
import { api } from "@/lib/api-client";

export type GroupRole = "owner" | "admin" | "moderator" | "viewer";
export type InviteRole = Exclude<GroupRole, "owner">;

export const ROLE_LABEL: Record<GroupRole, string> = {
  owner: "群主",
  admin: "管理员",
  moderator: "协管",
  viewer: "观察员",
};

export const ROLE_HINT: Record<GroupRole, string> = {
  owner: "改群名、删群、设任何人的角色",
  admin: "封禁、加 V、换图；管理协管和观察员",
  moderator: "踢人、换边",
  viewer: "只能查看",
};

export const ROLE_LEVEL: Record<GroupRole, number> = {
  viewer: 1,
  moderator: 2,
  admin: 3,
  owner: 4,
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
