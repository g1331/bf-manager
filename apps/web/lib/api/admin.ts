/**
 * 平台运维统计 API 客户端
 */
import { api } from "@/lib/api-client";

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

export const adminApi = {
  getMetrics: () => api.get<AdminMetrics>("/admin/metrics"),
};
