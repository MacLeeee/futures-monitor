"use client";
// ============================================================
// 科技轮动评分 — 中证1000基准 · 新框架 (daily_framework)
// 数据源: tech_rotation.json
// ============================================================

import { useState, useEffect, useCallback } from "react";
import {
  ArrowLeft, RefreshCw, AlertTriangle, Layers, TrendingUp, Compass,
} from "lucide-react";
import Link from "next/link";

const GITHUB_RAW =
  "https://raw.githubusercontent.com/MacLeeee/futures-monitor/main/futures-monitor/public";

// ── 数据类型 ────────────────────────────────────────────────
interface Theme {
  name: string;
  n_stocks: number;
  rel5: number | null;
  rel20: number | null;
  rel60: number | null;
  abs5: number | null;
  trend: number;
  volR: number | null;
  score: number | null;
  state: number;
  reason: number;
}
interface Attribution {
  name: string;
  score: number;
  hint: string;
}
interface RotationData {
  generated: string;
  data_date: string;
  primary: string;
  themes: Theme[];
  attribution: Attribution[];
}

// ── 状态映射 ────────────────────────────────────────────────
// state: 2强势 / 1偏强 / 0中性 / -1偏弱 / -2弱势 / 9无数据
const STATE_META: Record<number, { label: string; cls: string }> = {
  2:  { label: "强势", cls: "bg-emerald-50 text-emerald-600 ring-1 ring-emerald-500/25" },
  1:  { label: "偏强", cls: "bg-teal-50 text-teal-600 ring-1 ring-teal-500/25" },
  0:  { label: "中性", cls: "bg-stone-100 text-stone-500 ring-1 ring-stone-300/40" },
  [-1]: { label: "偏弱", cls: "bg-orange-50 text-orange-600 ring-1 ring-orange-500/25" },
  [-2]: { label: "弱势", cls: "bg-red-50 text-red-600 ring-1 ring-red-500/25" },
  9:  { label: "无数据", cls: "bg-stone-50 text-stone-300 ring-1 ring-stone-200" },
};

function scoreColor(s: number): string {
  if (s >= 70) return "bg-emerald-500";
  if (s >= 50) return "bg-teal-500";
  if (s >= 35) return "bg-amber-500";
  return "bg-stone-400";
}

function trendArrow(t: number): { arrow: string; cls: string } {
  if (t >= 2)  return { arrow: "↗↗", cls: "text-emerald-600" };
  if (t === 1) return { arrow: "↗",  cls: "text-teal-600" };
  if (t === 0) return { arrow: "→",  cls: "text-stone-400" };
  if (t === -1) return { arrow: "↘", cls: "text-orange-600" };
  return { arrow: "↘↘", cls: "text-red-600" };
}

// 超额收益着色
function Rel({ v }: { v: number | null }) {
  if (v === null || v === undefined) return <span className="text-stone-300 font-mono">—</span>;
  const c = v > 0 ? "text-emerald-600" : v < 0 ? "text-red-600" : "text-stone-400";
  return <span className={`font-mono text-xs tabular-nums ${c}`}>{v > 0 ? "+" : ""}{v.toFixed(2)}%</span>;
}

export default function TechRotationPage() {
  const [data, setData] = useState<RotationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const isLocal = typeof window !== "undefined" && window.location.port !== "";
      const base = isLocal ? "" : GITHUB_RAW;
      const url = `${base}/tech_rotation.json?t=${Date.now()}`;
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

  if (loading && !data) {
    return (
      <div className="min-h-screen bg-[#faf8f5] flex items-center justify-center">
        <div className="flex items-center gap-3 text-stone-500">
          <div className="w-2 h-2 bg-teal-600 rounded-full animate-pulse" />
          <span className="text-sm">加载轮动评分...</span>
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

  // 有效主题(有评分)按分排序，无数据主题垫底
  const valid = data.themes.filter((t) => t.score !== null).sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const noData = data.themes.filter((t) => t.score === null);
  const strongCnt = valid.filter((t) => t.state >= 1).length;
  const weakCnt = valid.filter((t) => t.state <= -1).length;
  const leader = valid[0];

  return (
    <div className="min-h-screen bg-[#faf8f5] text-stone-900 font-sans">
      <div className="max-w-screen-lg mx-auto p-4 space-y-4">

        {/* 顶栏 */}
        <header className="flex items-center justify-between pb-3 border-b border-stone-200">
          <div className="flex items-center gap-3">
            <Link href="/" className="text-stone-400 hover:text-stone-500 transition-colors">
              <ArrowLeft size={16} />
            </Link>
            <Layers size={16} className="text-teal-600" />
            <h1 className="text-sm font-bold tracking-tight text-teal-600">科技轮动评分</h1>
            <span className="text-[10px] text-stone-400">{data.primary} 基准</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[10px] text-stone-400 font-mono">
              {data.data_date} · {data.generated?.slice(-5)}
            </span>
            <button onClick={loadData} className="p-1.5 rounded-md hover:bg-stone-100 text-stone-400 hover:text-stone-500 transition-all">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </header>

        {/* 概览 */}
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-white border border-stone-200 rounded-xl p-4">
            <div className="text-[10px] text-stone-400 uppercase tracking-widest mb-1">当前主线</div>
            <div className="text-base font-bold text-emerald-600">{leader?.name ?? "—"}</div>
            <div className="text-[10px] text-stone-400 mt-0.5 font-mono">评分 {leader?.score?.toFixed(0) ?? "—"}</div>
          </div>
          <div className="bg-white border border-stone-200 rounded-xl p-4">
            <div className="text-[10px] text-stone-400 uppercase tracking-widest mb-1">强势主题</div>
            <div className="text-base font-bold text-teal-600 font-mono">{strongCnt}<span className="text-xs text-stone-400"> / {valid.length}</span></div>
            <div className="text-[10px] text-stone-400 mt-0.5">state ≥ 偏强</div>
          </div>
          <div className="bg-white border border-stone-200 rounded-xl p-4">
            <div className="text-[10px] text-stone-400 uppercase tracking-widest mb-1">偏弱主题</div>
            <div className="text-base font-bold text-orange-600 font-mono">{weakCnt}<span className="text-xs text-stone-400"> / {valid.length}</span></div>
            <div className="text-[10px] text-stone-400 mt-0.5">state ≤ 偏弱</div>
          </div>
        </div>

        {/* 主题排名表 */}
        <div className="bg-white border border-stone-200 rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-stone-200">
            <TrendingUp size={13} className="text-stone-400" />
            <span className="text-[10px] text-stone-400 font-medium uppercase tracking-widest">主题轮动排名</span>
            <span className="ml-auto text-[9px] text-stone-400">超额收益 = 相对{data.primary}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-stone-200 text-[10px] text-stone-400 uppercase tracking-wider">
                  <th className="py-2.5 px-3 text-left font-medium">#</th>
                  <th className="py-2.5 px-3 text-left font-medium">主题</th>
                  <th className="py-2.5 px-3 text-left font-medium w-40">评分</th>
                  <th className="py-2.5 px-3 text-center font-medium">状态</th>
                  <th className="py-2.5 px-3 text-right font-medium">5日</th>
                  <th className="py-2.5 px-3 text-right font-medium">20日</th>
                  <th className="py-2.5 px-3 text-right font-medium">60日</th>
                  <th className="py-2.5 px-3 text-right font-medium">量比</th>
                  <th className="py-2.5 px-3 text-center font-medium">趋势</th>
                </tr>
              </thead>
              <tbody>
                {valid.map((t, i) => {
                  const sm = STATE_META[t.state] ?? STATE_META[0];
                  const ta = trendArrow(t.trend);
                  const sc = t.score ?? 0;
                  return (
                    <tr key={t.name} className="border-b border-stone-100 hover:bg-teal-50/40 transition-colors">
                      <td className="py-2.5 px-3 text-stone-400 font-mono">{i + 1}</td>
                      <td className="py-2.5 px-3">
                        <span className="text-xs font-medium text-stone-900">{t.name}</span>
                        <span className="text-[9px] text-stone-400 ml-1.5">{t.n_stocks}支</span>
                      </td>
                      <td className="py-2.5 px-3">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono tabular-nums text-stone-900 w-7">{sc.toFixed(0)}</span>
                          <div className="flex-1 h-1.5 bg-stone-200 rounded-full overflow-hidden min-w-[60px]">
                            <div className={`h-full rounded-full transition-all duration-700 ${scoreColor(sc)}`} style={{ width: `${Math.min(100, sc)}%` }} />
                          </div>
                        </div>
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium ${sm.cls}`}>{sm.label}</span>
                      </td>
                      <td className="py-2.5 px-3 text-right"><Rel v={t.rel5} /></td>
                      <td className="py-2.5 px-3 text-right"><Rel v={t.rel20} /></td>
                      <td className="py-2.5 px-3 text-right"><Rel v={t.rel60} /></td>
                      <td className="py-2.5 px-3 text-right">
                        <span className={`font-mono text-xs tabular-nums ${(t.volR ?? 0) >= 1.2 ? "text-emerald-600" : (t.volR ?? 0) < 0.9 ? "text-stone-400" : "text-stone-600"}`}>
                          {t.volR?.toFixed(2) ?? "—"}
                        </span>
                      </td>
                      <td className={`py-2.5 px-3 text-center font-mono ${ta.cls}`}>{ta.arrow}</td>
                    </tr>
                  );
                })}
                {noData.map((t) => (
                  <tr key={t.name} className="border-b border-stone-100 opacity-40">
                    <td className="py-2.5 px-3 text-stone-300 font-mono">—</td>
                    <td className="py-2.5 px-3"><span className="text-xs text-stone-400">{t.name}</span></td>
                    <td className="py-2.5 px-3" colSpan={7}><span className="text-[10px] text-stone-300">无成分股数据</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 轮动叙事归因 */}
        {data.attribution && data.attribution.length > 0 && (
          <div className="bg-white border border-stone-200 rounded-xl overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-stone-200">
              <Compass size={13} className="text-stone-400" />
              <span className="text-[10px] text-stone-400 font-medium uppercase tracking-widest">轮动叙事归因</span>
              <span className="ml-auto text-[9px] text-stone-400">资金主线信号强度</span>
            </div>
            <div className="p-3 grid grid-cols-1 md:grid-cols-2 gap-2">
              {[...data.attribution].sort((a, b) => b.score - a.score).map((a) => (
                <div key={a.name} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-stone-50/60">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-stone-900 truncate">{a.name}</div>
                    <div className="text-[10px] text-stone-400 truncate">{a.hint}</div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 w-24">
                    <div className="flex-1 h-1.5 bg-stone-200 rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${scoreColor(a.score)}`} style={{ width: `${Math.min(100, a.score)}%` }} />
                    </div>
                    <span className="text-[10px] font-mono tabular-nums text-stone-500 w-6 text-right">{a.score.toFixed(0)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 页脚 */}
        <footer className="text-center text-[10px] text-stone-400 py-6 border-t border-stone-200">
          tushare 日线 · {data.primary} 基准 · 每日收盘更新 · 科技轮动 v2 (daily_framework)
        </footer>
      </div>
    </div>
  );
}
