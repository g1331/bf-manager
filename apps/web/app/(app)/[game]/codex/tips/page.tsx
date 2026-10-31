import type { Metadata } from "next";
import { CodexFootnote, CodexHeader } from "@/components/bf1/codex/CodexHeader";
import { TipsBrowser } from "@/components/bf1/codex/TipsBrowser";

export const metadata: Metadata = {
  title: "小贴士 · 图鉴",
  description:
    "战地 1 载入画面里轮播的全部 390 条小贴士：地图背景、模式玩法与一战冷知识，可按地图和模式筛选。",
};

export default function TipsPage() {
  return (
    <main className="mx-auto max-w-[1400px] px-4 py-6 text-white sm:py-8">
      <CodexHeader
        active="tips"
        intro="等待载入时屏幕下方的那一行字。地图贴士讲这张图背后的历史，模式贴士讲玩法，剩下的是一战冷知识。"
      />
      <TipsBrowser />
      <CodexFootnote />
    </main>
  );
}
