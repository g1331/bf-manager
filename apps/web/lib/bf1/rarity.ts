/**
 * BF1 稀有度阈值工具
 * 阈值参照游戏内武器/载具星级体系：每 100 击杀 1 星。
 */

export type Rarity = "gold" | "blue" | "white";

const GOLD_KILLS_THRESHOLD = 10000;
const BLUE_KILLS_THRESHOLD = 6000;

const GOLD_RANK_THRESHOLD = 150;
const BLUE_RANK_THRESHOLD = 100;

const GOLD_STARS_THRESHOLD = 100;
const BLUE_STARS_THRESHOLD = 60;

const KILLS_PER_STAR = 100;

export function rarityByKills(kills: number | null | undefined): Rarity {
  const k = kills ?? 0;
  if (k >= GOLD_KILLS_THRESHOLD) return "gold";
  if (k >= BLUE_KILLS_THRESHOLD) return "blue";
  return "white";
}

export function rarityByRank(rank: number | null | undefined): Rarity {
  const r = rank ?? 0;
  if (r >= GOLD_RANK_THRESHOLD) return "gold";
  if (r >= BLUE_RANK_THRESHOLD) return "blue";
  return "white";
}

export function starsByKills(kills: number | null | undefined): number {
  return Math.floor((kills ?? 0) / KILLS_PER_STAR);
}

export function rarityByStars(stars: number): Rarity {
  if (stars >= GOLD_STARS_THRESHOLD) return "gold";
  if (stars >= BLUE_STARS_THRESHOLD) return "blue";
  return "white";
}

export const rarityHex: Record<Rarity, string> = {
  gold: "#ca843a",
  blue: "#1e90ff",
  white: "#ffffff",
};

/**
 * 皮肤稀有度：对应 EA preset 数据里的 rarenessLevel.name。
 * 配色沿用游戏内皮肤名的着色惯例：
 *   superior 走金灰、enhanced 走蓝灰、standard 走白。
 */
export type SkinRarity = "superior" | "enhanced" | "standard";

export const skinRarityHex: Record<SkinRarity, string> = {
  superior: "#ecd996",
  enhanced: "#bfcfde",
  standard: "#ffffff",
};

/** 把上游 rarenessLevel.name（Superior/Enhanced/...）归一为本地稀有度枚举 */
export function skinRarityFromName(name: string | null | undefined): SkinRarity {
  switch (name) {
    case "Superior":
      return "superior";
    case "Enhanced":
      return "enhanced";
    default:
      return "standard";
  }
}
