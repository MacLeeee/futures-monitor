"use client";
// ============================================================
// 黄金宝宝巴士 — Redesign v2
// 31标的 · Pine Regime Machine v2 · OHLC结构
// ============================================================

import { useState, useEffect, useCallback } from "react";
import { GoldBusData, GoldRegime, TrendSign } from "@/lib/types";
import {
  Activity, Droplets, TrendingUp, Target, AlertTriangle,
  Shield, ArrowLeft, RefreshCw, Zap,
} from "lucide-react";
import Link from "next/link";

const GITHUB_RAW =
  "https://raw.githubusercontent.com/MacLeeee/futures-monitor/main/futures-monitor/public";

// ── 配色 ────────────────────────────────────────────────────

const REGIME_COLORS: Record<GoldRegime, { text: string; border: string; bar: string }> = {
  "Cash Liquidation":          { text: "text-red-600",   border: "border-red-500/20",   bar: "bg-red-500" },
  "Rates-Dollar Bearish Gold": { text: "text-orange-600", border: "border-orange-500/20", bar: "bg-orange-500" },
  "Clean Bullish Gold":        { text: "text-emerald-600", border: "border-emerald-500/20", bar: "bg-emerald-500" },
  "Reflation Gold":            { text: "text-amber-500",  border: "border-amber-200",  bar: "bg-amber-600" },
  "Defensive Gold":            { text: "text-indigo-600", border: "border-indigo-500/20", bar: "bg-indigo-500" },
  "Fiscal / Debasement Hedge": { text: "text-purple-600", border: "border-purple-500/20", bar: "bg-purple-500" },
  "Bullish Price Override":    { text: "text-cyan-400",   border: "border-cyan-500/20",   bar: "bg-cyan-500" },
  "Bearish Price Override":    { text: "text-pink-400",   border: "border-pink-500/20",   bar: "bg-pink-500" },
  "Mixed":                     { text: "text-stone-500",  border: "border-stone-300/20",  bar: "bg-stone-400" },
};

function liqColor(score: number) {
  if (score >= 75) return "text-red-600";
  if (score >= 60) return "text-orange-600";
  if (score >= 45) return "text-amber-500";
  if (score >= 30) return "text-sky-600";
  return "text-emerald-600";
}

function cardBg(score: number) {
  if (score >= 75) return "bg-red-500/5";
  if (score >= 60) return "bg-orange-500/5";
  if (score >= 45) return "bg-amber-50/40";
  if (score >= 30) return "bg-sky-500/5";
  return "bg-emerald-50/60";
}

// ── 趋势标签 ────────────────────────────────────────────────

function TrendChip({ label, sign }: { label: string; sign: TrendSign }) {
  const color = sign === "Bull"
    ? "bg-emerald-50/80 text-emerald-600 ring-1 ring-emerald-500/20"
    : sign === "Bear"
    ? "bg-red-500/10 text-red-600 ring-1 ring-red-500/20"
    : "bg-stone-200 text-stone-400";
  const arrow = sign === "Bull" ? "↗" : sign === "Bear" ? "↘" : "→";
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium font-mono ${color}`}>
      <span className="text-[10px] text-stone-400">{label}</span>
      {arrow} {sign}
    </span>
  );
}

// ── 进度条 ─────────────────────────────────────────────────

function Bar({ value, max, color, label }: { value: number; max: number; color: string; label: string }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-stone-400 w-16 text-right">{label}</span>
      <span className="text-xs font-mono text-stone-900 w-8 tabular-nums">{value}</span>
      <div className="flex-1 h-1.5 bg-stone-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-700 ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ── Flag ────────────────────────────────────────────────────

function Flag({ active, label, desc }: { active: boolean; label: string; desc: string }) {
  return (
    <div className={`px-2 py-1.5 rounded-md text-[10px] font-medium flex items-center gap-1.5 transition-all ${
      active
        ? "bg-amber-50/70 text-amber-500 ring-1 ring-amber-300/30"
        : "bg-white text-stone-400"
    }`}>
      <span className={`w-1.5 h-1.5 rounded-full ${active ? "bg-amber-500" : "bg-stone-400"}`} />
      <span>{label}</span>
      <span className="text-[9px] opacity-50 font-normal">{desc}</span>
    </div>
  );
}

// ── ETF 行 ─────────────────────────────────────────────────

const ETF_INFO: Record<string, { name: string; group: string }> = {
  "GC=F":    { name: "黄金期货", group: "核心" },
  "GLD":     { name: "黄金ETF",  group: "核心" },
  "IEF":     { name: "7-10年债",  group: "利率" },
  "TLT":     { name: "20年+债",  group: "利率" },
  "TIP":     { name: "抗通胀债",  group: "利率" },
  "SHY":     { name: "1-3年债",  group: "利率" },
  "BIL":     { name: "1-3月债",  group: "利率" },
  "UUP":     { name: "美元指数",  group: "外汇" },
  "EURUSD=X":{ name: "欧元/美元", group: "外汇" },
  "JPY=X":   { name: "美元/日元", group: "外汇" },
  "CNY=X":   { name: "美元/离岸人民币", group: "外汇" },
  "CL=F":    { name: "WTI原油",   group: "商品" },
  "HG=F":    { name: "铜",       group: "商品" },
  "DBC":     { name: "商品指数",  group: "商品" },
  "ES=F":    { name: "标普期货",  group: "权益" },
  "NQ=F":    { name: "纳指期货",  group: "权益" },
  "RTY=F":   { name: "罗素期货",  group: "权益" },
  "BTC-USD": { name: "比特币",    group: "另类" },
  "HYG":     { name: "高收益债",  group: "信用" },
  "JNK":     { name: "垃圾债",    group: "信用" },
  "LQD":     { name: "投资级债",  group: "信用" },
  "^VIX":    { name: "VIX恐慌",   group: "波动" },
  "^VVIX":   { name: "VIX之VIX",  group: "波动" },
  "^MOVE":   { name: "债市波动",  group: "波动" },
  "FXI":     { name: "中国大盘",  group: "亚洲" },
  "KWEB":    { name: "中国互联",  group: "亚洲" },
  "EWJ":     { name: "日本",     group: "亚洲" },
  "SPY":     { name: "标普500",  group: "权益" },
  "QQQ":     { name: "纳指100",  group: "权益" },
  "IWM":     { name: "罗素2000", group: "权益" },
};

function ETFRow({ ticker, price, chg15, chg60, chg240 }: {
  ticker: string; price: number;
  chg15: number | null; chg60: number | null; chg240: number | null;
}) {
  const fmt = (v: number | null) => {
    if (v === null) return <span className="text-stone-400 font-mono">—</span>;
    const c = v > 0 ? "text-emerald-600" : v < 0 ? "text-red-600" : "text-stone-400";
    const sign = v > 0 ? "+" : "";
    return <span className={`font-mono text-xs tabular-nums ${c}`}>{sign}{v.toFixed(2)}%</span>;
  };
  const info = ETF_INFO[ticker] || { name: ticker, group: "其他" };

  return (
    <tr className="border-b border-stone-200 hover:bg-amber-50/40 transition-colors">
      <td className="py-2 px-3"><span className="text-xs font-mono font-medium text-stone-500">{ticker}</span></td>
      <td className="py-2 px-3"><span className="text-[10px] text-stone-400">{info.name}</span></td>
      <td className="py-2 px-3 text-right"><span className="text-xs font-mono tabular-nums text-stone-900">{price.toFixed(2)}</span></td>
      <td className="py-2 px-3 text-right">{fmt(chg15)}</td>
      <td className="py-2 px-3 text-right">{fmt(chg60)}</td>
      <td className="py-2 px-3 text-right">{fmt(chg240)}</td>
    </tr>
  );
}

// ── 主组件 ─────────────────────────────────────────────────

const TICKER_ORDER = ["GC=F","GLD","IEF","TLT","TIP","SHY","BIL","UUP","EURUSD=X","JPY=X","CNY=X","CL=F","HG=F","DBC","ES=F","NQ=F","RTY=F","BTC-USD","HYG","JNK","LQD","^VIX","^VVIX","^MOVE","FXI","KWEB","EWJ","SPY","QQQ","IWM"];

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
      <div className="min-h-screen bg-[#faf8f5] flex items-center justify-center">
        <div className="flex items-center gap-3 text-stone-500">
          <div className="w-2 h-2 bg-amber-600 rounded-full animate-pulse" />
          <span className="text-sm">加载黄金监控...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-[#faf8f5] text-stone-900">
        <div className="max-w-screen-lg mx-auto p-4">
          <Link href="/" className="inline-flex items-center gap-1.5 text-xs text-stone-400 hover:text-stone-500 mb-6 transition-colors">
            <ArrowLeft size={12} /> 返回期货监控
          </Link>
          <div className="bg-white border border-stone-200 rounded-xl p-12 text-center">
            <AlertTriangle size={24} className="text-red-600 mx-auto mb-3" />
            <p className="text-stone-500 text-sm">数据暂不可用{error ? ` (${error})` : ""}</p>
            <button onClick={loadData} className="mt-4 px-4 py-1.5 text-xs bg-stone-200 rounded-md hover:bg-stone-300 transition-colors text-stone-500">
              重试
            </button>
          </div>
        </div>
      </div>
    );
  }

  const regimeStyle = REGIME_COLORS[data.regime] || REGIME_COLORS["Mixed"];
  const trend = data.trend_15m_1h_4h;
  const struct = data.structure;
  const lc = liqColor(data.liquidity_score);
  const liqPct = Math.min(100, data.liquidity_score);
  const etf = data.etf_snapshot;

  return (
    <div className="min-h-screen bg-[#faf8f5] text-stone-900 font-sans">
      <div className="max-w-screen-lg mx-auto p-4 space-y-4">

        {/* 顶栏 */}
        <header className="flex items-center justify-between pb-3 border-b border-stone-200">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-stone-400 hover:text-stone-500 transition-colors">
              <ArrowLeft size={16} />
            </Link>
            <Zap size={16} className="text-amber-600" />
            <h1 className="text-sm font-bold tracking-tight text-amber-600">
              黄金宝宝巴士
            </h1>
            <span className="text-[10px] text-stone-400">宏观监控 v2</span>
          </div>
          <div className="flex items-center gap-3">
            {data.timestamp && (
              <span className="text-[10px] text-stone-400 font-mono">
                {(() => { try { return new Date(data.timestamp).toLocaleString("zh-CN", { month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", second:"2-digit" }); } catch { return ""; } })()}
              </span>
            )}
            <button onClick={loadData} className="p-1.5 rounded-md hover:bg-stone-100 text-stone-400 hover:text-stone-500 transition-all">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </header>

        {/* ── 状态机 + 流动性 ───────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {/* 状态机 */}
          <div className={`bg-white border ${regimeStyle.border} rounded-xl p-4`}>
            <div className="flex items-center gap-2 mb-3">
              <Target size={13} className="text-stone-400" />
              <span className="text-[10px] text-stone-400 font-medium uppercase tracking-widest">Gold Regime</span>
            </div>
            <div className={`text-xl font-bold mb-2 tracking-tight ${regimeStyle.text}`}>{data.regime}</div>
            {data.regime_detail && (
              <div className="mb-2 flex items-center gap-3 text-[10px]">
                <span className="text-stone-400">主逻辑</span>
                <span className="text-stone-500 font-medium">{data.regime_detail.dominant_theme}</span>
                <span className="text-emerald-600 font-mono">Bull {data.regime_detail.bull_max}</span>
                <span className="text-red-600 font-mono">Bear {data.regime_detail.bear_max}</span>
              </div>
            )}
            <p className="text-xs text-stone-500 leading-relaxed">{data.regime_guide}</p>
          </div>

          {/* 流动性 */}
          <div className={`${cardBg(data.liquidity_score)} border border-stone-200 rounded-xl p-4`}>
            <div className="flex items-center gap-2 mb-3">
              <Droplets size={13} className="text-stone-400" />
              <span className="text-[10px] text-stone-400 font-medium uppercase tracking-widest">Liquidity Stress</span>
            </div>
            <div className="flex items-center gap-4">
              <div className="relative w-20 h-20 shrink-0">
                <svg className="w-20 h-20 -rotate-90" viewBox="0 0 64 64">
                  <circle cx="32" cy="32" r="27" fill="none" className="stroke-stone-200" strokeWidth="5"/>
                  <circle cx="32" cy="32" r="27" fill="none" className={lc.replace("text-","stroke-")}
                    strokeWidth="5" strokeLinecap="round"
                    strokeDasharray={`${(liqPct/100)*169.65} 169.65`}/>
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className={`text-xl font-bold font-mono ${lc}`}>{data.liquidity_score}</span>
                  <span className="text-[8px] text-stone-400">/100</span>
                </div>
              </div>
              <div className="flex-1">
                <span className={`text-sm font-semibold ${lc}`}>{data.liquidity_state}</span>
                <div className="mt-1 text-[10px] text-stone-400 leading-relaxed">
                  8维压力：DXY · CNH · JPY · Credit · IG · VIX · VVIX · MOVE · Gold
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── 趋势 + 结构 ────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {/* 趋势 */}
          <div className="bg-white border border-stone-200 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <TrendingUp size={13} className="text-stone-400" />
              <span className="text-[10px] text-stone-400 font-medium uppercase tracking-widest">GLD Trend</span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <TrendChip label="15m" sign={trend["15m"]} />
              <span className="text-stone-400 text-lg">→</span>
              <TrendChip label="1h" sign={trend["1h"]} />
              <span className="text-stone-400 text-lg">→</span>
              <TrendChip label="4h" sign={trend["4h"]} />
            </div>
            {data.combo_advice && (
              <p className="text-[10px] text-amber-500/80 mt-2">📋 {data.combo_advice}</p>
            )}
          </div>

          {/* 结构 */}
          <div className="bg-white border border-stone-200 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <Shield size={13} className="text-stone-400" />
              <span className="text-[10px] text-stone-400 font-medium uppercase tracking-widest">Structure Score</span>
            </div>
            <div className="space-y-2 mb-3">
              <Bar value={struct.long_score} max={10} color="bg-emerald-500" label="Long" />
              <Bar value={struct.short_score} max={10} color="bg-red-500" label="Short" />
            </div>
            <div className="flex flex-wrap gap-1.5">
              <Flag active={struct.flags.vwap_reclaim ?? false} label="VWAP↑" desc="突破均价" />
              <Flag active={struct.flags.vwap_reject ?? false} label="VWAP↓" desc="跌破均价" />
              <Flag active={struct.flags.near_key_fib ?? struct.flags.near_fib_618} label="KeyFib" desc="关键斐波" />
              <Flag active={struct.flags.bull_sweep ?? false} label="Sweep↑" desc="多头扫损" />
              <Flag active={struct.flags.bear_sweep ?? false} label="Sweep↓" desc="空头扫损" />
              <Flag active={struct.flags.double_bottom ?? false} label="2Btm" desc="双底" />
              <Flag active={struct.flags.double_top ?? false} label="2Top" desc="双顶" />
              <Flag active={struct.flags.higher_low ?? false} label="HL" desc="低点抬升" />
              <Flag active={struct.flags.lower_high ?? false} label="LH" desc="高点降低" />
            </div>
          </div>
        </div>

        {/* ── ETF 全景 ──────────────────────────────── */}
        <div className="bg-white border border-stone-200 rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-stone-200">
            <Activity size={13} className="text-stone-400" />
            <span className="text-[10px] text-stone-400 font-medium uppercase tracking-widest">ETF Snapshot</span>
            <span className="ml-auto text-[9px] text-stone-400">30 标的 · 15m/1h/4h 变化率</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-stone-200 text-[10px] text-stone-400 uppercase tracking-wider">
                  <th className="py-2.5 px-3 text-left font-medium">Ticker</th>
                  <th className="py-2.5 px-3 text-left font-medium">名称</th>
                  <th className="py-2.5 px-3 text-right font-medium">价格</th>
                  <th className="py-2.5 px-3 text-right font-medium">15m</th>
                  <th className="py-2.5 px-3 text-right font-medium">1h</th>
                  <th className="py-2.5 px-3 text-right font-medium">4h</th>
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
                  <tr><td colSpan={6} className="py-6 text-center text-stone-400 text-xs">ETF 快照暂不可用</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── 建议 ──────────────────────────────────── */}
        <div className="bg-white border border-stone-200 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle size={15} className="text-amber-600 mt-0.5 shrink-0" />
            <div className="flex-1">
              <span className="text-[10px] text-stone-400 font-medium uppercase tracking-widest block mb-2">Trading Advice</span>
              <p className="text-sm leading-relaxed">{data.advice}</p>
            </div>
          </div>
        </div>

        {/* 页脚 */}
        <footer className="text-center text-[10px] text-stone-400 py-6 border-t border-stone-200">
          yfinance · 31 标的跨资产监控 · 每 15 分钟更新 · 黄金宝宝巴士 v2
        </footer>
      </div>
    </div>
  );
}
