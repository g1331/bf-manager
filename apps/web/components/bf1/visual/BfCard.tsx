import Link from "next/link";
import { cn } from "@/lib/utils";

/**
 * 战地大图卡，借鉴开源复刻 BFUI（Arth101/BFUI）的 card 结构与数值：
 *   大图（高约 185px）+ 半透明黑内容区 rgba(0,0,0,.42) + 大写标题（letter-spacing）
 *   + 底部细线 action 条；hover 时内容区白底黑字反转、图片放大 1.1、action 滑出。
 * 这是经典战地主菜单（BF1/3/4/V 共用）最具辨识度的菜单卡形态。
 */
export function BfCard({
  href,
  image,
  title,
  description,
  action,
  className,
}: {
  href: string;
  image: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <Link href={href} className={cn("group block overflow-hidden", className)}>
      {/* 图区：固定高度裁切，hover 放大 */}
      <div className="h-44 overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={image}
          alt=""
          className="h-full w-full object-cover object-center transition-transform duration-500 ease-out group-hover:scale-110"
        />
      </div>
      {/* 内容区：半透明黑面板，hover 反转白底黑字 */}
      <div className="relative min-h-[150px] bg-black/40 px-5 pt-4 pb-12 backdrop-blur-sm transition-colors duration-300 group-hover:bg-white">
        <span className="font-display block text-xl font-medium tracking-wide text-white uppercase transition-colors duration-300 group-hover:text-black">
          {title}
        </span>
        {description ? (
          <p className="mt-2 text-sm leading-relaxed text-white/70 transition-colors duration-300 group-hover:text-black/70">
            {description}
          </p>
        ) : null}
        {action ? (
          <div className="absolute inset-x-0 bottom-0 translate-y-full border-t border-white/25 px-5 py-2 text-center text-sm font-medium tracking-wide text-white uppercase transition-all duration-300 group-hover:translate-y-0 group-hover:border-black/20 group-hover:text-black">
            {action}
          </div>
        ) : null}
      </div>
    </Link>
  );
}
