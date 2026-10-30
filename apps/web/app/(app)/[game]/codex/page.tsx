import type { Metadata } from "next";
import { CodexBrowser } from "@/components/bf1/codex/CodexBrowser";
import { CodexFootnote, CodexHeader } from "@/components/bf1/codex/CodexHeader";

export const metadata: Metadata = {
  title: "百科 · 图鉴",
  description:
    "战地 1 游戏内全部 310 条百科：武器、载具、战略、战争与世界，可搜索正文、按类别和资料片筛选。",
};

export default function CodexPage() {
  return (
    <main className="mx-auto max-w-[1400px] px-4 py-6 text-white sm:py-8">
      <CodexHeader
        active="entries"
        intro="战地 1 游戏里的全部百科条目，从武器、载具到战争里的人物和战役。文字和图片都原样存在本站，EA 的服务下线以后也能在这里查到。"
      />
      <CodexBrowser />
      <CodexFootnote />
    </main>
  );
}
