// ESLint flat config（Next.js 16 起 next lint 已移除，统一用 eslint CLI）。
// eslint-config-next 16 已是原生 flat 预设，直接展开 core-web-vitals 与 typescript 两组；
// 末尾 eslint-config-prettier 关闭与 Prettier 冲突的格式规则，让 lint 只管代码质量、
// 格式仍由 Prettier 负责，二者不打架。
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import eslintConfigPrettier from "eslint-config-prettier";

const eslintConfig = [
  ...nextVitals,
  ...nextTs,
  eslintConfigPrettier,
  {
    ignores: ["node_modules/**", ".next/**", "out/**", "build/**", "next-env.d.ts"],
  },
];

export default eslintConfig;
