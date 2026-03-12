"use client";
// ============================================================
// 抄底信号面板
// MA20 急速上行（斜率≥45°）→ MA20 支撑，收盘在 MA20 ±0.5% + MACD死叉缩窄
// MA20 缓慢上行（斜率<45°）→ MA60 支撑，收盘在 MA60 ±0.5% + MACD死叉缩窄
// ============================================================

import React, { useState } from "react";
import { FuturesStatus, DipSignal } from "@/lib/types";
import { ArrowDownToLine, ChevronDown, ChevronUp } from "lucide-react";

const CATEGORY_DOT: Record<string, string> = {
  贵金属: "bg-yellow-400", 有色: "bg-orange-400", 黑色: "bg-gray-400",
  农产品: "bg-lime-400",   油脂: "bg-amber-400",  能化: "bg-purple-400",
  建材: "bg-cyan-400",     股指: "bg-blue-400",
};

interface DipBuyPanelProps {
  data: FuturesStatus[];
}

export default function DipBuyPanel({ data }: DipBuyPanelProps) {
  const [expanded, setExpanded] = useState(true);

  const ma20Dips = data.filter((d) => d.dipSignal?.type === "MA20");
  const ma60Dips = data.filter((d) => d.dipSignal?.type === "MA60");
  const total = ma20Dips.length + ma60Dips.length;

  return (
    <div className={`rounded-lg border ${
      total > 0
        ? "border-teal-700/50 bg-teal-950/20"
        : "border-gray-700/50 bg-gray-900/30"
    }`}>
      {/* 折叠标题栏 */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left"
      >
        <div className="flex items-center gap-3">
          <ArrowDownToLine size={14} className={total > 0 ? "text-teal-400" : "text-gray-500"} />
          <span className="text-sm font-semibold text-gray-200">抄底信号</span>
          <div className="flex items-center gap-2">
            {ma20Dips.length > 0 && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-teal-900/60 border border-teal-700/60 text-teal-300">
                MA20抄底 {ma20Dips.length}
              </span>
            )}
            {ma60Dips.length > 0 && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-blue-900/60 border border-blue-700/60 text-blue-300">
                MA60抄底 {ma60Dips.length}
              </span>
            )}
            {total === 0 && (
              <span className="text-xs text-gray-600">暂无品种触及支撑抄底位</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 text-gray-500">
          <span className="text-[10px]">条件：MACD死叉缩窄 + 收盘距支撑≤0.5%</span>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {/* 展开内容 */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-800/50 pt-3 space-y-3">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

            {/* MA20 抄底列 */}
            <DipColumn
              title="MA20 抄底"
              subtitle="MA20急速上行（斜率≥45°）· 收盘贴近MA20支撑"
              colorClass="teal"
              items={ma20Dips}
              emptyText="无品种MA20斜率急速上行+触及MA20"
            />

            {/* MA60 抄底列 */}
            <DipColumn
              title="MA60 抄底"
              subtitle="MA20缓慢上行（斜率<45°）· 收盘贴近MA60支撑"
              colorClass="blue"
              items={ma60Dips}
              emptyText="无品种MA20缓慢上行+触及MA60"
            />
          </div>

          {/* 图例说明 */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 border-t border-gray-800/40 text-[10px] text-gray-600">
            <span><span className="text-teal-500">斜率≥0.2%/3K</span> = 急速上行(≥45°) → MA20支撑</span>
            <span><span className="text-blue-500">斜率0~0.2%/3K</span> = 缓慢上行(&lt;45°) → MA60支撑</span>
            <span className="ml-auto"><span className="text-gray-400">MACD死叉缩窄</span> = sign负+幅度未走扩(粘合)</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── 单侧信号列 ─────────────────────────────────────────────
function DipColumn({
  title,
  subtitle,
  colorClass,
  items,
  emptyText,
}: {
  title: string;
  subtitle: string;
  colorClass: "teal" | "blue";
  items: FuturesStatus[];
  emptyText: string;
}) {
  const titleColor = colorClass === "teal" ? "text-teal-400" : "text-blue-400";
  const subtitleColor = colorClass === "teal" ? "text-teal-700" : "text-blue-700";

  return (
    <div>
      <div className="mb-2">
        <span className={`text-xs font-bold ${titleColor}`}>{title}</span>
        <span className={`ml-2 text-[10px] ${subtitleColor}`}>{subtitle}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-gray-700 italic py-2">{emptyText}</p>
      ) : (
        <div className="space-y-1.5">
          {items.map((d) => (
            <DipCard key={d.symbol} d={d} sig={d.dipSignal!} colorClass={colorClass} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── 单个信号卡片 ──────────────────────────────────────────
function DipCard({
  d,
  sig,
  colorClass,
}: {
  d: FuturesStatus;
  sig: DipSignal;
  colorClass: "teal" | "blue";
}) {
  const dotColor = CATEGORY_DOT[d.category] ?? "bg-gray-500";
  const changeSign = d.change >= 0 ? "+" : "";

  const borderColor = colorClass === "teal"
    ? "border-teal-800/40 bg-teal-950/30"
    : "border-blue-800/40 bg-blue-950/30";
  const badgeColor = colorClass === "teal"
    ? "border-teal-700/50 bg-teal-900/40 text-teal-200"
    : "border-blue-700/50 bg-blue-900/40 text-blue-200";
  const distColor = sig.distPct <= 0.15
    ? "text-green-400"
    : colorClass === "teal" ? "text-teal-300" : "text-blue-300";
  const slopeColor = d.ma.slope20Pct > 0 ? "text-red-400" : "text-green-400";

  return (
    <div className={`rounded border ${borderColor} px-3 py-2 text-xs font-mono`}>
      {/* 第一行：名称 + 分类 + 信号标签 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotColor}`} />
          <span className="font-bold text-gray-100">{d.symbol}</span>
          <span className="text-gray-600 text-[10px]">{d.category}</span>
          <span className={`text-[10px] ${d.change >= 0 ? "text-red-400" : "text-green-400"}`}>
            {changeSign}{d.change.toFixed(2)}%
          </span>
        </div>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border font-bold ${badgeColor}`}>
          {sig.type} 抄底
        </span>
      </div>

      {/* 第二行：价格 / 支撑位 / 距离 / 斜率 / MACD */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-1.5 text-[10px] text-gray-500">
        <span>
          现价 <span className="text-gray-200 font-bold">{d.price}</span>
        </span>
        <span>
          {sig.type} <span className="text-gray-300">{sig.support}</span>
        </span>
        <span>
          距离 <span className={`font-bold ${distColor}`}>{sig.distPct.toFixed(3)}%</span>
        </span>
        <span>
          MA20斜率 <span className={slopeColor}>
            {d.ma.slope20Pct >= 0 ? "+" : ""}{d.ma.slope20Pct.toFixed(3)}%
          </span>
        </span>
        <span>
          MACD <span className="text-gray-400">死叉×{d.macd.cumulative}</span>
          <span className="text-gray-600 ml-1">
            ({d.macd.rapidExpanding ? "走扩" : "粘合"})
          </span>
        </span>
      </div>
    </div>
  );
}
