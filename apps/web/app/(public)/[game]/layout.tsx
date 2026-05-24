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
    <div data-theme={meta.themeToken} className="bg-background text-foreground min-h-screen">
      {children}
    </div>
  );
}
