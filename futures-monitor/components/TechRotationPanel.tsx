"use client";
// ============================================================
// A股科技板块轮动监控面板
// 数据源：tech_rotation.json（run.py --json 输出）
// ============================================================

import { useState, useEffect, useCallback } from "react";
import { TechRotationData, TechThemeRow, TechAttributionRow } from "@/lib/types";
import { TrendingUp, Zap, AlertTriangle, Cpu } from "lucide-react";

const GITHUB_RAW =
  "https://raw.githubusercontent.com/MacLeeee/futures-monitor/main/futures-monitor/public";

// ── 文本映射（和 engine.py 保持一致）──────────────────────────
const STATE_TEXT: Record<number, string> = {
  3: "拥挤主升", 2: "确认进入", 1: "早期轮动", 0: "中性观察",
  [-1]: "资金撤出", [-2]: "派发/撤出", 9: "无数据",
};
const TREND_TEXT: Record<number, string> = {
  2: "强", 1: "偏强", [-1]: "偏弱", [-2]: "弱", 0: "中性",
};
const REASON_TEXT: Record<number, string> = {
  1: "主动流入", 2: "早期轮动", 3: "Pair unwind", 4: "AI链条扩散",
  6: "拥挤主升", 7: "拥挤出清", 8: "派发/撤出", 9: "Beta假强",
  10: "抗跌观察", 11: "内部降风险", 12: "月/季再平衡", 13: "AI应用追赶",
  99: "无数据", 0: "中性",
};
const SOURCE_LABEL: Record<string, string> = {
  topic_table: "zz题材K线",
  zz_topic_basket: "zz成分股+ak合成",
  ak_concept: "ak概念",
  plate: "zz普通板块",
  none: "无数据",
};

// ── 样式工具 ────────────────────────────────────────────────
function scoreClass(score: number | null, state: number | null): string {
  if (state === 9) return "bg-stone-100 text-stone-400";
  if (state !== null && state <= -1) return "bg-red-100/60 text-red-600";
  if (state === 3) return "bg-amber-100/60 text-amber-700";
  if (score === null) return "bg-stone-100 text-stone-400";
  if (score >= 75) return "bg-emerald-200/60 text-emerald-800 font-bold";
  if (score >= 60) return "bg-emerald-100/60 text-emerald-700";
  if (score >= 45) return "bg-stone-100 text-stone-600";
  return "bg-red-50/60 text-red-500";
}

function stateBadge(state: number | null): { label: string; cls: string } {
  if (state === 3) return { label: "拥挤主升", cls: "bg-amber-100 text-amber-700 border-amber-300" };
  if (state === 2) return { label: "确认进入", cls: "bg-emerald-100 text-emerald-700 border-emerald-300" };
  if (state === 1) return { label: "早期轮动", cls: "bg-teal-50 text-teal-600 border-teal-200" };
  if (state === 0) return { label: "中性观察", cls: "bg-stone-100 text-stone-500 border-stone-300" };
  if (state === -1) return { label: "资金撤出", cls: "bg-red-50 text-red-500 border-red-200" };
  if (state === -2) return { label: "派发/撤出", cls: "bg-red-100 text-red-600 border-red-300" };
  return { label: "无数据", cls: "bg-stone-100 text-stone-400 border-stone-200" };
}

function pct(x: number | null): string {
  if (x === null) return "—";
  const sign = x >= 0 ? "+" : "";
  return `${sign}${x.toFixed(2)}%`;
}

function num2(x: number | null): string {
  if (x === null) return "—";
  return x.toFixed(2);
}

function scoreStr(x: number | null): string {
  if (x === null) return "—";
  return x.toFixed(0);
}

function attrScoreClass(score: number | null): string {
  if (score === null) return "bg-stone-100 text-stone-400";
  if (score >= 75) return "bg-emerald-200/60 text-emerald-800 font-bold";
  if (score >= 60) return "bg-emerald-100/60 text-emerald-700";
  if (score >= 45) return "bg-stone-100 text-stone-600";
  return "bg-stone-100 text-stone-400";
}

function pctColor(x: number | null): string {
  if (x === null) return "text-stone-400";
  if (x > 0) return "text-red-600";
  if (x < 0) return "text-emerald-600";
  return "text-stone-400";
}

// ── 组件 ────────────────────────────────────────────────────
export default function TechRotationPanel() {
  const [data, setData] = useState<TechRotationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const isLocal = typeof window !== "undefined" && window.location.port !== "";
      const base = isLocal ? "" : GITHUB_RAW;
      const url = `${base}/tech_rotation.json?t=${Date.now()}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(15000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: TechRotationData = await res.json();
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
    const timer = setInterval(loadData, 30 * 60 * 1000);
    return () => clearInterval(timer);
  }, [loadData]);

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto p-4">
        <div className="bg-white border border-stone-200 rounded-lg p-8 flex items-center gap-3 text-stone-500">
          <div className="w-2.5 h-2.5 bg-purple-500 rounded-full animate-pulse" />
          <span className="text-sm">加载科技板块轮动数据...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="max-w-6xl mx-auto p-4">
        <div className="bg-white border border-stone-200 rounded-lg p-8 flex items-center gap-3 text-stone-500">
          <AlertTriangle size={16} />
          <span className="text-sm">科技板块轮动数据暂不可用{error ? ` (${error})` : ""}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-4 space-y-6">
      {/* 标题 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Cpu size={20} className="text-purple-600" />
          <h1 className="text-lg font-bold text-stone-800">
            A股科技板块轮动监控器
            <span className="ml-2 text-xs font-normal text-stone-400">v2.4-CN</span>
          </h1>
        </div>
        <div className="text-xs text-stone-400 font-mono space-x-3">
          <span>数据: {data.data_date}</span>
          <span>更新: {data.generated}</span>
        </div>
      </div>

      {/* ── 主题轮动评分表 ── */}
      <div className="bg-white border border-stone-200 rounded-lg overflow-hidden">
        <div className="px-4 py-2.5 border-b border-stone-200 flex items-center gap-2">
          <TrendingUp size={14} className="text-purple-500" />
          <span className="text-xs font-semibold text-stone-600 uppercase tracking-wider">
            主题轮动评分
          </span>
          <span className="text-[10px] text-stone-400 ml-2">
            基准: {data.primary}{data.secondary ? ` + ${data.secondary}` : ""}
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="bg-stone-50 text-stone-500">
                <th className="text-left px-3 py-2 font-semibold sticky left-0 bg-stone-50 z-10">主题</th>
                <th className="px-2 py-2">5D相对</th>
                <th className="px-2 py-2">20D相对</th>
                <th className="px-2 py-2">60D相对</th>
                <th className="px-2 py-2">绝对5D</th>
                <th className="px-2 py-2">趋势</th>
                <th className="px-2 py-2">量比</th>
                <th className="px-2 py-2">广度</th>
                <th className="px-2 py-2">评分</th>
                {data.secondary && (
                  <>
                    <th className="px-2 py-2">5D相对</th>
                    <th className="px-2 py-2">评分</th>
                  </>
                )}
                <th className="px-2 py-2">状态</th>
                <th className="px-3 py-2 text-left">可能原因</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {data.themes.map((t) => (
                <ThemeRow key={t.name} theme={t} showSecondary={!!data.secondary} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── 资金轮动归因表 ── */}
      <div className="bg-white border border-stone-200 rounded-lg overflow-hidden">
        <div className="px-4 py-2.5 border-b border-stone-200 flex items-center gap-2">
          <Zap size={14} className="text-amber-500" />
          <span className="text-xs font-semibold text-stone-600 uppercase tracking-wider">
            资金轮动归因
          </span>
        </div>
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-stone-50 text-stone-500">
              <th className="text-left px-3 py-2 font-semibold">归因信号</th>
              <th className="px-2 py-2 w-16">分数</th>
              <th className="text-left px-3 py-2">核心依据</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {data.attribution.map((a) => (
              <AttrRow key={a.name} attr={a} />
            ))}
          </tbody>
        </table>
      </div>

      {/* 数据源说明 */}
      <div className="text-[10px] text-stone-400 leading-relaxed border-t border-stone-200 pt-3">
        数据源: 自在量化 zzshare + akshare 备用。仅为板块资金轮动观察工具，不构成投资建议。
      </div>
    </div>
  );
}

// ── 主题行 ──────────────────────────────────────────────────
function ThemeRow({ theme: t, showSecondary }: { theme: TechThemeRow; showSecondary: boolean }) {
  const badge = stateBadge(t.state);
  return (
    <tr className="hover:bg-stone-50/50 transition-colors">
      <td className="text-left px-3 py-2 font-semibold text-stone-800 sticky left-0 bg-white z-5">
        {t.name}
      </td>
      <td className={`px-2 py-2 ${pctColor(t.rel5)}`}>{pct(t.rel5)}</td>
      <td className={`px-2 py-2 ${pctColor(t.rel20)}`}>{pct(t.rel20)}</td>
      <td className={`px-2 py-2 ${pctColor(t.rel60)}`}>{pct(t.rel60)}</td>
      <td className={`px-2 py-2 ${pctColor(t.abs5)}`}>{pct(t.abs5)}</td>
      <td className="px-2 py-2 text-stone-600">
        {t.trend !== null ? TREND_TEXT[t.trend] ?? "中性" : "—"}
      </td>
      <td className="px-2 py-2 text-stone-600">{num2(t.volR)}x</td>
      <td className="px-2 py-2 text-stone-400">
        {t.breadth !== null ? `${t.breadth.toFixed(1)}%` : "—"}
      </td>
      <td className={`px-2 py-2 font-bold rounded ${scoreClass(t.score, t.state)}`}>
        {scoreStr(t.score)}
      </td>
      {showSecondary && (
        <>
          <td className={`px-2 py-2 ${pctColor(t.rel5_2)}`}>{pct(t.rel5_2)}</td>
          <td className={`px-2 py-2 ${scoreClass(t.score2, t.state)}`}>
            {scoreStr(t.score2)}
          </td>
        </>
      )}
      <td className="px-2 py-2">
        <span className={`px-1.5 py-0.5 rounded border text-[10px] ${badge.cls}`}>
          {badge.label}
        </span>
      </td>
      <td className="px-3 py-2 text-left text-stone-500">
        {t.reason !== null ? (REASON_TEXT[t.reason] ?? "—") : "—"}
      </td>
    </tr>
  );
}

// ── 归因行 ──────────────────────────────────────────────────
function AttrRow({ attr: a }: { attr: TechAttributionRow }) {
  return (
    <tr className="hover:bg-stone-50/50 transition-colors">
      <td className="px-3 py-2 font-semibold text-stone-700">{a.name}</td>
      <td className={`px-2 py-2 text-center font-bold font-mono ${attrScoreClass(a.score)}`}>
        {scoreStr(a.score)}
      </td>
      <td className="px-3 py-2 text-stone-500 font-mono">{a.hint || "—"}</td>
    </tr>
  );
}
