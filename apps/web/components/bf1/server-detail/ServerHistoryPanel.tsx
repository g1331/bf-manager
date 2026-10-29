"use client";

import { useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Bf1Panel } from "@/components/bf1/visual/Bf1Panel";
import { SectionHeading } from "@/components/layout/SectionHeading";
import type { ServerPlayerCountPoint } from "@/lib/api/bf1";
import { cn } from "@/lib/utils";
import {
  GAP_SECONDS,
  formatClock,
  formatDuration,
  toMapSegments,
  type MapSegment,
} from "./history";

/* ---------- 24 小时战况：人数面积 + 排队需求线 + 地图时间轴，悬停联动 ---------- */

/** SVG 逻辑坐标系；preserveAspectRatio="none" 拉伸适配容器，线宽靠 non-scaling-stroke 保持 */
const W = 1000;
const H = 220;
const PAD_TOP = 14;
const TICKS = 5;
/** 时间轴色块宽度低于这个比例就不写地图名，只留色块 */
const LABEL_MIN_SHARE = 0.07;

interface MapInfo {
  name: string;
  mode: string | null;
}

export function ServerHistoryPanel({
  points,
  colors,
  mapInfo,
}: {
  points: ServerPlayerCountPoint[];
  colors: Record<string, string>;
  mapInfo: (mapName: string, mode: string | null) => MapInfo;
}) {
  const [hoverTs, setHoverTs] = useState<number | null>(null);
  const plotRef = useRef<HTMLDivElement>(null);

  const view = useMemo(() => {
    const first = points[0].ts;
    const last = points[points.length - 1].ts;
    // 采集不足 24 小时时只画已有区间，避免大片空白
    const t0 = Math.max(first, last - 24 * 3600);
    const t1 = last + 60;
    const span = Math.max(t1 - t0, 60);
    const inView = points.filter((p) => p.ts >= t0);
    const capacity = inView[inView.length - 1].max_players || 64;
    const peak = inView.reduce((a, p) => (p.players > a.players ? p : a), inView[0]);
    const yMax = Math.max(capacity, ...inView.map((p) => p.players + p.queue), 1) * 1.04;
    const x = (ts: number) => ((ts - t0) / span) * W;
    const y = (v: number) => H - (v / yMax) * (H - PAD_TOP);

    // 断档处断开：每段各自闭合成面积
    const runs: ServerPlayerCountPoint[][] = [];
    for (const p of inView) {
      const run = runs[runs.length - 1];
      if (run && p.ts - run[run.length - 1].ts <= GAP_SECONDS) run.push(p);
      else runs.push([p]);
    }
    const line = (run: ServerPlayerCountPoint[], val: (p: ServerPlayerCountPoint) => number) =>
      run.map((p, i) => `${i ? "L" : "M"}${x(p.ts).toFixed(1)},${y(val(p)).toFixed(1)}`).join("");
    const area = runs
      .map((run) => {
        const r = run.length === 1 ? [run[0], { ...run[0], ts: run[0].ts + 60 }] : run;
        return `${line(r, (p) => p.players)}L${x(r[r.length - 1].ts).toFixed(1)},${H}L${x(r[0].ts).toFixed(1)},${H}Z`;
      })
      .join("");
    const playersLine = runs.map((run) => line(run, (p) => p.players)).join("");
    const demandLine = runs
      .filter((run) => run.some((p) => p.queue > 0))
      .map((run) => line(run, (p) => p.players + p.queue))
      .join("");

    // 按每个点实际代表的时长加权（单点封顶 2 分钟，与后端地图统计口径一致）
    // 每个点代表到下一个点的时长；断档前的最后一个点只算 1 分钟
    const spans = inView.map((p, i) => {
      const d = (inView[i + 1]?.ts ?? p.ts + 60) - p.ts;
      return (d > GAP_SECONDS ? 60 : d) / 60;
    });
    const sampledMinutes = spans.reduce((s, m) => s + m, 0);
    const fullMinutes = inView.reduce((s, p, i) => s + (p.players >= capacity ? spans[i] : 0), 0);
    const avg = inView.reduce((s, p, i) => s + p.players * spans[i], 0) / sampledMinutes;
    const ticks = Array.from({ length: TICKS }, (_, i) => t0 + (span * i) / (TICKS - 1));
    const segments = toMapSegments(inView);

    return {
      t0,
      span,
      inView,
      capacity,
      peak,
      avg,
      x,
      y,
      area,
      playersLine,
      demandLine,
      capY: y(capacity),
      ticks,
      segments,
      sampledMinutes,
      fullMinutes,
    };
  }, [points]);

  const hover = useMemo(() => {
    if (hoverTs == null) return null;
    // 二分找最近的采样点
    const arr = view.inView;
    let lo = 0;
    let hi = arr.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (arr[mid].ts < hoverTs) lo = mid + 1;
      else hi = mid;
    }
    const near = lo > 0 && hoverTs - arr[lo - 1].ts < arr[lo].ts - hoverTs ? arr[lo - 1] : arr[lo];
    if (Math.abs(near.ts - hoverTs) > GAP_SECONDS) return { ts: hoverTs, point: null };
    return { ts: near.ts, point: near };
  }, [hoverTs, view.inView]);

  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const rect = plotRef.current?.getBoundingClientRect();
    if (!rect) return;
    const ratio = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1);
    setHoverTs(view.t0 + ratio * view.span);
  };

  const latest = view.inView[view.inView.length - 1];
  const hoverLeft = hover ? (((hover.ts - view.t0) / view.span) * 100).toFixed(2) : null;
  const hoverSeg = hover
    ? view.segments.find((s) => hover.ts >= s.start && hover.ts < s.end)
    : undefined;
  const collectedHours = Math.round(view.span / 3600);

  return (
    <Bf1Panel
      variant="transparent"
      cut={20}
      corners={["topLeft", "bottomRight"]}
      className="h-full bg-black/45 p-4 backdrop-blur-sm sm:p-6"
    >
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <div>
          <SectionHeading className="mb-0">24 小时战况</SectionHeading>
          {view.span < 23 * 3600 ? (
            <p className="mt-1 pl-[13px] text-[11px] text-white/40">
              已采集 {collectedHours > 0 ? `${collectedHours} 小时` : "不到 1 小时"}，每分钟一个点
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-x-7 gap-y-2">
          <HeadStat label="当前" value={`${latest.players}`} unit={`/${latest.max_players}`} />
          <HeadStat label="峰值" value={`${view.peak.players}`} unit={formatClock(view.peak.ts)} />
          <HeadStat label="平均" value={view.avg.toFixed(0)} unit="人" />
          <HeadStat
            label="满员时长"
            value={formatDuration(view.fullMinutes)}
            unit={`占 ${Math.round((view.fullMinutes / view.sampledMinutes) * 100)}%`}
          />
        </div>
      </div>

      <div
        ref={plotRef}
        className="relative mt-5 cursor-crosshair touch-none select-none"
        onPointerMove={onMove}
        onPointerDown={onMove}
        onPointerLeave={() => setHoverTs(null)}
      >
        {/* 人数面积 */}
        <div className="relative h-48 sm:h-56">
          <svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            className="absolute inset-0 h-full w-full overflow-visible"
          >
            <defs>
              <linearGradient id="server-history-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="rgb(251 191 36)" stopOpacity="0.45" />
                <stop offset="100%" stopColor="rgb(251 191 36)" stopOpacity="0.02" />
              </linearGradient>
            </defs>
            {[0.25, 0.5, 0.75].map((f) => (
              <line
                key={f}
                x1={0}
                x2={W}
                y1={H - f * (H - PAD_TOP)}
                y2={H - f * (H - PAD_TOP)}
                stroke="rgba(255,255,255,0.05)"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            <line
              x1={0}
              x2={W}
              y1={view.capY}
              y2={view.capY}
              stroke="rgba(255,255,255,0.35)"
              strokeDasharray="5 5"
              vectorEffect="non-scaling-stroke"
            />
            <motion.path
              d={view.area}
              fill="url(#server-history-fill)"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.8 }}
            />
            <motion.path
              d={view.playersLine}
              fill="none"
              stroke="rgb(251 191 36)"
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 1.2, ease: "easeOut" }}
            />
            {view.demandLine ? (
              <path
                d={view.demandLine}
                fill="none"
                stroke="rgb(253 230 138 / 0.7)"
                strokeWidth={1}
                strokeDasharray="2 3"
                vectorEffect="non-scaling-stroke"
              />
            ) : null}
          </svg>

          <span
            className="pointer-events-none absolute right-0 -translate-y-full pb-0.5 text-[10px] text-white/45 tabular-nums"
            style={{ top: `${(view.capY / H) * 100}%` }}
          >
            满员 {view.capacity}
          </span>

          {hover?.point && hoverLeft ? (
            <span
              className="pointer-events-none absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-black bg-amber-400"
              style={{ left: `${hoverLeft}%`, top: `${(view.y(hover.point.players) / H) * 100}%` }}
            />
          ) : null}
        </div>

        {/* 地图时间轴 */}
        <MapStrip
          segments={view.segments}
          t0={view.t0}
          span={view.span}
          colors={colors}
          mapInfo={mapInfo}
          activeKey={hoverSeg?.key}
        />

        {/* 时间刻度 */}
        <div className="mt-1.5 flex justify-between text-[10px] text-white/35 tabular-nums">
          {view.ticks.map((t) => (
            <span key={t}>{formatClock(t)}</span>
          ))}
        </div>

        {hover && hoverLeft ? (
          <>
            <div
              className="pointer-events-none absolute top-0 bottom-5 w-px bg-white/40"
              style={{ left: `${hoverLeft}%` }}
            />
            <HoverCard
              left={Number(hoverLeft)}
              ts={hover.ts}
              point={hover.point}
              seg={hoverSeg}
              mapInfo={mapInfo}
              colors={colors}
            />
          </>
        ) : null}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-[11px] text-white/45">
        <Legend swatch={<span className="h-0.5 w-4 bg-amber-400" />} text="在线人数" />
        <Legend
          swatch={<span className="w-4 border-t border-dashed border-amber-200/70" />}
          text="在线 + 排队"
        />
        <Legend
          swatch={<span className="w-4 border-t border-dashed border-white/40" />}
          text="满员线"
        />
        <span className="ml-auto">色块为当时地图，空白处服务器无人</span>
      </div>
    </Bf1Panel>
  );
}

function HeadStat({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div>
      <div className="text-[11px] text-white/45">{label}</div>
      <div className="mt-0.5 flex items-baseline gap-1">
        <span className="font-display text-xl font-semibold text-white tabular-nums">{value}</span>
        <span className="text-[11px] text-white/45 tabular-nums">{unit}</span>
      </div>
    </div>
  );
}

function Legend({ swatch, text }: { swatch: React.ReactNode; text: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {swatch}
      {text}
    </span>
  );
}

function MapStrip({
  segments,
  t0,
  span,
  colors,
  mapInfo,
  activeKey,
}: {
  segments: MapSegment[];
  t0: number;
  span: number;
  colors: Record<string, string>;
  mapInfo: (mapName: string, mode: string | null) => MapInfo;
  activeKey: string | undefined;
}) {
  return (
    <div className="relative mt-2 h-7 bg-white/[0.04]">
      {segments.map((s) => {
        const left = ((s.start - t0) / span) * 100;
        const width = Math.max(((s.end - s.start) / span) * 100, 0.3);
        const color = colors[s.mapName] ?? "#888";
        const info = mapInfo(s.mapName, s.mode);
        return (
          <div
            key={`${s.key}-${s.start}`}
            className={cn(
              "absolute inset-y-0 overflow-hidden border-r border-black/60 transition-opacity",
              activeKey && activeKey !== s.key ? "opacity-45" : "opacity-100",
            )}
            style={{ left: `${left}%`, width: `${width}%`, background: `${color}cc` }}
          >
            {width / 100 >= LABEL_MIN_SHARE ? (
              <span className="absolute inset-0 truncate px-1.5 text-[11px] leading-7 font-medium text-black/80">
                {info.name}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function HoverCard({
  left,
  ts,
  point,
  seg,
  mapInfo,
  colors,
}: {
  left: number;
  ts: number;
  point: ServerPlayerCountPoint | null;
  seg: MapSegment | undefined;
  mapInfo: (mapName: string, mode: string | null) => MapInfo;
  colors: Record<string, string>;
}) {
  const info = seg ? mapInfo(seg.mapName, seg.mode) : null;
  return (
    <div
      className="pointer-events-none absolute top-2 z-10 w-52 border border-white/15 bg-black/85 px-3 py-2 text-xs shadow-xl backdrop-blur"
      style={left > 60 ? { right: `${100 - left + 1}%` } : { left: `${left + 1}%` }}
    >
      <div className="text-white/50 tabular-nums">{formatClock(ts)}</div>
      {point ? (
        <div className="mt-1 flex items-baseline gap-1.5 tabular-nums">
          <span className="font-display text-lg font-semibold text-amber-300">{point.players}</span>
          <span className="text-white/45">/{point.max_players}</span>
          {point.queue > 0 ? <span className="text-amber-200/80">+{point.queue} 排队</span> : null}
        </div>
      ) : (
        <div className="mt-1 text-white/45">服务器无人</div>
      )}
      {seg && info ? (
        <div className="mt-2 border-t border-white/10 pt-2">
          <div className="flex items-center gap-1.5">
            <span className="size-2 shrink-0" style={{ background: colors[seg.mapName] }} />
            <span className="truncate text-white/90">{info.name}</span>
            {info.mode ? <span className="shrink-0 text-white/45">{info.mode}</span> : null}
          </div>
          <div className="mt-0.5 text-white/45 tabular-nums">
            {formatClock(seg.start)}–{formatClock(seg.end)} · 平均 {seg.avg.toFixed(0)} 人
          </div>
        </div>
      ) : null}
    </div>
  );
}
