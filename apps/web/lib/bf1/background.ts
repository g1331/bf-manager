/**
 * BF1 玩家页背景图选取
 *
 * 优先级：
 *   1. 玩家最近游玩地图 → 该地图专属背景图（按 persona_id 哈希取一张）
 *   2. 通用背景池 → persona_id 哈希取一张
 *   3. CSS 渐变兜底（背景图资源未就位时）
 *
 * 背景图资源存放于 public/bf1/backgrounds 下。
 */

export const FALLBACK_GRADIENT =
  "linear-gradient(135deg, oklch(0.18 0.02 50), oklch(0.30 0.03 30) 60%, oklch(0.15 0.015 40))";

const GENERAL_POOL: string[] = [
  "/bf1/backgrounds/general/general-1.jpg",
  "/bf1/backgrounds/general/general-2.jpg",
  "/bf1/backgrounds/general/general-3.jpg",
  "/bf1/backgrounds/general/general-4.jpg",
  "/bf1/backgrounds/general/general-5.jpg",
  "/bf1/backgrounds/general/general-6.jpg",
  "/bf1/backgrounds/general/general-7.jpg",
  "/bf1/backgrounds/general/general-8.jpg",
];

/**
 * BF1 地图 → 背景图候选列表。
 * key 用 EA Stats API 返回的 map_name（蛇形命名），例如 "argonne_forest"。
 * 阶段二将按地图分类组织 /bf1/backgrounds/maps/<map_name>/*.webp 后填入。
 */
const MAP_BACKGROUNDS: Record<string, string[]> = {};

function normalizeMapKey(name: string | null | undefined): string | null {
  if (!name) return null;
  return name.toLowerCase().trim().replace(/\s+/g, "_");
}

function hashPick<T>(seed: number, pool: readonly T[]): T | null {
  if (pool.length === 0) return null;
  const i = Math.abs(Math.floor(seed)) % pool.length;
  return pool[i];
}

/**
 * 选取玩家页背景图 URL。先按最近地图取专属图，再退到通用池。
 * 无可用资源时返回 null，由调用方决定如何回落（例如改用渐变）。
 */
export function pickBackgroundUrl(
  personaId: number,
  recentMapName: string | null | undefined,
): string | null {
  const mapKey = normalizeMapKey(recentMapName);
  const mapCandidates = mapKey ? MAP_BACKGROUNDS[mapKey] : undefined;
  const fromMap = mapCandidates ? hashPick(personaId, mapCandidates) : null;
  if (fromMap) return fromMap;
  return hashPick(personaId, GENERAL_POOL);
}

/**
 * 返回可直接赋给 CSS `background` 短写的字符串。
 * 资源未就位时回落到 CSS 渐变，组件无需做额外判空。
 */
export function selectBackgroundCss(
  personaId: number,
  recentMapName: string | null | undefined,
): string {
  const url = pickBackgroundUrl(personaId, recentMapName);
  return url ? `url(${url}) center/cover no-repeat` : FALLBACK_GRADIENT;
}
