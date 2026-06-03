"use client";

import React from "react";
import { Position } from "@/lib/types";

interface Props {
  positions: Position[];
  currentPrices: Record<string, number>;
}

// ══════════════════════════════════════════════════════════════
// 合约规格表  [乘数, 保证金率, 单位, tick大小]
// ══════════════════════════════════════════════════════════════
const SPECS: Record<string, [number, number, string, number]> = {
  "黄金":     [1000, 0.07, "克",  0.01],
  "白银":     [15,   0.07, "kg",  1.0 ],
  "铜":       [5,    0.10, "吨",  10.0],
  "铝":       [5,    0.08, "吨",  5.0 ],
  "锡":       [1,    0.10, "吨",  10.0],
  "镍":       [1,    0.10, "吨",  10.0],
  "螺纹钢":   [10,   0.07, "吨",  1.0 ],
  "橡胶":     [10,   0.09, "吨",  5.0 ],
  "合成橡胶": [5,    0.09, "吨",  5.0 ],
  "燃油":     [10,   0.10, "吨",  1.0 ],
  "低硫燃油": [10,   0.10, "吨",  1.0 ],
  "豆粕":     [10,   0.07, "吨",  1.0 ],
  "豆油":     [10,   0.07, "吨",  2.0 ],
  "棕榈油":   [10,   0.07, "吨",  2.0 ],
  "玉米":     [10,   0.05, "吨",  1.0 ],
  "铁矿石":   [100,  0.08, "吨",  0.5 ],
  "焦煤":     [60,   0.10, "吨",  0.5 ],
  "乙二醇":   [10,   0.08, "吨",  1.0 ],
  "苯乙烯":   [5,    0.08, "吨",  1.0 ],
  "生猪":     [16,   0.10, "吨",  5.0 ],
  "白糖":     [10,   0.07, "吨",  1.0 ],
  "菜粕":     [10,   0.07, "吨",  1.0 ],
  "菜油":     [10,   0.07, "吨",  1.0 ],
  "纯碱":     [20,   0.08, "吨",  1.0 ],
  "锰硅":     [5,    0.10, "吨",  2.0 ],
  "硅铁":     [5,    0.10, "吨",  2.0 ],
  "甲醇":     [10,   0.07, "吨",  1.0 ],
  "对二甲苯": [5,    0.08, "吨",  2.0 ],
  "玻璃":     [20,   0.08, "吨",  1.0 ],
  "棉花":     [5,    0.07, "吨",  5.0 ],
  "原油":     [1000, 0.10, "桶",  0.1 ],
  "碳酸锂":   [1,    0.10, "吨",  50.0],
  "烧碱":     [30,   0.08, "吨",  1.0 ],
  "PVC":      [5,    0.08, "吨",  1.0 ],
};

const MARGIN_PER_TRADE = 200_000; // 每笔保证金 20万

function getSpec(symbol: string): [number, number] {
  const s = SPECS[symbol] ?? [1, 0.10];
  return [s[0], s[1]];
}

/** 格式化绝对金额：>=1万显示万，否则显示元 */
function fmtRmb(v: number): string {
  const sign = v >= 0 ? "+" : "";
  const abs = Math.abs(v);
  if (abs >= 10_000) return `${sign}${(v / 10_000).toFixed(1)}万`;
  return `${sign}${v.toFixed(0)}元`;
}

export default function CurrentPositions({ positions, currentPrices }: Props) {
  const open = positions.filter((p) => p.status === "open");
  const longs  = open.filter((p) => p.direction === "long");
  const shorts = open.filter((p) => p.direction === "short");

  // 计算浮盈（绝对金额）
  let totalPnl = 0;
  const posWithPnl = open.map((p) => {
    const cur = currentPrices[p.symbol] ?? p.entryPrice;
    const pts = p.direction === "long" ? cur - p.entryPrice : p.entryPrice - cur;
    const [mult, mgnRate] = getSpec(p.symbol);
    const marginPerLot = p.entryPrice * mult * mgnRate;
    const lots = Math.max(1, Math.floor(MARGIN_PER_TRADE / marginPerLot));
    const rmb = pts * mult * lots;
    totalPnl += rmb;
    return { ...p, floatPts: pts, floatRmb: rmb };
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
          浮盈 {fmtRmb(totalPnl)}
        </span>

        <span className="text-[10px] text-emerald-600">▲{longs.length}</span>
        <span className="text-[10px] text-red-600">▼{shorts.length}</span>

        {/* 持仓 chips */}
        <div className="flex flex-wrap gap-1">
          {posWithPnl.map((p) => (
            <PositionChip key={p.id} pos={p} floatPts={p.floatPts} floatRmb={p.floatRmb} />
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

function PositionChip({ pos, floatPts, floatRmb }: { pos: Position; floatPts: number; floatRmb: number }) {
  const isLong    = pos.direction === "long";
  const isProfit  = floatRmb >= 0;

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
      title={`入场 ${pos.entryPrice.toFixed(2)}  当前SL ${pos.stopLoss.toFixed(2)}  初始SL ${pos.initialStopLoss?.toFixed(2) ?? pos.stopLoss.toFixed(2)}  ${pos.trailingActive ? "移动止损" : pos.breakEvenMoved ? "保本" : "初始"}  浮盈 ${floatPts >= 0 ? "+" : ""}${floatPts.toFixed(1)}pts  ${pos.entryTime}`}
    >
      <span className={`font-bold ${dirColor}`}>
        {isLong ? "▲" : "▼"}
      </span>
      <span className="font-medium text-stone-800">{pos.symbol}</span>
      <span className={pnlColor}>
        {fmtRmb(floatRmb)}
      </span>
    </span>
  );
}
