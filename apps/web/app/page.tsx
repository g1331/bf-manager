"use client";

import { useRef } from "react";
import Link from "next/link";
import {
  MotionConfig,
  motion,
  useInView,
  useScroll,
  useTransform,
  type MotionValue,
} from "framer-motion";
import { ChevronDown, ChevronRight } from "lucide-react";
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

// 宣传片分镜：每个能力一个整屏镜头，滚动推进；image 的主体在画面另一侧，文字压在留白处
const CHAPTERS = [
  {
    no: "01",
    en: "Player Intel",
    title: "战绩查询",
    line: "每一发子弹，都会留下记录。",
    description: "深度战绩数据分析，武器、载具、地图统计全覆盖",
    image: "/bf1/backgrounds/general/general-7.jpg", // 奥斯曼步枪兵，主体在右
    align: "left",
  },
  {
    no: "02",
    en: "Server Command",
    title: "服务器管理",
    line: "整片战场，尽在掌握。",
    description: "实时玩家列表，踢人、封禁、换图一站式操作",
    image: "/bf1/backgrounds/general/general-2.jpg", // 黄昏空战，主体在右
    align: "left",
  },
  {
    no: "03",
    en: "Audit Trail",
    title: "操作审计",
    line: "每一道命令，有据可查。",
    description: "完整操作日志记录，每一次管理行为有据可查",
    image: "/bf1/backgrounds/general/general-1.jpg", // 德军军官，主体在左
    align: "right",
  },
  {
    no: "04",
    en: "Chain of Command",
    title: "权限管控",
    line: "授权，精确到每一台服务器。",
    description: "精细化服管授权体系，按服务器分配管理权限",
    image: "/bf1/backgrounds/general/general-4.jpg", // 官方主视觉，主体居中偏左
    align: "right",
  },
] as const;

const FINALE_IMAGE = "/bf1/backgrounds/general/general-8.jpg";

// 应用版本号：生产镜像构建时由 CI 注入（NEXT_PUBLIC_APP_VERSION，源自 git tag）；
// 本地 next dev 无注入时回落 "dev"。展示值直接取注入原文（tag 构建为 vX.Y.Z，main 构建为 main）。
const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || "dev";

export default function HomePage() {
  return (
    // reducedMotion="user"：系统开启「减少动态效果」时 framer 跳过位移/缩放，只保留淡入淡出
    <MotionConfig reducedMotion="user">
      <div className="relative min-h-screen bg-black">
        <Timecode />
        <HeroSection />
        {CHAPTERS.map((c) => (
          <ChapterScene key={c.no} chapter={c} />
        ))}
        <GamesSection />
        <FinaleSection />
        {/* 胶片颗粒 + 暗角，覆盖整页 */}
        <div aria-hidden className="pointer-events-none fixed inset-0 z-40 overflow-hidden">
          <div className="film-grain" />
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_55%,rgba(0,0,0,0.55)_100%)]" />
        </div>
      </div>
    </MotionConfig>
  );
}

/* ---------- 时间码：整页滚动进度映射成一支 2 分 30 秒的片子 ---------- */

const RUNTIME_SECONDS = 150;
const FPS = 24;

function Timecode() {
  const { scrollYProgress } = useScroll();
  const text = useTransform(scrollYProgress, (p) => {
    const frames = Math.round(p * RUNTIME_SECONDS * FPS);
    const s = Math.floor(frames / FPS);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `00:${pad(Math.floor(s / 60))}:${pad(s % 60)}:${pad(frames % FPS)}`;
  });

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed bottom-5 left-6 z-30 hidden items-center gap-2 font-mono text-[11px] tracking-widest text-white/40 sm:flex lg:left-16"
    >
      <span className="size-1.5 animate-pulse rounded-full bg-red-500/80" />
      <motion.span>{text}</motion.span>
    </div>
  );
}

/* ---------- 开场：快门拉开 → 片名卡 ---------- */

function HeroSection() {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const bgY = useTransform(scrollYProgress, [0, 1], ["0%", "30%"]);
  const contentOpacity = useTransform(scrollYProgress, [0, 0.5], [1, 0]);
  const contentY = useTransform(scrollYProgress, [0, 0.5], [0, -60]);
  // 遮幅黑边：开场 2.39:1 宽银幕感，往下滚逐渐收起
  const barH = useTransform(scrollYProgress, [0, 0.6], ["9vh", "0vh"]);

  return (
    <section ref={ref} className="relative h-screen overflow-hidden">
      <motion.div style={{ y: bgY }} className="absolute inset-0 scale-110">
        <HeroBackground images={HERO_IMAGES} />
      </motion.div>

      <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-black/20" />
      <div className="absolute inset-0 bg-gradient-to-r from-black/80 via-black/30 to-transparent" />

      <motion.div style={{ height: barH }} className="absolute inset-x-0 top-0 z-10 bg-black" />
      <motion.div style={{ height: barH }} className="absolute inset-x-0 bottom-0 z-10 bg-black" />

      {/* 快门：上下两片黑幕从中线拉开 */}
      <motion.div
        aria-hidden
        initial={{ scaleY: 1 }}
        animate={{ scaleY: 0 }}
        transition={{ duration: 1.3, delay: 0.25, ease: [0.76, 0, 0.24, 1] }}
        className="absolute inset-x-0 top-0 z-20 h-1/2 origin-top bg-black"
      />
      <motion.div
        aria-hidden
        initial={{ scaleY: 1 }}
        animate={{ scaleY: 0 }}
        transition={{ duration: 1.3, delay: 0.25, ease: [0.76, 0, 0.24, 1] }}
        className="absolute inset-x-0 bottom-0 z-20 h-1/2 origin-bottom bg-black"
      />

      <nav className="absolute inset-x-0 top-0 z-30 flex items-center justify-between px-6 py-6 sm:px-10 lg:px-16">
        <span className="font-display inline-action text-base font-semibold tracking-[0.2em] text-white uppercase">
          BF-Manager
        </span>
        <Link
          href="/login"
          className="inline-action text-sm tracking-wide text-white/60 uppercase transition-colors hover:text-white"
        >
          登录
        </Link>
      </nav>

      <motion.div
        style={{ opacity: contentOpacity, y: contentY }}
        className="relative z-10 flex h-full flex-col justify-end px-6 pb-[16vh] sm:px-10 lg:px-16"
      >
        <div className="max-w-4xl">
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 1.2 }}
            className="mb-5 flex items-center gap-3"
          >
            <span className="h-[3px] w-10 bg-amber-500" />
            <span className="font-display text-sm font-medium tracking-[0.4em] text-amber-400 uppercase">
              1916 · 1944 · 2042
            </span>
          </motion.div>

          {/* 片名：字距从极宽收拢、由虚到实，模拟预告片片名卡 */}
          <motion.h1
            initial={{ opacity: 0, letterSpacing: "0.45em", filter: "blur(14px)" }}
            animate={{ opacity: 1, letterSpacing: "-0.01em", filter: "blur(0px)" }}
            transition={{ duration: 1.8, delay: 1.3, ease: [0.16, 1, 0.3, 1] }}
            className="font-display text-6xl leading-[0.95] font-bold text-white uppercase sm:text-8xl lg:text-9xl"
          >
            BF-Manager
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, delay: 2.4 }}
            className="mt-6 max-w-xl text-lg leading-relaxed text-white/80 sm:text-xl"
          >
            一个平台，指挥你的整片战场。
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.9, delay: 2.7 }}
            className="mt-9"
          >
            <CallToAction />
          </motion.div>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 3.4 }}
        className="absolute inset-x-0 bottom-[10vh] z-10 flex justify-center"
      >
        <a href="#chapter-01" className="inline-action block" aria-label="向下滚动">
          <motion.div
            animate={{ y: [0, 8, 0] }}
            transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
          >
            <ChevronDown className="size-5 text-white/40" />
          </motion.div>
        </a>
      </motion.div>
    </section>
  );
}

function CallToAction() {
  return (
    <div className="flex flex-wrap gap-4">
      <Link
        href="/bf1"
        className="font-display group inline-flex items-center gap-2.5 bg-amber-500 px-9 py-3.5 text-sm font-semibold tracking-[0.15em] text-black uppercase transition-colors hover:bg-amber-400"
      >
        进入 BF1
        <ChevronRight className="size-4 transition-transform group-hover:translate-x-1" />
      </Link>
      <Link
        href="/login"
        className="font-display inline-flex items-center border border-white/30 px-9 py-3.5 text-sm font-semibold tracking-[0.15em] text-white uppercase backdrop-blur-sm transition-colors hover:border-white/60 hover:bg-white/5"
      >
        登录
      </Link>
    </div>
  );
}

/* ---------- 分镜：钉住整屏，滚动推镜，首尾黑场转场 ---------- */

function ChapterScene({ chapter }: { chapter: (typeof CHAPTERS)[number] }) {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress: p } = useScroll({ target: ref, offset: ["start start", "end end"] });

  const imgScale = useTransform(p, [0, 1], [1.25, 1.02]);
  const imgX = useTransform(p, [0, 1], chapter.align === "left" ? ["2%", "-2%"] : ["-2%", "2%"]);
  const blackout = useTransform(p, [0, 0.14, 0.86, 1], [1, 0, 0, 1]);
  const textOpacity = useTransform(p, [0.14, 0.3, 0.72, 0.86], [0, 1, 1, 0]);
  const textY = useTransform(p, [0.14, 0.3], [50, 0]);
  const numberY = useTransform(p, [0, 1], ["25%", "-25%"]);
  const right = chapter.align === "right";

  return (
    <section id={`chapter-${chapter.no}`} ref={ref} className="relative h-[220vh]">
      <div className="sticky top-0 h-screen overflow-hidden">
        <motion.div style={{ scale: imgScale, x: imgX }} className="absolute inset-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={chapter.image} alt="" className="h-full w-full object-cover" loading="lazy" />
        </motion.div>
        <div
          className={cn(
            "absolute inset-0 from-black/90 via-black/45 to-transparent",
            right ? "bg-gradient-to-l" : "bg-gradient-to-r",
          )}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/40" />

        <div
          className={cn(
            "relative flex h-full items-center px-6 sm:px-10 lg:px-16",
            right && "justify-end text-right",
          )}
        >
          <motion.div style={{ opacity: textOpacity, y: textY }} className="relative max-w-xl">
            <motion.span
              aria-hidden
              style={{ y: numberY, WebkitTextStroke: "1px rgba(255,255,255,0.18)" }}
              className={cn(
                "font-display pointer-events-none absolute -top-28 text-[10rem] leading-none font-bold text-transparent select-none sm:-top-36 sm:text-[14rem]",
                right ? "-right-2" : "-left-2",
              )}
            >
              {chapter.no}
            </motion.span>
            <p className="font-display relative text-xs font-medium tracking-[0.4em] text-amber-400 uppercase">
              {chapter.no} — {chapter.en}
            </p>
            <h2 className="font-display relative mt-4 text-5xl font-bold tracking-tight text-white uppercase sm:text-7xl">
              {chapter.title}
            </h2>
            <p className="relative mt-5 text-xl text-white/90 sm:text-2xl">{chapter.line}</p>
            <p className="relative mt-3 text-sm leading-relaxed text-white/55 sm:text-base">
              {chapter.description}
            </p>
          </motion.div>
        </div>

        <ChapterProgress progress={p} />
        <motion.div
          aria-hidden
          style={{ opacity: blackout }}
          className="pointer-events-none absolute inset-0 bg-black"
        />
      </div>
    </section>
  );
}

function ChapterProgress({ progress }: { progress: MotionValue<number> }) {
  return (
    <div className="absolute inset-x-0 bottom-0 h-[2px] bg-white/10">
      <motion.div style={{ scaleX: progress }} className="h-full origin-left bg-amber-500/80" />
    </div>
  );
}

/* ---------- 选择战场 ---------- */

function GamesSection() {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-80px" });
  const allGames = Object.values(GAMES);

  return (
    <section ref={ref} className="bg-black px-4 py-28 sm:px-6 lg:py-36">
      <div className="mx-auto max-w-5xl">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.8 }}
          className="mb-16 text-center"
        >
          <p className="font-display text-xs font-medium tracking-[0.4em] text-amber-400 uppercase">
            Select Your Battlefield
          </p>
          <h2 className="font-display mt-4 text-4xl font-bold tracking-tight text-white uppercase sm:text-6xl">
            选择你的战场
          </h2>
        </motion.div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {allGames.map((game, i) => (
            <motion.div
              key={game.id}
              initial={{ opacity: 0, y: 40 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.7, delay: 0.15 * i }}
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

/* ---------- 终幕 + 片尾字幕 ---------- */

function FinaleSection() {
  const ref = useRef<HTMLElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-120px" });
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end end"] });
  const imgScale = useTransform(scrollYProgress, [0, 1], [1.2, 1]);

  return (
    <section ref={ref} className="relative overflow-hidden bg-black">
      <div className="relative flex h-screen items-center justify-center overflow-hidden px-6 text-center">
        <motion.div style={{ scale: imgScale }} className="absolute inset-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={FINALE_IMAGE} alt="" className="h-full w-full object-cover" loading="lazy" />
        </motion.div>
        <div className="absolute inset-0 bg-black/55" />
        <div className="absolute inset-0 bg-gradient-to-b from-black via-transparent to-black" />

        <div className="relative flex flex-col items-center">
          <motion.p
            initial={{ opacity: 0 }}
            animate={isInView ? { opacity: 1 } : {}}
            transition={{ duration: 1 }}
            className="font-display text-xs font-medium tracking-[0.5em] text-amber-400 uppercase"
          >
            Deploy Now
          </motion.p>
          <motion.h2
            initial={{ opacity: 0, letterSpacing: "0.3em", filter: "blur(10px)" }}
            animate={isInView ? { opacity: 1, letterSpacing: "-0.01em", filter: "blur(0px)" } : {}}
            transition={{ duration: 1.6, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="font-display mt-5 text-5xl font-bold text-white uppercase sm:text-8xl"
          >
            战场已就绪
          </motion.h2>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.9, delay: 1.1 }}
            className="mt-10"
          >
            <CallToAction />
          </motion.div>
        </div>
      </div>

      <footer className="flex flex-col items-center gap-2 px-4 pt-4 pb-14 text-center">
        <span className="font-display inline-action text-sm font-semibold tracking-[0.4em] text-white/60 uppercase">
          BF-Manager
        </span>
        <p className="inline-action text-xs tracking-[0.2em] text-white/30">
          Battlefield 系列服务器管理平台 · MIT License
        </p>
        <span className="font-mono text-[11px] text-white/20">{APP_VERSION}</span>
      </footer>
    </section>
  );
}
