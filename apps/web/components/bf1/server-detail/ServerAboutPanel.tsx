"use client";

import { ArrowRight } from "lucide-react";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { SectionHeading } from "@/components/layout/SectionHeading";
import type { ServerSettings } from "@/lib/api/bf1";

/**
 * 官服默认规则（取自生产上多台官方征服 / 行动服的设置，彼此一致）。规则摘要只列与它不同的项，
 * 回合时限 0、制式步枪关闭这类默认值不再被当成服主的改动。不在表里的条目不参与比较。
 */
const DEFAULT_RULES: Record<string, Record<string, string>> = {
  Kits: { 侦察兵: "on", 医护兵: "on", 支援兵: "on", 突击兵: "on", 精英兵种: "on" },
  Vehicles: { 地面载具: "on", 空中载具: "on" },
  Weapons: {
    兵种配备: "on",
    冲锋枪: "on",
    制式步枪: "off",
    半自动步枪: "on",
    单动式步枪: "on",
    手枪: "on",
    爆裂物: "on",
    轻机枪: "on",
    近战武器: "on",
    霰弹枪: "on",
  },
  Misc: {
    "3D 索敌": "on",
    允许较高延迟: "off",
    击杀镜头: "on",
    加载填满弹匣: "off",
    友军炮火: "off",
    只能在小队长附近重生: "off",
    名牌: "on",
    地图投票: "on",
    延迟锁定: "off",
    抬头显示: "on",
    无上限弹匣: "off",
    机械巨兽: "on",
    永久迷雾: "off",
    瞄准辅助减速: "on",
    瞄准辅助自动转向: "on",
    禁用回合前就绪阶段: "off",
    禁用观众延迟: "off",
    禁用队伍平衡: "off",
    自动回复生命值: "on",
    载具第三人称视角: "on",
    迷你地图标记: "on",
  },
  Scales: { 兵力值: "1.0", 回合时限: "0.0", 子弹伤害: "1.0", 载具重置时间: "1.0", 重生时间: "1.0" },
};

const TOGGLE_GROUPS = ["Kits", "Vehicles", "Weapons", "Misc"] as const;

/** 与官服默认不同的开关项，分成「关掉了」与「打开了」两组 */
function diffToggles(settings: ServerSettings): { off: string[]; on: string[] } {
  const off: string[] = [];
  const on: string[] = [];
  for (const group of TOGGLE_GROUPS) {
    for (const [name, raw] of Object.entries(settings[group] ?? {})) {
      const def = DEFAULT_RULES[group][name];
      const value = String(raw).toLowerCase();
      if (!def || value === def) continue;
      (value === "on" ? on : off).push(name);
    }
  }
  return { off, on };
}

/**
 * 服务器介绍 + 规则摘要。摘要只列与官服默认不同的项：倍率改动、被关掉的、被打开的；
 * 完整矩阵在「规则」分区。
 */
export function ServerAboutPanel({
  description,
  settings,
  descriptions,
  onShowRules,
}: {
  description: string | null;
  settings: ServerSettings;
  descriptions: Record<string, string>;
  onShowRules: () => void;
}) {
  const scales = Object.entries(settings.Scales ?? {})
    .filter(([name, v]) => name in DEFAULT_RULES.Scales && v !== DEFAULT_RULES.Scales[name])
    .map(([name, v]) => [name, Number(v)] as const)
    .filter(([, v]) => Number.isFinite(v));
  const toggles = diffToggles(settings);
  const changed = [
    { label: "关闭了", names: toggles.off },
    { label: "开启了", names: toggles.on },
  ].filter((g) => g.names.length > 0);
  const hasSettings = Object.keys(settings).length > 0;

  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="h-full bg-black/45 p-3.5 backdrop-blur-sm sm:p-6"
    >
      <SectionHeading>服务器介绍</SectionHeading>
      {description ? (
        <p className="text-sm leading-relaxed whitespace-pre-line text-white/80">{description}</p>
      ) : (
        <p className="text-sm text-white/40">服主没有填写介绍</p>
      )}

      {hasSettings ? (
        <div className="mt-6 border-t border-white/10 pt-5">
          <div className="flex items-baseline justify-between">
            <h3 className="text-xs font-semibold tracking-[0.2em] text-white/55">
              规则改动{" "}
              <span className="font-normal tracking-normal text-white/35">对比官服默认</span>
            </h3>
            <button
              type="button"
              onClick={onShowRules}
              className="group flex items-center gap-1 text-xs text-amber-400/90 hover:text-amber-300"
            >
              全部规则
              <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
            </button>
          </div>

          {scales.length === 0 && changed.length === 0 ? (
            <p className="mt-3 text-sm text-white/45">与官服默认规则一致</p>
          ) : null}

          {scales.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {scales.map(([name, v]) => (
                <span
                  key={name}
                  title={descriptions[name] ?? name}
                  className="inline-flex items-baseline gap-1.5 border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-xs"
                >
                  <span className="text-white/70">{name}</span>
                  <span className="font-semibold text-amber-300 tabular-nums">
                    {Math.round(v * 100)}%
                  </span>
                </span>
              ))}
            </div>
          ) : null}

          {changed.length > 0 ? (
            <dl className="mt-3 space-y-2 text-xs">
              {changed.map((g) => (
                <div key={g.label} className="flex gap-3">
                  <dt className="w-12 shrink-0 text-white/45">{g.label}</dt>
                  <dd className="min-w-0 flex-1 leading-relaxed text-white/75">
                    {g.names.join("、")}
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      ) : null}
    </Bf1Panel>
  );
}
