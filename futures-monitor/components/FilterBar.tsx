"use client";
// ============================================================
// 筛选栏组件 - 按板块、均线状态、MACD 状态快速过滤
// ============================================================

import React from "react";
import { Filter } from "lucide-react";

interface FilterBarProps {
  selectedCategory: string;
  selectedMAStatus: string;
  onCategoryChange: (v: string) => void;
  onMAStatusChange: (v: string) => void;
  totalCount: number;
  filteredCount: number;
}

const CATEGORIES = ["全部", "贵金属", "有色", "黑色", "农产品", "油脂", "能化", "建材", "股指"];
const MA_STATUSES = [
  { value: "全部", label: "全部状态" },
  { value: "Upward",   label: "均线上行" },
  { value: "Downward", label: "均线下行" },
  { value: "Silent",   label: "均线静默" },
];

export default function FilterBar({
  selectedCategory,
  selectedMAStatus,
  onCategoryChange,
  onMAStatusChange,
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

      {/* 均线状态筛选 */}
      <div className="flex gap-1">
        {MA_STATUSES.map((s) => (
          <button
            key={s.value}
            onClick={() => onMAStatusChange(s.value)}
            className={`px-2.5 py-1 text-xs rounded border transition-all ${
              selectedMAStatus === s.value
                ? "bg-stone-200 border-gray-500 text-white font-semibold"
                : "bg-stone-100 border-stone-300 text-stone-400 hover:border-stone-400"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* 过滤结果计数 */}
      <span className="ml-auto text-xs text-stone-400 font-mono">
        显示 <span className="text-stone-400 font-semibold">{filteredCount}</span> / {totalCount} 个品种
      </span>
    </div>
  );
}
