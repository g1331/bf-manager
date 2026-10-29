/**
 * 装到桌面（PWA）相关的浏览器状态。
 *
 * - 判断当前环境该用哪种方式安装：Chromium 系能弹系统安装框；iOS 只能走「分享 → 添加到主屏幕」；
 *   微信 / QQ 内置浏览器装不了，得先跳到浏览器；UA 带 OpenHarmony 的浏览器装不了 PWA，
 *   改为下载安卓壳 App（apps/android）；其余浏览器（UC、夸克等）去菜单里找，找不到也可以下载 App。
 * - 截住 Chromium 的 beforeinstallprompt，留给安装提示条在用户点「安装」时再弹。
 * - 记录提示条的关闭时间，关掉后 30 天内不再自动出现。
 * - 生产环境注册 service worker（public/sw.js），只负责断网时给出提示页。
 *
 * 状态放在模块级小 store 里，用 useSyncExternalStore 读取；服务端快照恒为「不显示」。
 */

import { useSyncExternalStore } from "react";

export type InstallMethod = "prompt" | "ios" | "in-app" | "app" | "menu";

/** 安卓壳 App 的安装包，由 tools/build-android.sh 生成 */
export const APP_DOWNLOAD_URL = "/download/bf-manager.apk";

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

interface PwaSnapshot {
  /** 已初始化（只在浏览器里为 true） */
  ready: boolean;
  /** 正从桌面图标打开，或刚在本页装好 */
  installed: boolean;
  method: InstallMethod;
  /** 提示条处于关闭期 */
  dismissed: boolean;
  /** 从菜单手动打开了提示条，忽略关闭期 */
  forced: boolean;
}

const DISMISS_KEY = "bfm:install-dismissed-at";
const DISMISS_DAYS = 30;

const SERVER_SNAPSHOT: PwaSnapshot = {
  ready: false,
  installed: false,
  method: "menu",
  dismissed: true,
  forced: false,
};

let snapshot: PwaSnapshot = SERVER_SNAPSHOT;
let deferredPrompt: BeforeInstallPromptEvent | null = null;
let initialized = false;
const listeners = new Set<() => void>();

function update(patch: Partial<PwaSnapshot>) {
  snapshot = { ...snapshot, ...patch };
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function detectMethod(hasPrompt: boolean): InstallMethod {
  const ua = navigator.userAgent;
  if (/MicroMessenger|\bQQ\//i.test(ua)) return "in-app";
  // UA 带 OpenHarmony 的浏览器不支持 PWA 安装，只能加打开浏览器的快捷方式
  if (/OpenHarmony/i.test(ua)) return "app";
  if (hasPrompt) return "prompt";
  // iPadOS 默认伪装成 Mac Safari，靠触控点数区分
  const isIOS =
    /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  return isIOS ? "ios" : "menu";
}

function isStandalone(): boolean {
  return (
    // 安卓壳 App（apps/android）在 UA 末尾带 BFManagerApp
    /BFManagerApp\//.test(navigator.userAgent) ||
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function readDismissed(): boolean {
  try {
    const at = Number(localStorage.getItem(DISMISS_KEY));
    return Number.isFinite(at) && Date.now() - at < DISMISS_DAYS * 24 * 60 * 60 * 1000;
  } catch {
    return false;
  }
}

/** 在根布局挂载时调用一次。 */
export function initPwa() {
  if (initialized || typeof window === "undefined") return;
  initialized = true;

  window.addEventListener("beforeinstallprompt", (e) => {
    // 拦下浏览器自带的迷你提示，改由提示条里的「安装」按钮触发
    e.preventDefault();
    deferredPrompt = e as BeforeInstallPromptEvent;
    update({ method: detectMethod(true) });
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    update({ installed: true, forced: false });
  });

  update({
    ready: true,
    installed: isStandalone(),
    method: detectMethod(false),
    dismissed: readDismissed(),
  });

  if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // 注册失败只影响离线提示页，不打扰用户
    });
  }
}

export function usePwa() {
  const state = useSyncExternalStore(
    subscribe,
    () => snapshot,
    () => SERVER_SNAPSHOT,
  );
  return {
    ...state,
    /** 是否该显示安装提示条 */
    bannerVisible: state.ready && !state.installed && (state.forced || !state.dismissed),
  };
}

/** 关闭提示条，30 天内不再自动出现。 */
export function dismissInstallBanner() {
  try {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
  } catch {
    // 隐私模式等写不进 localStorage，只在本次会话内关闭
  }
  update({ dismissed: true, forced: false });
}

/** 从菜单手动打开提示条。 */
export function openInstallBanner() {
  update({ forced: true });
}

/** 弹出 Chromium 的系统安装框；用户拒绝也视为关闭提示条。 */
export async function promptInstall() {
  const event = deferredPrompt;
  if (!event) return;
  deferredPrompt = null;
  await event.prompt();
  const { outcome } = await event.userChoice;
  if (outcome === "accepted") {
    update({ installed: true, forced: false });
  } else {
    update({ method: detectMethod(false) });
    dismissInstallBanner();
  }
}
