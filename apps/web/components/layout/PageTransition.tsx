"use client";

import { usePathname } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";

/**
 * 路由切换时的进入过渡：新页面内容淡入，取代默认的整页硬切。
 *
 * 以 pathname 作为 key，使主内容区在路由变化时重新挂载，从而触发 initial → animate。
 * 这里刻意只做不透明度过渡，不加 translateY / scale 等任何 transform：玩家详情、
 * 服务器详情等页面使用 `fixed` 全屏背景，父级一旦带有 transform 就会成为其
 * containing block，导致 `fixed inset-0 lg:left-60` 的定位在动画期间发生错位。
 * filter、perspective 等属性同样会触发该行为，故一并避免。
 * 系统开启「减弱动效」时跳过入场动画。
 */
export function PageTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      key={pathname}
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}
