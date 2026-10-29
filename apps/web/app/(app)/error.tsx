"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/common/ErrorState";
import { errorDigest } from "@/lib/error-digest";

/** (app) 组的错误边界：页面渲染出错时保留侧栏与顶栏，只替换主内容区 */
export default function AppError({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="flex min-h-[60vh] items-center justify-center">
      <ErrorState
        title="页面出错了"
        description="这个页面遇到了意外错误。可以先重试，不行的话回首页再进来。"
        digest={errorDigest(error)}
        onRetry={retry}
        homeHref="/"
        showFeedback
      />
    </main>
  );
}
