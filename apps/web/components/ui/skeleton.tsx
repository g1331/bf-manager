import { cn } from "@/lib/utils";

/**
 * 骨架占位块：暗色玻璃风的脉动矩形，供各路由段 loading.tsx 在真实内容就绪前占位。
 * 配色对齐应用内玻璃面板（border-white/10 bg-white/[0.04]）的亮度层级，
 * 避免骨架比真实内容更亮产生闪烁感。
 */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded-sm bg-white/[0.07]", className)}
      {...props}
    />
  );
}

export { Skeleton };
