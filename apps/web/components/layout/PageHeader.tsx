import { cn } from "@/lib/utils";

/**
 * 页面级标题：中性起始刻线 + 英文 kicker + 主标题 + 描述，延续工业风排版而不铺色。
 * 纯展示组件，无 hooks，可同时用于服务端与客户端组件。
 * 标题与操作按钮同处一行，描述独占下方一行，避免长描述与右侧按钮互相挤压。
 */
export function PageHeader({
  kicker,
  title,
  description,
  action,
  className,
}: {
  kicker?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("space-y-2", className)}>
      {kicker ? (
        <div className="font-display text-muted-foreground flex items-center gap-2 text-xs font-medium tracking-[0.2em] uppercase">
          <span className="bg-muted-foreground h-[2px] w-6" />
          {kicker}
        </div>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold sm:text-3xl">{title}</h1>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {description ? <p className="text-muted-foreground text-sm">{description}</p> : null}
    </header>
  );
}
