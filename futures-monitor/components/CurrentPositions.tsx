"use client";

import { Position } from "@/lib/types";

interface Props {
  positions: Position[];
  currentPrices: Record<string, number>;
}

const DIR_LABEL: Record<string, string> = { long: "做多 ▲", short: "做空 ▼" };
const DIR_COLOR: Record<string, string> = {
  long:  "text-emerald-400",
  short: "text-red-400",
};
const SIG_LABEL: Record<string, string> = { breakout: "突破", pullback: "回踩" };

function floatPnl(pos: Position, curPrice: number): { pts: number; pct: number } {
  const pts =
    pos.direction === "long"
      ? curPrice - pos.entryPrice
      : pos.entryPrice - curPrice;
  const pct = pos.entryPrice ? (pts / pos.entryPrice) * 100 : 0;
  return { pts, pct };
}

export default function CurrentPositions({ positions, currentPrices }: Props) {
  const open = positions.filter((p) => p.status === "open");

  if (open.length === 0) {
    return (
      <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
        <div className="mb-3 flex items-center gap-2">
          <span className="text-base font-semibold text-gray-200">📋 当前持仓</span>
          <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-500">0 笔</span>
        </div>
        <p className="text-sm text-gray-600">暂无持仓记录</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4">
      {/* 标题 */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold text-gray-200">📋 当前持仓</span>
          <span className="rounded bg-emerald-900/60 px-2 py-0.5 text-xs text-emerald-400">
            {open.length} 笔持仓中
          </span>
        </div>
        <a
          href="/trades"
          className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          查看完整记录 →
        </a>
      </div>

      {/* 持仓卡片列表 */}
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {open.map((pos) => {
          const cur = currentPrices[pos.symbol] ?? pos.entryPrice;
          const { pts, pct } = floatPnl(pos, cur);
          const isProfit = pts >= 0;
          const riskPct = pos.riskDist / pos.entryPrice * 100;

          return (
            <div
              key={pos.id}
              className="rounded-lg border border-gray-700/60 bg-gray-800/50 p-3 space-y-1.5"
            >
              {/* 行 1：品种 + 方向 + 信号类型 */}
              <div className="flex items-center justify-between">
                <span className="font-semibold text-gray-100">{pos.symbol}</span>
                <div className="flex items-center gap-1.5">
                  <span className={`text-xs font-medium ${DIR_COLOR[pos.direction]}`}>
                    {DIR_LABEL[pos.direction]}
                  </span>
                  <span className="rounded bg-gray-700 px-1.5 py-0.5 text-[10px] text-gray-400">
                    {SIG_LABEL[pos.signalType]}
                  </span>
                </div>
              </div>

              {/* 行 2：当前价 + 浮动盈亏 */}
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">
                  现价 <span className="text-gray-200 font-medium">{cur.toFixed(2)}</span>
                </span>
                <span className={`font-semibold ${isProfit ? "text-emerald-400" : "text-red-400"}`}>
                  {isProfit ? "+" : ""}{pts.toFixed(2)}
                  <span className="text-xs ml-1 opacity-75">
                    ({isProfit ? "+" : ""}{pct.toFixed(2)}%)
                  </span>
                </span>
              </div>

              {/* 行 3：入场价 + 时间 */}
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>入场 {pos.entryPrice.toFixed(2)}</span>
                <span>{pos.entryTime.slice(5)}</span>
              </div>

              {/* 行 4：止损 / 止盈 */}
              <div className="flex items-center justify-between text-xs">
                <span className="text-red-400/80">
                  SL {pos.stopLoss.toFixed(2)}
                  <span className="text-gray-600 ml-1">(-{riskPct.toFixed(1)}%)</span>
                </span>
                <span className="text-emerald-400/80">
                  TP {pos.takeProfit.toFixed(2)}
                  <span className="text-gray-600 ml-1">(+{(riskPct * 2).toFixed(1)}%)</span>
                </span>
              </div>

              {/* 进度条：当前价在 SL~TP 之间的位置 */}
              <ProgressBar pos={pos} cur={cur} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ProgressBar({ pos, cur }: { pos: Position; cur: number }) {
  const sl = pos.stopLoss;
  const tp = pos.takeProfit;
  const range = Math.abs(tp - sl);
  if (range === 0) return null;

  let pct: number;
  if (pos.direction === "long") {
    pct = ((cur - sl) / range) * 100;
  } else {
    pct = ((sl - cur) / range) * 100;
  }
  pct = Math.max(0, Math.min(100, pct));

  const color =
    pct < 33 ? "bg-red-500" : pct < 67 ? "bg-yellow-500" : "bg-emerald-500";

  return (
    <div className="mt-1 h-1 w-full rounded-full bg-gray-700">
      <div
        className={`h-1 rounded-full transition-all ${color}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
