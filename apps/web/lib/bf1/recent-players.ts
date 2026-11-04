/** BF1 战绩查询的「最近查看」 */

import { createRecentList } from "@/lib/recent-list";

export interface RecentPlayer {
  persona_id: number;
  display_name: string;
  avatar_url: string | null;
}

const recent = createRecentList<RecentPlayer>("bf1:recent-players", (p) => p.persona_id);

export const pushRecentPlayer = recent.push;
export const clearRecentPlayers = recent.clear;
export const useRecentPlayers = recent.useList;
