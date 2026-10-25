"use client";

import { useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { SectionHeading } from "@/components/layout/SectionHeading";

/* ---------- 24h 趋势面积图（手写 SVG），全服统计与服务器详情共用 ---------- */

/** SVG 逻辑坐标系尺寸；preserveAspectRatio="none" 拉伸适配容器，线宽靠 non-scaling-stroke 保持 */
const CHART_W = 1000;
const CHART_H = 240;
const CHART_PAD_TOP = 12;
const CHART_PAD_BOTTOM = 6;

/** 降采样上限：超过后按桶取均值，曲线更平滑、SVG path 更轻 */
const CHART_MAX_POINTS = 288;

/** 曲线只画 players；其它字段由 describe 渲染到 hover 读数里 */
interface TrendLike {
  ts: number;
  players: number;
}

export function TrendPanel<P extends TrendLike>({
  title,
  points: rawPoints,
  emptyText,
  describe,
}: {
  title: string;
  points: P[];
  emptyText: string;
  describe?: (p: P) => string;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const plotRef = useRef<HTMLDivElement>(null);

  const points = useMemo(() => {
    if (rawPoints.length <= CHART_MAX_POINTS) return rawPoints;
    const bucket = Math.ceil(rawPoints.length / CHART_MAX_POINTS);
    const out: P[] = [];
    for (let i = 0; i < rawPoints.length; i += bucket) {
      const slice = rawPoints.slice(i, i + bucket);
      // players 取桶均值，其它字段沿用桶中点
      out.push({
        ...slice[Math.floor(slice.length / 2)],
        players: Math.round(slice.reduce((sum, p) => sum + p.players, 0) / slice.length),
      });
    }
    return out;
  }, [rawPoints]);

  const chart = useMemo(() => {
    if (points.length < 2) return null;
    const t0 = points[0].ts;
    const span = Math.max(points[points.length - 1].ts - t0, 1);
    // 顶部留 8% 余量，避免峰值顶到面板边缘
    const yMax = Math.max(...points.map((p) => p.players), 1) * 1.08;
    const plotH = CHART_H - CHART_PAD_TOP - CHART_PAD_BOTTOM;
    const x = (p: TrendLike) => ((p.ts - t0) / span) * CHART_W;
    const y = (v: number) => CHART_PAD_TOP + (1 - v / yMax) * plotH;
    const line = points
      .map((p, i) => `${i === 0 ? "M" : "L"}${x(p).toFixed(1)} ${y(p.players).toFixed(1)}`)
      .join(" ");
    const baseline = CHART_H - CHART_PAD_BOTTOM;
    return { t0, span, yMax, x, y, line, area: `${line} L${CHART_W} ${baseline} L0 ${baseline} Z` };
  }, [points]);

  // 峰值取原始数据，不受降采样均值影响
  const peak = useMemo(
    () => (rawPoints.length > 0 ? Math.max(...rawPoints.map((p) => p.players)) : 0),
    [rawPoints],
  );

  function handleMove(e: React.MouseEvent) {
    if (!chart || !plotRef.current) return;
    const rect = plotRef.current.getBoundingClientRect();
    const targetTs = chart.t0 + ((e.clientX - rect.left) / rect.width) * chart.span;
    // 二分找到 >= targetTs 的第一个点，再与前一个点比距离取更近者
    let lo = 0;
    let hi = points.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (points[mid].ts < targetTs) lo = mid + 1;
      else hi = mid;
    }
    const idx = lo > 0 && targetTs - points[lo - 1].ts < points[lo].ts - targetTs ? lo - 1 : lo;
    setHoverIdx(idx);
  }

  const hovered = hoverIdx !== null ? points[hoverIdx] : null;

  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="bg-white/[0.03] p-5"
    >
      <div className="flex items-baseline justify-between gap-4">
        <SectionHeading className="mb-0">{title}</SectionHeading>
        <div className="text-muted-foreground shrink-0 text-xs tabular-nums">
          {hovered ? (
            <>
              {formatTime(hovered.ts)} ·{" "}
              <span className="text-foreground font-medium">
                {hovered.players.toLocaleString()}
              </span>{" "}
              人{describe ? ` · ${describe(hovered)}` : null}
            </>
          ) : (
            <>
              峰值 <span className="text-foreground font-medium">{peak.toLocaleString()}</span> 人
            </>
          )}
        </div>
      </div>

      {!chart ? (
        <div className="text-muted-foreground flex h-48 items-center justify-center text-sm">
          {emptyText}
        </div>
      ) : (
        <div className="mt-4">
          <div
            ref={plotRef}
            className="relative"
            onMouseMove={handleMove}
            onMouseLeave={() => setHoverIdx(null)}
          >
            <svg
              width="100%"
              height="192"
              viewBox={`0 0 ${CHART_W} ${CHART_H}`}
              preserveAspectRatio="none"
              className="block"
              aria-hidden
            >
              <defs>
                <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgb(245 158 11 / 0.35)" />
                  <stop offset="100%" stopColor="rgb(245 158 11 / 0.02)" />
                </linearGradient>
              </defs>
              {/* 水平参考线：峰值与半值 */}
              {[chart.y(chart.yMax / 1.08), chart.y(chart.yMax / 1.08 / 2)].map((gy) => (
                <line
                  key={gy}
                  x1="0"
                  x2={CHART_W}
                  y1={gy}
                  y2={gy}
                  stroke="rgb(255 255 255 / 0.08)"
                  strokeDasharray="4 6"
                  vectorEffect="non-scaling-stroke"
                />
              ))}
              <motion.path
                d={chart.area}
                fill="url(#trend-fill)"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.9, delay: 0.5 }}
              />
              <motion.path
                d={chart.line}
                fill="none"
                stroke="rgb(245 158 11 / 0.9)"
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 1.3, ease: "easeOut" }}
              />
            </svg>

            {/* hover 跟随竖线与圆点：HTML 绝对定位，避开 SVG 非等比拉伸 */}
            {hovered ? (
              <div
                className="pointer-events-none absolute inset-y-0"
                style={{ left: `${(chart.x(hovered) / CHART_W) * 100}%` }}
              >
                <div className="absolute inset-y-0 w-px bg-white/25" />
                <div
                  className="absolute size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.8)]"
                  style={{ top: `${(chart.y(hovered.players) / CHART_H) * 100}%`, left: "0.5px" }}
                />
              </div>
            ) : null}
          </div>

          {/* 时间轴：首 / 中 / 尾 */}
          <div className="text-muted-foreground/70 mt-2 flex justify-between text-[11px] tabular-nums">
            <span>{formatTime(chart.t0)}</span>
            <span>{formatTime(chart.t0 + chart.span / 2)}</span>
            <span>{formatTime(chart.t0 + chart.span)}</span>
          </div>
        </div>
      )}
    </Bf1Panel>
  );
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}
