import type { Metadata } from "next";
import { CodexFootnote, CodexHeader } from "@/components/bf1/codex/CodexHeader";
import { DogtagBrowser } from "@/components/bf1/codex/DogtagBrowser";

export const metadata: Metadata = {
  title: "狗牌 · 图鉴",
  description: "战地 1 全部 320 枚狗牌：基本狗牌 129 枚、高级狗牌 191 枚，可以搭配正反面 3D 查看。",
};

export default function DogtagsPage() {
  return (
    <main className="mx-auto max-w-[1400px] px-4 py-6 text-white sm:py-8">
      <CodexHeader
        active="dogtags"
        intro="游戏里的狗牌一正一反：正面挂基本狗牌，背面挂高级狗牌。点开任意一枚，可以给它搭配另一面，拿在手里转着看。"
      />
      <DogtagBrowser />
      <CodexFootnote />
    </main>
  );
}
