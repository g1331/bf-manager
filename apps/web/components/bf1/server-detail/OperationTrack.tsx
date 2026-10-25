"use client";

import { Fragment } from "react";
import type { OperationProgress } from "@/lib/api/bf1";
import { FACTION_SLUG } from "@/lib/bf1/factions";
import { cn } from "@/lib/utils";

/** 游戏 HUD 里的区域箭头：右侧尖角、左侧内凹 */
const CHEVRON = "polygon(0 0,calc(100% - 5px) 0,100% 50%,calc(100% - 5px) 100%,0 100%,5px 50%)";

/**
 * 行动进度条，仿游戏顶部 HUD 与行动地图界面：攻方旗帜 → 每张图「缩略图 + 区域箭头链」→
 * 守方旗帜。攻方已拿下的区域为蓝色，守方仍在坚守的为红色，正在争夺的区域闪烁。
 */
export function OperationTrack({ operation }: { operation: OperationProgress }) {
  const { maps, map_index, sectors_taken } = operation;
  const current = maps[map_index];
  const total = current?.sectors ?? null;

  return (
    <div className="mt-4 flex flex-col gap-1.5 lg:items-end">
      <div className="flex flex-wrap items-center gap-1.5 lg:justify-end">
        <FactionFlag faction={operation.attacker} />
        {maps.map((m, i) => (
          <Fragment key={m.name}>
            {i > 0 ? <span className="mx-0.5 h-px w-2 bg-white/30" aria-hidden /> : null}
            <div className={cn("flex items-center gap-1", i > map_index && "opacity-50")}>
              {m.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={m.image_url}
                  alt=""
                  title={m.name}
                  className={cn(
                    "h-[18px] w-8 object-cover",
                    i === map_index ? "ring-1 ring-amber-400" : "opacity-70",
                  )}
                />
              ) : null}
              {m.sectors ? (
                <span className="flex" title={m.name}>
                  {Array.from({ length: m.sectors }, (_, s) => {
                    const taken = i < map_index || (i === map_index && s < sectors_taken);
                    const fighting = i === map_index && s === sectors_taken;
                    return (
                      <span
                        key={s}
                        className={cn(
                          "-ml-[3px] h-[18px] w-4 first:ml-0",
                          taken ? "bg-sky-500" : "bg-red-500/85",
                          fighting && "animate-pulse",
                        )}
                        style={{ clipPath: CHEVRON }}
                      />
                    );
                  })}
                </span>
              ) : null}
            </div>
          </Fragment>
        ))}
        <FactionFlag faction={operation.defender} />
      </div>
      <div className="text-xs text-white/55 tabular-nums">
        {total != null
          ? sectors_taken >= total
            ? "本图已攻破"
            : `区域 ${sectors_taken + 1}/${total}`
          : `已拿下 ${sectors_taken} 区`}
        {maps.length > 1 ? ` · 第 ${map_index + 1}/${maps.length} 张图` : null}
      </div>
    </div>
  );
}

function FactionFlag({ faction }: { faction: string | null }) {
  const slug = faction ? FACTION_SLUG[faction] : undefined;
  if (!slug) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`/factions/${slug}.png`}
      alt={faction ?? ""}
      title={faction ?? ""}
      className="size-6 object-contain drop-shadow"
    />
  );
}
