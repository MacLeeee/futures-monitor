"use client";
// ============================================================
// 主 Dashboard 容器 — 浅色专业版
// ============================================================

import React, { useState, useEffect, useCallback } from "react";
import { FuturesStatus, Position, PositionsData } from "@/lib/types";
import DashboardHeader from "./DashboardHeader";
import FuturesTable from "./FuturesTable";
import FilterBar from "./FilterBar";
import SignalPanel from "./SignalPanel";
import DipBuyPanel from "./DipBuyPanel";
import CurrentPositions from "./CurrentPositions";
import { Database, WifiOff, TrendingUp, Zap } from "lucide-react";
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

  const [selectedCategory, setSelectedCategory] = useState("全部");
  const [selectedMAStatus, setSelectedMAStatus] = useState("全部");

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

  useEffect(() => { loadData(); loadPositions(); }, [loadData, loadPositions]);

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
    setNextRefreshIn(AUTO_REFRESH_INTERVAL); loadData();
  }, [loadData]);

  useEffect(() => {
    let result = data;
    if (selectedCategory !== "全部") result = result.filter((d) => d.category === selectedCategory);
    if (selectedMAStatus !== "全部") result = result.filter((d) => d.ma.status === selectedMAStatus);
    setFilteredData(result);
  }, [data, selectedCategory, selectedMAStatus]);

  const formatCountdown = (ms: number) => {
    const m = Math.floor(ms / 60000);
    const s = Math.ceil((ms % 60000) / 1000);
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  };

  return (
    <div className="min-h-screen bg-[#f4f5f7] text-gray-900 font-sans">
      <div className="max-w-screen-2xl mx-auto p-4 space-y-4">

        {/* ── 顶栏 ───────────────── */}
        <header className="flex items-center gap-3 pb-3 border-b border-gray-200">
          <Zap size={18} className="text-blue-600" />
          <span className="text-sm font-bold tracking-tight text-blue-600">
            期货监控
          </span>
          <span className="text-[10px] text-gray-400">30min</span>

          <div className="flex-1" />

          <Link
            href="/gold"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-all text-gray-500 hover:text-blue-500 hover:bg-blue-50/70"
          >
            <TrendingUp size={12} />
            黄金监控
          </Link>
        </header>

        {/* ── 数据源状态 ─────────────────────────────── */}
        <DataSourceBanner source={dataSource} updatedAt={remoteUpdatedAt} />

        {/* ── 概览栏 ──────────────────────────────────── */}
        <DashboardHeader
          data={data}
          lastRefresh={lastRefresh}
          autoRefresh={autoRefresh}
          onToggleAutoRefresh={() => setAutoRefresh((v) => !v)}
          onManualRefresh={handleManualRefresh}
          isLoading={isLoading}
          nextRefreshIn={autoRefresh ? formatCountdown(nextRefreshIn) : null}
        />

        {/* ── 筛选栏 ──────────────────────────────────── */}
        <FilterBar
          selectedCategory={selectedCategory}
          selectedMAStatus={selectedMAStatus}
          onCategoryChange={setSelectedCategory}
          onMAStatusChange={setSelectedMAStatus}
          totalCount={data.length}
          filteredCount={filteredData.length}
        />

        {/* ── 信号面板 ────────────────────────────────── */}
        <SignalPanel data={data} />
        <DipBuyPanel data={data} />

        {/* ── 持仓 ────────────────────────────────────── */}
        <CurrentPositions
          positions={positions}
          currentPrices={Object.fromEntries(data.map((d) => [d.symbol, d.price]))}
        />

        {/* ── 数据表格 ────────────────────────────────── */}
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
              <div className="absolute top-3 right-3 z-30 flex items-center gap-2 px-2.5 py-1 bg-white/95 backdrop-blur border border-gray-200 rounded-md text-xs text-gray-500">
                <div className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-pulse" />
                拉取数据...
              </div>
            )}
            <FuturesTable data={filteredData} />
          </div>
        )}

        {/* ── 页脚 ────────────────────────────────────── */}
        <footer className="flex items-center justify-between text-[10px] text-gray-400 pt-4 border-t border-gray-200">
          <div className="flex gap-4">
            <span>AKShare · 新浪财经</span>
            <span>30min K 线</span>
            <span>MA20/60 · MACD · Vol · OI</span>
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
      <div className="flex items-center gap-2 px-3 py-2 bg-emerald-50/80 border border-emerald-500/20 rounded-md text-xs text-emerald-600">
        <Database size={12} />
        <span className="font-medium">实盘数据</span>
        <span className="text-emerald-600/60">— 数据源已连接</span>
        {updatedAt && <span className="ml-auto text-emerald-600/40 font-mono text-[10px]">{fmtTime(updatedAt)}</span>}
      </div>
    );
  }

  if (source === "mock") {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-blue-50/70 border border-blue-200 rounded-md text-xs text-blue-500">
        <WifiOff size={12} />
        <span className="font-medium">模拟数据</span>
        <span className="text-blue-500/60">— 演示模式</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-white border border-gray-200 rounded-md text-xs text-gray-400">
      <div className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-pulse" />
      加载数据...
    </div>
  );
}
