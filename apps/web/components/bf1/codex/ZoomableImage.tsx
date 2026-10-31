"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

const ZOOM = 2;
const MAX_ZOOM = 2.5;
/** 手指移动不超过这个距离算点按，超过算拖动 */
const TAP_SLOP = 6;

/**
 * 可放大看细节的图片。原图只有 640 宽，放到 2 倍已经是能看清笔触的上限，再大就糊了。
 *   - 鼠标：点击在点击处放大 2 倍，移动鼠标看不同位置，放大后滚轮可在 1–2.5 倍间微调；再点一次复原。
 *   - 触屏：点按放大，单指拖动平移，再点按复原。未放大时不拦截手势，页面照常滚动。
 * 换图（src 变化）时由调用方用 key 重新挂载来复位。
 * children 是叠在图上的卡面文字，放大时淡出，免得挡住细节。
 */
export function ZoomableImage({
  src,
  srcSet,
  sizes,
  alt,
  width,
  height,
  className,
  priority,
  children,
}: {
  src: string;
  srcSet?: string;
  sizes?: string;
  alt: string;
  width: number;
  height: number;
  className?: string;
  priority?: boolean;
  children?: React.ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [origin, setOrigin] = useState({ x: 50, y: 50 });
  const [panning, setPanning] = useState(false);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number; moved: boolean } | null>(
    null,
  );
  // iOS Safari 的 click 事件不带 pointerType，靠 pointerdown 记下的类型区分鼠标和手指
  const lastPointer = useRef("mouse");

  // React 的 onWheel 是 passive 监听，拦不住页面滚动，只能自己挂；未放大时不拦截，免得详情页上滚不动
  useEffect(() => {
    const el = box.current;
    if (!el || zoom <= 1) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      setOrigin({
        x: Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100)),
        y: Math.min(100, Math.max(0, ((e.clientY - r.top) / r.height) * 100)),
      });
      setZoom((z) => Math.min(MAX_ZOOM, Math.max(1, z - e.deltaY * 0.002)));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoom]);

  const at = (e: { clientX: number; clientY: number }) => {
    const r = box.current!.getBoundingClientRect();
    return {
      x: Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100)),
      y: Math.min(100, Math.max(0, ((e.clientY - r.top) / r.height) * 100)),
    };
  };
  const toggle = (e: { clientX: number; clientY: number }) => {
    if (zoom > 1) {
      setZoom(1);
    } else {
      setOrigin(at(e));
      setZoom(ZOOM);
    }
  };

  return (
    <div
      ref={box}
      role="button"
      tabIndex={0}
      aria-label={zoom > 1 ? "缩小图片" : "放大图片"}
      aria-pressed={zoom > 1}
      className={cn(
        "relative block overflow-hidden bg-white/[0.04] outline-none select-none focus-visible:ring-2 focus-visible:ring-amber-400/70",
        zoom > 1 ? "cursor-zoom-out touch-none" : "cursor-zoom-in touch-pan-y",
        className,
      )}
      style={{ aspectRatio: `${width} / ${height}` }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          const r = box.current!.getBoundingClientRect();
          toggle({ clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 });
        }
      }}
      onPointerDown={(e) => {
        lastPointer.current = e.pointerType;
        if (e.pointerType === "mouse") return;
        drag.current = { x: e.clientX, y: e.clientY, ox: origin.x, oy: origin.y, moved: false };
      }}
      onPointerMove={(e) => {
        if (zoom <= 1) return;
        if (e.pointerType === "mouse") {
          setPanning(true);
          setOrigin(at(e));
          return;
        }
        const d = drag.current;
        if (!d) return;
        const dx = e.clientX - d.x;
        const dy = e.clientY - d.y;
        if (!d.moved && Math.hypot(dx, dy) < TAP_SLOP) return;
        d.moved = true;
        setPanning(true);
        // 改变缩放中心 dO 会让画面平移 -dO·(z-1)，所以手指移动 dx 对应中心反向移动 dx/(z-1)
        const r = box.current!.getBoundingClientRect();
        setOrigin({
          x: Math.min(100, Math.max(0, d.ox - (dx / r.width / (zoom - 1)) * 100)),
          y: Math.min(100, Math.max(0, d.oy - (dy / r.height / (zoom - 1)) * 100)),
        });
      }}
      onPointerUp={(e) => {
        if (e.pointerType === "mouse") return;
        const d = drag.current;
        drag.current = null;
        setPanning(false);
        if (d && !d.moved) toggle(e);
      }}
      onPointerCancel={() => {
        drag.current = null;
        setPanning(false);
      }}
      onPointerLeave={(e) => {
        if (e.pointerType === "mouse") setPanning(false);
      }}
      onClick={(e) => {
        // 触屏的点按在 pointerup 里处理过了，这里只接鼠标
        if (lastPointer.current === "mouse") toggle(e);
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- 自托管的静态 webp，已按宽度出两档 */}
      <img
        src={src}
        srcSet={srcSet}
        sizes={sizes}
        alt={alt}
        width={width}
        height={height}
        draggable={false}
        decoding="async"
        fetchPriority={priority ? "high" : undefined}
        className={cn(
          "pointer-events-none block size-full object-cover transition-transform duration-300 ease-out",
          panning && "duration-0",
        )}
        style={{
          transform: `scale(${zoom})`,
          transformOrigin: `${origin.x}% ${origin.y}%`,
        }}
      />
      {children ? (
        <div
          className={cn(
            "transition-opacity duration-300",
            zoom > 1 && "opacity-0 motion-reduce:transition-none",
          )}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}
