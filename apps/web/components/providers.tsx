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
import { ApiException } from "@/lib/api-client";
import { initPwa } from "@/lib/pwa";

/**
 * 登录态中途失效（token 过期、被冻结）时任意请求会回 401：把 session 置空，
 * 需要登录的页面随之跳去登录页，头部菜单回到未登录状态。
 * 本来就没登录时的 401 是预期内的结果（如探测性请求），不打扰用户。
 */
function handleUnauthorized(client: QueryClient, error: unknown, queryKey?: QueryKey) {
  if (!(error instanceof ApiException) || error.status !== 401) return;
  if (queryKey?.[0] === "session") return;
  if (!client.getQueryData(["session"])) return;
  client.setQueryData(["session"], null);
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
          retry: (failureCount, error) => {
            if (error instanceof ApiException) {
              if (error.status >= 400 && error.status < 500) return false;
              // 查询繁忙和超时自动重试只会加重负担或让用户多等，交给页面上的「重试」按钮
              if (error.code === "EA_BUSY" || error.code === "TIMEOUT") return false;
            }
            return failureCount < 2;
          },
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
      {children}
      {process.env.NODE_ENV === "development" ? <ReactQueryDevtools initialIsOpen={false} /> : null}
    </QueryClientProvider>
  );
}
