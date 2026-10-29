"use client";

import { useEffect } from "react";
import { feedbackUrl } from "@/lib/feedback";
import { errorDigest } from "@/lib/error-digest";

/**
 * 根布局本身出错时的兜底页。它替换整个根布局、不带全局样式，所以只用内联样式，
 * 不依赖任何组件，保证在最坏的情况下也能显示出来。
 */
export default function GlobalError({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  const digest = errorDigest(error);

  return (
    <html lang="zh-CN">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#120c06",
          color: "#f5efe6",
          fontFamily: "system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif",
          textAlign: "center",
          padding: "24px",
        }}
      >
        <title>出错了 · BF-Manager</title>
        <div style={{ maxWidth: 420 }}>
          <h1 style={{ fontSize: 22, margin: "0 0 12px" }}>页面出错了</h1>
          <p style={{ fontSize: 14, lineHeight: 1.7, opacity: 0.7, margin: "0 0 20px" }}>
            网站遇到了意外错误，请重试或稍后再来。
          </p>
          {digest ? (
            <p style={{ fontSize: 12, opacity: 0.5, margin: "0 0 20px" }}>错误编号 {digest}</p>
          ) : null}
          <button
            type="button"
            onClick={() => retry()}
            style={{
              background: "#e8892c",
              color: "#1a1208",
              border: "none",
              borderRadius: 6,
              padding: "10px 28px",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            重试
          </button>
          <p style={{ marginTop: 20 }}>
            <a
              href={feedbackUrl({ digest })}
              target="_blank"
              rel="noreferrer"
              style={{ color: "#f5efe6", opacity: 0.5, fontSize: 12 }}
            >
              问题一直出现？到 GitHub 反馈
            </a>
          </p>
        </div>
      </body>
    </html>
  );
}
