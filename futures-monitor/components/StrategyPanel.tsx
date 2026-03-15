"use client";
// ============================================================
// 回踩策略信号面板
// 做多: 日MA20上方 · 30m多头排列 · 回踩MA20/MA60 · MACD金叉扩口 · 放量
// 做空: 日MA20下方 · 30m空头排列 · 反抽MA20/MA60 · MACD死叉扩口 · 放量
// ============================================================

import React, { useState } from "react";
import { FuturesStatus, StrategySignal } from "@/lib/types";
import { Target, ChevronDown, ChevronUp } from "lucide-react";

const CATEGORY_DOT: Record<string, string> = {
  贵金属: "bg-yellow-400", 有色: "bg-orange-400", 黑色: "bg-gray-400",
  农产品: "bg-lime-400",   油脂: "bg-amber-400",  能化: "bg-purple-400",
  建材: "bg-cyan-400",     股指: "bg-blue-400",
};

interface StrategyPanelProps {
  data: FuturesStatus[];
}

export default function StrategyPanel({ data }: StrategyPanelProps) {
  const [expanded, setExpanded] = useState(true);

  const longs  = data.filter((d) => d.strategySignal?.type === "long");
  const shorts = data.filter((d) => d.strategySignal?.type === "short");
  const total  = longs.length + shorts.length;

  return (
    <div className={`rounded-lg border ${
      total > 0
        ? "border-violet-700/50 bg-violet-950/20"
        : "border-gray-700/50 bg-gray-900/30"
    }`}>
      {/* 折叠标题栏 */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left"
      >
        <div className="flex items-center gap-3">
          <Target size={14} className={total > 0 ? "text-violet-400" : "text-gray-500"} />
          <span className="text-sm font-semibold text-gray-200">回踩策略</span>
          <div className="flex items-center gap-2">
            {longs.length > 0 && (
              <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-900/60 border border-emerald-700/60 text-emerald-300">
                做多回踩 {longs.length}
              </span>
            )}
            {shorts.length > 0 && (
              <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-red-900/60 border border-red-700/60 text-red-300">
                做空反抽 {shorts.length}
              </span>
            )}
            {total === 0 && (
              <span className="text-xs text-gray-600">暂无满足回踩条件的品种</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 text-gray-500">
          <span className="text-[10px]">
            条件：日MA20过滤 · 30m排列 · 回踩均线≤0.5% · MACD扩口 · 放量
          </span>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {/* 展开内容 */}
      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-800/50 pt-3 space-y-3">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* 做多列 */}
            <StrategyColumn
              title="做多回踩"
              subtitle="30m多头排列(MA20>MA60) · 价格回踩MA20/MA60 · 金叉扩口 · 放量 · 日MA20上方"
              colorClass="long"
              items={longs}
              emptyText="暂无满足做多回踩条件的品种"
            />
            {/* 做空列 */}
            <StrategyColumn
              title="做空反抽"
              subtitle="30m空头排列(MA20<MA60) · 价格反抽MA20/MA60 · 死叉扩口 · 放量 · 日MA20下方"
              colorClass="short"
              items={shorts}
              emptyText="暂无满足做空反抽条件的品种"
            />
          </div>

          {/* 图例说明 */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 border-t border-gray-800/40 text-[10px] text-gray-600">
            <span><span className="text-emerald-500">做多</span>: 日MA20↑ · MA20&gt;MA60 · 回踩均线 · 金叉走扩 · 放量</span>
            <span><span className="text-red-500">做空</span>: 日MA20↓ · MA20&lt;MA60 · 反抽均线 · 死叉走扩 · 放量</span>
            <span className="ml-auto text-gray-700">回踩距离≤0.5% · 均线排列由30m MA20/MA60决定</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── 单侧信号列 ─────────────────────────────────────────────
function StrategyColumn({
  title,
  subtitle,
  colorClass,
  items,
  emptyText,
}: {
  title: string;
  subtitle: string;
  colorClass: "long" | "short";
  items: FuturesStatus[];
  emptyText: string;
}) {
  const titleColor    = colorClass === "long" ? "text-emerald-400" : "text-red-400";
  const subtitleColor = colorClass === "long" ? "text-emerald-800" : "text-red-900";

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
            <StrategyCard key={d.symbol} d={d} sig={d.strategySignal!} colorClass={colorClass} />
          ))}
        </div>
      )}
    </div>
  );
}

// ── 单个信号卡片 ──────────────────────────────────────────
function StrategyCard({
  d,
  sig,
  colorClass,
}: {
  d: FuturesStatus;
  sig: StrategySignal;
  colorClass: "long" | "short";
}) {
  const dotColor     = CATEGORY_DOT[d.category] ?? "bg-gray-500";
  const changeSign   = d.change >= 0 ? "+" : "";
  const isLong       = colorClass === "long";

  const borderColor  = isLong
    ? "border-emerald-800/40 bg-emerald-950/30"
    : "border-red-800/40 bg-red-950/30";
  const badgeColor   = isLong
    ? "border-emerald-700/50 bg-emerald-900/40 text-emerald-200"
    : "border-red-700/50 bg-red-900/40 text-red-200";
  const distColor    = sig.distPct <= 0.15 ? "text-yellow-400" : isLong ? "text-emerald-300" : "text-red-300";

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
          {isLong ? "↗" : "↘"} {isLong ? "做多" : "做空"} {sig.bounceAt}
        </span>
      </div>

      {/* 第二行：价格 / 均线值 / 回踩距离 / 日MA20 / MACD */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-1.5 text-[10px] text-gray-500">
        <span>现价 <span className="text-gray-200 font-bold">{d.price}</span></span>
        <span>
          {sig.bounceAt} <span className="text-gray-300">{sig.bounceAt === "MA20" ? sig.ma20 : sig.ma60}</span>
        </span>
        <span>
          距离 <span className={`font-bold ${distColor}`}>{sig.distPct.toFixed(3)}%</span>
        </span>
        {sig.dailyMa20 && (
          <span>
            日MA20 <span className={isLong ? "text-emerald-400" : "text-red-400"}>{sig.dailyMa20}</span>
          </span>
        )}
        <span>
          MACD
          <span className={`ml-1 ${isLong ? "text-emerald-400" : "text-red-400"}`}>
            {isLong ? "金叉" : "死叉"}×{d.macd.cumulative}
          </span>
          <span className="text-yellow-500 ml-1">走扩</span>
        </span>
      </div>
    </div>
  );
}
