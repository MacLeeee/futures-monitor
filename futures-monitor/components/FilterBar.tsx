"use client";
// ============================================================
// 筛选栏组件 — 按板块、策略状态快速过滤
// ============================================================

import React from "react";
import { Filter } from "lucide-react";

export type StateFilter = "全部" | "SIGNAL" | "PENDING" | "APPROACHING" | "TRENDING" | "IDLE";

interface FilterBarProps {
  selectedCategory: string;
  selectedState: StateFilter;
  onCategoryChange: (v: string) => void;
  onStateChange: (v: StateFilter) => void;
  totalCount: number;
  filteredCount: number;
}

const CATEGORIES = ["全部", "贵金属", "有色", "黑色", "农产品", "油脂", "能化", "建材", "股指"];

const STATE_FILTERS: { value: StateFilter; label: string; emoji: string }[] = [
  { value: "全部",         label: "全部",       emoji: "" },
  { value: "SIGNAL",       label: "信号",       emoji: "🎯" },
  { value: "PENDING",      label: "冷却中",     emoji: "⚫" },
  { value: "APPROACHING",  label: "接近信号",    emoji: "🟡" },
  { value: "TRENDING",     label: "趋势就绪",    emoji: "🔵" },
  { value: "IDLE",         label: "观望",       emoji: "⬜" },
];

export default function FilterBar({
  selectedCategory,
  selectedState,
  onCategoryChange,
  onStateChange,
  totalCount,
  filteredCount,
}: FilterBarProps) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <div className="flex items-center gap-1.5 text-xs text-stone-500">
        <Filter size={12} />
        筛选:
      </div>

      {/* 板块筛选 */}
      <div className="flex gap-1 flex-wrap">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => onCategoryChange(cat)}
            className={`px-2.5 py-1 text-xs rounded border transition-all ${
              selectedCategory === cat
                ? "bg-amber-100/60 border-amber-600 text-amber-700 font-semibold"
                : "bg-stone-100 border-stone-300 text-stone-400 hover:border-stone-400 hover:text-stone-700"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      <div className="w-px h-4 bg-stone-200" />

      {/* 状态筛选 */}
      <div className="flex gap-1">
        {STATE_FILTERS.map((s) => (
          <button
            key={s.value}
            onClick={() => onStateChange(s.value)}
            className={`px-2.5 py-1 text-xs rounded border transition-all ${
              selectedState === s.value
                ? "bg-stone-200 border-gray-500 text-white font-semibold"
                : "bg-stone-100 border-stone-300 text-stone-400 hover:border-stone-400"
            }`}
          >
            {s.emoji} {s.label}
          </button>
        ))}
      </div>

      {/* 计数 */}
      <span className="ml-auto text-xs text-stone-400 font-mono">
        显示 <span className="text-stone-400 font-semibold">{filteredCount}</span> / {totalCount} 个品种
      </span>
    </div>
  );
}
