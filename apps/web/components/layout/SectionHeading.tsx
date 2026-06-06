import { cn } from "@/lib/utils";

/** 区块标题：中性刻线 + 标题，延续工业风排版而不铺色。 */
export function SectionHeading({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-2.5", className ?? "mb-3")}>
      <span className="bg-foreground h-4 w-[3px] shrink-0" />
      <h2 className="text-lg font-semibold">{children}</h2>
    </div>
  );
}
