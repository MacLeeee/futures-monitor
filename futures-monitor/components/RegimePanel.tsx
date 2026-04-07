"use client";

import { FuturesStatus, MarketRegime, BoxSignal } from "@/lib/types";

interface Props {
  data: FuturesStatus[];
}

const REGIME_BADGE: Record<string, { label: string; bg: string; text: string }> = {
  trending: { label: "趋势", bg: "bg-purple-900/50", text: "text-purple-300" },
  ranging:  { label: "震荡", bg: "bg-amber-900/50",  text: "text-amber-300" },
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
  const boxSigs  = data.filter((d) => d.boxSignal);
  const boxLongs = boxSigs.filter((d) => d.boxSignal?.type === "long");
  const boxShorts= boxSigs.filter((d) => d.boxSignal?.type === "short");

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/60 p-4 space-y-4">
      {/* 标题栏 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold text-gray-200">🔮 市场状态</span>
          <span className="rounded bg-purple-900/40 px-2 py-0.5 text-xs text-purple-300">
            趋势 {trending.length}
          </span>
          <span className="rounded bg-amber-900/40 px-2 py-0.5 text-xs text-amber-300">
            震荡 {ranging.length}
          </span>
        </div>
        <div className="text-[10px] text-gray-600">
          30m唐奇安通道 · 枢轴点结构 · EMA缎带(20/50/120)
        </div>
      </div>

      {/* 趋势品种列表 */}
      {trending.length > 0 && (
        <div>
          <div className="mb-2 text-xs font-medium text-purple-400">
            📊 趋势行情 — 关注<span className="text-gray-500">突破策略（顺势）+ 回踩策略</span>
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
          <div className="mb-2 text-xs font-medium text-amber-400">
            📦 震荡行情 — 重点关注<span className="text-gray-500">突破策略 / 箱体策略</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {ranging.map((d) => (
              <RegimeChip key={d.symbol} d={d} />
            ))}
          </div>
        </div>
      )}

      {/* 箱体信号 */}
      {(boxLongs.length > 0 || boxShorts.length > 0) && (
        <div className="border-t border-gray-800 pt-3">
          <div className="mb-2 text-xs font-semibold text-amber-300">
            📦 箱体信号（震荡行情 · 触及唐奇安通道边沿）
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {/* 做多箱体 */}
            {boxLongs.length > 0 && (
              <div className="rounded-lg border border-emerald-800/40 bg-emerald-900/10 p-3">
                <div className="mb-1.5 text-xs font-medium text-emerald-400">
                  ▲ 做多（触下沿支撑）
                </div>
                {boxLongs.length === 0 ? (
                  <p className="text-xs text-gray-600">暂无</p>
                ) : (
                  <div className="space-y-1">
                    {boxLongs.map((d) => (
                      <BoxItem key={d.symbol} d={d} />
                    ))}
                  </div>
                )}
              </div>
            )}
            {/* 做空箱体 */}
            {boxShorts.length > 0 && (
              <div className="rounded-lg border border-red-800/40 bg-red-900/10 p-3">
                <div className="mb-1.5 text-xs font-medium text-red-400">
                  ▼ 做空（触上沿阻力）
                </div>
                {boxShorts.length === 0 ? (
                  <p className="text-xs text-gray-600">暂无</p>
                ) : (
                  <div className="space-y-1">
                    {boxShorts.map((d) => (
                      <BoxItem key={d.symbol} d={d} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 说明 */}
      <div className="text-[10px] text-gray-600 leading-relaxed">
        <span className="text-purple-400">趋势</span> = 唐奇安通道扩张 + 枢轴HH/HL或LL/LH + EMA多/空头排列 + 斜率显著
        &nbsp;·&nbsp;
        <span className="text-amber-400">震荡</span> = 通道走平 + 枢轴无序 + EMA缠绕 + 斜率≈0
        &nbsp;·&nbsp;
        箱体信号 = 震荡行情中价格触及通道上沿(空)/下沿(多)
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
      <span className="text-gray-500">{arrow}</span>
      <span className="text-gray-400 text-[10px]">{chg}</span>
      <span className="text-gray-600 text-[10px]">{regime.score}分</span>
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
        <span className={`font-medium ${isLong ? "text-emerald-400" : "text-red-400"}`}>
          {isLong ? "●" : "●"} {d.symbol}
        </span>
        <span className="text-gray-500">{chg}</span>
      </div>
      <div className="flex items-center gap-2 text-gray-500">
        <span>
          {isLong ? "下沿" : "上沿"}{sig.boundaryPrice}
        </span>
        <span className="text-gray-600">距{sig.distPct.toFixed(2)}%</span>
        <span className="text-gray-700 text-[10px]">
          [{sig.boxLower}~{sig.boxUpper}]
        </span>
      </div>
    </div>
  );
}
