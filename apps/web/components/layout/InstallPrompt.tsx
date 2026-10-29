"use client";

import { Ellipsis, Share, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  APP_DOWNLOAD_URL,
  dismissInstallBanner,
  promptInstall,
  usePwa,
  type InstallMethod,
} from "@/lib/pwa";

/**
 * 手机端「装到桌面」提示条，浮在底部标签栏上方。
 * 按环境给出能走通的那一种装法（见 lib/pwa），关掉后 30 天内不再自动出现；
 * 侧边抽屉里的「安装到桌面」可随时重新打开。已经从桌面图标或 App 里打开时不显示。
 */
export function InstallPrompt() {
  const { bannerVisible, method } = usePwa();
  if (!bannerVisible) return null;

  return (
    <div
      role="dialog"
      aria-label="装到桌面"
      className="fixed inset-x-3 bottom-[calc(3.5rem+env(safe-area-inset-bottom)+0.5rem)] z-40 flex items-center gap-3 border border-white/12 bg-zinc-950/95 p-3 pr-1 shadow-lg shadow-black/40 backdrop-blur-md lg:hidden"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src="/icons/icon-192.png" alt="" className="size-10 shrink-0 rounded-md" />
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-medium text-white">装到桌面，像 App 一样打开</p>
        <p className="mt-0.5 text-xs leading-relaxed text-white/60">
          <Hint method={method} />
        </p>
      </div>
      {method === "prompt" ? (
        <Button size="sm" className="shrink-0" onClick={() => void promptInstall()}>
          安装
        </Button>
      ) : null}
      {method === "app" ? (
        <Button size="sm" className="shrink-0" asChild>
          <a href={APP_DOWNLOAD_URL} download>
            下载
          </a>
        </Button>
      ) : null}
      <Button
        variant="ghost"
        size="icon"
        className="shrink-0 text-white/50"
        onClick={dismissInstallBanner}
        aria-label="不再提示"
      >
        <X className="size-4" />
      </Button>
    </div>
  );
}

function Hint({ method }: { method: InstallMethod }) {
  switch (method) {
    case "prompt":
      return <>全屏打开、不用再找网址</>;
    case "ios":
      return (
        <>
          点分享
          <Share className="mx-0.5 inline size-3.5 -translate-y-px" aria-label="分享" />
          再选「添加到主屏幕」。没看到分享就先点
          <span className="whitespace-nowrap">
            <Ellipsis className="mx-0.5 inline size-3.5" aria-label="更多" />。
          </span>
        </>
      );
    case "in-app":
      return <>这里装不了。点右上角 ··· 选「在浏览器打开」，再从浏览器装</>;
    case "app":
      return <>下载后点开安装包，装好就能从桌面打开</>;
    case "menu":
      return (
        <>
          在浏览器菜单里找「添加到主屏幕」或「安装应用」。找不到或点不了，可以
          <a href={APP_DOWNLOAD_URL} download className="inline-action text-primary underline">
            下载 App
          </a>
        </>
      );
  }
}
