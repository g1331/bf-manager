"use client";

import { useEffect, useState, type ReactNode } from "react";
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
  type QueryKey,
} from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { toast } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiException } from "@/lib/api-client";
import { initPwa } from "@/lib/pwa";
import { accountKeys } from "@/lib/queries/account";
import { shouldRetryQuery } from "@/lib/query-retry";

/**
 * 登录态中途失效（token 过期、被冻结）时任意请求会回 401：把 session 置空，
 * 需要登录的页面随之跳去登录页，头部菜单回到未登录状态。
 * 本来就没登录时的 401 是预期内的结果（如探测性请求），不打扰用户。
 */
function handleUnauthorized(client: QueryClient, error: unknown, queryKey?: QueryKey) {
  if (!(error instanceof ApiException) || error.status !== 401) return;
  if (queryKey?.[0] === accountKeys.session()[0]) return;
  if (!client.getQueryData(accountKeys.session())) return;
  client.setQueryData(accountKeys.session(), null);
  toast.error("登录已过期，请重新登录", { id: "session-expired" });
}

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => {
    const client: QueryClient = new QueryClient({
      queryCache: new QueryCache({
        onError: (error, query) => handleUnauthorized(client, error, query.queryKey),
      }),
      mutationCache: new MutationCache({
        onError: (error) => handleUnauthorized(client, error),
      }),
      defaultOptions: {
        queries: {
          staleTime: 30 * 1000,
          gcTime: 5 * 60 * 1000,
          refetchOnWindowFocus: false,
          retry: shouldRetryQuery,
        },
      },
    });
    return client;
  });

  // 装到桌面的状态和离线页 service worker，全站挂一次，落地页上也能截住安装事件
  useEffect(() => {
    initPwa();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>{children}</TooltipProvider>
      {process.env.NODE_ENV === "development" ? <ReactQueryDevtools initialIsOpen={false} /> : null}
    </QueryClientProvider>
  );
}
