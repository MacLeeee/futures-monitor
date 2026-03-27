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
  农产品: "bg-lime-400", 油脂: "bg-amber-400", 能化: "bg-purple-400",
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
      hasSignal ? "border-amber-600/50 bg-amber-950/20" : "border-gray-700/50 bg-gray-900/30"
    }`}>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left"
      >
        <div className="flex items-center gap-3">
          <Zap size={14} className={hasSignal ? "text-amber-400" : "text-gray-500"} />
          <span className="text-sm font-semibold text-gray-200">突破信号</span>
          <div className="flex items-center gap-2">
            {longs.length > 0 && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-red-900/60 border border-red-700/60 text-red-300">
                <TrendingUp size={10} /> 做多 {longs.length}
              </span>
            )}
            {shorts.length > 0 && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold bg-green-900/60 border border-green-700/60 text-green-300">
                <TrendingDown size={10} /> 做空 {shorts.length}
              </span>
            )}
            {!hasSignal && !hasNear && (maFirstUp.length + maFirstDn.length === 0) && (
              <span className="text-xs text-gray-600">暂无满足条件的品种</span>
            )}
            {hasNear && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-gray-800 border border-gray-700 text-gray-400">
                <AlertTriangle size={9} /> 待观察 {nearLong.length + nearShort.length}
              </span>
            )}
            {(maFirstUp.length + maFirstDn.length) > 0 && (
              <span className="px-2 py-0.5 rounded-full text-xs bg-blue-900/40 border border-blue-800/50 text-blue-400">
                首根变化 {maFirstUp.length + maFirstDn.length}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 text-gray-500">
          <span className="text-[10px]">30m均线斜率同向 · 15m MACD扩口 · 15m放量&gt;均量</span>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gray-800/50 pt-3">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <BreakoutColumn title="做多突破" subtitle="30m上行 · 15m金叉扩口 · 15m放量" direction="long"
              signals={longs} near={nearLong} />
            <BreakoutColumn title="做空突破" subtitle="30m下行 · 15m死叉扩口 · 15m放量" direction="short"
              signals={shorts} near={nearShort} />
          </div>

          {/* 均线首根变化 */}
          {(maFirstUp.length + maFirstDn.length) > 0 && (
            <div className="border-t border-gray-800/40 pt-2 flex flex-wrap gap-2">
              <span className="text-[10px] text-gray-500 self-center">30m均线首根变化：</span>
              {maFirstUp.map((d) => (
                <span key={d.symbol} className="text-[10px] px-1.5 py-0.5 rounded bg-red-950/40 border border-red-800/40 text-red-400">
                  ↗ {d.symbol}
                </span>
              ))}
              {maFirstDn.map((d) => (
                <span key={d.symbol} className="text-[10px] px-1.5 py-0.5 rounded bg-green-950/40 border border-green-800/40 text-green-400">
                  ↘ {d.symbol}
                </span>
              ))}
            </div>
          )}

          <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 border-t border-gray-800/40 text-[10px] text-gray-600">
            <span><span className="text-blue-400">MA 30m</span> = 方向层（斜率同向上/下）</span>
            <span><span className="text-amber-400">MACD 15m</span> = 触发层（金/死叉快速扩口）</span>
            <span><span className="text-orange-400">V 15m</span> = 放量且高于均量（双确认）</span>
            <span className="ml-auto text-gray-700"><span className="text-purple-400">+OI</span> = 增仓（或有加分项，不影响触发）</span>
          </div>
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
      isLong ? "border-red-800/40 bg-red-950/20" : "border-green-800/40 bg-green-950/20"
    }`}>
      <div className="flex items-center gap-2 mb-2.5">
        {isLong ? <TrendingUp size={13} className="text-red-400" /> : <TrendingDown size={13} className="text-green-400" />}
        <span className={`text-sm font-bold ${isLong ? "text-red-300" : "text-green-300"}`}>{title}</span>
        <span className="text-[10px] text-gray-600">{subtitle}</span>
      </div>
      {signals.length > 0 ? (
        <div className="space-y-1.5 mb-2">
          {signals.map((d) => <BreakoutCard key={d.symbol} d={d} isLong={isLong} confirmed />)}
        </div>
      ) : (
        <p className="text-xs text-gray-600 mb-2">暂无满足全条件的品种</p>
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
  const chgClr = d.change > 0 ? "text-red-400" : d.change < 0 ? "text-green-400" : "text-gray-400";
  const sig    = d.breakoutSignal;

  return (
    <div className={`flex items-center justify-between px-2.5 py-1.5 rounded text-xs font-mono ${
      confirmed
        ? isLong ? "bg-red-950/50 border border-red-800/50" : "bg-green-950/50 border border-green-800/50"
        : "bg-gray-800/40 border border-gray-700/30"
    }`}>
      <div className="flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
        <span className="font-bold text-gray-100">{d.symbol}</span>
        <span className="text-[10px] text-gray-600">{d.category}</span>
        <span className={`text-[10px] ${chgClr}`}>
          {d.change >= 0 ? "+" : ""}{d.change.toFixed(2)}%
        </span>
      </div>
      <div className="flex items-center gap-1 text-[10px]">
        <span className="text-gray-500">MA×{d.ma.cumulative}</span>
        <span className="text-gray-500">·</span>
        <span className={isLong ? "text-amber-400" : "text-amber-400"}>
          {sig ? `${sig.expansionRate.toFixed(1)}x` : "MACD"}
        </span>
        {sig?.oiConfirmed && <span className="text-purple-400 ml-0.5">+OI</span>}
      </div>
    </div>
  );
}
