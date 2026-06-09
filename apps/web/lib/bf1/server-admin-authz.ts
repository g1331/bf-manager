/**
 * 内联服管操作的前端权限判断。
 *
 * 角色等级与最低角色要求必须与后端保持一致：
 * - 等级映射对应 `authz_service.ROLE_LEVEL`；
 * - 每个操作的最低角色对应各服管端点 `require_role(min_role=...)`。
 * 前端判断仅用于 gating UI（决定是否渲染入口、是否禁用按钮），真正的鉴权仍以后端为准。
 */
import type { MyServerRole } from "@/lib/api/bf1";
import type { MembershipRole } from "@/lib/api/memberships";

/** 内联服管的操作种类，与后端服管端点一一对应 */
export type ServerAdminAction =
  | "kick"
  | "move"
  | "ban"
  | "unban"
  | "addVip"
  | "removeVip"
  | "addAdmin"
  | "removeAdmin"
  | "chooseLevel";

const ROLE_LEVEL: Record<MembershipRole, number> = {
  viewer: 1,
  moderator: 2,
  admin: 3,
  owner: 4,
};

/** 每个操作所需的最低角色，与后端各端点的 require_role(min_role) 对齐 */
export const SERVER_ADMIN_ACTION_MIN_ROLE: Record<ServerAdminAction, MembershipRole> = {
  kick: "moderator",
  move: "moderator",
  ban: "admin",
  unban: "admin",
  addVip: "admin",
  removeVip: "admin",
  addAdmin: "owner",
  removeAdmin: "owner",
  chooseLevel: "admin",
};

/** 判断当前角色能否执行某操作。平台 admin 放开全部。 */
export function canDo(action: ServerAdminAction, role: MyServerRole | null | undefined): boolean {
  if (!role) return false;
  if (role.is_platform_admin) return true;
  if (!role.role) return false;
  return ROLE_LEVEL[role.role] >= ROLE_LEVEL[SERVER_ADMIN_ACTION_MIN_ROLE[action]];
}

/**
 * 是否拥有任意服管权限，用于决定是否渲染服管入口（⋯ 菜单、批量栏、换图按钮）。
 * 最低可执行操作是踢人（moderator），因此等价于 canDo("kick")。
 */
export function hasAnyServerAdmin(role: MyServerRole | null | undefined): boolean {
  return canDo("kick", role);
}
