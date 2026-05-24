"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GameSwitcher } from "@/components/layout/GameSwitcher";
import type { GameId } from "@/lib/game-registry";

export function AppHeader({ game }: { game: GameId }) {
  const pathname = usePathname();
  const router = useRouter();
  const isGameRoot = pathname === `/${game}`;

  return (
    <header className="bg-background/95 supports-[backdrop-filter]:bg-background/60 sticky top-0 z-40 border-b backdrop-blur">
      <div className="mx-auto flex h-14 max-w-5xl items-center gap-3 px-4 sm:px-6">
        {isGameRoot ? (
          <Link href={`/${game}`} className="font-semibold tracking-tight">
            BF-Manager
          </Link>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="-ml-2 gap-1.5 px-2"
            onClick={() => router.back()}
          >
            <ArrowLeft className="size-4" />
            <span>返回</span>
          </Button>
        )}
        <div className="ml-auto">
          <GameSwitcher current={game} />
        </div>
      </div>
    </header>
  );
}
