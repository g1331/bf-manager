import { Fragment } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

/** 详情页顶部的位置：图鉴 / 分区 / 分类 */
export function Breadcrumbs({ items }: { items: Array<{ label: string; href: string }> }) {
  return (
    <nav
      aria-label="位置"
      className="flex flex-wrap items-center gap-1.5 text-xs text-white/45 lg:mt-4"
    >
      {items.map((it, i) => (
        <Fragment key={it.href + it.label}>
          {i > 0 ? <span className="text-white/20">/</span> : null}
          <Link href={it.href} className="inline-action hover:text-white">
            {it.label}
          </Link>
        </Fragment>
      ))}
    </nav>
  );
}

export interface StepItem {
  href: string;
  name: string;
  image: string;
  /** 缩略图的形状：百科是竖卡，狗牌是圆片，勋章是透明底 */
  shape: "card" | "round" | "free";
}

/** 详情页底部的上一条 / 下一条 */
export function StepNav({ prev, next }: { prev?: StepItem; next?: StepItem }) {
  return (
    <nav aria-label="翻页" className="mt-12 grid grid-cols-2 gap-3 sm:gap-4">
      {prev ? <StepLink item={prev} dir="prev" /> : <span />}
      {next ? <StepLink item={next} dir="next" /> : <span />}
    </nav>
  );
}

function StepLink({ item, dir }: { item: StepItem; dir: "prev" | "next" }) {
  const next = dir === "next";
  return (
    <Link
      href={item.href}
      className={cn(
        "group flex min-w-0 items-center gap-3 border border-white/10 bg-black/30 p-2.5 transition-colors hover:border-amber-400/50",
        next && "flex-row-reverse text-right",
      )}
    >
      {next ? (
        <ChevronRight className="size-5 shrink-0 text-white/40 group-hover:text-amber-300" />
      ) : (
        <ChevronLeft className="size-5 shrink-0 text-white/40 group-hover:text-amber-300" />
      )}
      {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp */}
      <img
        src={item.image}
        alt=""
        loading="lazy"
        className={cn(
          "hidden h-16 shrink-0 sm:block",
          item.shape === "card" && "w-auto ring-1 ring-white/10",
          item.shape === "round" && "w-16 rounded-full",
          item.shape === "free" && "w-16 object-contain",
        )}
      />
      <span className="min-w-0">
        <span className="block text-[11px] text-white/40">{next ? "下一条" : "上一条"}</span>
        <span className="block truncate text-sm font-medium text-white/90 group-hover:text-amber-200">
          {item.name}
        </span>
      </span>
    </Link>
  );
}

/** 详情页正文右栏：压在战场氛围图上，桌面端垫一层深色面板保证可读 */
export function DetailPanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="max-w-[42rem] min-w-0 lg:border lg:border-white/[0.06] lg:bg-black/45 lg:p-8 lg:backdrop-blur-sm">
      {children}
    </div>
  );
}

/** 分区列表里的分组标题，带锚点，可以从页首的分组目录直接跳过来 */
export function GroupHeading({ id, title, count }: { id: string; title: string; count: number }) {
  return (
    <h2
      id={id}
      className="flex scroll-mt-28 items-baseline gap-2 text-lg font-semibold tracking-wide lg:scroll-mt-20"
    >
      <span className="h-4 w-[3px] self-center bg-amber-500" aria-hidden />
      {title}
      <span className="text-xs font-normal text-white/40 tabular-nums">{count}</span>
    </h2>
  );
}

/** 页首的分组目录：横向一排锚点 */
export function GroupIndex({
  groups,
}: {
  groups: Array<{ id: string; title: string; count: number }>;
}) {
  return (
    <div className="-mx-4 mt-5 flex [scrollbar-width:none] gap-1.5 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0 [&::-webkit-scrollbar]:hidden">
      {groups.map((g) => (
        <a
          key={g.id}
          href={`#${g.id}`}
          className="compact-action flex h-9 shrink-0 items-center gap-1.5 border border-white/20 px-3 text-[13px] whitespace-nowrap text-white/65 transition-colors hover:border-white/45 hover:text-white sm:h-8 sm:px-2.5 sm:text-xs"
        >
          {g.title}
          <span className="text-white/35 tabular-nums">{g.count}</span>
        </a>
      ))}
    </div>
  );
}
