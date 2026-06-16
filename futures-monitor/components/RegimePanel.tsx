"use client";

import { FuturesStatus, MarketRegime } from "@/lib/types";

interface Props {
  data: FuturesStatus[];
}

const REGIME_BADGE: Record<string, { label: string; bg: string; text: string }> = {
  trending: { label: "趋势", bg: "bg-purple-50", text: "text-purple-700" },
  ranging:  { label: "震荡", bg: "bg-amber-100/50",  text: "text-amber-600" },
};
const DIR_ICON: Record<string, string> = {
  bullish: "↗",
  bearish: "↘",
  neutral: "→",
};

export default function RegimePanel({ data }: Props) {
  const withRegime = data.filter((d) => d.marketRegime);
  if (withRegime.length === 0) return null;

  const trending = withRegime.filter((d) => d.marketRegime?.regime === "trending");
  const ranging  = withRegime.filter((d) => d.marketRegime?.regime === "ranging");

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-4 space-y-4">
      {/* 标题栏 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold text-stone-800">🔮 市场状态</span>
          <span className="rounded bg-purple-50/80 px-2 py-0.5 text-xs text-purple-700">
            趋势 {trending.length}
          </span>
          <span className="rounded bg-amber-100/40 px-2 py-0.5 text-xs text-amber-600">
            震荡 {ranging.length}
          </span>
        </div>
        <div className="text-[10px] text-stone-400">
          15m·30m·日线 MTF 状态矩阵
        </div>
      </div>

      {/* 趋势品种列表 */}
      {trending.length > 0 && (
        <div>
          <div className="mb-2 text-xs font-medium text-purple-600">
            📊 趋势 — <span className="text-stone-500">突破+回踩策略关注</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {trending.map((d) => (
              <RegimeChip key={d.symbol} d={d} />
            ))}
          </div>
        </div>
      )}

      {/* 震荡品种列表 */}
      {ranging.length > 0 && (
        <div>
          <div className="mb-2 text-xs font-medium text-amber-500">
            📦 震荡 — <span className="text-stone-500">等MTF对齐或回踩结构</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {ranging.map((d) => (
              <RegimeChip key={d.symbol} d={d} />
            ))}
          </div>
        </div>
      )}

      {/* 说明 */}
      <div className="text-[10px] text-stone-400 leading-relaxed">
        <span className="text-purple-600">趋势</span> = 15m+30m+日线 ≥2 周期对齐（price&gt;MA20&gt;MA60 + MACD同向）
        &nbsp;·&nbsp;
        <span className="text-amber-500">震荡</span> = 对齐不足2周期
        &nbsp;·&nbsp;
        状态矩阵决定操作建议 + 信号门控
      </div>
    </div>
  );
}

function RegimeChip({ d }: { d: FuturesStatus }) {
  const regime = d.marketRegime!;
  const badge  = REGIME_BADGE[regime.regime];
  const arrow  = DIR_ICON[regime.direction] ?? "→";
  const chg    = d.change >= 0 ? `+${d.change.toFixed(2)}%` : `${d.change.toFixed(2)}%`;

  return (
    <div className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs ${badge.bg}`}>
      <span className={`font-medium ${badge.text}`}>{d.symbol}</span>
      <span className="text-stone-500">{arrow}</span>
      <span className="text-stone-400 text-[10px]">{chg}</span>
      <span className="text-stone-400 text-[10px]">{regime.bullCount}/{regime.bearCount}</span>
    </div>
  );
}

function BoxItem({ d }: { d: FuturesStatus }) {
  const sig = d.boxSignal!;
  const chg = d.change >= 0 ? `+${d.change.toFixed(2)}%` : `${d.change.toFixed(2)}%`;
  const isLong = sig.type === "long";

  return (
    <div className="flex items-center justify-between text-xs">
      <div className="flex items-center gap-1.5">
        <span className={`font-medium ${isLong ? "text-emerald-600" : "text-red-600"}`}>
          {isLong ? "●" : "●"} {d.symbol}
        </span>
        <span className="text-stone-500">{chg}</span>
      </div>
      <div className="flex items-center gap-2 text-stone-500">
        <span>
          {isLong ? "下沿" : "上沿"}{sig.boundaryPrice}
        </span>
        <span className="text-stone-400">距{sig.distPct.toFixed(2)}%</span>
        <span className="text-stone-300 text-[10px]">
          [{sig.boxLower}~{sig.boxUpper}]
        </span>
      </div>
    </div>
  );
}
