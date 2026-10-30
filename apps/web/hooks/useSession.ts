"use client";

import { useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { getSession, type SessionUser } from "@/lib/auth";

const noopSubscribe = () => () => {};

export interface SessionState {
  data: SessionUser | null | undefined;
  isLoading: boolean;
  isError: boolean;
}

const HYDRATING: SessionState = {
  data: undefined,
  isLoading: true,
  isError: false,
};

/**
 * 当前登录态。
 *
 * 服务端渲染时还没查过 session，页面总是渲染成“加载中”。页面正文在 Suspense 边界里，
 * 往往比头部晚水合；头部先发出的 session 请求可能已经回来，正文首帧就会直接渲染成登录后的样子，
 * 和服务端 HTML 对不上。所以水合期间一律按服务端的样子返回“加载中”，水合完再给真实结果；
 * 客户端路由跳转不经过水合，不受影响。
 *
 * 只返回调用方用到的三个字段：react-query 按读取过的属性决定是否通知重渲染，
 * 展开整个结果会让后台重取时的 isFetching 等变化也触发重渲染。
 */
export function useSession(): SessionState {
  const query = useQuery<SessionUser | null>({
    queryKey: ["session"],
    queryFn: getSession,
    staleTime: 60 * 1000,
  });
  const hydrated = useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
  if (!hydrated) return HYDRATING;
  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
