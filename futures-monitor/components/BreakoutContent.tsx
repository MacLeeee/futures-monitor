"use client";
// ============================================================
// 突破信号内容（从 SignalPanel 提取）
// ============================================================

import React from "react";
import { FuturesStatus } from "@/lib/types";
import { TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";

const CATEGORY_DOT: Record<string, string> = {
  贵金属: "bg-yellow-400", 有色: "bg-orange-400", 黑色: "bg-stone-400",
  农产品: "bg-lime-400", 油脂: "bg-amber-500", 能化: "bg-purple-400",
  建材: "bg-cyan-400", 股指: "bg-amber-400",
};

interface BreakoutContentProps { data: FuturesStatus[] }

export default function BreakoutContent({ data }: BreakoutContentProps) {
  const longs  = data.filter((d) => d.breakoutSignal?.type === "long");
  const shorts = data.filter((d) => d.breakoutSignal?.type === "short");

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

  const maFirstUp = data.filter((d) => d.ma.status === "Upward"   && d.ma.cumulative === 1);
  const maFirstDn = data.filter((d) => d.ma.status === "Downward" && d.ma.cumulative === 1);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <BreakoutColumn title="做多突破" direction="long"
          signals={longs} near={nearLong} />
        <BreakoutColumn title="做空突破" direction="short"
          signals={shorts} near={nearShort} />
      </div>

      {(maFirstUp.length + maFirstDn.length) > 0 && (
        <div className="border-t border-stone-200 pt-2 flex flex-wrap gap-2">
          <span className="text-[10px] text-stone-500 self-center">30m均线首根变化：</span>
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
  );
}

function BreakoutColumn({ title, direction, signals, near }: {
  title: string; direction: "long" | "short";
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
        <p className="text-xs text-stone-400 mb-2">暂无满足全条件的品种</p>
      )}
      {near.length > 0 && (
        <>
          <div className="flex items-center gap-1.5 mb-1">
            <AlertTriangle size={10} className="text-stone-500" />
            <span className="text-[10px] text-stone-500">待观察（仅缺增仓）</span>
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
  const dot    = CATEGORY_DOT[d.category] ?? "bg-stone-500";
  const chgClr = d.change > 0 ? "text-red-600" : d.change < 0 ? "text-emerald-600" : "text-stone-400";
  const sig    = d.breakoutSignal;

  return (
    <div className={`flex items-center justify-between px-2.5 py-1.5 rounded text-xs font-mono ${
      confirmed
        ? isLong ? "bg-red-50/80 border border-red-200" : "bg-emerald-50/80 border border-emerald-200"
        : "bg-stone-100 border border-stone-300/30"
    }`}>
      <div className="flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
        <span className="font-bold text-stone-900">{d.symbol}</span>
        <span className="text-[10px] text-stone-400">{d.category}</span>
        <span className={`text-[10px] ${chgClr}`}>
          {d.change >= 0 ? "+" : ""}{d.change.toFixed(2)}%
        </span>
      </div>
      <div className="flex items-center gap-1 text-[10px]">
        <span className="text-stone-500">MA×{d.ma.cumulative}</span>
        <span className="text-stone-500">·</span>
        <span className="text-amber-500">
          {sig ? `${sig.expansionRate.toFixed(1)}x` : "MACD"}
        </span>
        {sig?.oiConfirmed && <span className="text-purple-600 ml-0.5">+OI</span>}
      </div>
    </div>
  );
}
