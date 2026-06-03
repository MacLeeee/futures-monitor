"use client";

import React from "react";
import { Position } from "@/lib/types";

interface Props {
  positions: Position[];
  currentPrices: Record<string, number>;
}

export default function CurrentPositions({ positions, currentPrices }: Props) {
  const open = positions.filter((p) => p.status === "open");
  const longs  = open.filter((p) => p.direction === "long");
  const shorts = open.filter((p) => p.direction === "short");

  // 计算浮盈
  let totalPnl = 0;
  let pnlCount = 0;
  const posWithPnl = open.map((p) => {
    const cur = currentPrices[p.symbol] ?? p.entryPrice;
    const pts = p.direction === "long" ? cur - p.entryPrice : p.entryPrice - cur;
    totalPnl += pts;
    pnlCount++;
    return { ...p, floatPts: pts };
  });

  if (open.length === 0) {
    return (
      <div className="rounded-lg border border-stone-200 bg-white px-3 py-2">
        <span className="text-xs text-stone-400">📋 暂无持仓</span>
      </div>
    );
  }

  const pnlClr = totalPnl >= 0 ? "text-emerald-500" : "text-red-500";
  const pnlBg  = totalPnl >= 0 ? "bg-emerald-50" : "bg-red-50";

  return (
    <div className="rounded-lg border border-stone-200 bg-white px-3 py-2">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-xs font-semibold text-stone-800">📋 持仓</span>

        {/* 浮盈汇总 */}
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold font-mono ${pnlBg} ${pnlClr}`}>
          浮盈 {totalPnl >= 0 ? "+" : ""}{totalPnl.toFixed(1)} pts
        </span>

        <span className="text-[10px] text-emerald-600">▲{longs.length}</span>
        <span className="text-[10px] text-red-600">▼{shorts.length}</span>

        {/* 持仓 chips */}
        <div className="flex flex-wrap gap-1">
          {posWithPnl.map((p) => (
            <PositionChip key={p.id} pos={p} floatPts={p.floatPts} />
          ))}
        </div>

        <a
          href="/trades"
          className="ml-auto text-[10px] text-stone-400 hover:text-stone-700 transition-colors"
        >
          记录 →
        </a>
      </div>
    </div>
  );
}

function PositionChip({ pos, floatPts }: { pos: Position; floatPts: number }) {
  const isLong    = pos.direction === "long";
  const isProfit  = floatPts >= 0;

  const borderColor = isLong
    ? "border-emerald-300"
    : "border-red-200";
  const bgColor = isLong
    ? "bg-emerald-50/60"
    : "bg-red-50/60";
  const dirColor = isLong ? "text-emerald-600" : "text-red-600";
  const pnlColor = isProfit ? "text-emerald-600" : "text-red-600";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] ${borderColor} ${bgColor}`}
      title={`入场 ${pos.entryPrice.toFixed(2)}  当前SL ${pos.stopLoss.toFixed(2)}  初始SL ${pos.initialStopLoss?.toFixed(2) ?? pos.stopLoss.toFixed(2)}  ${pos.trailingActive ? "移动止损" : pos.breakEvenMoved ? "保本" : "初始"}  ${pos.entryTime}`}
    >
      <span className={`font-bold ${dirColor}`}>
        {isLong ? "▲" : "▼"}
      </span>
      <span className="font-medium text-stone-800">{pos.symbol}</span>
      <span className={pnlColor}>
        {floatPts >= 0 ? "+" : ""}{floatPts.toFixed(1)}
      </span>
    </span>
  );
}
