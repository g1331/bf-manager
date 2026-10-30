"use client";

import { ArrowLeft } from "lucide-react";
import { useBack } from "@/hooks/useNavigation";
import { type CodexEntry, codexPlainText } from "@/lib/bf1/codex/codex";
import { CopyButton } from "./CopyButton";

/** 详情页的复制按钮：链接用当前访问的域名拼，所以放在客户端 */
export function CodexCopyActions({ entry, body }: { entry: CodexEntry; body: string }) {
  const link = () => `${window.location.origin}/bf1/codex/${entry.code}`;
  return (
    <div className="flex flex-wrap gap-2">
      <CopyButton
        kind="text"
        label="复制正文"
        text={() => codexPlainText(entry, body, link())}
        className="flex-1 sm:flex-none"
      />
      <CopyButton kind="link" label="复制链接" text={link} className="flex-1 sm:flex-none" />
    </div>
  );
}

/** 桌面端的返回：回到真正来的那一页（保留筛选），直接打开时退到百科列表。手机端由顶栏返回键负责 */
export function CodexBack({ fallback }: { fallback: string }) {
  const back = useBack(fallback);
  return (
    <button
      type="button"
      onClick={back}
      className="hidden items-center gap-1.5 text-sm text-white/55 transition-colors hover:text-white lg:inline-flex"
    >
      <ArrowLeft className="size-4" />
      返回
    </button>
  );
}
