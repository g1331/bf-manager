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
    // 桌面端撑满外层滚动容器并作 flex 列：自身撑满高度的页面（服务器列表）据此把滚动
    // 收进内部区域；普通长内容页（玩家列表 / 详情）的 main 高度自然增长、由外层容器整体滚动。
    <div
      data-theme={meta.themeToken}
      className="text-foreground lg:flex lg:h-full lg:min-h-0 lg:flex-col"
    >
      {children}
    </div>
  );
}
