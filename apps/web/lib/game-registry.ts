/**
 * 前端游戏元数据注册表
 * 与后端 GameRegistry 对应，包含展示信息与路由信息
 */

export type GameId = "bf1" | "bf6" | "bfv" | "bf2042";

export interface GameMeta {
  id: GameId;
  displayName: string;
  shortName: string;
  themeToken: string; // 对应 [data-theme="<token>"]
  /** MVP 是否启用 */
  enabled: boolean;
  /** 卡片副标题 */
  tagline: string;
  /** 图标路径（public/） */
  iconPath: string;
  /** 着陆页游戏卡片用的官方封面 key art（public/） */
  cardImage: string;
  /** 封面图里没有游戏 logo 时，卡片上叠加的文字标识 */
  cardWordmark?: string;
}

export const GAMES: Record<GameId, GameMeta> = {
  bf1: {
    id: "bf1",
    displayName: "Battlefield 1",
    shortName: "BF1",
    themeToken: "bf1",
    enabled: true,
    tagline: "战争废土，重返一战",
    iconPath: "/games/bf1.svg",
    cardImage: "/bf1/backgrounds/general/general-5.jpg",
  },
  bf6: {
    id: "bf6",
    displayName: "Battlefield 6",
    shortName: "BF6",
    themeToken: "bf6",
    enabled: true,
    tagline: "全面战争，现代战场",
    iconPath: "/games/bf6.svg",
    cardImage: "/bf6/key-art.webp",
    cardWordmark: "BATTLEFIELD 6",
  },
  bfv: {
    id: "bfv",
    displayName: "Battlefield V",
    shortName: "BFV",
    themeToken: "bfv",
    enabled: false,
    tagline: "二战群像（即将到来）",
    iconPath: "/games/bfv.svg",
    cardImage: "/bfv/backgrounds/key-art.jpg",
  },
  bf2042: {
    id: "bf2042",
    displayName: "Battlefield 2042",
    shortName: "BF2042",
    themeToken: "bf2042",
    enabled: false,
    tagline: "近未来全境战场（即将到来）",
    iconPath: "/games/bf2042.svg",
    cardImage: "/bf2042/backgrounds/key-art.jpg",
  },
};

export const ENABLED_GAMES: GameMeta[] = Object.values(GAMES).filter((g) => g.enabled);

export function getGame(id: string): GameMeta | undefined {
  return GAMES[id as GameId];
}

export function isValidGame(id: string): id is GameId {
  return id in GAMES;
}
