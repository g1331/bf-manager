/** BF6 战绩页的数字格式。null 一律显示「—」：EA 没给这一项，不是 0。 */

const DASH = "—";

export function fmtInt(v: number | null | undefined): string {
  return v == null ? DASH : Math.round(v).toLocaleString("en-US");
}

export function fmtFixed(v: number | null | undefined, digits = 2): string {
  return v == null ? DASH : v.toFixed(digits);
}

/** 0.281 → 28.1% */
export function fmtPct(ratio: number | null | undefined, digits = 1): string {
  return ratio == null ? DASH : `${(ratio * 100).toFixed(digits)}%`;
}

export function hours(seconds: number | null | undefined): number | null {
  return seconds ? seconds / 3600 : null;
}

/** 秒 → 小时，保留一位：451800 → 125.5 */
export function fmtHours(seconds: number | null | undefined): string {
  const h = hours(seconds);
  return h == null
    ? DASH
    : h.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
}

/** 大数缩写：≥10 万用「万」，≥1 亿用「亿」 */
export function fmtCompact(v: number | null | undefined): { value: string; unit: string } {
  if (v == null) return { value: DASH, unit: "" };
  if (v >= 1e8) return { value: (v / 1e8).toFixed(2), unit: "亿" };
  if (v >= 1e5)
    return { value: (v / 1e4).toLocaleString("en-US", { maximumFractionDigits: 1 }), unit: "万" };
  return { value: fmtInt(v), unit: "" };
}

export function fmtKm(meters: number | null | undefined): string {
  return meters == null ? DASH : Math.round(meters / 1000).toLocaleString("en-US");
}

/** 按战斗时长折算每小时次数 */
export function perHour(v: number | null | undefined, seconds: number | null | undefined): string {
  if (!v || !seconds) return DASH;
  return (v / (seconds / 3600)).toFixed(1);
}

export function share(part: number | null | undefined, total: number): number {
  return total > 0 && part ? part / total : 0;
}
