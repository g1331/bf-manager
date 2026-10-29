"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/common/ErrorState";
import { errorDigest } from "@/lib/error-digest";

/** 根级错误边界：门户首页、登录页等不在 (app) 组里的页面出错时显示 */
export default function RootError({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="dark bg-background text-foreground flex min-h-screen items-center justify-center">
      <ErrorState
        title="页面出错了"
        description="这个页面遇到了意外错误。可以先重试，不行的话回首页再进来。"
        digest={errorDigest(error)}
        onRetry={retry}
        homeHref="/"
        showFeedback
      />
    </div>
  );
}
