"use client";
// ============================================================
// 主 Dashboard 容器 — v4 状态机视图
// 布局：顶栏 → 数据源 → 统计pills → 信号 → 持仓 → 筛选+表格
// ============================================================

import React, { useState, useEffect, useCallback } from "react";
import { FuturesStatus, Position, PositionsData } from "@/lib/types";
import DashboardHeader from "./DashboardHeader";
import FuturesTable from "./FuturesTable";
import FilterBar, { StateFilter } from "./FilterBar";
import SignalTabs from "./SignalTabs";
import CurrentPositions from "./CurrentPositions";
import { Database, WifiOff, TrendingUp, Zap, Users } from "lucide-react";
import Link from "next/link";

const AUTO_REFRESH_INTERVAL = 30 * 60 * 1000;

const GITHUB_RAW = "https://raw.githubusercontent.com/MacLeeee/futures-monitor/main/futures-monitor/public";
function getDataUrl(): string {
  const isLocalhost = typeof window !== "undefined" && window.location.port !== "";
  const base = isLocalhost ? "" : GITHUB_RAW;
  return `${base}/data.json`;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function normalizeMacd(data: any[]): FuturesStatus[] {
  return data.map((d) => {
    if (d.macd && d.macd.sign === undefined) {
      const oldRegion: string = d.macd.region ?? "";
      d.macd.sign = oldRegion === "水上" ? "positive" : "negative";
      d.macd.rapidExpanding = d.macd.spreadStatus === "Expanding";
      d.macd.expansionRate = d.macd.rapidExpanding ? 1.0 : 0.0;
    }
    return d as FuturesStatus;
  });
}

type DataSource = "akshare" | "mock" | "github-actions" | null;

export default function FuturesDashboard() {
  const [data, setData] = useState<FuturesStatus[]>([]);
  const [filteredData, setFilteredData] = useState<FuturesStatus[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [dataSource, setDataSource] = useState<DataSource>(null);
  const [nextRefreshIn, setNextRefreshIn] = useState(AUTO_REFRESH_INTERVAL);
  const [remoteUpdatedAt, setRemoteUpdatedAt] = useState<string | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [pendingSet, setPendingSet] = useState<Set<string>>(new Set());

  const [selectedCategory, setSelectedCategory] = useState("全部");
  const [selectedState, setSelectedState] = useState<StateFilter>("全部");

  // ── 状态推断（供筛选用）──
  const getSymbolState = useCallback((row: FuturesStatus): string => {
    const bo = row.breakoutSignal;
    const pb = row.pullbackSignal;
    if (bo || pb) return "SIGNAL";
    if (pendingSet.has(row.symbol)) return "PENDING";
    const ma = row.ma;
    const macd = row.macd;
    const vol = row.volume;
    const oi = row.openInterest;
    const maOk = ma.status === "Upward" || ma.status === "Downward";
    const macdOk = macd.sign === (ma.status === "Upward" ? "positive" : "negative") && macd.rapidExpanding;
    const volOk = vol.status === "Surge";
    const oiOk = oi.status === "Increasing";
    if ([maOk, macdOk, volOk, oiOk].filter(Boolean).length >= 3) return "APPROACHING";
    if (row.marketRegime?.regime === "trending" && maOk) return "TRENDING";
    return "IDLE";
  }, [pendingSet]);

  // ── 数据加载 ──
  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const url = `${getDataUrl()}?t=${Date.now()}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(20000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(normalizeMacd(json.data ?? []));
      setDataSource(json.source as DataSource);
      if (json.updatedAt) setRemoteUpdatedAt(json.updatedAt);
    } catch (err) {
      console.error("[Dashboard] 数据加载失败:", err);
    } finally {
      setIsLoading(false);
      setLastRefresh(new Date());
      setNextRefreshIn(AUTO_REFRESH_INTERVAL);
    }
  }, []);

  const loadPositions = useCallback(async () => {
    try {
      const isLocal = typeof window !== "undefined" && window.location.port !== "";
      const base = isLocal ? "" : GITHUB_RAW;
      const url = `${base}/positions.json?t=${Date.now()}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(10000) });
      if (!res.ok) return;
      const json: PositionsData = await res.json();
      setPositions(json.positions ?? []);
    } catch { /* 静默 */ }
  }, []);

  const loadPending = useCallback(async () => {
    try {
      const isLocal = typeof window !== "undefined" && window.location.port !== "";
      const base = isLocal ? "" : GITHUB_RAW;
      const url = `${base}/pending_breakouts.json?t=${Date.now()}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
      if (!res.ok) return;
      const json = await res.json();
      const symbols = (json.pending ?? []).map((p: { symbol: string }) => p.symbol);
      setPendingSet(new Set(symbols));
    } catch { /* 静默 */ }
  }, []);

  useEffect(() => { loadData(); loadPositions(); loadPending(); }, [loadData, loadPositions, loadPending]);

  // ── 自动刷新 ──
  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(loadData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(timer);
  }, [autoRefresh, loadData]);

  useEffect(() => {
    if (!autoRefresh) return;
    const tick = setInterval(() => setNextRefreshIn((p) => Math.max(0, p - 1000)), 1000);
    return () => clearInterval(tick);
  }, [autoRefresh, lastRefresh]);

  const handleManualRefresh = useCallback(() => {
    setNextRefreshIn(AUTO_REFRESH_INTERVAL);
    loadData();
  }, [loadData]);

  // ── 筛选 ──
  useEffect(() => {
    let result = data;
    if (selectedCategory !== "全部") result = result.filter((d) => d.category === selectedCategory);
    if (selectedState !== "全部") result = result.filter((d) => getSymbolState(d) === selectedState);
    setFilteredData(result);
  }, [data, selectedCategory, selectedState, getSymbolState]);

  const formatCountdown = (ms: number) => {
    const m = Math.floor(ms / 60000);
    const s = Math.ceil((ms % 60000) / 1000);
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  };

  return (
    <div className="min-h-screen bg-[#faf8f5] text-stone-900 font-sans">
      <div className="max-w-screen-2xl mx-auto p-4 space-y-3">

        {/* ── 顶栏 ───────────────── */}
        <header className="flex items-center gap-3 pb-2 border-b border-stone-200">
          <Zap size={18} className="text-amber-600" />
          <span className="text-sm font-bold tracking-tight text-amber-600">
            期货监控
          </span>
          <span className="text-[10px] text-stone-400">30min · 状态机视图</span>

          <div className="flex-1" />

          <Link
            href="/gold"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-all text-stone-500 hover:text-amber-500 hover:bg-amber-50/70"
          >
            <TrendingUp size={12} />
            黄金监控
          </Link>
          <Link
            href="/seats"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-all text-stone-500 hover:text-purple-500 hover:bg-purple-50/70"
          >
            <Users size={12} />
            席位监控
          </Link>
        </header>

        {/* ── 数据源状态 ─────────────────────────────── */}
        <DataSourceBanner source={dataSource} updatedAt={remoteUpdatedAt} />

        {/* ── 概览栏 ───────────────────── */}
        <DashboardHeader
          data={data}
          lastRefresh={lastRefresh}
          autoRefresh={autoRefresh}
          onToggleAutoRefresh={() => setAutoRefresh((v) => !v)}
          onManualRefresh={handleManualRefresh}
          isLoading={isLoading}
          nextRefreshIn={autoRefresh ? formatCountdown(nextRefreshIn) : null}
        />

        {/* ── 信号面板 ───────────────── */}
        <SignalTabs data={data} />

        {/* ── 持仓 ─────────────────────── */}
        <CurrentPositions
          positions={positions}
          currentPrices={Object.fromEntries(data.map((d) => [d.symbol, d.price]))}
        />

        {/* ── 筛选栏 + 表格 ─────────────────────────── */}
        <div className="space-y-2">
          <FilterBar
            selectedCategory={selectedCategory}
            selectedState={selectedState}
            onCategoryChange={setSelectedCategory}
            onStateChange={setSelectedState}
            totalCount={data.length}
            filteredCount={filteredData.length}
          />

          {isLoading && data.length === 0 ? (
            <div className="space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-10 bg-white rounded-md animate-pulse"
                  style={{ opacity: 1 - i * 0.08 }} />
              ))}
            </div>
          ) : (
            <div className="relative">
              {isLoading && (
                <div className="absolute top-3 right-3 z-30 flex items-center gap-2 px-2.5 py-1 bg-white/95 backdrop-blur border border-stone-200 rounded-md text-xs text-stone-500">
                  <div className="w-1.5 h-1.5 bg-amber-600 rounded-full animate-pulse" />
                  拉取数据...
                </div>
              )}
              <FuturesTable data={filteredData} pendingSet={pendingSet} />
            </div>
          )}
        </div>

        {/* ── 页脚 ────────────────────────────────────── */}
        <footer className="flex items-center justify-between text-[10px] text-stone-400 pt-3 border-t border-stone-200">
          <div className="flex gap-4">
            <span>AKShare · 新浪财经</span>
            <span>30min K 线</span>
            <span>H-005 回踩 + H-010 突破 状态机</span>
          </div>
        </footer>
      </div>
    </div>
  );
}

// ── 数据源横幅 ──────────────────────────────────────────────

function DataSourceBanner({ source, updatedAt }: { source: DataSource; updatedAt: string | null }) {
  const fmtTime = (iso: string | null) => {
    if (!iso) return "";
    try { return new Date(iso).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }); }
    catch { return ""; }
  };

  if (source === "github-actions" || source === "akshare") {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50/80 border border-emerald-500/20 rounded-md text-xs text-emerald-600">
        <Database size={12} />
        <span className="font-medium">实盘数据</span>
        <span className="text-emerald-600/60">— 数据源已连接</span>
        {updatedAt && <span className="ml-auto text-emerald-600/40 font-mono text-[10px]">{fmtTime(updatedAt)}</span>}
      </div>
    );
  }

  if (source === "mock") {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50/70 border border-amber-200 rounded-md text-xs text-amber-500">
        <WifiOff size={12} />
        <span className="font-medium">模拟数据</span>
        <span className="text-amber-500/60">— 演示模式</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-white border border-stone-200 rounded-md text-xs text-stone-400">
      <div className="w-1.5 h-1.5 rounded-full bg-stone-400 animate-pulse" />
      加载数据...
    </div>
  );
}
