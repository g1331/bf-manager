import { notFound } from "next/navigation";
import { ENABLED_GAMES, isValidGame, getGame } from "@/lib/game-registry";

// 只有已启用的游戏才是合法的 [game] 段；其余路径（/robots.txt、拼错的地址等）在渲染前
// 直接返回 404。仅靠下面的 notFound() 不够：上层 loading.tsx 已经开始流式输出，
// 那时状态码固定为 200，只能给出「看起来像 404 的 200」
export const dynamicParams = false;

export function generateStaticParams() {
  return ENABLED_GAMES.map((g) => ({ game: g.id }));
}

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
