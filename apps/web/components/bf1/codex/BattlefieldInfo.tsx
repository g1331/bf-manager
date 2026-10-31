"use client";

import { useState } from "react";
import Link from "next/link";
import * as Popover from "@radix-ui/react-popover";
import { ArrowRight, Info, Quote } from "lucide-react";
import { Drawer, DrawerContent, DrawerDescription, DrawerTitle } from "@/components/ui/drawer";
import { useIsDesktop } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/utils";

type Battlefield = typeof import("@/lib/bf1/codex/battlefield");
type Intros = Record<string, { header: string; excerpt: string }>;

/**
 * 图鉴数据第一次点开时才拉：battlefield 模块带着模式、地图和贴士，地图简介是导出时截好的摘要。
 * 服务器页本身不为这个说明多背一份数据。
 */
let dataPromise: Promise<{ bf: Battlefield; intros: Intros }> | null = null;
function loadData() {
  dataPromise ??= Promise.all([
    import("@/lib/bf1/codex/battlefield"),
    import("@/lib/bf1/codex/data/map-intros.json"),
  ]).then(([bf, intros]) => ({ bf, intros: intros.default as Intros }));
  return dataPromise;
}

interface Props {
  kind: "map" | "mode";
  /** 地图或模式代号，如 MP_Amiens、Conquest */
  id: string;
  /** 页面上显示的名字，用于按钮的无障碍标签 */
  label: string;
  /** 气泡和图标的间距；图标挨着大号标题时加大，免得盖住文字下沿 */
  sideOffset?: number;
  className?: string;
}

/**
 * 地图、模式名字旁边的 ⓘ：点开看图鉴里的介绍。桌面端贴着图标弹出气泡卡片，
 * 手机上从底部滑出抽屉；按钮的可点区域在手机上保持 44px。
 */
export function BattlefieldInfo({ kind, id, label, sideOffset = 8, className }: Props) {
  const isDesktop = useIsDesktop();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<{ bf: Battlefield; intros: Intros }>();
  // 每次打开换一条贴士，在打开的那一下抽，不在渲染里随机
  const [tipSeed, setTipSeed] = useState(0);

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (next) {
      setTipSeed(Math.random());
      if (!data) void loadData().then(setData);
    }
  };

  const title = kind === "map" ? `关于地图「${label}」` : `关于模式「${label}」`;
  const trigger = (
    <button
      type="button"
      aria-label={title}
      title={kind === "map" ? "地图介绍" : "模式介绍"}
      onClick={isDesktop ? undefined : () => onOpenChange(true)}
      className={cn(
        "compact-action inline-flex size-11 shrink-0 items-center justify-center text-white/45 transition-colors hover:text-amber-300 focus-visible:text-amber-300 data-[state=open]:text-amber-300 lg:size-7",
        className,
      )}
    >
      <Info className="size-4" />
    </button>
  );
  const body = <InfoBody kind={kind} id={id} label={label} data={data} tipSeed={tipSeed} />;

  if (isDesktop) {
    return (
      <Popover.Root open={open} onOpenChange={onOpenChange}>
        <Popover.Trigger asChild>{trigger}</Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            side="bottom"
            align="end"
            sideOffset={sideOffset}
            collisionPadding={16}
            aria-label={title}
            className="data-[state=open]:animate-in data-[state=open]:fade-in data-[state=closed]:animate-out data-[state=closed]:fade-out z-50 w-[22rem] overflow-hidden border border-white/12 bg-neutral-950/95 text-left text-white shadow-[0_18px_50px_rgba(0,0,0,0.6)] backdrop-blur-md outline-none"
          >
            {body}
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    );
  }

  return (
    <>
      {trigger}
      <Drawer open={open} onOpenChange={onOpenChange} shouldScaleBackground={false}>
        <DrawerContent className="border-white/10 bg-neutral-950 text-left text-white outline-none">
          <DrawerTitle className="sr-only">{title}</DrawerTitle>
          <DrawerDescription className="sr-only">
            图鉴里的{kind === "map" ? "地图" : "模式"}介绍
          </DrawerDescription>
          <div className="mt-3 max-h-[70vh] overflow-y-auto">{body}</div>
        </DrawerContent>
      </Drawer>
    </>
  );
}

function InfoBody({
  kind,
  id,
  label,
  data,
  tipSeed,
}: {
  kind: Props["kind"];
  id: string;
  label: string;
  data?: { bf: Battlefield; intros: Intros };
  tipSeed: number;
}) {
  if (!data) {
    return (
      <div className="space-y-2.5 p-4" aria-label="正在加载介绍">
        <div className="aspect-[16/7] animate-pulse bg-white/[0.06]" />
        {[100, 92, 70].map((w) => (
          <div key={w} className="h-3.5 animate-pulse bg-white/[0.07]" style={{ width: `${w}%` }} />
        ))}
      </div>
    );
  }
  const { bf, intros } = data;

  if (kind === "mode") {
    const mode = bf.getMode(id);
    if (!mode) return <Missing text={`图鉴里没有「${label}」这个模式的资料。`} />;
    return (
      <>
        <Banner image={bf.modeImage(mode.id, 480)} eyebrow="模式" title={mode.name} />
        <div className="space-y-2 px-4 pt-3 pb-4">
          {mode.header !== mode.name ? (
            <div className="text-sm font-semibold text-white/90">{mode.header}</div>
          ) : null}
          <p className="text-[13px] leading-relaxed text-white/70">{mode.body}</p>
          <MoreLink href={`/bf1/codex/modes/${mode.id}`} label="模式详情" />
        </div>
      </>
    );
  }

  const map = bf.getMap(id);
  if (!map) return <Missing text={`图鉴里没有「${label}」这张地图的资料。`} />;
  const intro = intros[map.id];
  const tips = bf.tipsFor(map.id);
  const tip = tips.length ? tips[Math.floor(tipSeed * tips.length)] : undefined;
  return (
    <>
      <Banner
        image={bf.mapImage(map.id, 480)}
        eyebrow={`地图 · ${bf.mapExpansionLabel(map.expansion)}`}
        title={bf.mapName(map)}
      />
      <div className="space-y-2.5 px-4 pt-3 pb-4">
        {intro ? (
          <div>
            {intro.header !== bf.mapName(map) ? (
              <div className="mb-1 text-sm font-semibold text-white/90">{intro.header}</div>
            ) : null}
            <p className="text-[13px] leading-relaxed text-white/70">{intro.excerpt}</p>
          </div>
        ) : null}
        {tip ? (
          <p className="flex gap-2 border-t border-white/[0.07] pt-2.5 text-[13px] leading-relaxed text-white/60">
            <Quote className="mt-0.5 size-3.5 shrink-0 text-amber-400/60" aria-hidden />
            {tip.text}
          </p>
        ) : null}
        <MoreLink href={`/bf1/codex/maps/${map.id}`} label="地图详情" />
      </div>
    </>
  );
}

function Banner({ image, eyebrow, title }: { image: string; eyebrow: string; title: string }) {
  return (
    <div className="relative aspect-[16/7] overflow-hidden bg-black/40">
      {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
      <img src={image} alt="" className="size-full object-cover" />
      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 px-4 pb-2.5">
        <div className="text-[11px] tracking-[0.18em] text-amber-400/90">{eyebrow}</div>
        <div className="text-lg leading-tight font-bold">{title}</div>
      </div>
    </div>
  );
}

function MoreLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      prefetch={false}
      className="compact-action inline-flex h-11 items-center gap-1 text-[13px] text-amber-300/90 hover:text-amber-200 lg:h-8"
    >
      图鉴里的{label}
      <ArrowRight className="size-3.5" />
    </Link>
  );
}

function Missing({ text }: { text: string }) {
  return <p className="p-4 text-sm text-white/55">{text}</p>;
}
