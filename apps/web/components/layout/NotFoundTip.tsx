"use client";

import { useSyncExternalStore } from "react";
import { TipLine } from "@/components/bf1/codex/TipLine";
import { isBf6Path } from "@/lib/nav";

const noSubscribe = () => () => {};

/**
 * 404 页的载入贴士：贴士是 BF1 的内容，/bf6 下的错地址不显示。
 * 404 页服务端渲染时拿不到真实地址（usePathname 和客户端对不上会水合报错），
 * 所以服务端先不出贴士，水合后按 window.location 再判断。
 */
export function NotFoundTip() {
  const pathname = useSyncExternalStore(
    noSubscribe,
    () => window.location.pathname,
    () => null,
  );
  if (pathname === null || isBf6Path(pathname)) return null;
  return <TipLine className="w-full max-w-xl" />;
}
