"use client";

import { useEffect, useState } from "react";

/**
 * 从 #token=… 里取出 token 后立刻把它从地址栏抹掉，免得截图、分享时带出去。
 * 返回 undefined 表示还没读（首屏），null 表示地址里没有 token。
 */
export function useHashToken(): string | null | undefined {
  const [token, setToken] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    const read = () => {
      const value = new URLSearchParams(window.location.hash.slice(1)).get("token");
      if (value) window.history.replaceState(null, "", window.location.pathname);
      return value;
    };
    // 开发模式下 effect 会跑两遍，第二遍 hash 已经清空，不能把第一遍读到的 token 覆盖成 null
    const first = read();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setToken((prev) => prev ?? first);
    // 页面开着时又点了一条同路径的链接（只有 hash 变），组件不会重新挂载，靠 hashchange 接住
    const onHashChange = () => {
      const value = read();
      if (value) setToken(value);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  return token;
}
