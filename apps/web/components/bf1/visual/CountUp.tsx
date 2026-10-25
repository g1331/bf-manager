"use client";

import { useEffect } from "react";
import { animate, motion, useMotionValue, useTransform } from "framer-motion";

/** 数字 count-up：mount 时从 0 滚入，值变化时从旧值滚到新值 */
export function CountUp({ value }: { value: number }) {
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => Math.round(v).toLocaleString());

  useEffect(() => {
    const controls = animate(mv, value, { duration: 1.1, ease: "circOut" });
    return () => controls.stop();
  }, [mv, value]);

  return <motion.span>{text}</motion.span>;
}
