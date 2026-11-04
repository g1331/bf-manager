/** 服管权限授予 API（仅平台 admin 可访问） */
import { api, type RequestOpts } from "@/lib/api-client";

/** 服管权限：管理员能做全部服管操作，服主另可增删游戏内管理员、管这台服挂的群 */
export type MembershipRole = "admin" | "owner";

export interface MembershipItem {
  id: number;
  user_id: number;
  user_username: string;
  // 本地 admin（无 EA 绑定）被授予服管时，下面两个字段为 null
  user_persona_id: number | null;
  user_display_name: string | null;
  server_pk: number;
  game: string;
  server_id: number;
  server_name: string | null;
  role: MembershipRole;
  granted_by: number | null;
  granted_at: string;
}

export interface MembershipPage {
  items: MembershipItem[];
  total: number;
}

export interface MembershipUpsertRequest {
  target_persona_id: number;
  game: string;
  server_id: number;
  role: MembershipRole;
}

export const membershipsApi = {
  list: (params?: { game?: string; page?: number; pageSize?: number }, opts?: RequestOpts) => {
    const search = new URLSearchParams();
    if (params?.game) search.set("game", params.game);
    if (params?.page) search.set("page", String(params.page));
    if (params?.pageSize) search.set("page_size", String(params.pageSize));
    const qs = search.toString();
    return api.get<MembershipPage>(`/memberships${qs ? `?${qs}` : ""}`, opts);
  },

  upsert: (payload: MembershipUpsertRequest) => api.post<MembershipItem>("/memberships", payload),

  delete: (id: number) => api.delete<void>(`/memberships/${id}`),
};
