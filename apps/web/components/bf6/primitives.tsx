/**
 * BF6 战绩页的基础件：分区标题、面板、统计格、比例条、遮罩图标。
 * 视觉取自游戏 UI：冷灰面板 + 信号橙，面板左上 / 右下有直角刻线，大面板切角。
 */
import type { CSSProperties, ReactNode } from "react";
import { cn } from "@/lib/utils";

/** 用 SVG 当遮罩、颜色跟随 currentColor 的图标，图标原色不影响主题 */
export function MaskIcon({ src, className }: { src: string; className?: string }) {
  const mask = `url(${src}) center / contain no-repeat`;
  return (
    <span
      aria-hidden
      className={cn("inline-block shrink-0 bg-current", className)}
      style={{ mask, WebkitMask: mask }}
    />
  );
}

/** 分区标题：01 生涯之最 CAREER BESTS ——————— 右侧附注 */
export function SectionTitle({
  index,
  title,
  en,
  aside,
}: {
  index: string;
  title: string;
  en: string;
  aside?: ReactNode;
}) {
  return (
    <div className="mt-10 mb-4 flex items-baseline gap-3.5 first:mt-0 sm:mt-11">
      <span className="text-bf6 font-mono text-[11px] tracking-[0.15em]">{index}</span>
      <h2 className="text-bf6-fg text-lg font-bold tracking-[0.04em] sm:text-xl">{title}</h2>
      <span className="font-display text-bf6-mute hidden text-xs tracking-[0.3em] uppercase sm:inline">
        {en}
      </span>
      <span className="bg-bf6-line h-px flex-1 self-center" />
      {aside ? <span className="text-bf6-mute text-xs">{aside}</span> : null}
    </div>
  );
}

export function Panel({
  children,
  className,
  ticks = true,
}: {
  children: ReactNode;
  className?: string;
  ticks?: boolean;
}) {
  return (
    <div
      className={cn(
        "border-bf6-line bg-bf6-panel relative border",
        ticks && "bf6-ticks",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** 面板小标题：橙色竖条 + 标题，右侧可放说明 */
export function PanelTitle({ children, note }: { children: ReactNode; note?: ReactNode }) {
  return (
    <div className="text-bf6-fg flex items-center gap-2.5 text-[15px] font-bold tracking-[0.06em]">
      <span className="bg-bf6 h-3.5 w-[3px]" />
      {children}
      {note ? (
        <span className="text-bf6-mute ml-auto text-xs font-normal tracking-normal">{note}</span>
      ) : null}
    </div>
  );
}

/** 标签 + 大号数字 */
export function Stat({
  label,
  value,
  unit,
  note,
  size = "md",
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: string;
  note?: ReactNode;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <span className="text-bf6-mute block truncate text-xs">{label}</span>
      <b
        className={cn(
          "font-display text-bf6-fg mt-0.5 block font-medium tabular-nums",
          size === "sm" && "text-base",
          size === "md" && "text-xl sm:text-2xl",
          size === "lg" && "text-[26px] sm:text-[34px] sm:leading-tight",
        )}
      >
        {value}
        {unit ? <small className="ml-0.5 text-[0.55em] font-normal">{unit}</small> : null}
        {note ? (
          <em className="text-bf6-mute ml-1.5 font-sans text-[11px] font-normal not-italic">
            {note}
          </em>
        ) : null}
      </b>
    </div>
  );
}

/** 细比例条，宽度按 ratio（0–1） */
export function Bar({
  ratio,
  className,
  color = "bg-bf6",
}: {
  ratio: number;
  className?: string;
  color?: string;
}) {
  return (
    <div className={cn("h-[3px] bg-white/10", className)}>
      <div
        className={cn("h-full", color)}
        style={{ width: `${Math.min(1, Math.max(0, ratio)) * 100}%` }}
      />
    </div>
  );
}

/** 胜 / 负两段条 */
export function WinLossBar({
  wins,
  losses,
  className,
}: {
  wins: number | null;
  losses: number | null;
  className?: string;
}) {
  const total = (wins ?? 0) + (losses ?? 0);
  if (!total) return <div className={cn("h-1 bg-white/10", className)} />;
  return (
    <div className={cn("flex h-1 gap-0.5", className)}>
      <i className="bg-bf6-win block" style={{ width: `${((wins ?? 0) / total) * 100}%` }} />
      <i className="bg-bf6-loss block" style={{ width: `${((losses ?? 0) / total) * 100}%` }} />
    </div>
  );
}

/** 胜率圆环 */
export function Ring({ ratio, size = 64 }: { ratio: number | null; size?: number }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  const style: CSSProperties = { width: size, height: size };
  return (
    <div className="relative shrink-0" style={style}>
      <svg viewBox="0 0 64 64" className="size-full -rotate-90">
        <circle cx="32" cy="32" r={r} fill="none" stroke="#2a2e31" strokeWidth="5" />
        <circle
          cx="32"
          cy="32"
          r={r}
          fill="none"
          stroke="var(--color-bf6)"
          strokeWidth="5"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - (ratio ?? 0))}
        />
      </svg>
      <div className="font-display text-bf6-fg absolute inset-0 grid place-items-center text-[15px] font-semibold tabular-nums">
        {ratio == null ? "—" : `${Math.round(ratio * 100)}%`}
      </div>
    </div>
  );
}

/** 筛选按钮组：全部 66 / 突击步枪 12 / … */
export function FilterChips<K extends string>({
  options,
  value,
  onChange,
}: {
  options: ReadonlyArray<{ key: K; label: string; count: number }>;
  value: K;
  onChange: (k: K) => void;
}) {
  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          aria-pressed={value === o.key}
          onClick={() => onChange(o.key)}
          className={cn(
            "border px-3 py-1.5 text-[13px] transition-colors",
            value === o.key
              ? "border-bf6 bg-bf6 text-black"
              : "border-bf6-line-strong bg-bf6-panel text-bf6-fg2 hover:text-bf6-fg",
          )}
        >
          {o.label}
          <b
            className={cn(
              "font-display ml-1.5 font-medium tabular-nums",
              value === o.key ? "text-black/60" : "text-bf6-mute",
            )}
          >
            {o.count}
          </b>
        </button>
      ))}
    </div>
  );
}
