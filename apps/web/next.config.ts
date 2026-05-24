import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 多阶段 Docker 镜像最小化产物
  output: "standalone",
  // 严格模式
  reactStrictMode: true,
  // 类型与 lint 错误必须先修复
  typescript: { ignoreBuildErrors: false },
  // 后端 API 反向代理（dev 环境直接走，prod 由 Caddy 处理）
  async rewrites() {
    const backend = process.env.BACKEND_API_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backend}/api/v1/:path*`,
      },
    ];
  },
  // 图片域白名单（如需加载 EA CDN 头像）
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "secure.download.dm.origin.com" },
      { protocol: "https", hostname: "eaassets-a.akamaihd.net" },
    ],
  },
};

export default nextConfig;
