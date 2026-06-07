import { notFound } from "next/navigation";
import { isValidGame, getGame } from "@/lib/game-registry";

interface GameLayoutProps {
  children: React.ReactNode;
  params: Promise<{ game: string }>;
}

export default async function GameLayout({ children, params }: GameLayoutProps) {
  const { game } = await params;
  if (!isValidGame(game)) notFound();
  const meta = getGame(game)!;
  if (!meta.enabled) notFound();

  return (
    // 仅承载 data-theme 与文字色，不铺实色背景，让底层战场氛围（AmbientBackground）透出。
    // 详情页自带 fixed 专属背景层（地图 / 生涯图），覆盖在此氛围之上，互不影响。
    // 桌面端以块级方式撑满外层滚动容器并向下传递确定高度：自身撑满高度的页面（服务器列表）
    // 据此把滚动收进内部区域；普通长内容页（玩家列表 / 详情）的 main 高度自然增长、由外层
    // 容器整体滚动。这里刻意保持块级而非 flex 列，避免 main 在 flex 交叉轴上被外层
    // `mr-auto` 规则触发收缩、退化为内容宽度而无法铺满主内容区。
    <div data-theme={meta.themeToken} className="text-foreground lg:h-full lg:min-h-0">
      {children}
    </div>
  );
}
