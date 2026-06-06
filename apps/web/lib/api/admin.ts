/**
 * 平台运维统计 API 客户端
 */
import { api } from "@/lib/api-client";

/** 按接口分组累计的请求次数，group 形如 bf1/stats、bf1/servers */
export interface EndpointCount {
  group: string;
  count: number;
}

/** 单日请求量与去重活跃用户数，date 为 YYYY-MM-DD */
export interface DailyCount {
  date: string;
  requests: number;
  active_users: number;
}

export interface AdminMetrics {
  available: boolean;
  total_requests: number;
  requests_today: number;
  requests_7d: number;
  active_users_today: number;
  active_users_7d: number;
  top_endpoints: EndpointCount[];
  /** 最近 7 天，按日期升序排列 */
  daily: DailyCount[];
}

export const adminApi = {
  getMetrics: () => api.get<AdminMetrics>("/admin/metrics"),
};
