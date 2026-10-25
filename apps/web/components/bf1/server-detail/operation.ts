import type { MapRotationItem, OperationMap } from "@/lib/api/bf1";

/** 条目在所属战役里的位置（0 起），非行动模式条目为 -1 */
export function operationStep(m: MapRotationItem): number {
  return m.operation ? m.operation.findIndex((o) => o.map_name === m.map_name) : -1;
}

/** 战役标识：取战役第一张图的代号 */
export function operationKey(m: MapRotationItem): string | null {
  return m.operation?.[0]?.map_name ?? null;
}

/** 按轮换顺序，当前战役之后下一个战役的第一张图的下标；找不到为 -1 */
export function nextOperationStart(items: MapRotationItem[], currentIdx: number): number {
  const currentKey = operationKey(items[currentIdx]);
  for (let k = 1; k < items.length; k++) {
    const j = (currentIdx + k) % items.length;
    if (operationStep(items[j]) === 0 && operationKey(items[j]) !== currentKey) return j;
  }
  return -1;
}

/**
 * 当前地图之后会打哪张。行动服不按轮换顺序走：攻破当前图进入本战役下一张；战役打完后
 * 私服的落点有 bug（常落到别的战役第二张），无法预测。其它模式就是轮换里的下一项。
 */
export type NextMap =
  | { kind: "rotation"; index: number }
  | { kind: "breakthrough"; map: OperationMap }
  | { kind: "uncertain" };

export function nextMap(items: MapRotationItem[]): NextMap | null {
  const currentIdx = items.findIndex((m) => m.is_current);
  if (currentIdx < 0) return null;
  const current = items[currentIdx];
  if (current.operation) {
    const step = operationStep(current);
    const next = step >= 0 ? current.operation[step + 1] : undefined;
    return next ? { kind: "breakthrough", map: next } : { kind: "uncertain" };
  }
  return items.length > 1 ? { kind: "rotation", index: (currentIdx + 1) % items.length } : null;
}
