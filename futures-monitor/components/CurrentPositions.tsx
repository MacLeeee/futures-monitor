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
      <div className="rounded-xl border border-stone-200 bg-white p-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-stone-800">📋 当前持仓</span>
          <span className="rounded bg-stone-100 px-2 py-0.5 text-xs text-stone-500">0 笔</span>
        </div>
        <p className="mt-2 text-xs text-stone-400">暂无持仓记录</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-3">
      {/* 标题行 */}
      <div className="mb-2.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-stone-800">📋 当前持仓</span>
          <span className="rounded bg-sky-100/50 px-1.5 py-0.5 text-[10px] text-sky-600 font-medium">
            {open.length} 笔
          </span>
          <span className="text-[10px] text-emerald-600">▲{longs.length}</span>
          <span className="text-[10px] text-red-600">▼{shorts.length}</span>
        </div>
        <a
          href="/trades"
          className="text-[11px] text-stone-400 hover:text-stone-700 transition-colors"
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
    ? "border-emerald-300"
    : "border-red-200";
  const bgColor = isLong
    ? "bg-emerald-50/60"
    : "bg-red-50/60";
  const dirColor = isLong ? "text-emerald-600" : "text-red-600";
  const pnlColor = isProfit ? "text-emerald-600" : "text-red-600";

  return (
    <div
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 ${borderColor} ${bgColor}`}
      title={`入场 ${pos.entryPrice.toFixed(2)}  SL ${pos.stopLoss.toFixed(2)}  TP ${pos.takeProfit.toFixed(2)}  ${pos.entryTime}`}
    >
      <span className={`text-[10px] font-bold ${dirColor}`}>
        {isLong ? "▲" : "▼"}
      </span>
      <span className="text-[11px] font-medium text-stone-800">{pos.symbol}</span>
      <span className={`text-[10px] ${pnlColor}`}>
        {floatPts >= 0 ? "+" : ""}{floatPts.toFixed(1)}
      </span>
    </div>
  );
}
