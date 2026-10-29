"use client";

import * as React from "react";
import { Search } from "lucide-react";
import { DarkInput } from "@/components/common/DarkInput";
import { cn } from "@/lib/utils";

/**
 * 武器 / 载具列表的过滤工具条：名称搜索 + 分类单选 chips。
 *
 * 纯前端过滤（数据已整页加载），不做防抖；分类从数据 distinct 推导、
 * 保持出现顺序，由父组件传入。手机端 chips 排成一行横向滑动，贴到面板边缘，不占多行。
 */
export interface EquipmentFilterBarProps {
  categories: string[];
  /** null 表示「全部」 */
  selected: string | null;
  onSelect: (category: string | null) => void;
  search: string;
  onSearch: (value: string) => void;
  placeholder?: string;
}

export function EquipmentFilterBar({
  categories,
  selected,
  onSelect,
  search,
  onSearch,
  placeholder,
}: EquipmentFilterBarProps) {
  return (
    <div className="mb-4 space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-white/35" />
        <DarkInput
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder={placeholder}
          className="pl-9"
        />
      </div>
      <div className="-mx-4 flex [scrollbar-width:none] gap-1.5 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0 [&::-webkit-scrollbar]:hidden">
        <CategoryChip label="全部" active={selected == null} onClick={() => onSelect(null)} />
        {categories.map((c) => (
          <CategoryChip key={c} label={c} active={selected === c} onClick={() => onSelect(c)} />
        ))}
      </div>
    </div>
  );
}

function CategoryChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "compact-action h-9 shrink-0 border px-3 text-[13px] whitespace-nowrap transition-colors sm:h-auto sm:px-2.5 sm:py-1 sm:text-xs sm:tracking-wide",
        active
          ? "border-white bg-white font-semibold text-black"
          : "border-white/20 text-white/60 hover:border-white/45 hover:text-white",
      )}
    >
      {label}
    </button>
  );
}
