/** BF6 战绩查询的「最近查看」 */

import { createRecentList } from "@/lib/recent-list";

export interface Bf6RecentPlayer {
  nucleus_id: number;
  display_name: string;
  avatar_url: string | null;
  platform: string | null;
}

const recent = createRecentList<Bf6RecentPlayer>("bf6:recent-players", (p) => p.nucleus_id);

export const pushBf6RecentPlayer = recent.push;
export const clearBf6RecentPlayers = recent.clear;
export const useBf6RecentPlayers = recent.useList;
