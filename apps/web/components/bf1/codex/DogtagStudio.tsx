"use client";

import { useMemo, useState, useSyncExternalStore } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Search, X } from "lucide-react";
import { DarkInput } from "@/components/common/DarkInput";
import {
  type Dogtag,
  DOGTAG_SIDE_LABEL,
  dogtagImage,
  dogtagPlainText,
  DOGTAGS,
  getDogtag,
} from "@/lib/bf1/codex/collection";
import { searchTerms } from "@/lib/bf1/codex/search";
import { cn } from "@/lib/utils";
import { ShareActions } from "./CodexActions";
import { ObjectViewer } from "./viewer/ObjectViewer";

/*
 * 搭配的另一面存在地址栏 ?with= 里，复制出去的链接能还原同一块狗牌。
 * history.replaceState 不发事件，改完自己广播一次。
 */
const PARTNER_EVENT = "bfm:dogtag-partner";

function subscribe(onChange: () => void) {
  window.addEventListener("popstate", onChange);
  window.addEventListener(PARTNER_EVENT, onChange);
  return () => {
    window.removeEventListener("popstate", onChange);
    window.removeEventListener(PARTNER_EVENT, onChange);
  };
}

const readPartner = () => new URLSearchParams(window.location.search).get("with");

function setPartner(id: string | null) {
  const u = new URLSearchParams(window.location.search);
  if (id) u.set("with", id);
  else u.delete("with");
  const s = u.toString();
  window.history.replaceState(null, "", `${window.location.pathname}${s ? `?${s}` : ""}`);
  window.dispatchEvent(new Event(PARTNER_EVENT));
}

/** 只接受另一种狗牌：基本狗牌配高级狗牌，反之亦然 */
function usePartner(tag: Dogtag): Dogtag | undefined {
  const id = useSyncExternalStore(subscribe, readPartner, () => null);
  const partner = id ? getDogtag(id) : undefined;
  return partner && partner.side !== tag.side ? partner : undefined;
}

/**
 * 狗牌详情页的检视区：当前这枚贴在朝向镜头的一面，另一面可以从另一种狗牌里挑一枚搭配，
 * 不挑就是空白金属。
 */
export function DogtagStudio({ tag }: { tag: Dogtag }) {
  const partner = usePartner(tag);
  const [picking, setPicking] = useState(false);
  const otherKind = DOGTAG_SIDE_LABEL[tag.side === "front" ? "back" : "front"];

  return (
    <div>
      <ObjectViewer
        subject={{
          kind: "tag",
          front: dogtagImage(tag.id),
          back: partner ? dogtagImage(partner.id) : null,
        }}
        sideLabels={{
          front: `${DOGTAG_SIDE_LABEL[tag.side]} · ${tag.name}`,
          back: partner ? `${DOGTAG_SIDE_LABEL[partner.side]} · ${partner.name}` : "空白的一面",
        }}
        className="aspect-square max-h-[min(70vh,560px)] w-full border border-white/[0.06] bg-black/35"
        fallback={
          // eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp
          <img src={dogtagImage(tag.id)} alt={tag.name} className="size-3/4 rounded-full" />
        }
      />

      <div className="mt-3 flex items-center gap-3 border border-white/[0.07] bg-black/35 p-2.5">
        {partner ? (
          // eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp
          <img src={dogtagImage(partner.id)} alt="" className="size-10 shrink-0 rounded-full" />
        ) : (
          <span className="size-10 shrink-0 rounded-full bg-[radial-gradient(circle_at_35%_30%,#d8d4cc,#8d897f_60%,#5c5952)]" />
        )}
        <div className="min-w-0 flex-1">
          <div className="text-[11px] text-white/40">另一面</div>
          <div className="truncate text-sm text-white/85">
            {partner ? partner.name : `空白，可以挑一枚${otherKind}`}
          </div>
        </div>
        {partner ? (
          <button
            type="button"
            onClick={() => setPartner(null)}
            className="compact-action h-11 px-2 text-xs text-white/50 hover:text-white sm:h-9"
          >
            清除
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => setPicking(true)}
          className="compact-action h-11 border border-white/20 px-3 text-xs text-white/85 transition-colors hover:border-amber-400/60 hover:text-amber-300 sm:h-9"
        >
          {partner ? "更换" : "搭配"}
        </button>
      </div>

      {picking ? (
        <PartnerPicker
          side={tag.side === "front" ? "back" : "front"}
          current={partner?.id}
          onPick={(id) => {
            setPartner(id);
            setPicking(false);
          }}
          onClose={() => setPicking(false)}
        />
      ) : null}
    </div>
  );
}

/** 复制按钮：链接带上当前搭配 */
export function DogtagShare({ tag }: { tag: Dogtag }) {
  const partner = usePartner(tag);
  const path = `/bf1/codex/dogtags/${tag.id}${partner ? `?with=${partner.id}` : ""}`;
  let text = dogtagPlainText(tag, "{link}");
  if (partner) {
    text = text.replace(
      "\n\n—— ",
      `\n\n另一面：【${partner.name}】${DOGTAG_SIDE_LABEL[partner.side]}\n${partner.description}\n\n—— `,
    );
  }
  return <ShareActions text={text} path={path} />;
}

function PartnerPicker({
  side,
  current,
  onPick,
  onClose,
}: {
  side: Dogtag["side"];
  current?: string;
  onPick: (id: string | null) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const list = useMemo(() => {
    const terms = searchTerms(query);
    return DOGTAGS.filter(
      (t) =>
        t.side === side &&
        terms.every((w) => `${t.name} ${t.category} ${t.description}`.toLowerCase().includes(w)),
    );
  }, [side, query]);

  return (
    <DialogPrimitive.Root open onOpenChange={(open) => !open && onClose()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="data-[state=open]:animate-in data-[state=open]:fade-in-0 fixed inset-0 z-50 bg-black/80" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="data-[state=open]:animate-in data-[state=open]:fade-in-0 fixed inset-x-0 bottom-0 z-50 flex max-h-[85dvh] flex-col border-t border-white/10 bg-[#0d0c0a] text-white outline-none sm:inset-x-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:max-h-[80vh] sm:w-[min(760px,92vw)] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:border"
        >
          <div className="flex items-center gap-2 border-b border-white/[0.07] p-3">
            <DialogPrimitive.Title className="flex-1 text-[15px] font-semibold">
              挑一枚{DOGTAG_SIDE_LABEL[side]}
              <span className="ml-2 text-xs font-normal text-white/40">{list.length} 枚</span>
            </DialogPrimitive.Title>
            <DialogPrimitive.Close
              aria-label="关闭"
              className="flex size-10 items-center justify-center text-white/60 hover:text-white"
            >
              <X className="size-5" />
            </DialogPrimitive.Close>
          </div>
          <div className="relative p-3 pb-0">
            <Search className="pointer-events-none absolute top-1/2 left-6 mt-1.5 size-4 -translate-y-1/2 text-white/40" />
            <DarkInput
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索名称或描述"
              aria-label="搜索狗牌"
              className="h-10 pl-9"
            />
          </div>
          <div className="grid min-h-0 flex-1 auto-rows-max grid-cols-4 content-start gap-x-2 gap-y-3 overflow-y-auto overscroll-contain p-3 sm:grid-cols-6">
            <PickItem label="空白" active={!current} onClick={() => onPick(null)}>
              <span className="block aspect-square w-full rounded-full bg-[radial-gradient(circle_at_35%_30%,#d8d4cc,#8d897f_60%,#5c5952)]" />
            </PickItem>
            {list.map((t) => (
              <PickItem
                key={t.id}
                label={t.name}
                active={current === t.id}
                onClick={() => onPick(t.id)}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
                <img
                  src={dogtagImage(t.id)}
                  alt=""
                  loading="lazy"
                  className="block aspect-square w-full rounded-full"
                />
              </PickItem>
            ))}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function PickItem({
  label,
  active,
  onClick,
  children,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "compact-action group flex flex-col items-center gap-1 p-1 text-center transition-colors",
        active ? "bg-amber-400/15 ring-1 ring-amber-400/60" : "hover:bg-white/[0.05]",
      )}
    >
      {children}
      <span className="line-clamp-2 text-[11px] leading-tight text-white/70 group-hover:text-white">
        {label}
      </span>
    </button>
  );
}
