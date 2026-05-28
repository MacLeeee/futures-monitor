"use client";
// ============================================================
// 黄金宝宝巴士 - 宏观监控面板
// 展示：黄金状态机 / 流动性评分 / 趋势组合 / 多空结构 / 交易建议
// ============================================================

import { useState, useEffect, useCallback } from "react";
import { GoldBusData, GoldRegime, TrendSign } from "@/lib/types";
import { Activity, Droplets, TrendingUp, Target, AlertTriangle, Shield } from "lucide-react";

const GITHUB_RAW =
  "https://raw.githubusercontent.com/MacLeeee/futures-monitor/main/futures-monitor/public";

// 状态机配色
const REGIME_COLORS: Record<GoldRegime, { bg: string; border: string; text: string }> = {
  "Cash Liquidation":            { bg: "bg-red-50/90",  border: "border-red-300",   text: "text-red-600" },
  "Rates-Dollar Bearish Gold":   { bg: "bg-orange-50/90", border: "border-orange-300", text: "text-orange-600" },
  "Clean Bullish Gold":          { bg: "bg-emerald-50/90", border: "border-emerald-300", text: "text-emerald-600" },
  "Reflation Gold":              { bg: "bg-amber-50/90",  border: "border-amber-300",  text: "text-amber-500" },
  "Defensive Gold":              { bg: "bg-slate-50/90",  border: "border-slate-300",  text: "text-slate-600" },
  "Fiscal / Debasement Hedge":   { bg: "bg-purple-50/90", border: "border-purple-300", text: "text-purple-600" },
  "Bullish Price Override":      { bg: "bg-cyan-50/90",   border: "border-cyan-700",   text: "text-cyan-400" },
  "Bearish Price Override":      { bg: "bg-pink-50/90",   border: "border-pink-700",   text: "text-pink-400" },
  "Mixed":                       { bg: "bg-white/90",   border: "border-stone-300",   text: "text-stone-400" },
};

// 流动性状态配色
function getLiquidityColor(score: number): string {
  if (score >= 75) return "text-red-600";
  if (score >= 60) return "text-orange-600";
  if (score >= 45) return "text-yellow-600";
  if (score >= 30) return "text-amber-600";
  return "text-emerald-600";
}

function getLiquidityBg(score: number): string {
  if (score >= 75) return "bg-red-500";
  if (score >= 60) return "bg-orange-500";
  if (score >= 45) return "bg-yellow-500";
  if (score >= 30) return "bg-amber-500";
  return "bg-emerald-500";
}

// 趋势信号标记
function TrendBadge({ sign }: { sign: TrendSign }) {
  const color =
    sign === "Bull"  ? "bg-emerald-100/60 text-emerald-600 border-emerald-300" :
    sign === "Bear"  ? "bg-red-100/60 text-red-600 border-red-300" :
                       "bg-stone-100 text-stone-500 border-stone-300";
  const label = sign === "Bull" ? "↗" : sign === "Bear" ? "↘" : "→";
  return (
    <span className={`px-2 py-0.5 text-xs rounded border font-mono ${color}`}>
      {label} {sign}
    </span>
  );
}

// 结构分数条
function ScoreBar({ score, max, color }: { score: number; max: number; color: string }) {
  const pct = Math.min(100, (score / max) * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-stone-400 w-12 text-right">{score}/{max}</span>
      <div className="flex-1 h-1.5 bg-stone-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// 结构标志
function FlagItem({ active, label }: { active: boolean; label: string }) {
  return (
    <span
      className={`px-1.5 py-0.5 text-[10px] rounded border font-mono ${
        active
          ? "bg-emerald-50 text-emerald-600 border-emerald-800"
          : "bg-white text-stone-400 border-stone-200"
      }`}
    >
      {label}
    </span>
  );
}

export default function GoldBusPanel() {
  const [data, setData] = useState<GoldBusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const isLocal = typeof window !== "undefined" && window.location.port !== "";
      const base = isLocal ? "" : GITHUB_RAW;
      const url = `${base}/gold_bus.json?t=${Date.now()}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(15000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: GoldBusData = await res.json();
      setData(json);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const timer = setInterval(loadData, 30 * 60 * 1000); // 30分钟刷新
    return () => clearInterval(timer);
  }, [loadData]);

  if (loading) {
    return (
      <div className="bg-white border border-stone-200 rounded-lg p-4">
        <div className="flex items-center gap-2 text-stone-500 text-xs">
          <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse" />
          加载黄金监控数据...
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-white border border-stone-200 rounded-lg p-4">
        <div className="flex items-center gap-2 text-stone-500 text-xs">
          <AlertTriangle size={14} />
          黄金监控数据暂不可用{error ? ` (${error})` : ""}
        </div>
      </div>
    );
  }

  const regimeStyle = REGIME_COLORS[data.regime] || REGIME_COLORS["Mixed"];
  const trend = data.trend_15m_1h_4h;
  const struct = data.structure;
  const liqColor = getLiquidityColor(data.liquidity_score);
  const liqBg = getLiquidityBg(data.liquidity_score);
  const liqPct = Math.min(100, data.liquidity_score);

  return (
    <div className={`${regimeStyle.bg} border ${regimeStyle.border} rounded-lg overflow-hidden`}>
      {/* 标题栏 */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-stone-200">
        <Activity size={14} className="text-yellow-600" />
        <span className="text-xs font-semibold text-yellow-600 tracking-wide">
          黄金宝宝巴士 · 宏观监控
        </span>
        {data.timestamp && (
          <span className="ml-auto text-[10px] text-stone-400 font-mono">
            {(() => {
              try {
                return new Date(data.timestamp).toLocaleString("zh-CN", {
                  month: "2-digit", day: "2-digit",
                  hour: "2-digit", minute: "2-digit",
                });
              } catch { return ""; }
            })()}
          </span>
        )}
      </div>

      <div className="p-4 space-y-4">
        {/* 第一行：状态机 + 流动性 */}
        <div className="grid grid-cols-2 gap-4">
          {/* 状态机 */}
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Target size={13} className="text-stone-500" />
              <span className="text-[10px] text-stone-500 uppercase tracking-wider">Regime</span>
            </div>
            <div className={`text-base font-bold ${regimeStyle.text}`}>
              {data.regime}
            </div>
            <p className="text-[10px] text-stone-500 mt-1 leading-relaxed">
              {data.regime_guide}
            </p>
          </div>

          {/* 流动性评分 */}
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Droplets size={13} className="text-stone-500" />
              <span className="text-[10px] text-stone-500 uppercase tracking-wider">Liquidity</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="relative w-16 h-16">
                {/* 环形进度 */}
                <svg className="w-16 h-16 -rotate-90" viewBox="0 0 64 64">
                  <circle cx="32" cy="32" r="26" fill="none" stroke="currentColor"
                    className="text-stone-800" strokeWidth="6" />
                  <circle cx="32" cy="32" r="26" fill="none" stroke="currentColor"
                    className={liqColor.replace("text-", "stroke-")}
                    strokeWidth="6"
                    strokeDasharray={`${(liqPct / 100) * 163.36} 163.36`}
                    strokeLinecap="round"
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className={`text-lg font-bold font-mono ${liqColor}`}>
                    {data.liquidity_score}
                  </span>
                </div>
              </div>
              <div>
                <span className={`text-xs font-semibold ${liqColor}`}>
                  {data.liquidity_state}
                </span>
                <div className={`mt-1 w-2 h-2 rounded-full ${liqBg}`} />
              </div>
            </div>
          </div>
        </div>

        {/* 第二行：趋势组合 + 多空结构 */}
        <div className="grid grid-cols-2 gap-4 pt-2 border-t border-stone-200">
          {/* 趋势 15m/1h/4h */}
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <TrendingUp size={13} className="text-stone-500" />
              <span className="text-[10px] text-stone-500 uppercase tracking-wider">Trend</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex flex-col items-center gap-0.5">
                <span className="text-[9px] text-stone-400">15m</span>
                <TrendBadge sign={trend["15m"]} />
              </div>
              <span className="text-stone-300">→</span>
              <div className="flex flex-col items-center gap-0.5">
                <span className="text-[9px] text-stone-400">1h</span>
                <TrendBadge sign={trend["1h"]} />
              </div>
              <span className="text-stone-300">→</span>
              <div className="flex flex-col items-center gap-0.5">
                <span className="text-[9px] text-stone-400">4h</span>
                <TrendBadge sign={trend["4h"]} />
              </div>
            </div>
          </div>

          {/* 多空结构分 */}
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Shield size={13} className="text-stone-500" />
              <span className="text-[10px] text-stone-500 uppercase tracking-wider">Structure</span>
            </div>
            <div className="space-y-1.5">
              <ScoreBar score={struct.long_score} max={10} color="bg-emerald-500" />
              <ScoreBar score={struct.short_score} max={10} color="bg-red-500" />
              <div className="flex flex-wrap gap-1 pt-1">
                <FlagItem active={struct.flags.vwap_reclaim} label="VWAP↑" />
                <FlagItem active={struct.flags.vwap_reject} label="VWAP↓" />
                <FlagItem active={struct.flags.near_fib_618} label="Fib618" />
                <FlagItem active={struct.flags.higher_low} label="HL" />
                <FlagItem active={struct.flags.lower_high} label="LH" />
              </div>
            </div>
          </div>
        </div>

        {/* 第三行：交易建议 */}
        <div className="pt-2 border-t border-stone-200">
          <div className="flex items-start gap-2">
            <AlertTriangle size={13} className="text-yellow-500 mt-0.5 shrink-0" />
            <div>
              <span className="text-[10px] text-stone-500 uppercase tracking-wider block mb-1">
                Advice
              </span>
              <p className="text-xs text-stone-300 leading-relaxed">
                {data.advice}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
