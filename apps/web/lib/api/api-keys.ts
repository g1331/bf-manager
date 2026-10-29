/** 开放 API Key：用户自助签发 / 吊销，平台 admin 查看全部并调整额度 */
import { api } from "@/lib/api-client";

export interface ApiKeyItem {
  id: number;
  name: string;
  /** key 开头几位，用来认出是哪个 key */
  prefix: string;
  /** 实际生效的额度倍数 */
  rate_multiplier: number;
  /** 管理员是否单独调过倍数 */
  custom_multiplier: boolean;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  used_today: number;
  used_7d: number;
}

/** 倍数为 1 时的基础额度，实际额度 = 基础额度 × key 的倍数 */
export interface ApiKeyQuota {
  lookup_per_minute: number;
  lookup_per_day: number;
  read_per_minute: number;
  read_per_day: number;
  avatar_per_minute: number;
}

export interface ApiKeyListResponse {
  items: ApiKeyItem[];
  max_keys: number;
  quota: ApiKeyQuota;
}

export interface ApiKeyCreated {
  item: ApiKeyItem;
  /** 完整 key，只在创建时返回这一次 */
  key: string;
}

export interface AdminApiKeyItem extends ApiKeyItem {
  user_id: number;
  user_username: string;
  user_display_name: string | null;
}

export interface AdminApiKeyListResponse {
  items: AdminApiKeyItem[];
  default_multiplier: number;
}

export const apiKeysApi = {
  listMine: () => api.get<ApiKeyListResponse>("/me/api-keys"),
  create: (name: string) => api.post<ApiKeyCreated>("/me/api-keys", { name }),
  revokeMine: (id: number) => api.post<ApiKeyItem>(`/me/api-keys/${id}/revoke`),

  listAll: () => api.get<AdminApiKeyListResponse>("/admin/api-keys"),
  /** multiplier 传 null 恢复默认倍数 */
  setMultiplier: (id: number, multiplier: number | null) =>
    api.patch<ApiKeyItem>(`/admin/api-keys/${id}`, { rate_multiplier: multiplier }),
  revoke: (id: number) => api.post<ApiKeyItem>(`/admin/api-keys/${id}/revoke`),
};
