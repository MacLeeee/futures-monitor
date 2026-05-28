"use client";
// ============================================================
// 回踩信号面板（多周期）
// 方向层：30min MA60 锚定多空
//   price > MA60(30m) → 多头方向，等回踩 MA20/MA60 支撑
//   price < MA60(30m) → 空头方向，等反抽 MA20/MA60 阻力
// 触发层：15min MACD 缩窄（粘合）+ 15min 放量
// ============================================================

import React, { useState } from "react";
import { FuturesStatus, PullbackSignal } from "@/lib/types";
import { ArrowDownToLine, ChevronDown, ChevronUp } from "lucide-react";

const CATEGORY_DOT: Record<string, string> = {
  贵金属: "bg-yellow-400", 有色: "bg-orange-400", 黑色: "bg-gray-400",
  农产品: "bg-lime-400",   油脂: "bg-blue-500",  能化: "bg-purple-400",
  建材: "bg-cyan-400",     股指: "bg-blue-400",
};

interface DipBuyPanelProps { data: FuturesStatus[] }

export default function DipBuyPanel({ data }: DipBuyPanelProps) {
  const [expanded, setExpanded] = useState(true);

  const longs  = data.filter((d) => d.pullbackSignal?.type === "long");
  const shorts = data.filter((d) => d.pullbackSignal?.type === "short");
  const total  = longs.length + shorts.length;

  return (
    <div className={`rounded-lg border ${
      total > 0 ? "border-teal-700/50 bg-teal-950/20" : "border-gray-200 bg-gray-50/60"
    }`}>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left"
      >
        <div className="flex items-center gap-3">
          <ArrowDownToLine size={14} className={total > 0 ? "text-teal-400" : "text-gray-500"} />
          <span className="text-sm font-semibold text-gray-800">回踩信号</span>
          <div className="flex items-center gap-2">
            {longs.length > 0 && (
              <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-teal-900/60 border border-teal-700/60 text-teal-300">
                做多回踩 {longs.length}
              </span>
            )}
            {shorts.length > 0 && (
              <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-orange-900/60 border border-orange-300/60 text-orange-700">
                做空反抽 {shorts.length}
              </span>
            )}
            {total === 0 && (
              <span className="text-xs text-gray-400">暂无品种回踩均线支撑/阻力位</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 text-gray-500">
          <span className="text-[10px]">30m MA60锚定方向 · 价格回踩≤0.5% · 15m MACD缩窄 · 15m放量</span>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-gray-200 pt-3 space-y-3">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <PullbackColumn
              title="做多回踩"
              subtitle="30m MA60上方·价格贴近MA20/MA60·15m死叉缩窄·15m放量"
              colorClass="long"
              items={longs}
              emptyText="暂无品种满足做多回踩条件"
            />
            <PullbackColumn
              title="做空反抽"
              subtitle="30m MA60下方·价格贴近MA20/MA60·15m金叉缩窄·15m放量"
              colorClass="short"
              items={shorts}
              emptyText="暂无品种满足做空反抽条件"
            />
          </div>

          <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 border-t border-gray-200 text-[10px] text-gray-400">
            <span><span className="text-teal-500">做多回踩</span>: price&gt;MA60 · 贴近MA20(steep)/MA60(gentle) · 15m死叉+粘合</span>
            <span><span className="text-orange-500">做空反抽</span>: price&lt;MA60 · 贴近MA20(declining)/MA60 · 15m金叉+粘合</span>
            <span className="ml-auto text-gray-300">回踩距离≤0.5% · 放量确认</span>
          </div>
        </div>
      )}
    </div>
  );
}

function PullbackColumn({ title, subtitle, colorClass, items, emptyText }: {
  title: string; subtitle: string; colorClass: "long" | "short";
  items: FuturesStatus[]; emptyText: string;
}) {
  const isLong = colorClass === "long";
  return (
    <div>
      <div className="mb-2">
        <span className={`text-xs font-bold ${isLong ? "text-teal-400" : "text-orange-600"}`}>{title}</span>
        <span className={`ml-2 text-[10px] ${isLong ? "text-teal-800" : "text-orange-800"}`}>{subtitle}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-gray-300 italic py-2">{emptyText}</p>
      ) : (
        <div className="space-y-1.5">
          {items.map((d) => <PullbackCard key={d.symbol} d={d} sig={d.pullbackSignal!} isLong={isLong} />)}
        </div>
      )}
    </div>
  );
}

function PullbackCard({ d, sig, isLong }: { d: FuturesStatus; sig: PullbackSignal; isLong: boolean }) {
  const dot      = CATEGORY_DOT[d.category] ?? "bg-gray-500";
  const border   = isLong ? "border-teal-800/40 bg-teal-950/30" : "border-orange-800/40 bg-orange-950/30";
  const badge    = isLong ? "border-teal-700/50 bg-teal-900/40 text-teal-200" : "border-orange-200 bg-orange-900/40 text-orange-200";
  const distClr  = sig.distPct <= 0.15 ? "text-yellow-600" : isLong ? "text-teal-300" : "text-orange-700";
  const slopeClr = d.ma.slope20Pct >= 0 ? "text-red-600" : "text-emerald-600";

  return (
    <div className={`rounded border ${border} px-3 py-2 text-xs font-mono`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dot}`} />
          <span className="font-bold text-gray-900">{d.symbol}</span>
          <span className="text-gray-400 text-[10px]">{d.category}</span>
          <span className={`text-[10px] ${d.change >= 0 ? "text-red-600" : "text-emerald-600"}`}>
            {d.change >= 0 ? "+" : ""}{d.change.toFixed(2)}%
          </span>
        </div>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border font-bold ${badge}`}>
          {isLong ? "↩" : "↪"} {isLong ? "做多回踩" : "做空反抽"} {sig.target}
        </span>
        {/* 方向标记：做多回踩显示价格是否仍在均线上方 */}
        <span className={`text-[10px] px-1 rounded ${
          isLong
            ? sig.aboveMa ? "text-teal-400" : "text-yellow-500"
            : sig.aboveMa ? "text-yellow-500" : "text-orange-600"
        }`}>
          {isLong
            ? (sig.aboveMa ? "↗贴近" : "↘微穿")
            : (sig.aboveMa ? "↗微突" : "↙贴近")}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-1.5 text-[10px] text-gray-500">
        <span>现价 <span className="text-gray-800 font-bold">{d.price}</span></span>
        <span>
          {sig.target} <span className="text-gray-300">{sig.support}</span>
        </span>
        <span>
          距离 <span className={`font-bold ${distClr}`}>{sig.distPct.toFixed(3)}%</span>
        </span>
        <span>
          MA20斜率 <span className={slopeClr}>{d.ma.slope20Pct >= 0 ? "+" : ""}{d.ma.slope20Pct.toFixed(3)}%</span>
        </span>
        <span>
          15m MACD <span className={`${isLong ? "text-teal-400" : "text-orange-600"}`}>
            {isLong ? "死叉粘合" : "金叉粘合"}
          </span>
          <span className="text-gray-400 ml-1">×{d.macd.cumulative}</span>
        </span>
        <span>
          15m量 <span className="text-blue-500">放量</span>
        </span>
      </div>
    </div>
  );
}
