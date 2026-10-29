/** 反馈入口：统一走 GitHub Issues，带上错误编号与当前页面，便于在日志里定位 */

const ISSUES_NEW_URL = "https://github.com/g1331/bf-manager/issues/new";

export function feedbackUrl({
  requestId,
  digest,
  path,
}: {
  requestId?: string;
  digest?: string;
  path?: string;
} = {}): string {
  const lines = [
    "**遇到的问题**：",
    "",
    "",
    "---",
    path ? `页面：${path}` : null,
    requestId ? `错误编号：${requestId}` : null,
    digest ? `前端错误摘要：${digest}` : null,
  ].filter((line): line is string => line !== null);
  const params = new URLSearchParams({
    title: requestId ? `[反馈] 错误编号 ${requestId}` : "[反馈] ",
    body: lines.join("\n"),
  });
  return `${ISSUES_NEW_URL}?${params.toString()}`;
}
