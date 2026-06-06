"use client";

import { useRef } from "react";
import Link from "next/link";
import { motion, useScroll, useTransform, useInView } from "framer-motion";
import { ChevronDown, ChevronRight, Crosshair, ScrollText, Server, Shield } from "lucide-react";
import { GAMES } from "@/lib/game-registry";
import { cn } from "@/lib/utils";
import { HeroBackground } from "@/components/landing/HeroBackground";

// Hero 轮播图：混编 BF1 / BFV / BF2042 三代官方无 logo 大图，每张都是激烈交战镜头。
// 相邻两张刻意错开游戏与时代色调（一战 → 近未来 → 二战…），制造跨代张力。
const HERO_IMAGES = [
  "/bf1/backgrounds/general/general-3.jpg", // BF1 坦克破障冲锋
  "/bf2042/backgrounds/general/general-3.jpg", // BF2042 玻璃楼内近距交火
  "/bfv/backgrounds/general/general-2.jpg", // BFV 坦克中弹火海、士兵掩护
  "/bf1/backgrounds/general/general-8.jpg", // BF1 沙漠骑兵冲锋
  "/bfv/backgrounds/general/general-3.jpg", // BFV 港口步兵突击开火
  "/bf2042/backgrounds/general/general-2.jpg", // BF2042 火海中冲锋
];

const FEATURES = [
  {
    icon: Crosshair,
    title: "战绩查询",
    description: "深度战绩数据分析，武器、载具、地图统计全覆盖",
  },
  {
    icon: Server,
    title: "服务器管理",
    description: "实时玩家列表，踢人、封禁、换图一站式操作",
  },
  {
    icon: ScrollText,
    title: "操作审计",
    description: "完整操作日志记录，每一次管理行为有据可查",
  },
  {
    icon: Shield,
    title: "权限管控",
    description: "精细化服管授权体系，按服务器分配管理权限",
  },
];

export default function HomePage() {
  return (
    <div className="min-h-screen bg-black">
      <HeroSection />
      <FeaturesSection />
      <GamesSection />
      <footer className="border-t border-white/10 bg-[#0d0a04] px-4 py-8 text-center">
        <p className="inline-action text-xs text-white/30">
          BF-Manager · Battlefield 系列服务器管理平台 · MIT License
        </p>
      </footer>
    </div>
  );
}

/* ---------- Hero ---------- */

function HeroSection() {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const bgY = useTransform(scrollYProgress, [0, 1], ["0%", "30%"]);
  const contentOpacity = useTransform(scrollYProgress, [0, 0.5], [1, 0]);
  const contentY = useTransform(scrollYProgress, [0, 0.5], [0, -60]);

  return (
    <section ref={ref} className="relative h-screen overflow-hidden">
      {/* Parallax background — 视频背景（已配置时）/ 多代战地图 Ken Burns 轮播 */}
      <motion.div style={{ y: bgY }} className="absolute inset-0 scale-110">
        <HeroBackground images={HERO_IMAGES} />
      </motion.div>

      {/* Gradient overlays — 底部加重、左侧加重，托住左下角文字组 */}
      <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-black/20" />
      <div className="absolute inset-0 bg-gradient-to-r from-black/80 via-black/30 to-transparent" />

      {/* Top nav */}
      <nav className="absolute inset-x-0 top-0 z-10 flex items-center justify-between px-6 py-6 sm:px-10 lg:px-16">
        <span className="font-display inline-action text-base font-semibold tracking-[0.2em] text-white uppercase">
          BF-Manager
        </span>
        <Link
          href="/login?next=/dashboard"
          className="inline-action text-sm tracking-wide text-white/60 uppercase transition-colors hover:text-white"
        >
          登录
        </Link>
      </nav>

      {/* Hero content — 左下角锚定，电影海报式排版 */}
      <motion.div
        style={{ opacity: contentOpacity, y: contentY }}
        className="relative flex h-full flex-col justify-end px-6 pb-20 sm:px-10 sm:pb-24 lg:px-16 lg:pb-28"
      >
        <div className="max-w-3xl">
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="mb-4 flex items-center gap-3"
          >
            <span className="h-[3px] w-10 bg-amber-500" />
            <span className="font-display text-sm font-medium tracking-[0.3em] text-amber-400 uppercase">
              Battlefield 系列管理平台
            </span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, delay: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="font-display text-6xl leading-[0.95] font-bold tracking-tight text-white uppercase sm:text-7xl lg:text-8xl"
          >
            BF-Manager
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.6 }}
            className="mt-5 max-w-xl text-base leading-relaxed text-white/70 sm:text-lg"
          >
            战绩查询、服务器管理、操作审计与权限管控，一个平台覆盖全部需求。
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.9 }}
            className="mt-9 flex flex-wrap gap-4"
          >
            <Link
              href="/bf1"
              className="font-display group inline-flex items-center gap-2.5 bg-amber-500 px-9 py-3.5 text-sm font-semibold tracking-[0.15em] text-black uppercase transition-colors hover:bg-amber-400"
            >
              进入 BF1
              <ChevronRight className="size-4 transition-transform group-hover:translate-x-1" />
            </Link>
            <Link
              href="/login?next=/dashboard"
              className="font-display inline-flex items-center border border-white/30 px-9 py-3.5 text-sm font-semibold tracking-[0.15em] text-white uppercase backdrop-blur-sm transition-colors hover:border-white/60 hover:bg-white/5"
            >
              登录后台
            </Link>
          </motion.div>
        </div>
      </motion.div>

      {/* Scroll indicator */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.8 }}
        className="absolute inset-x-0 bottom-6 flex justify-center"
      >
        <a href="#features" className="inline-action block">
          <motion.div
            animate={{ y: [0, 8, 0] }}
            transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
          >
            <ChevronDown className="size-5 text-white/30" />
          </motion.div>
        </a>
      </motion.div>
    </section>
  );
}

/* ---------- Features ---------- */

function FeaturesSection() {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-80px" });

  return (
    <section
      id="features"
      ref={ref}
      className="relative bg-gradient-to-b from-black to-[#0d0a04] px-4 py-24 sm:px-6 lg:py-32"
    >
      <div className="mx-auto max-w-5xl">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="mb-16 text-center"
        >
          <h2 className="font-display text-4xl font-bold tracking-tight text-white uppercase sm:text-5xl">
            平台能力
          </h2>
          <div className="mx-auto mt-4 h-[3px] w-12 bg-amber-500" />
        </motion.div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          {FEATURES.map((f, i) => {
            const Icon = f.icon;
            return (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 30 }}
                animate={isInView ? { opacity: 1, y: 0 } : {}}
                transition={{ duration: 0.5, delay: 0.1 * i }}
                className="group rounded-lg border border-white/[0.06] bg-white/[0.03] p-6 transition-colors hover:border-amber-500/20 hover:bg-white/[0.06]"
              >
                <div className="mb-4 inline-flex rounded-md bg-amber-500/10 p-2.5">
                  <Icon className="size-5 text-amber-500" />
                </div>
                <h3 className="font-display mb-2 text-lg font-semibold tracking-wide text-white uppercase">
                  {f.title}
                </h3>
                <p className="text-sm leading-relaxed text-white/50">{f.description}</p>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ---------- Games ---------- */

function GamesSection() {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-80px" });
  const allGames = Object.values(GAMES);

  return (
    <section ref={ref} className="bg-[#0d0a04] px-4 py-24 sm:px-6 lg:py-32">
      <div className="mx-auto max-w-5xl">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          className="mb-16 text-center"
        >
          <h2 className="font-display text-4xl font-bold tracking-tight text-white uppercase sm:text-5xl">
            选择游戏
          </h2>
          <div className="mx-auto mt-4 h-[3px] w-12 bg-amber-500" />
        </motion.div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {allGames.map((game, i) => (
            <motion.div
              key={game.id}
              initial={{ opacity: 0, y: 30 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.5, delay: 0.12 * i }}
            >
              <GameCard game={game} />
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function GameCard({ game }: { game: (typeof GAMES)[keyof typeof GAMES] }) {
  const card = (
    <div
      className={cn(
        "group relative aspect-[4/5] overflow-hidden rounded-md",
        game.enabled ? "cursor-pointer" : "cursor-not-allowed",
      )}
    >
      {/* 官方封面 key art（图内已含 BATTLEFIELD logo） */}
      <div className="absolute inset-0 transition-transform duration-700 ease-out group-hover:scale-105">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={game.cardImage}
          alt={game.displayName}
          className={cn("h-full w-full object-cover", game.enabled ? "" : "grayscale")}
          loading="lazy"
        />
      </div>
      <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/10 to-black/20" />
      {/* 未启用游戏：覆盖“即将到来”标签 */}
      {!game.enabled ? (
        <div className="absolute top-3 right-3 rounded-sm bg-black/70 px-2.5 py-1">
          <span className="inline-action font-display text-[11px] font-medium tracking-[0.15em] text-white/80 uppercase">
            即将到来
          </span>
        </div>
      ) : null}
      <div className="relative flex h-full flex-col justify-end p-5">
        <p className="text-sm text-white/70">{game.tagline}</p>
        {game.enabled ? (
          <div className="font-display mt-3 flex items-center gap-1.5 text-sm font-medium tracking-wide text-amber-400 uppercase">
            <span className="inline-action">进入</span>
            <ChevronRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
          </div>
        ) : null}
      </div>
    </div>
  );

  return game.enabled ? <Link href={`/${game.id}`}>{card}</Link> : card;
}
