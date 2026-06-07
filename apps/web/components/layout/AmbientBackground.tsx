"use client";

import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";

/**
 * BF1 大厅式氛围底层：战场场景图铺底 + 中性压暗 + 径向暗角 + 胶片颗粒。
 *
 * 仿照战地主菜单「战场实景在底、UI 浮于其上」的双层结构（参考开源复刻 BFUI 的
 * 半透明面板叠实景背景做法）。所有叠加层一律使用中性黑，不给画面附加任何色相——
 * 暖冷氛围全部来自背景图本身，UI 面板保持中性深色，避免整屏发黄发褐。
 * 固定铺满视口并强压暗，以保证上层信息密集内容的可读性。
 *
 * 多张战场图缓慢交叉淡入轮换，呼应游戏大厅的动态氛围；系统开启「减弱动效」时
 * 只渲染首图、不轮换。
 */

// 轮换图集（排除带 BATTLEFIELD 1 字样的 general-5 / general-6）
const IMAGES = [
  "/bf1/backgrounds/general/general-2.jpg",
  "/bf1/backgrounds/general/general-1.jpg",
  "/bf1/backgrounds/general/general-4.jpg",
  "/bf1/backgrounds/general/general-8.jpg",
  "/bf1/backgrounds/general/general-3.jpg",
  "/bf1/backgrounds/general/general-7.jpg",
];

const SWITCH_INTERVAL_MS = 12_000;

const FILM_GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='g'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23g)'/%3E%3C/svg%3E\")";

export function AmbientBackground() {
  const reduceMotion = useReducedMotion();
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (reduceMotion) return;
    const timer = setInterval(() => {
      setIndex((i) => (i + 1) % IMAGES.length);
    }, SWITCH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [reduceMotion]);

  const slides = reduceMotion ? IMAGES.slice(0, 1) : IMAGES;

  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden" aria-hidden>
      {/* 战场实景：多图叠放，仅当前图淡入，其余淡出，形成缓慢轮换 */}
      {slides.map((src, i) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={src}
          src={src}
          alt=""
          className="absolute inset-0 h-full w-full scale-105 object-cover object-center blur-[1.5px] transition-opacity duration-[2000ms] ease-in-out"
          style={{ opacity: i === index ? 0.55 : 0 }}
        />
      ))}
      {/* 中性压暗：参考 BFUI 让战场实景清晰透出，仅上浅下深做轻压保证主内容区文字对比 */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(to bottom, oklch(0.12 0 0 / 0.3) 0%, oklch(0.12 0 0 / 0.45) 55%, oklch(0.1 0 0 / 0.7) 100%)",
        }}
      />
      {/* 径向暗角：聚焦中上、四周沉入黑 */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(125% 95% at 50% 8%, transparent 0%, oklch(0.1 0 0 / 0.38) 70%, oklch(0.08 0 0 / 0.8) 100%)",
        }}
      />
      {/* 胶片颗粒：极淡 fractalNoise，叠出做旧质感 */}
      <div
        className="absolute inset-0"
        style={{ backgroundImage: FILM_GRAIN, backgroundSize: "140px 140px", opacity: 0.05 }}
      />
    </div>
  );
}
