"use client";
// ============================================================
// 黄金宝宝巴士 - 独立宏观监控页面
// ============================================================

import { useState, useEffect, useCallback } from "react";
import { GoldBusData, GoldRegime, TrendSign } from "@/lib/types";
import {
  Activity, Droplets, TrendingUp, Target, AlertTriangle,
  Shield, ArrowLeft, RefreshCw,
} from "lucide-react";
import Link from "next/link";

const GITHUB_RAW =
  "https://raw.githubusercontent.com/MacLeeee/futures-monitor/main/futures-monitor/public";

// ── 配色 ────────────────────────────────────────────────────

const REGIME_COLORS: Record<GoldRegime, { bg: string; border: string; text: string; bar: string }> = {
  "Cash Liquidation":          { bg: "bg-red-950/70",  border: "border-red-700",   text: "text-red-400",   bar: "bg-red-500" },
  "Rates-Dollar Bearish Gold": { bg: "bg-orange-950/70", border: "border-orange-700", text: "text-orange-400", bar: "bg-orange-500" },
  "Clean Bullish Gold":        { bg: "bg-emerald-950/70", border: "border-emerald-700", text: "text-emerald-400", bar: "bg-emerald-500" },
  "Reflation Gold":            { bg: "bg-amber-950/70",  border: "border-amber-700",  text: "text-amber-400",  bar: "bg-amber-500" },
  "Defensive Gold":            { bg: "bg-indigo-950/70", border: "border-indigo-700", text: "text-indigo-400", bar: "bg-indigo-500" },
  "Fiscal / Debasement Hedge": { bg: "bg-purple-950/70", border: "border-purple-700", text: "text-purple-400", bar: "bg-purple-500" },
  "Bullish Price Override":    { bg: "bg-cyan-950/70",   border: "border-cyan-700",   text: "text-cyan-400",   bar: "bg-cyan-500" },
  "Bearish Price Override":    { bg: "bg-pink-950/70",   border: "border-pink-700",   text: "text-pink-400",   bar: "bg-pink-500" },
  "Mixed":                     { bg: "bg-gray-900/70",   border: "border-gray-700",   text: "text-gray-400",   bar: "bg-gray-500" },
};

function liqColor(score: number) {
  if (score >= 75) return "text-red-400";
  if (score >= 60) return "text-orange-400";
  if (score >= 45) return "text-yellow-400";
  if (score >= 30) return "text-blue-400";
  return "text-emerald-400";
}

function liqBg(score: number) {
  if (score >= 75) return "bg-red-500";
  if (score >= 60) return "bg-orange-500";
  if (score >= 45) return "bg-yellow-500";
  if (score >= 30) return "bg-blue-500";
  return "bg-emerald-500";
}

// ── 趋势标签 ────────────────────────────────────────────────

function TrendChip({ label, sign }: { label: string; sign: TrendSign }) {
  const color = sign === "Bull"  ? "bg-emerald-900/60 text-emerald-400 border-emerald-700" :
                sign === "Bear"  ? "bg-red-900/60 text-red-400 border-red-700" :
                                   "bg-gray-800/60 text-gray-500 border-gray-700";
  const arrow = sign === "Bull" ? "↗" : sign === "Bear" ? "↘" : "→";
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded border text-xs font-mono ${color}`}>
      <span className="text-[10px] text-gray-500">{label}</span>
      {arrow} {sign}
    </span>
  );
}

// ── 进度条 ──────────────────────────────────────────────────

function Bar({ value, max, color, label }: { value: number; max: number; color: string; label: string }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-gray-500 w-14 text-right">{label}</span>
      <span className="text-xs text-gray-300 font-mono w-8">{value}</span>
      <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ── Flag 徽章 ───────────────────────────────────────────────

function Flag({ active, label, desc }: { active: boolean; label: string; desc: string }) {
  return (
    <div className={`px-2 py-1 rounded text-[10px] font-mono flex items-center gap-1.5 ${
      active ? "bg-emerald-950/60 text-emerald-400 border border-emerald-800" :
               "bg-gray-900 text-gray-600 border border-gray-800"
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${active ? "bg-emerald-400" : "bg-gray-700"}`} />
      <span className="font-semibold">{label}</span>
      <span className="text-[9px] opacity-60">{desc}</span>
    </div>
  );
}

// ── ETF 行 ──────────────────────────────────────────────────

function ETFRow({ ticker, price, chg15, chg60, chg240 }: {
  ticker: string; price: number;
  chg15: number | null; chg60: number | null; chg240: number | null;
}) {
  const fmtChg = (v: number | null) => {
    if (v === null) return <span className="text-gray-700">—</span>;
    const color = v > 0 ? "text-emerald-400" : v < 0 ? "text-red-400" : "text-gray-500";
    return <span className={`font-mono ${color}`}>{v > 0 ? "+" : ""}{v.toFixed(2)}%</span>;
  };

  // 根据 ETF 类型分类
  const ETF_LABELS: Record<string, { name: string; group: string }> = {
    GLD: { name: "黄金", group: "核心" },
    UUP: { name: "美元", group: "外汇" },
    TIP: { name: "实际利率", group: "利率" },
    TLT: { name: "长债", group: "利率" },
    SHY: { name: "短债", group: "利率" },
    SPY: { name: "标普500", group: "权益" },
    QQQ: { name: "纳指100", group: "权益" },
    IWM: { name: "罗素2000", group: "权益" },
    HYG: { name: "高收益债", group: "信用" },
    JNK: { name: "垃圾债", group: "信用" },
    USO: { name: "原油", group: "商品" },
    DBC: { name: "商品指数", group: "商品" },
    FXI: { name: "中国大盘", group: "海外" },
    KWEB: { name: "中国互联", group: "海外" },
    EWJ: { name: "日本", group: "海外" },
  };
  const info = ETF_LABELS[ticker] || { name: ticker, group: "其他" };

  return (
    <tr className="border-b border-gray-800/40 hover:bg-gray-900/40 transition-colors">
      <td className="py-1.5 px-2">
        <span className="text-xs font-mono text-gray-400">{ticker}</span>
      </td>
      <td className="py-1.5 px-2">
        <span className="text-[10px] text-gray-600">{info.name}</span>
      </td>
      <td className="py-1.5 px-2 text-right">
        <span className="text-xs font-mono text-gray-300">{price.toFixed(2)}</span>
      </td>
      <td className="py-1.5 px-2 text-right">{fmtChg(chg15)}</td>
      <td className="py-1.5 px-2 text-right">{fmtChg(chg60)}</td>
      <td className="py-1.5 px-2 text-right">{fmtChg(chg240)}</td>
    </tr>
  );
}

// ── 主组件 ──────────────────────────────────────────────────

export default function GoldPage() {
  const [data, setData] = useState<GoldBusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const isLocal = typeof window !== "undefined" && window.location.port !== "";
      const base = isLocal ? "" : GITHUB_RAW;
      const url = `${base}/gold_bus.json?t=${Date.now()}`;
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

  useEffect(() => { loadData(); }, [loadData]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-gray-100 p-4 font-mono flex items-center justify-center">
        <div className="flex items-center gap-2 text-gray-500">
          <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse" />
          加载黄金监控数据...
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-gray-950 text-gray-100 p-4 font-mono">
        <div className="max-w-screen-lg mx-auto">
          <Link href="/" className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 mb-4">
            <ArrowLeft size={12} /> 返回期货监控
          </Link>
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-8 text-center">
            <AlertTriangle size={24} className="text-red-400 mx-auto mb-2" />
            <p className="text-gray-400 text-sm">数据暂不可用{error ? ` (${error})` : ""}</p>
          </div>
        </div>
      </div>
    );
  }

  const regimeStyle = REGIME_COLORS[data.regime] || REGIME_COLORS["Mixed"];
  const trend = data.trend_15m_1h_4h;
  const struct = data.structure;
  const lc = liqColor(data.liquidity_score);
  const lb = liqBg(data.liquidity_score);
  const liqPct = Math.min(100, data.liquidity_score);
  const etf = data.etf_snapshot;

  // ETF 按组分块
  const TICKER_ORDER = ["GLD","UUP","TIP","TLT","SHY","SPY","QQQ","IWM","HYG","JNK","USO","DBC","FXI","KWEB","EWJ"];

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 font-mono">
      <div className="max-w-screen-lg mx-auto p-4 space-y-4">

        {/* 顶部导航 */}
        <div className="flex items-center justify-between border-b border-gray-800 pb-3">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-gray-500 hover:text-gray-300 transition-colors">
              <ArrowLeft size={16} />
            </Link>
            <Activity size={16} className="text-yellow-400" />
            <h1 className="text-sm font-bold text-yellow-400 tracking-wide">
              黄金宝宝巴士 · 宏观监控
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {data.timestamp && (
              <span className="text-[10px] text-gray-600">
                更新于 {(() => { try { return new Date(data.timestamp).toLocaleString("zh-CN", { month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", second:"2-digit" }); } catch { return ""; } })()}
              </span>
            )}
            <button onClick={loadData} className="p-1.5 rounded hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-colors">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        {/* ── 第一行：状态机 + 流动性 ─────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* 状态机 */}
          <div className={`${regimeStyle.bg} border ${regimeStyle.border} rounded-lg p-4`}>
            <div className="flex items-center gap-2 mb-3">
              <Target size={14} className="text-gray-500" />
              <span className="text-[10px] text-gray-500 uppercase tracking-wider">Gold Regime</span>
            </div>
            <div className={`text-xl font-bold mb-2 ${regimeStyle.text}`}>{data.regime}</div>
            {data.regime_detail && (
              <div className="mb-2 flex items-center gap-3 text-[10px]">
                <span className="text-gray-500">主逻辑:</span>
                <span className="text-gray-300 font-mono">{data.regime_detail.dominant_theme}</span>
                <span className="text-emerald-600">Bull ↑{data.regime_detail.bull_max}</span>
                <span className="text-red-600">Bear ↓{data.regime_detail.bear_max}</span>
              </div>
            )}
            <p className="text-xs text-gray-400 leading-relaxed">{data.regime_guide}</p>
            <div className="mt-3 pt-3 border-t border-gray-800/60">
              <span className="text-[9px] text-gray-600 uppercase">Regime 判定逻辑</span>
              <p className="text-[10px] text-gray-600 mt-1 leading-relaxed">
                基于 GLD/UUP/TIP/TLT/USO/DBC/SPY/QQQ/HYG 的 15m 涨跌方向交叉判定。
                7 种宏观情景 + Mixed（混杂）共 8 种状态机。
              </p>
            </div>
          </div>

          {/* 流动性评分 */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <Droplets size={14} className="text-gray-500" />
              <span className="text-[10px] text-gray-500 uppercase tracking-wider">Liquidity Stress</span>
            </div>
            <div className="flex items-center gap-4">
              <div className="relative w-20 h-20 shrink-0">
                <svg className="w-20 h-20 -rotate-90" viewBox="0 0 64 64">
                  <circle cx="32" cy="32" r="26" fill="none" className="stroke-gray-800" strokeWidth="6"/>
                  <circle cx="32" cy="32" r="26" fill="none" className={lc.replace("text-","stroke-")}
                    strokeWidth="6" strokeLinecap="round"
                    strokeDasharray={`${(liqPct/100)*163.36} 163.36`}/>
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className={`text-xl font-bold ${lc}`}>{data.liquidity_score}</span>
                  <span className="text-[8px] text-gray-600">/100</span>
                </div>
              </div>
              <div className="flex-1">
                <span className={`text-sm font-semibold ${lc}`}>{data.liquidity_state}</span>
                <div className="mt-2 space-y-1 text-[10px] text-gray-600">
                  <p className="text-gray-500">评分维度（15m 变化）：</p>
                  <p>• 美元 UUP ↑ +12 | 短债 SHY ↓ +8 | 长债 TLT ↓ +10</p>
                  <p>• 信用 HYG/JNK ↓ +12/+10 | 股市 SPY/IWM ↓ +12/+8</p>
                  <p>• 黄金 GLD ↓ +8 | 原油 USO ↑ +5 | 商品 DBC ↑ +5</p>
                  <p className="mt-1 text-gray-600">
                    ≥75 流动性冲击 | ≥60 紧缩 | ≥45 警戒 | ≥30 关注 | 正常
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── 第二行：趋势 + 结构 ────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* 趋势 */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <TrendingUp size={14} className="text-gray-500" />
              <span className="text-[10px] text-gray-500 uppercase tracking-wider">GLD Trend</span>
            </div>
            <div className="flex items-center gap-3">
              <TrendChip label="15m" sign={trend["15m"]} />
              <span className="text-gray-700 text-lg">→</span>
              <TrendChip label="1h" sign={trend["1h"]} />
              <span className="text-gray-700 text-lg">→</span>
              <TrendChip label="4h" sign={trend["4h"]} />
            </div>
            <div className="mt-3 pt-3 border-t border-gray-800/60">
              {data.combo_advice && (
                <p className="text-[10px] text-gray-400 mb-2">📋 {data.combo_advice}</p>
              )}
              <p className="text-[10px] text-gray-600">
                基于 GLD 在 15m/1h/4h 窗口的涨跌 (阈 ±0.10%)。<br/>
                Bull/Bear 信号需与 Regime 方向一致才构成有效共振。
              </p>
            </div>
          </div>

          {/* 结构分 */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <Shield size={14} className="text-gray-500" />
              <span className="text-[10px] text-gray-500 uppercase tracking-wider">Structure Score</span>
            </div>
            <div className="space-y-2 mb-3">
              <Bar value={struct.long_score} max={10} color="bg-emerald-500" label="Long" />
              <Bar value={struct.short_score} max={10} color="bg-red-500" label="Short" />
            </div>
            <div className="flex flex-wrap gap-1.5">
              <Flag active={struct.flags.vwap_reclaim} label="VWAP↑" desc="价格突破均价" />
              <Flag active={struct.flags.vwap_reject} label="VWAP↓" desc="价格跌破均价" />
              <Flag active={struct.flags.near_key_fib ?? struct.flags.near_fib_618} label="KeyFib" desc="接近关键斐波" />
              <Flag active={struct.flags.bull_sweep} label="BullSweep" desc="多头扫损" />
              <Flag active={struct.flags.bear_sweep} label="BearSweep" desc="空头扫损" />
              <Flag active={struct.flags.double_bottom} label="DoubleBtm" desc="双底" />
              <Flag active={struct.flags.double_top} label="DoubleTop" desc="双顶" />
              <Flag active={struct.flags.higher_low} label="HL" desc="低点抬升" />
              <Flag active={struct.flags.lower_high} label="LH" desc="高点降低" />
            </div>
          </div>
        </div>

        {/* ── 第三行：ETF 全景 ──────────────────────────── */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-gray-800">
            <Activity size={14} className="text-gray-500" />
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">ETF Snapshot</span>
            <span className="ml-auto text-[9px] text-gray-700">15 ETF · 15m/1h/4h 变化率</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-800 text-[10px] text-gray-600 uppercase">
                  <th className="py-2 px-2 text-left">Ticker</th>
                  <th className="py-2 px-2 text-left">名称</th>
                  <th className="py-2 px-2 text-right">价格</th>
                  <th className="py-2 px-2 text-right">15m</th>
                  <th className="py-2 px-2 text-right">1h</th>
                  <th className="py-2 px-2 text-right">4h</th>
                </tr>
              </thead>
              <tbody>
                {etf ? TICKER_ORDER.map(t => (
                  <ETFRow key={t} ticker={t}
                    price={etf.prices[t] || 0}
                    chg15={etf.chg_15m[t] ?? null}
                    chg60={etf.chg_60m[t] ?? null}
                    chg240={etf.chg_240m[t] ?? null}
                  />
                )) : (
                  <tr><td colSpan={6} className="py-4 text-center text-gray-600">ETF 快照数据暂不可用</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── 第四行：交易建议 ──────────────────────────── */}
        <div className={`${regimeStyle.bg} border ${regimeStyle.border} rounded-lg p-4`}>
          <div className="flex items-start gap-3">
            <AlertTriangle size={16} className="text-yellow-500 mt-0.5 shrink-0" />
            <div className="flex-1">
              <span className="text-[10px] text-gray-500 uppercase tracking-wider block mb-2">Trading Advice</span>
              <p className="text-sm text-gray-200 leading-relaxed">{data.advice}</p>
              <div className="mt-3 pt-3 border-t border-gray-800/60 text-[10px] text-gray-600">
                建议基于 Regime × 流动性 × 趋势 × 结构四层共振判定生成。
                流动性冲击 (≥75) 时优先风控；多头共振需 Regime 偏多 + 低流动性压力 + 趋势 Bull + 结构 Long≥7。
              </div>
            </div>
          </div>
        </div>

        {/* 底部 */}
        <footer className="text-center text-[10px] text-gray-700 py-4 border-t border-gray-800">
          数据源: yfinance (Yahoo Finance) · 15 个 ETF 跨资产监控 · 每 15 分钟自动更新 · 黄金宝宝巴士 v1.0
        </footer>
      </div>
    </div>
  );
}
