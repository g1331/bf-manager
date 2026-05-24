/** 服管权限授予 API（仅平台 admin 可访问） */
import { api } from "@/lib/api-client";

export type MembershipRole = "viewer" | "moderator" | "admin" | "owner";

export interface MembershipItem {
  id: number;
  user_id: number;
  user_persona_id: number;
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
  list: (params?: { game?: string; page?: number; pageSize?: number }) => {
    const search = new URLSearchParams();
    if (params?.game) search.set("game", params.game);
    if (params?.page) search.set("page", String(params.page));
    if (params?.pageSize) search.set("page_size", String(params.pageSize));
    const qs = search.toString();
    return api.get<MembershipPage>(`/memberships${qs ? `?${qs}` : ""}`);
  },

  upsert: (payload: MembershipUpsertRequest) => api.post<MembershipItem>("/memberships", payload),

  delete: (id: number) => api.delete<void>(`/memberships/${id}`),
};
