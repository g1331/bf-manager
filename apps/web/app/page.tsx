import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ENABLED_GAMES, GAMES } from "@/lib/game-registry";
import { cn } from "@/lib/utils";

export default function HomePage() {
  const allGames = Object.values(GAMES);
  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-10 px-4 py-10 sm:px-6 lg:py-16">
      <header className="flex flex-col gap-3">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">BF-Manager</h1>
        <p className="text-muted-foreground text-base sm:text-lg">
          Battlefield 系列战绩查询与服务器管理平台。选择一款游戏开始使用。
        </p>
      </header>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {allGames.map((game) => {
          const inner = (
            <Card
              className={cn(
                "h-full transition-all",
                game.enabled
                  ? "hover:border-primary cursor-pointer hover:shadow-md"
                  : "cursor-not-allowed opacity-60",
              )}
            >
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span>{game.displayName}</span>
                  <span className="text-muted-foreground text-xs font-normal">
                    {game.shortName}
                  </span>
                </CardTitle>
                <CardDescription>{game.tagline}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-muted-foreground text-sm">
                  {game.enabled ? "点击进入战绩与服管" : "即将到来"}
                </div>
              </CardContent>
            </Card>
          );

          return game.enabled ? (
            <Link key={game.id} href={`/${game.id}`} prefetch={false}>
              {inner}
            </Link>
          ) : (
            <div key={game.id}>{inner}</div>
          );
        })}
      </section>

      <footer className="text-muted-foreground mt-auto pt-8 text-center text-xs">
        MVP · 当前启用 {ENABLED_GAMES.length} 款游戏 · MIT License
      </footer>
    </main>
  );
}
