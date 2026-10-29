/** Next 把服务端组件的错误换成通用消息，只留 digest 供对照服务端日志 */
export function errorDigest(error: unknown): string | undefined {
  if (error instanceof Error && "digest" in error && typeof error.digest === "string") {
    return error.digest;
  }
  return undefined;
}
