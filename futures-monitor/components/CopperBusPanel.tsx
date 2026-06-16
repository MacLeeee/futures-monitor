"use client";
// ============================================================
// 铜宝宝巴士 - 状态机监控面板
// 展示：铜状态机 / 危险评分 / 多周期趋势 / 驱动指标 / DO/DON'T
// ============================================================

import { useState, useEffect, useCallback } from "react";
import { Activity, TrendingUp, Target, AlertTriangle, Shield, Zap } from "lucide-react";

const GITHUB_RAW =
  "https://raw.githubusercontent.com/MacLeeee/futures-monitor/main/futures-monitor/public";

interface CopperBusData {
  timestamp: string;
  interval: string;
  regime: string;
  regime_color: string;
  dominant_theme: string;
  secondary: string;
  bull_max: number;
  bear_max: number;
  bias: number;
  do: string;
  dont: string;
  scores: Record<string, number>;
  mtf_regime: string;
  mtf_danger: number;
  mtf_danger_state: string;
  mtf_action: string;
  mtf_states: { fast: number; mid: number; slow: number };
  drivers: Record<string, number | null>;
  data_ok: number;
  data_total: number;
  data_missing: string[];
  error?: string;
}

function getRegimeColor(regime: string, color?: string): { text: string; bar: string } {
  switch (color) {
    case "green": return { text: "text-emerald-600", bar: "bg-emerald-500" };
    case "red": return { text: "text-red-600", bar: "bg-red-500" };
    case "orange": return { text: "text-orange-600", bar: "bg-orange-500" };
    default: return { text: "text-stone-500", bar: "bg-stone-400" };
  }
}

function getDangerColor(score: number): string {
  if (score >= 75) return "text-red-600 stroke-red-600";
  if (score >= 60) return "text-orange-600 stroke-orange-600";
  if (score >= 45) return "text-amber-500 stroke-amber-500";
  if (score >= 30) return "text-sky-600 stroke-sky-600";
  return "text-emerald-600 stroke-emerald-600";
}

function StatePill({ label, st }: { label: string; st: number }) {
  const txt = st === 1 ? "Bull ↗" : st === -1 ? "Bear ↘" : "Neutral →";
  const cls = st === 1
    ? "bg-emerald-100/80 text-emerald-600 ring-1 ring-emerald-500/20"
    : st === -1
    ? "bg-red-100/80 text-red-600 ring-1 ring-red-500/20"
    : "bg-stone-100 text-stone-400";
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-mono ${cls}`}>
      <span className="text-[10px] opacity-60">{label}</span> {txt}
    </span>
  );
}

function ScoreBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-stone-400 w-20 text-right">{label}</span>
      <span className="text-xs font-mono text-stone-900 w-6 tabular-nums">{value}</span>
      <div className="flex-1 h-1.5 bg-stone-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function DriverCell({ name, value, suffix }: { name: string; value: number | null; suffix: string }) {
  const cls = value !== null && !isNaN(value)
    ? value > 0 ? "text-emerald-600" : value < 0 ? "text-red-600" : "text-stone-400"
    : "text-stone-300";
  const display = value !== null && !isNaN(value) ? `${value > 0 ? "+" : ""}${value.toFixed(2)}${suffix}` : "n/a";
  return (
    <div className="bg-stone-50 border border-stone-100 rounded-lg px-3 py-2">
      <div className="text-[10px] text-stone-400">{name}</div>
      <div className={`text-sm font-bold font-mono mt-0.5 ${cls}`}>{display}</div>
    </div>
  );
}

const DRIVER_LABELS: Record<string, string> = {
  copper: "铜 ROC", gold: "黄金 ROC", copper_gold_ratio: "铜金比",
  copper_alu_ratio: "铜铝比", cross_premium: "跨市溢价",
  term_spread: "期限结构", inv_trend: "库存趋势",
  dxy: "DXY", real_pressure: "真实利率压力", us10y: "10Y收益率",
  usdcnh: "USDCNH", usdclp: "USDCLP", oil: "原油",
  copx: "COPX矿企", fxi: "FXI中国", es: "标普", vix: "VIX",
};

const DRIVER_ORDER = [
  "copper", "gold", "copper_gold_ratio", "copper_alu_ratio",
  "cross_premium", "term_spread", "inv_trend",
  "dxy", "real_pressure", "us10y", "usdcnh", "usdclp",
  "oil", "copx", "fxi", "es", "vix",
];

export default function CopperBusPanel() {
  const [data, setData] = useState<CopperBusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const isLocal = typeof window !== "undefined" && window.location.port !== "";
      const base = isLocal ? "" : GITHUB_RAW;
      const url = `${base}/copper_bus.json?t=${Date.now()}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(15000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const timer = setInterval(loadData, 30 * 60 * 1000);
    return () => clearInterval(timer);
  }, [loadData]);

  if (loading) {
    return (
      <div className="bg-white border border-stone-200 rounded-lg p-4">
        <div className="flex items-center gap-2 text-stone-500 text-xs">
          <div className="w-2 h-2 bg-orange-500 rounded-full animate-pulse" />
          加载铜状态机数据...
        </div>
      </div>
    );
  }

  if (error || !data || data.error) {
    return (
      <div className="bg-white border border-stone-200 rounded-lg p-4">
        <div className="flex items-center gap-2 text-stone-500 text-xs">
          <AlertTriangle size={14} />
          铜宝宝巴士暂不可用{data?.error ? ` (${data.error})` : error ? ` (${error})` : ""}
        </div>
      </div>
    );
  }

  const rc = getRegimeColor(data.regime, data.regime_color);
  const dc = getDangerColor(data.mtf_danger);
  const dangerPct = Math.min(100, data.mtf_danger);
  const bullKeys = ["Structural Demand", "Growth / Reflation", "China Demand",
    "Supply Squeeze", "Weak Dollar", "Risk-On Growth", "Easing / Relief"];
  const bearKeys = ["Growth Scare", "Dollar+Rates", "Cash Liquidation",
    "China Slowdown", "Supply Glut"];
  const sortedScores = data.scores || {};

  return (
    <div className="bg-white border border-stone-200 rounded-lg overflow-hidden">
      {/* 标题栏 */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-stone-200 bg-orange-50/50">
        <Zap size={14} className="text-orange-600" />
        <span className="text-xs font-semibold text-orange-600 tracking-wide">
          铜宝宝巴士 · Regime Monitor
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
        {/* 第一行：状态机 + 危险评分 */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Target size={13} className="text-stone-500" />
              <span className="text-[10px] text-stone-500 uppercase tracking-wider">Regime</span>
            </div>
            <div className={`text-base font-bold ${rc.text}`}>{data.regime}</div>
            <div className="text-[10px] text-stone-500 mt-1">
              主逻辑: {data.dominant_theme} · Bull {data.bull_max} Bear {data.bear_max}
            </div>
          </div>

          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Shield size={13} className="text-stone-500" />
              <span className="text-[10px] text-stone-500 uppercase tracking-wider">Danger Score</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="relative w-16 h-16">
                <svg className="w-16 h-16 -rotate-90" viewBox="0 0 64 64">
                  <circle cx="32" cy="32" r="26" fill="none" className="stroke-stone-200" strokeWidth="6" />
                  <circle cx="32" cy="32" r="26" fill="none" className={dc.split(" ").find(c => c.startsWith("stroke-")) || "stroke-stone-400"}
                    strokeWidth="6"
                    strokeDasharray={`${(dangerPct / 100) * 163.36} 163.36`}
                    strokeLinecap="round"
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className={`text-lg font-bold font-mono ${dc.split(" ")[0]}`}>{data.mtf_danger}</span>
                </div>
              </div>
              <div>
                <span className={`text-xs font-semibold ${dc.split(" ")[0]}`}>{data.mtf_danger_state}</span>
                <p className="text-[10px] text-stone-400 mt-0.5">{data.mtf_regime}</p>
                <p className="text-[10px] text-stone-500 font-medium">{data.mtf_action}</p>
              </div>
            </div>
          </div>
        </div>

        {/* 第二行：多周期趋势 */}
        <div className="pt-2 border-t border-stone-200">
          <div className="flex items-center gap-1.5 mb-2">
            <TrendingUp size={13} className="text-stone-500" />
            <span className="text-[10px] text-stone-500 uppercase tracking-wider">Multi-TF Trend</span>
          </div>
          <div className="flex items-center gap-2">
            <StatePill label="15m" st={data.mtf_states.fast} />
            <span className="text-stone-300">→</span>
            <StatePill label="60m" st={data.mtf_states.mid} />
            <span className="text-stone-300">→</span>
            <StatePill label="日线" st={data.mtf_states.slow} />
          </div>
        </div>

        {/* 第三行：DO / DON'T */}
        <div className="pt-2 border-t border-stone-200">
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-emerald-50/60 border border-emerald-200/50 rounded-lg px-3 py-2">
              <span className="text-[9px] text-emerald-500 uppercase tracking-wider font-semibold">✅ DO</span>
              <p className="text-xs text-emerald-700 mt-0.5">{data.do}</p>
            </div>
            <div className="bg-red-50/60 border border-red-200/50 rounded-lg px-3 py-2">
              <span className="text-[9px] text-red-500 uppercase tracking-wider font-semibold">❌ DON'T</span>
              <p className="text-xs text-red-700 mt-0.5">{data.dont}</p>
            </div>
          </div>
        </div>

        {/* 第四行：主题打分 */}
        <div className="pt-2 border-t border-stone-200">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-[10px] text-stone-400 uppercase tracking-wider block mb-2">多头主题</span>
              <div className="space-y-1.5">
                {bullKeys.map(k => (
                  <ScoreBar key={k} label={k} value={sortedScores[k] ?? 0} max={8} color="bg-emerald-500" />
                ))}
              </div>
            </div>
            <div>
              <span className="text-[10px] text-stone-400 uppercase tracking-wider block mb-2">空头主题</span>
              <div className="space-y-1.5">
                {bearKeys.map(k => (
                  <ScoreBar key={k} label={k} value={sortedScores[k] ?? 0} max={8} color="bg-red-500" />
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* 第五行：驱动指标网格 */}
        <div className="pt-2 border-t border-stone-200">
          <div className="flex items-center gap-1.5 mb-2">
            <Activity size={13} className="text-stone-500" />
            <span className="text-[10px] text-stone-500 uppercase tracking-wider">
              Drivers ({data.interval} ROC)
            </span>
            <span className="ml-auto text-[9px] text-stone-400">
              数据 {data.data_ok}/{data.data_total}
              {data.data_missing.length > 0 ? ` 缺: ${data.data_missing.join(", ")}` : ""}
            </span>
          </div>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
            {DRIVER_ORDER.map(k => {
              const v = data.drivers[k];
              const label = DRIVER_LABELS[k] || k;
              const suffix = ["us10y", "dxy", "usdcnh", "usdclp", "real_pressure"].includes(k) ? "%" : "%";
              return <DriverCell key={k} name={label} value={v ?? null} suffix={suffix} />;
            })}
          </div>
        </div>

        {/* 页脚 */}
        <div className="text-[9px] text-stone-400 pt-2">
          yfinance · 25 序列跨资产监控 · 每 15 分钟更新 · 铜宝宝巴士
        </div>
      </div>
    </div>
  );
}
