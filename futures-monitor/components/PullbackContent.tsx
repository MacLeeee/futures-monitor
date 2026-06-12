"use client";
// ============================================================
// H-005 MTF回踩信号内容
// ============================================================

import React from "react";
import { FuturesStatus, PullbackSignal } from "@/lib/types";

const CATEGORY_DOT: Record<string, string> = {
  贵金属: "bg-yellow-400", 有色: "bg-orange-400", 黑色: "bg-stone-400",
  农产品: "bg-lime-400",   油脂: "bg-amber-500",  能化: "bg-purple-400",
  建材: "bg-cyan-400",     股指: "bg-amber-400",
};

interface PullbackContentProps { data: FuturesStatus[] }

export default function PullbackContent({ data }: PullbackContentProps) {
  const longs  = data.filter((d) => d.pullbackSignal?.type === "long");
  const shorts = data.filter((d) => d.pullbackSignal?.type === "short");

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <PullbackColumn
        title="做多回踩"
        colorClass="long"
        items={longs}
        emptyText="暂无品种满足做多回踩条件"
      />
      <PullbackColumn
        title="做空反抽"
        colorClass="short"
        items={shorts}
        emptyText="暂无品种满足做空反抽条件"
      />
    </div>
  );
}

function PullbackColumn({ title, colorClass, items, emptyText }: {
  title: string; colorClass: "long" | "short";
  items: FuturesStatus[]; emptyText: string;
}) {
  const isLong = colorClass === "long";
  return (
    <div>
      <div className="mb-2">
        <span className={`text-xs font-bold ${isLong ? "text-teal-400" : "text-orange-600"}`}>{title}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-stone-300 italic py-2">{emptyText}</p>
      ) : (
        <div className="space-y-1.5">
          {items.map((d) => <PullbackCard key={d.symbol} d={d} sig={d.pullbackSignal!} isLong={isLong} />)}
        </div>
      )}
    </div>
  );
}

function PullbackCard({ d, sig, isLong }: { d: FuturesStatus; sig: PullbackSignal; isLong: boolean }) {
  const dot      = CATEGORY_DOT[d.category] ?? "bg-stone-500";
  const border   = isLong ? "border-teal-800/40 bg-teal-950/30" : "border-orange-800/40 bg-orange-950/30";
  const badge    = isLong ? "border-teal-700/50 bg-teal-900/40 text-teal-200" : "border-orange-200 bg-orange-900/40 text-orange-200";
  const q        = sig.quality ?? {};
  const isSweep  = sig.trigger === "sweep";
  const tet      = sig.tet;

  return (
    <div className={`rounded border ${border} px-3 py-2 text-xs font-mono`}>
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dot}`} />
          <span className="font-bold text-stone-900">{d.symbol}</span>
          <span className="text-stone-400 text-[10px]">{d.category}</span>
          <span className={`text-[10px] ${d.change >= 0 ? "text-red-600" : "text-emerald-600"}`}>
            {d.change >= 0 ? "+" : ""}{d.change.toFixed(2)}%
          </span>
        </div>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border font-bold ${badge}`}>
          {isSweep ? "⚡扫损" : sig.trigger}@{sig.zone}
        </span>
      </div>
      <div className="flex items-center gap-2 text-[10px] text-stone-500">
        <span>entry={sig.entry}</span>
        <span>SL={sig.stopLoss}</span>
        <span className={isLong ? "text-teal-500" : "text-orange-500"}>risk={sig.riskPct}%</span>
        <span>pb={q.pbBars}K</span>
        <span>ret={q.retrace?.toFixed(2)}</span>
        <span>vr={q.volRatio?.toFixed(2)}</span>
      </div>
      {tet && (
        <div className="flex items-center gap-1.5 mt-1 text-[9px]">
          <span className="text-teal-300">TET</span>
          <span className="text-stone-400">ATS={tet.ats?.toFixed(2)}</span>
          <span className="text-stone-400">EI={tet.eiNow?.toFixed(2)}</span>
          <span className="text-stone-400">TI={tet.ti?.toFixed(2)}</span>
        </div>
      )}
    </div>
  );
}
