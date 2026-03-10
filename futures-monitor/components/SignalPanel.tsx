"use client";
// ============================================================
// 交易信号面板
// 做多信号：均线上行 + MACD扩口 + 放量 + 增仓
// 做空信号：均线下行 + MACD缩口 + 放量 + 增仓
// ============================================================

import React, { useState } from "react";
import { FuturesStatus } from "@/lib/types";
import { TrendingUp, TrendingDown, ChevronDown, ChevronUp, Zap, AlertTriangle } from "lucide-react";

interface SignalPanelProps {
  data: FuturesStatus[];
}

// 做多信号：均线上行 + MACD金叉区且快速走扩 + 放量 + 增仓
function isLongSignal(d: FuturesStatus): boolean {
  return (
    d.ma.status === "Upward" &&
    d.macd.sign === "positive" &&
    d.macd.rapidExpanding &&
    d.volume.status === "Surge" &&
    d.openInterest.status === "Increasing"
  );
}

// 做空信号：均线下行 + MACD死叉区且快速走扩 + 放量 + 增仓
function isShortSignal(d: FuturesStatus): boolean {
  return (
    d.ma.status === "Downward" &&
    d.macd.sign === "negative" &&
    d.macd.rapidExpanding &&
    d.volume.status === "Surge" &&
    d.openInterest.status === "Increasing"
  );
}

function signalScore(d: FuturesStatus, direction: "long" | "short"): number {
  let score = 0;
  if (direction === "long") {
    if (d.ma.status === "Upward") score++;
    if (d.macd.sign === "positive" && d.macd.rapidExpanding) score++;
    if (d.volume.status === "Surge") score++;
    if (d.openInterest.status === "Increasing") score++;
  } else {
    if (d.ma.status === "Downward") score++;
    if (d.macd.sign === "negative" && d.macd.rapidExpanding) score++;
    if (d.volume.status === "Surge") score++;
    if (d.openInterest.status === "Increasing") score++;
  }
  return score;
}

// 板块颜色
const CATEGORY_DOT: Record<string, string> = {
  贵金属: "bg-yellow-400", 有色: "bg-orange-400", 黑色: "bg-gray-400",
  农产品: "bg-lime-400", 油脂: "bg-amber-400", 能化: "bg-purple-400",
  建材: "bg-cyan-400", 股指: "bg-blue-400",
};

export default function SignalPanel({ data }: SignalPanelProps) {
  const [expanded, setExpanded] = useState(true);

  const longSignals = data.filter(isLongSignal);
  const shortSignals = data.filter(isShortSignal);

  // 三条件品种（差一个即触发预警）
  const nearLong = data.filter(
    (d) => !isLongSignal(d) && signalScore(d, "long") === 3
  );
  const nearShort = data.filter(
    (d) => !isShortSignal(d) && signalScore(d, "short") === 3
  );

  const hasSignal = longSignals.length > 0 || shortSignals.length > 0;
  const hasNear = nearLong.length > 0 || nearShort.length > 0;

  return (
    <div className={`rounded-lg border ${
      hasSignal
        ? "border-amber-600/50 bg-amber-950/20"
        : "border-gray-700/50 bg-gray-900/30"
    }`}>
      {/* 折叠标题栏 */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left"
      >
        <div className="flex items-center gap-3">
          <Zap size={14} className={hasSignal ? "text-amber-400" : "text-gray-500"} />
          <span className="text-sm font-semibold text-gray-200">
            交易信号
          </span>
          <div className="flex items-center gap-2">
            {longSignals.length > 0 && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-red-900/60 border border-red-700/60 text-red-300">
                <TrendingUp size={10} />
                做多 {longSignals.length}
              </span>
            )}
            {shortSignals.length > 0 && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-green-900/60 border border-green-700/60 text-green-300">
                <TrendingDown size={10} />
                做空 {shortSignals.length}
              </span>
            )}
            {!hasSignal && (
              <span className="text-xs text-gray-600">暂无满足四条件的品种</span>
            )}
            {hasNear && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-gray-800 border border-gray-700 text-gray-400">
                <AlertTriangle size={9} />
                待观察 {nearLong.length + nearShort.length}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 text-gray-500">
          <span className="text-[10px]">条件：均线 + MACD + 量能 + 持仓</span>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {/* 展开内容 */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gray-800/50 pt-3">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

            {/* 做多信号 */}
            <SignalColumn
              title="做多信号"
              subtitle="均线上行 · MACD金叉区快速走扩 · 放量 · 增仓"
              direction="long"
              signals={longSignals}
              near={nearLong}
              emptyText="暂无满足四条件的做多品种"
            />

            {/* 做空信号 */}
            <SignalColumn
              title="做空信号"
              subtitle="均线下行 · MACD死叉区快速走扩 · 放量 · 增仓"
              direction="short"
              signals={shortSignals}
              near={nearShort}
              emptyText="暂无满足四条件的做空品种"
            />
          </div>

          {/* 图例说明 */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 border-t border-gray-800/40 text-[10px] text-gray-600">
            <ConditionLegend icon="MA" color="text-blue-400" label="均线方向" />
            <ConditionLegend icon="MACD" color="text-amber-400" label="金叉/死叉区走扩" />
            <ConditionLegend icon="V" color="text-orange-400" label="成交量放量" />
            <ConditionLegend icon="OI" color="text-purple-400" label="持仓量增仓" />
            <span className="ml-auto text-gray-700">做多=金叉区+走扩 · 做空=死叉区+走扩 · 否则=粘合</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── 单侧信号列 ──
function SignalColumn({
  title,
  subtitle,
  direction,
  signals,
  near,
  emptyText,
}: {
  title: string;
  subtitle: string;
  direction: "long" | "short";
  signals: FuturesStatus[];
  near: FuturesStatus[];
  emptyText: string;
}) {
  const isLong = direction === "long";

  return (
    <div className={`rounded border ${
      isLong
        ? "border-red-800/40 bg-red-950/20"
        : "border-green-800/40 bg-green-950/20"
    } p-3`}>
      <div className="flex items-center gap-2 mb-2.5">
        {isLong
          ? <TrendingUp size={13} className="text-red-400" />
          : <TrendingDown size={13} className="text-green-400" />
        }
        <span className={`text-sm font-bold ${isLong ? "text-red-300" : "text-green-300"}`}>
          {title}
        </span>
        <span className="text-[10px] text-gray-600 font-normal">{subtitle}</span>
      </div>

      {signals.length > 0 ? (
        <div className="space-y-1.5 mb-3">
          {signals.map((d) => (
            <SignalCard key={d.symbol} data={d} direction={direction} confirmed />
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-600 mb-2">{emptyText}</p>
      )}

      {/* 待观察（3/4 条件） */}
      {near.length > 0 && (
        <>
          <div className="flex items-center gap-1.5 mb-1.5">
            <AlertTriangle size={10} className="text-gray-500" />
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">待观察（差一个条件）</span>
          </div>
          <div className="space-y-1">
            {near.map((d) => (
              <SignalCard key={d.symbol} data={d} direction={direction} confirmed={false} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ── 单品种信号卡片 ──
function SignalCard({
  data,
  direction,
  confirmed,
}: {
  data: FuturesStatus;
  direction: "long" | "short";
  confirmed: boolean;
}) {
  const isLong = direction === "long";

  // 各条件是否满足（MACD = 方向正确 且 快速走扩）
  const conds = isLong
    ? {
        MA:   data.ma.status === "Upward",
        MACD: data.macd.sign === "positive" && data.macd.rapidExpanding,
        V:    data.volume.status === "Surge",
        OI:   data.openInterest.status === "Increasing",
      }
    : {
        MA:   data.ma.status === "Downward",
        MACD: data.macd.sign === "negative" && data.macd.rapidExpanding,
        V:    data.volume.status === "Surge",
        OI:   data.openInterest.status === "Increasing",
      };

  const dotColor = CATEGORY_DOT[data.category] ?? "bg-gray-500";
  const priceColor = data.change > 0 ? "text-red-400" : data.change < 0 ? "text-green-400" : "text-gray-400";
  const changeSign = data.change > 0 ? "+" : "";

  return (
    <div className={`flex items-center justify-between px-2.5 py-1.5 rounded ${
      confirmed
        ? isLong
          ? "bg-red-950/50 border border-red-800/50"
          : "bg-green-950/50 border border-green-800/50"
        : "bg-gray-800/40 border border-gray-700/30"
    }`}>
      {/* 品种名 + 板块 */}
      <div className="flex items-center gap-2 min-w-[60px]">
        <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dotColor}`} />
        <span className="text-sm font-semibold text-gray-100">{data.symbol}</span>
        <span className="text-[10px] text-gray-600">{data.category}</span>
      </div>

      {/* 价格 */}
      <span className={`font-mono text-xs ${priceColor}`}>
        {changeSign}{data.change.toFixed(2)}%
      </span>

      {/* 条件指示点 */}
      <div className="flex items-center gap-1">
        {(Object.entries(conds) as [string, boolean][]).map(([key, met]) => (
          <span
            key={key}
            title={key}
            className={`inline-flex items-center justify-center w-5 h-5 rounded text-[9px] font-bold border ${
              met
                ? isLong
                  ? "bg-red-900/60 border-red-700 text-red-300"
                  : "bg-green-900/60 border-green-700 text-green-300"
                : "bg-gray-800/60 border-gray-700 text-gray-600"
            }`}
          >
            {key}
          </span>
        ))}
      </div>
    </div>
  );
}

function ConditionLegend({ icon, color, label }: { icon: string; color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`font-bold text-[10px] ${color}`}>{icon}</span>
      <span>{label}</span>
    </span>
  );
}
