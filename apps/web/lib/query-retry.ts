import { ApiException } from "@/lib/api-client";

/**
 * 查询失败后要不要自动重试：4xx 是确定的结果，重试也一样；
 * 查询繁忙和超时自动重试只会加重负担或让用户多等，交给页面上的「重试」按钮。
 * 其余（网络断开、5xx）最多再试两次。
 */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiException) {
    if (error.status >= 400 && error.status < 500) return false;
    if (error.code === "EA_BUSY" || error.code === "TIMEOUT") return false;
  }
  return failureCount < 2;
}
