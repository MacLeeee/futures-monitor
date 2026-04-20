"use client";

import { Position } from "@/lib/types";

interface Props {
  positions: Position[];
  currentPrices: Record<string, number>;
}

export default function CurrentPositions({ positions, currentPrices }: Props) {
  const open = positions.filter((p) => p.status === "open");
  const longs  = open.filter((p) => p.direction === "long");
  const shorts = open.filter((p) => p.direction === "short");

  if (open.length === 0) {
    return (
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-200">📋 当前持仓</span>
          <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-500">0 笔</span>
        </div>
        <p className="mt-2 text-xs text-gray-600">暂无持仓记录</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-3">
      {/* 标题行 */}
      <div className="mb-2.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-200">📋 当前持仓</span>
          <span className="rounded bg-sky-900/50 px-1.5 py-0.5 text-[10px] text-sky-400 font-medium">
            {open.length} 笔
          </span>
          <span className="text-[10px] text-emerald-500">▲{longs.length}</span>
          <span className="text-[10px] text-red-500">▼{shorts.length}</span>
        </div>
        <a
          href="/trades"
          className="text-[11px] text-gray-600 hover:text-gray-300 transition-colors"
        >
          完整记录 →
        </a>
      </div>

      {/* 多头标签组 */}
      {longs.length > 0 && (
        <div className="mb-1.5">
          <div className="flex flex-wrap gap-1.5">
            {longs.map((pos) => {
              const cur = currentPrices[pos.symbol] ?? pos.entryPrice;
              const pts = cur - pos.entryPrice;
              return (
                <PositionChip key={pos.id} pos={pos} floatPts={pts} />
              );
            })}
          </div>
        </div>
      )}

      {/* 空头标签组 */}
      {shorts.length > 0 && (
        <div>
          <div className="flex flex-wrap gap-1.5">
            {shorts.map((pos) => {
              const cur = currentPrices[pos.symbol] ?? pos.entryPrice;
              const pts = pos.entryPrice - cur;
              return (
                <PositionChip key={pos.id} pos={pos} floatPts={pts} />
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function PositionChip({ pos, floatPts }: { pos: Position; floatPts: number }) {
  const isLong    = pos.direction === "long";
  const isProfit  = floatPts >= 0;

  const borderColor = isLong
    ? "border-emerald-800/60"
    : "border-red-800/60";
  const bgColor = isLong
    ? "bg-emerald-950/40"
    : "bg-red-950/40";
  const dirColor = isLong ? "text-emerald-400" : "text-red-400";
  const pnlColor = isProfit ? "text-emerald-400" : "text-red-400";

  return (
    <div
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 ${borderColor} ${bgColor}`}
      title={`入场 ${pos.entryPrice.toFixed(2)}  SL ${pos.stopLoss.toFixed(2)}  TP ${pos.takeProfit.toFixed(2)}  ${pos.entryTime}`}
    >
      <span className={`text-[10px] font-bold ${dirColor}`}>
        {isLong ? "▲" : "▼"}
      </span>
      <span className="text-[11px] font-medium text-gray-200">{pos.symbol}</span>
      <span className={`text-[10px] ${pnlColor}`}>
        {floatPts >= 0 ? "+" : ""}{floatPts.toFixed(1)}
      </span>
    </div>
  );
}
