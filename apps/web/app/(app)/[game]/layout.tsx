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
    <div data-theme={meta.themeToken} className="text-foreground">
      {children}
    </div>
  );
}
