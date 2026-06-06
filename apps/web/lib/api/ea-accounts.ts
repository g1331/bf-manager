import { api } from "@/lib/api-client";

export interface EAAccountItem {
  id: number;
  persona_id: number;
  display_name: string | null;
  enabled: boolean;
  last_used_at: string | null;
  failure_count: number;
  use_count: number;
  has_session: boolean;
  has_access_token: boolean;
  created_at: string;
  updated_at: string;
}

export interface EAAccountCreateRequest {
  persona_id: number;
  display_name?: string | null;
  remid: string;
  sid: string;
  session?: string | null;
  access_token?: string | null;
  enabled?: boolean;
}

export interface EAAccountCredentialsUpdateRequest {
  remid?: string | null;
  sid?: string | null;
  session?: string | null;
  access_token?: string | null;
}

export interface EAAccountDisplayNameUpdateRequest {
  /** 传 null 显式清空备注；传字符串覆盖。 */
  display_name: string | null;
}

export interface EAAccountVerifyResult {
  success: boolean;
  persona_id: number;
  message: string | null;
}

export const eaAccountsApi = {
  list: () => api.get<EAAccountItem[]>("/ea-accounts"),

  create: (payload: EAAccountCreateRequest) => api.post<EAAccountItem>("/ea-accounts", payload),

  updateCredentials: (id: number, payload: EAAccountCredentialsUpdateRequest) =>
    api.patch<EAAccountItem>(`/ea-accounts/${id}/credentials`, payload),

  updateDisplayName: (id: number, payload: EAAccountDisplayNameUpdateRequest) =>
    api.patch<EAAccountItem>(`/ea-accounts/${id}/display-name`, payload),

  setEnabled: (id: number, enabled: boolean) =>
    api.patch<EAAccountItem>(`/ea-accounts/${id}/enabled`, { enabled }),

  delete: (id: number) => api.delete<void>(`/ea-accounts/${id}`),

  verify: (id: number) => api.post<EAAccountVerifyResult>(`/ea-accounts/${id}/verify`),
};
