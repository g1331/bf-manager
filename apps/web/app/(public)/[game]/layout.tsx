import { notFound } from "next/navigation";
import { isValidGame, getGame, type GameId } from "@/lib/game-registry";
import { AppHeader } from "@/components/layout/AppHeader";

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
    <div data-theme={meta.themeToken} className="bg-background text-foreground min-h-screen">
      <AppHeader game={game as GameId} />
      {children}
    </div>
  );
}
