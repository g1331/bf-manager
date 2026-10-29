"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { feedbackUrl } from "@/lib/feedback";
import { describeApiError } from "@/lib/api-client";
import { cn } from "@/lib/utils";

/**
 * 整块的出错提示：错误页、详情页加载失败共用。
 * 有错误编号时展示编号并给 GitHub 反馈入口，用户反馈时带上编号即可在日志里定位。
 */
export function ErrorState({
  kicker = "ERROR",
  title,
  description,
  requestId,
  digest,
  onRetry,
  retrying = false,
  homeHref,
  showFeedback = false,
  className,
}: {
  kicker?: string;
  title: string;
  description?: string;
  requestId?: string;
  digest?: string;
  onRetry?: () => void;
  retrying?: boolean;
  homeHref?: string;
  showFeedback?: boolean;
  className?: string;
}) {
  const pathname = usePathname();
  const errorId = requestId ?? digest;

  return (
    <div
      role="alert"
      className={cn(
        "mx-auto flex w-full max-w-md flex-col items-center gap-4 px-6 py-16 text-center text-white",
        className,
      )}
    >
      <div className="font-display flex items-center gap-2 text-xs font-medium tracking-[0.2em] text-amber-500 uppercase">
        <span className="h-[2px] w-6 bg-amber-500" />
        {kicker}
        <span className="h-[2px] w-6 bg-amber-500" />
      </div>
      <h1 className="text-xl font-bold sm:text-2xl">{title}</h1>
      {description ? <p className="text-sm leading-relaxed text-white/65">{description}</p> : null}
      {errorId ? (
        <p className="text-xs text-white/45">
          错误编号
          <code className="ml-1.5 rounded bg-white/10 px-1.5 py-0.5 font-mono text-white/75 select-all">
            {errorId}
          </code>
        </p>
      ) : null}
      {onRetry || homeHref ? (
        <div className="flex flex-wrap justify-center gap-3 pt-1">
          {onRetry ? (
            <Button onClick={onRetry} disabled={retrying} className="min-w-28">
              {retrying ? "重试中…" : "重试"}
            </Button>
          ) : null}
          {homeHref ? (
            <Button asChild variant="outline" className="min-w-28">
              <Link href={homeHref}>回首页</Link>
            </Button>
          ) : null}
        </div>
      ) : null}
      {showFeedback ? (
        <a
          href={feedbackUrl({ requestId, digest, path: pathname ?? undefined })}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-white/45 underline-offset-4 transition-colors hover:text-white/80 hover:underline"
        >
          问题一直出现？到 GitHub 反馈
        </a>
      ) : null}
    </div>
  );
}

/** 查询失败时按错误类别给出标题与说明；not_found 用页面传入的文案 */
export function QueryErrorState({
  error,
  notFoundText,
  onRetry,
  retrying,
  className,
}: {
  error: unknown;
  notFoundText: string;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}) {
  const view = describeApiError(error);
  const titles: Record<typeof view.kind, string> = {
    not_found: notFoundText,
    busy: "查询人数较多",
    timeout: "请求超时",
    network: "网络连接失败",
    server: "加载失败",
  };
  return (
    <ErrorState
      kicker={view.kind === "not_found" ? "NOT FOUND" : "ERROR"}
      title={titles[view.kind]}
      description={view.kind === "not_found" ? undefined : view.message}
      requestId={view.requestId}
      onRetry={view.retryable ? onRetry : undefined}
      retrying={retrying}
      showFeedback={view.kind === "server"}
      className={className}
    />
  );
}
