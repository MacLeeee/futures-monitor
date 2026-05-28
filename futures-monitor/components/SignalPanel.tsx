"use client";
// ============================================================
// 突破信号面板（多周期）
// 方向层：30min MA 排列（上行/下行）
// 触发层：15min MACD 扩口 + 15min 放量 + 15min 增仓（宽松）
// ============================================================

import React, { useState } from "react";
import { FuturesStatus } from "@/lib/types";
import { TrendingUp, TrendingDown, ChevronDown, ChevronUp, Zap, AlertTriangle } from "lucide-react";

const CATEGORY_DOT: Record<string, string> = {
  贵金属: "bg-yellow-400", 有色: "bg-orange-400", 黑色: "bg-gray-400",
  农产品: "bg-lime-400", 油脂: "bg-blue-500", 能化: "bg-purple-400",
  建材: "bg-cyan-400", 股指: "bg-blue-400",
};

interface SignalPanelProps { data: FuturesStatus[] }

export default function SignalPanel({ data }: SignalPanelProps) {
  const [expanded, setExpanded] = useState(true);

  const longs  = data.filter((d) => d.breakoutSignal?.type === "long");
  const shorts = data.filter((d) => d.breakoutSignal?.type === "short");

  // 近信号：MA 方向正确 + 15min MACD 正确 + 15min 放量，仅缺增仓
  const nearLong = data.filter(
    (d) => !d.breakoutSignal &&
      d.ma.status === "Upward" &&
      d.macd.sign === "positive" && d.macd.rapidExpanding &&
      d.volume.status === "Surge"
  );
  const nearShort = data.filter(
    (d) => !d.breakoutSignal &&
      d.ma.status === "Downward" &&
      d.macd.sign === "negative" && d.macd.rapidExpanding &&
      d.volume.status === "Surge"
  );

  // 均线方向首根变化（单独提示）
  const maFirstUp = data.filter((d) => d.ma.status === "Upward"   && d.ma.cumulative === 1);
  const maFirstDn = data.filter((d) => d.ma.status === "Downward" && d.ma.cumulative === 1);

  const hasSignal = longs.length > 0 || shorts.length > 0;
  const hasNear   = nearLong.length > 0 || nearShort.length > 0;

  return (
    <div className={`rounded-lg border ${
      hasSignal ? "border-blue-400/50 bg-blue-50/40" : "border-gray-200 bg-gray-50/60"
    }`}>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left"
      >
        <div className="flex items-center gap-3">
          <Zap size={14} className={hasSignal ? "text-blue-500" : "text-gray-500"} />
          <span className="text-sm font-semibold text-gray-800">突破信号</span>
          <div className="flex items-center gap-2">
            {longs.length > 0 && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-red-100/60 border border-red-300 text-red-700">
                <TrendingUp size={10} /> 做多 {longs.length}
              </span>
            )}
            {shorts.length > 0 && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-emerald-100/60 border border-emerald-300 text-emerald-700">
                <TrendingDown size={10} /> 做空 {shorts.length}
              </span>
            )}
            {!hasSignal && !hasNear && (maFirstUp.length + maFirstDn.length === 0) && (
              <span className="text-xs text-gray-400">暂无满足条件的品种</span>
            )}
            {hasNear && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-gray-100 border border-gray-300 text-gray-400">
                <AlertTriangle size={9} /> 待观察 {nearLong.length + nearShort.length}
              </span>
            )}
            {(maFirstUp.length + maFirstDn.length) > 0 && (
              <span className="px-2 py-0.5 rounded-full text-xs bg-blue-100/40 border border-blue-200 text-blue-600">
                首根变化 {maFirstUp.length + maFirstDn.length}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 text-gray-500">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gray-200 pt-3">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <BreakoutColumn title="做多突破" subtitle="30m上行 · 15m金叉扩口 · 15m放量" direction="long"
              signals={longs} near={nearLong} />
            <BreakoutColumn title="做空突破" subtitle="30m下行 · 15m死叉扩口 · 15m放量" direction="short"
              signals={shorts} near={nearShort} />
          </div>

          {/* 均线首根变化 */}
          {(maFirstUp.length + maFirstDn.length) > 0 && (
            <div className="border-t border-gray-200 pt-2 flex flex-wrap gap-2">
              <span className="text-[10px] text-gray-500 self-center">30m均线首根变化：</span>
              {maFirstUp.map((d) => (
                <span key={d.symbol} className="text-[10px] px-1.5 py-0.5 rounded bg-red-50/60 border border-red-200 text-red-600">
                  ↗ {d.symbol}
                </span>
              ))}
              {maFirstDn.map((d) => (
                <span key={d.symbol} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50/60 border border-emerald-200 text-emerald-600">
                  ↘ {d.symbol}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function BreakoutColumn({ title, subtitle, direction, signals, near }: {
  title: string; subtitle: string; direction: "long" | "short";
  signals: FuturesStatus[]; near: FuturesStatus[];
}) {
  const isLong = direction === "long";
  return (
    <div className={`rounded border p-3 ${
      isLong ? "border-red-200 bg-red-50/40" : "border-emerald-200 bg-emerald-50/40"
    }`}>
      <div className="flex items-center gap-2 mb-2.5">
        {isLong ? <TrendingUp size={13} className="text-red-600" /> : <TrendingDown size={13} className="text-emerald-600" />}
        <span className={`text-sm font-bold ${isLong ? "text-red-700" : "text-emerald-700"}`}>{title}</span>
      </div>
      {signals.length > 0 ? (
        <div className="space-y-1.5 mb-2">
          {signals.map((d) => <BreakoutCard key={d.symbol} d={d} isLong={isLong} confirmed />)}
        </div>
      ) : (
        <p className="text-xs text-gray-400 mb-2">暂无满足全条件的品种</p>
      )}
      {near.length > 0 && (
        <>
          <div className="flex items-center gap-1.5 mb-1">
            <AlertTriangle size={10} className="text-gray-500" />
            <span className="text-[10px] text-gray-500">待观察（仅缺增仓）</span>
          </div>
          <div className="space-y-1">
            {near.map((d) => <BreakoutCard key={d.symbol} d={d} isLong={isLong} confirmed={false} />)}
          </div>
        </>
      )}
    </div>
  );
}

function BreakoutCard({ d, isLong, confirmed }: { d: FuturesStatus; isLong: boolean; confirmed: boolean }) {
  const dot    = CATEGORY_DOT[d.category] ?? "bg-gray-500";
  const chgClr = d.change > 0 ? "text-red-600" : d.change < 0 ? "text-emerald-600" : "text-gray-400";
  const sig    = d.breakoutSignal;

  return (
    <div className={`flex items-center justify-between px-2.5 py-1.5 rounded text-xs font-mono ${
      confirmed
        ? isLong ? "bg-red-50/80 border border-red-200" : "bg-emerald-50/80 border border-emerald-200"
        : "bg-gray-100 border border-gray-300/30"
    }`}>
      <div className="flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
        <span className="font-bold text-gray-900">{d.symbol}</span>
        <span className="text-[10px] text-gray-400">{d.category}</span>
        <span className={`text-[10px] ${chgClr}`}>
          {d.change >= 0 ? "+" : ""}{d.change.toFixed(2)}%
        </span>
      </div>
      <div className="flex items-center gap-1 text-[10px]">
        <span className="text-gray-500">MA×{d.ma.cumulative}</span>
        <span className="text-gray-500">·</span>
        <span className={isLong ? "text-blue-500" : "text-blue-500"}>
          {sig ? `${sig.expansionRate.toFixed(1)}x` : "MACD"}
        </span>
        {sig?.oiConfirmed && <span className="text-purple-600 ml-0.5">+OI</span>}
      </div>
    </div>
  );
}
