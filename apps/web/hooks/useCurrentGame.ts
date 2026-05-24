"use client";

import { useParams } from "next/navigation";
import { getGame, type GameMeta } from "@/lib/game-registry";

/** 从动态路由 [game] 段读取当前游戏元数据 */
export function useCurrentGame(): GameMeta | undefined {
  const params = useParams<{ game?: string }>();
  if (!params?.game) return undefined;
  return getGame(params.game);
}
