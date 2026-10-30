"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getAuthConfig } from "@/lib/auth";

interface TurnstileApi {
  render: (el: HTMLElement, options: Record<string, unknown>) => string;
  remove: (widgetId: string) => void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
let scriptPromise: Promise<TurnstileApi> | null = null;

function loadTurnstile(): Promise<TurnstileApi> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = SCRIPT_SRC;
      script.async = true;
      script.onload = () =>
        window.turnstile ? resolve(window.turnstile) : reject(new Error("turnstile missing"));
      script.onerror = () => {
        scriptPromise = null;
        reject(new Error("turnstile load failed"));
      };
      document.head.appendChild(script);
    });
  }
  return scriptPromise;
}

function TurnstileWidget({
  siteKey,
  onToken,
}: {
  siteKey: string;
  onToken: (token: string | null) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let widgetId: string | null = null;
    let cancelled = false;
    loadTurnstile()
      .then((ts) => {
        if (cancelled || !ref.current) return;
        widgetId = ts.render(ref.current, {
          sitekey: siteKey,
          theme: "dark",
          size: "flexible",
          language: "zh-cn",
          callback: (token: string) => onToken(token),
          "expired-callback": () => onToken(null),
          "error-callback": () => onToken(null),
        });
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (widgetId && window.turnstile) window.turnstile.remove(widgetId);
    };
    // onToken 由 useCaptcha 传入 setState，引用稳定，不会让验证框反复重建
  }, [siteKey, onToken]);

  if (failed) {
    return <p className="text-destructive text-sm">人机验证加载失败，请检查网络后刷新页面。</p>;
  }
  return <div ref={ref} className="min-h-[65px]" />;
}

export function useAuthConfig() {
  return useQuery({
    queryKey: ["auth-config"],
    queryFn: getAuthConfig,
    // 注册方式可以在后台随时切换，别缓存太久
    staleTime: 30 * 1000,
  });
}

/**
 * 发信类表单的人机验证。后端没启用时 widget 为 null、token 恒为 null，表单照常提交。
 * token 只能用一次：每次提交后调 reset() 换一个新的验证框。
 */
export function useCaptcha() {
  const config = useAuthConfig();
  const siteKey = config.data?.turnstile_site_key ?? null;
  const [token, setToken] = useState<string | null>(null);
  const [round, setRound] = useState(0);

  // 配置没拿到就不知道要不要人机验证：给出重试入口，别放行提交
  const failed = !config.data && config.isError;

  return {
    widget: failed ? (
      <p className="text-destructive text-sm">
        读取站点配置失败，
        <button
          type="button"
          className="underline underline-offset-4"
          onClick={() => void config.refetch()}
        >
          重试
        </button>
      </p>
    ) : siteKey ? (
      <TurnstileWidget key={round} siteKey={siteKey} onToken={setToken} />
    ) : null,
    token,
    ready: !!config.data && (!siteKey || token !== null),
    reset: () => {
      setToken(null);
      setRound((r) => r + 1);
    },
  };
}
