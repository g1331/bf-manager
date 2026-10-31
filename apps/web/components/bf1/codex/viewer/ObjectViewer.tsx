"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { FlipHorizontal2, Loader2, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Viewer, ViewerSubject } from "./scene";

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";
function subscribeMotion(onChange: () => void) {
  const mq = matchMedia(REDUCED_MOTION);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}
const readMotion = () => matchMedia(REDUCED_MOTION).matches;

/**
 * 狗牌 / 勋章的实体检视器：拖动旋转、滚轮或双指缩放、双击或按钮翻面，停手 4 秒后接着自转。
 * three.js 在挂载后才按需加载，不进页面首包；浏览器开不了 WebGL 或加载失败时退回静态图。
 */
export function ObjectViewer({
  subject,
  sideLabels,
  fallback,
  className,
}: {
  subject: ViewerSubject;
  /** 角标上显示的正反面说明 */
  sideLabels: { front: string; back: string };
  /** 退回静态展示时用的图 */
  fallback: React.ReactNode;
  className?: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const viewer = useRef<Viewer | null>(null);
  // subject 每次渲染都是新对象，按内容比较
  const key = JSON.stringify(subject);
  const latest = useRef(key);
  const [shown, setShown] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [front, setFront] = useState(true);
  const reducedMotion = useSyncExternalStore(subscribeMotion, readMotion, () => false);
  const [autoChoice, setAutoChoice] = useState<boolean | null>(null);
  const auto = autoChoice ?? !reducedMotion;

  const show = (v: Viewer, k: string) =>
    v
      .show(JSON.parse(k) as ViewerSubject)
      .then(() => setShown(k))
      .catch(() => setFailed(true));

  useEffect(() => {
    latest.current = key;
    if (viewer.current) void show(viewer.current, key);
  }, [key]);

  useEffect(() => {
    let cancelled = false;
    let io: IntersectionObserver | undefined;
    import("./scene")
      .then(({ createViewer, webglAvailable }) => {
        if (cancelled || !canvas.current) return;
        if (!webglAvailable()) {
          setFailed(true);
          return;
        }
        const v = createViewer(canvas.current, {
          reducedMotion: matchMedia(REDUCED_MOTION).matches,
          onSide: setFront,
        });
        viewer.current = v;
        void show(v, latest.current);
        // 滚出视口就停掉渲染循环
        io = new IntersectionObserver(([e]) => v.setActive(e.isIntersecting));
        io.observe(box.current!);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      io?.disconnect();
      viewer.current?.dispose();
      viewer.current = null;
    };
  }, []);

  const loading = shown !== key;

  if (failed) {
    return (
      <div className={cn("relative flex items-center justify-center", className)}>
        {fallback}
        <span className="absolute bottom-3 left-3 text-[11px] text-white/40">
          当前浏览器无法显示 3D，已改为平面图
        </span>
      </div>
    );
  }

  return (
    <div ref={box} className={cn("@container relative overflow-hidden select-none", className)}>
      {/* 舞台底光：中间亮一点，四周压暗，物件像放在展台上 */}
      <div
        aria-hidden
        className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_42%,rgba(255,236,200,0.10),transparent_62%)]"
      />
      <canvas
        ref={canvas}
        onDoubleClick={() => viewer.current?.flip()}
        className="relative block size-full cursor-grab touch-none outline-none active:cursor-grabbing"
        aria-label="3D 检视：拖动旋转，滚轮或双指缩放，双击翻面"
      />

      <div className="pointer-events-none absolute top-3 left-3 border border-white/12 bg-black/55 px-2 py-1 text-xs text-white/80">
        {front ? sideLabels.front : sideLabels.back}
      </div>

      {loading ? (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <Loader2 className="size-6 animate-spin text-white/40" />
        </div>
      ) : null}

      <div className="absolute inset-x-3 bottom-3 flex items-center gap-2">
        <ViewerButton onClick={() => viewer.current?.flip()} label="翻面">
          <FlipHorizontal2 className="size-4" />
        </ViewerButton>
        <ViewerButton onClick={() => viewer.current?.reset()} label="复位">
          <RotateCcw className="size-4" />
        </ViewerButton>
        <label className="ml-1 flex h-11 cursor-pointer items-center gap-1.5 text-xs whitespace-nowrap text-white/60 sm:h-9">
          <input
            type="checkbox"
            checked={auto}
            onChange={(e) => {
              setAutoChoice(e.target.checked);
              viewer.current?.setAutoRotate(e.target.checked);
            }}
            className="size-3.5 accent-amber-400"
          />
          自动旋转
        </label>
        <span className="ml-auto hidden text-[11px] whitespace-nowrap text-white/35 @md:block">
          拖动旋转 · 滚轮缩放 · 双击翻面
        </span>
      </div>
    </div>
  );
}

function ViewerButton({
  onClick,
  label,
  children,
}: {
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="compact-action flex h-11 items-center gap-1.5 border border-white/15 bg-black/55 px-3 text-xs whitespace-nowrap text-white/80 transition-colors hover:border-amber-400/60 hover:text-amber-300 sm:h-9"
    >
      {children}
      {label}
    </button>
  );
}
