/**
 * BF6 玩家链接与平台显示。
 *
 * 战绩接口只认 nucleus ID，不返回名字；链接里带上显示名和平台，详情页用它们重新查一次（后端有缓存），
 * 查到的 ID 和地址里的一致才显示名字和头像，避免改地址栏冒充别人。
 */
import type { Bf6Platform } from "@/lib/api/bf6";

/** Drop API 返回的命名空间 → 查人接口的平台参数与显示名 */
const NAMESPACES: Record<string, { param: Bf6Platform; label: string }> = {
  cem_ea_id: { param: "ea", label: "EA" },
  ps3: { param: "psn", label: "PlayStation" },
  xbox: { param: "xbox", label: "Xbox" },
  epic: { param: "epic", label: "Epic" },
};

export function platformLabel(namespace: string | null | undefined): string | null {
  return namespace ? (NAMESPACES[namespace]?.label ?? null) : null;
}

export function platformParam(namespace: string | null | undefined): Bf6Platform | null {
  return namespace ? (NAMESPACES[namespace]?.param ?? null) : null;
}

const PARAMS: readonly Bf6Platform[] = ["ea", "psn", "xbox", "steam", "epic"];

export function parsePlatform(v: string | null): Bf6Platform | null {
  return PARAMS.find((p) => p === v) ?? null;
}

export function bf6PlayerHref(p: {
  nucleus_id: number;
  display_name: string | null;
  /** Drop API 命名空间（cem_ea_id / ps3 …） */
  platform: string | null;
}): string {
  const qs = new URLSearchParams();
  if (p.display_name) qs.set("name", p.display_name);
  const param = platformParam(p.platform);
  if (param) qs.set("platform", param);
  const query = qs.toString();
  return `/bf6/player/${p.nucleus_id}${query ? `?${query}` : ""}`;
}
