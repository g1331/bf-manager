/** 玩家详情页共用的取数与格式化小工具 */

// 兵种代号 → 中文名。后端兵种代号为小写英文，未知代号回退为原值
const SOLDIER_CLASS_LABEL: Record<string, string> = {
  assault: "突击兵",
  medic: "医疗兵",
  support: "支援兵",
  scout: "侦察兵",
  tanker: "坦克兵",
  pilot: "飞行员",
  cavalry: "骑兵",
};

export function classLabel(code: string): string {
  return SOLDIER_CLASS_LABEL[code] ?? code;
}

export function isKnownClass(code: string | null): code is string {
  return !!code && code in SOLDIER_CLASS_LABEL;
}

/** 完整数字带千分位，缺失为「—」 */
export function fmtFull(value: number | null | undefined): string {
  return value == null ? "—" : Math.round(value).toLocaleString("en-US");
}

export function fmtFixed(value: number | null | undefined, digits = 2): string {
  return value == null ? "—" : value.toFixed(digits);
}

/** 胜率（0–1），胜负都缺或为 0 时返回 null */
export function winRate(wins: number | null, losses: number | null): number | null {
  if (wins == null || losses == null || wins + losses === 0) return null;
  return wins / (wins + losses);
}

export function fmtPct(ratio: number | null, digits = 1): string {
  return ratio == null ? "—" : `${(ratio * 100).toFixed(digits)}%`;
}

/** 每分钟击杀；时长缺失或为 0 时为 null。武器 / 载具 / 兵种接口都不直接给 KPM */
export function perMinute(count: number | null, seconds: number | null): number | null {
  if (count == null || !seconds || seconds <= 0) return null;
  return count / (seconds / 60);
}

/** 秒 → 「553 小时」/「42 分钟」，生涯尺度只看到小时就够 */
export function fmtHours(seconds: number | null | undefined): string {
  if (!seconds) return "0 分钟";
  const h = Math.floor(seconds / 3600);
  return h > 0 ? `${h.toLocaleString("en-US")} 小时` : `${Math.floor(seconds / 60)} 分钟`;
}
