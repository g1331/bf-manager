/**
 * 平台运维统计 API 客户端
 */
import { api } from "@/lib/api-client";
import type { RegistrationMode } from "@/lib/auth";

/** 按接口分组累计的请求次数，group 形如 bf1/stats、bf1/servers */
export interface EndpointCount {
  group: string;
  count: number;
}

/** 单日请求量、去重活跃用户与去重游客（未登录，按 IP），date 为 YYYY-MM-DD */
export interface DailyCount {
  date: string;
  requests: number;
  active_users: number;
  guests: number;
  /** 当天发给 EA 的请求数 */
  ea_calls: number;
}

/** 今天某个来源发给 EA 的请求数；pids 为其中 Stats.getStats 查询的人次 */
export interface EaSourceCount {
  source: string;
  calls: number;
  pids: number;
}

/** 今天按通道（blaze / gateway / accounts / sal）、方法、来源细分的 EA 请求数 */
export interface EaMethodCount {
  channel: string;
  method: string;
  source: string;
  count: number;
}

/** 某个整点小时（UTC，ISO 格式）内的 EA 请求总数 */
export interface EaHourCount {
  hour: string;
  count: number;
}

/** 今天对局跟踪器的一类事件计数，name 如 want_join、join_hop、recheck_changed_fresh */
export interface TrackerEventCount {
  name: string;
  count: number;
}

export interface AdminMetrics {
  available: boolean;
  total_requests: number;
  requests_today: number;
  requests_7d: number;
  active_users_today: number;
  active_users_7d: number;
  guests_today: number;
  guests_7d: number;
  top_endpoints: EndpointCount[];
  /** 最近 7 天，按日期升序排列 */
  daily: DailyCount[];
  ea_calls_today: number;
  ea_calls_7d: number;
  ea_sources: EaSourceCount[];
  ea_methods: EaMethodCount[];
  /** 最近 24 小时，按小时升序 */
  ea_hourly: EaHourCount[];
  tracker_events: TrackerEventCount[];
}

/** 注册方式；is_default 为 true 表示后台还没设过，跟着环境变量的默认值走 */
export interface RegistrationSetting {
  mode: RegistrationMode;
  is_default: boolean;
  updated_at: string | null;
  updated_by_name: string | null;
}

/** 后台用户列表的一行 */
export interface AdminUser {
  id: number;
  username: string;
  email: string | null;
  role: "user" | "admin";
  /** active / pending_binding / legacy */
  status: string;
  persona_id: number | null;
  display_name: string | null;
  created_at: string;
  last_login_at: string | null;
  active_api_keys: number;
  is_frozen: boolean;
  frozen_at: string | null;
  frozen_reason: string | null;
  frozen_by_name: string | null;
}

export interface AdminUserPage {
  items: AdminUser[];
  total: number;
  page: number;
  page_size: number;
}

export type AdminUserFilter = "all" | "frozen" | "admin";

export const adminApi = {
  getMetrics: () => api.get<AdminMetrics>("/admin/metrics"),
  getRegistration: () => api.get<RegistrationSetting>("/admin/settings/registration"),
  setRegistration: (mode: RegistrationMode) =>
    api.put<RegistrationSetting>("/admin/settings/registration", { mode }),
  listUsers: (params: { q?: string; only?: AdminUserFilter; page: number; pageSize: number }) => {
    const sp = new URLSearchParams({
      page: String(params.page),
      page_size: String(params.pageSize),
    });
    if (params.q) sp.set("q", params.q);
    if (params.only && params.only !== "all") sp.set("only", params.only);
    return api.get<AdminUserPage>(`/admin/users?${sp.toString()}`);
  },
  freezeUser: (id: number, reason: string) =>
    api.post<AdminUser>(`/admin/users/${id}/freeze`, { reason }),
  unfreezeUser: (id: number) => api.post<AdminUser>(`/admin/users/${id}/unfreeze`),
};
