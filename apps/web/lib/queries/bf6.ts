/**
 * BF6 读查询的 queryKey 与 queryFn。两个接口都会打到 EA，后端各自缓存（找人 1 小时、战绩 20 分钟），
 * 前端 staleTime 跟着放长，来回切页不重复请求。
 */
import { queryOptions } from "@tanstack/react-query";
import { bf6Api, type Bf6Platform } from "@/lib/api/bf6";

export const bf6Keys = {
  resolve: (name: string, platform: Bf6Platform | null) =>
    ["bf6-resolve", name.toLowerCase(), platform] as const,
  stats: (nucleusId: number) => ["bf6-stats", nucleusId] as const,
};

export const bf6Queries = {
  resolve: (name: string, platform: Bf6Platform | null) =>
    queryOptions({
      queryKey: bf6Keys.resolve(name, platform),
      queryFn: ({ signal }) => bf6Api.resolvePlayer(name, platform, { signal }),
      staleTime: 30 * 60_000,
    }),
  stats: (nucleusId: number) =>
    queryOptions({
      queryKey: bf6Keys.stats(nucleusId),
      queryFn: ({ signal }) => bf6Api.getStats(nucleusId, { signal }),
      staleTime: 10 * 60_000,
    }),
};
