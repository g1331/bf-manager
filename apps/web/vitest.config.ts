import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// 只测不依赖 DOM 的纯逻辑（请求客户端、权限判断、查询键），跑在 node 环境
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./", import.meta.url)) },
  },
  test: {
    environment: "node",
    include: ["**/*.test.ts"],
    exclude: ["node_modules/**", ".next/**"],
  },
});
