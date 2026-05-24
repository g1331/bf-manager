"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Check, ChevronDown } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ENABLED_GAMES, GAMES, type GameId } from "@/lib/game-registry";
import { cn } from "@/lib/utils";

interface GameSwitcherProps {
  current: GameId;
  /** dashboard 路径前缀（如 "/dashboard"），默认 "" 走公开页 */
  basePath?: string;
}

export function GameSwitcher({ current, basePath = "" }: GameSwitcherProps) {
  const pathname = usePathname();
  const currentMeta = GAMES[current];

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" className="gap-2">
          <span className="font-medium">{currentMeta.shortName}</span>
          <ChevronDown className="size-4 opacity-60" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>切换游戏</DialogTitle>
          <DialogDescription>选择要查询或管理的游戏</DialogDescription>
        </DialogHeader>
        <ul className="grid gap-2">
          {ENABLED_GAMES.map((game) => {
            const isCurrent = game.id === current;
            const targetPath = basePath
              ? `${basePath}/${game.id}`
              : pathname.replace(/^\/(bf1|bfv|bf2042)/, `/${game.id}`);
            return (
              <li key={game.id}>
                <Link
                  href={targetPath}
                  className={cn(
                    "flex w-full items-center justify-between rounded-md border px-4 py-3 transition",
                    isCurrent
                      ? "border-primary bg-accent"
                      : "hover:border-primary hover:bg-accent/50",
                  )}
                >
                  <span className="flex flex-col">
                    <span className="font-medium">{game.displayName}</span>
                    <span className="text-muted-foreground text-xs">{game.tagline}</span>
                  </span>
                  {isCurrent ? <Check className="text-primary size-4" /> : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
