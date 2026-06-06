"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

/**
 * Hero 背景的渐进增强组件，三档表现：
 *
 *   1. 配置了视频地址 + 桌面端 + 非 reduced-motion → 播放背景视频（最高优先级）
 *   2. 否则 → 多张战地图片的 Ken Burns 轮播（交叉淡化 + 缓慢缩放），营造电影感
 *   3. prefers-reduced-motion → 仅显示第一张静态图，不轮播、不缩放
 *
 * 轮播参考通行的影视/游戏官网做法：图片交叉淡入淡出（非硬切），
 * 每张在展示期间持续缓慢放大（Ken Burns），切换时新旧两张同时淡化过渡。
 *
 * 视频用 muted + playsInline 满足浏览器自动播放策略；首张图同时作为视频 poster。
 */

const HERO_VIDEO_URL = process.env.NEXT_PUBLIC_HERO_VIDEO_URL ?? "";

interface HeroBackgroundProps {
  /** 轮播图组（public/ 路径），第一张也用作视频 poster 与 reduced-motion 静态图 */
  images: string[];
  /** 每张停留时长（毫秒） */
  intervalMs?: number;
}

export function HeroBackground({ images, intervalMs = 7000 }: HeroBackgroundProps) {
  const [useVideo, setUseVideo] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [index, setIndex] = useState(0);

  // 根据屏宽与动效偏好决定走视频 / 轮播 / 静态
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1024px)");
    const motionReduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    const evaluate = () => {
      setReduced(motionReduce.matches);
      setUseVideo(!!HERO_VIDEO_URL && desktop.matches && !motionReduce.matches);
    };
    evaluate();
    desktop.addEventListener("change", evaluate);
    motionReduce.addEventListener("change", evaluate);
    return () => {
      desktop.removeEventListener("change", evaluate);
      motionReduce.removeEventListener("change", evaluate);
    };
  }, []);

  // 预加载全部轮播图，避免切换时白屏
  useEffect(() => {
    images.forEach((src) => {
      const img = new Image();
      img.src = src;
    });
  }, [images]);

  // 轮播定时器：仅在走图片轮播且多于一张时启用
  useEffect(() => {
    if (useVideo || reduced || images.length <= 1) return;
    const timer = setInterval(() => {
      setIndex((i) => (i + 1) % images.length);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [useVideo, reduced, images.length, intervalMs]);

  if (useVideo) {
    return (
      <video
        autoPlay
        muted
        loop
        playsInline
        poster={images[0]}
        className="h-full w-full object-cover object-center"
      >
        <source src={HERO_VIDEO_URL} type="video/mp4" />
      </video>
    );
  }

  if (reduced) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={images[0]}
        alt=""
        className="h-full w-full object-cover object-center"
        loading="eager"
      />
    );
  }

  // Ken Burns 交叉淡化轮播
  return (
    <AnimatePresence>
      <motion.img
        key={index}
        src={images[index]}
        alt=""
        initial={{ opacity: 0, scale: 1.05 }}
        animate={{ opacity: 1, scale: 1.18 }}
        exit={{ opacity: 0 }}
        transition={{
          opacity: { duration: 1.6, ease: "easeInOut" },
          scale: { duration: (intervalMs + 1600) / 1000, ease: "linear" },
        }}
        className="absolute inset-0 h-full w-full object-cover object-center"
        loading="eager"
      />
    </AnimatePresence>
  );
}
