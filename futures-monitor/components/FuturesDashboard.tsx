"use client";
// ============================================================
// 主 Dashboard 容器组件
// 管理数据状态、自动刷新、筛选逻辑
// ============================================================

import React, { useState, useEffect, useCallback } from "react";
import { FuturesStatus } from "@/lib/types";
import DashboardHeader from "./DashboardHeader";
import FuturesTable from "./FuturesTable";
import FilterBar from "./FilterBar";
import SignalPanel from "./SignalPanel";
import { AlertCircle, WifiOff, Database } from "lucide-react";

// 30 分钟自动刷新（与 K 线周期对齐）
const AUTO_REFRESH_INTERVAL = 30 * 60 * 1000;

// 数据来源类型
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

  // 筛选状态
  const [selectedCategory, setSelectedCategory] = useState("全部");
  const [selectedMAStatus, setSelectedMAStatus] = useState("全部");

  // 数据 URL 优先级:
  //   1. NEXT_PUBLIC_DATA_URL (CI 构建时注入，生产用 /data.json)
  //   2. 开发环境: /api/futures (本地 AKShare Python 服务)
  const DATA_URL =
    process.env.NEXT_PUBLIC_DATA_URL ??
    (typeof window !== "undefined" && window.location.port !== ""
      ? "/api/futures"   // localhost 开发
      : "/data.json");   // 生产兜底

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      // 添加时间戳强制跳过浏览器缓存
      const url = `${DATA_URL}${DATA_URL.includes("?") ? "&" : "?"}t=${Date.now()}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(20000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json.data ?? []);
      setDataSource(json.source as DataSource);
      if (json.updatedAt) setRemoteUpdatedAt(json.updatedAt);
    } catch (err) {
      console.error("[Dashboard] 数据加载失败:", err);
    } finally {
      setIsLoading(false);
      setLastRefresh(new Date());
      setNextRefreshIn(AUTO_REFRESH_INTERVAL);
    }
  }, [DATA_URL]);

  // 初始加载
  useEffect(() => {
    loadData();
  }, [loadData]);

  // 自动刷新定时器（30 分钟触发一次）
  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(loadData, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(timer);
  }, [autoRefresh, loadData]);

  // 倒计时更新（每秒）
  useEffect(() => {
    if (!autoRefresh) return;
    const tick = setInterval(() => {
      setNextRefreshIn((prev) => Math.max(0, prev - 1000));
    }, 1000);
    return () => clearInterval(tick);
  }, [autoRefresh, lastRefresh]);

  // 手动刷新时重置倒计时
  const handleManualRefresh = useCallback(() => {
    setNextRefreshIn(AUTO_REFRESH_INTERVAL);
    loadData();
  }, [loadData]);

  // 筛选逻辑
  useEffect(() => {
    let result = data;
    if (selectedCategory !== "全部") {
      result = result.filter((d) => d.category === selectedCategory);
    }
    if (selectedMAStatus !== "全部") {
      result = result.filter((d) => d.ma.status === selectedMAStatus);
    }
    setFilteredData(result);
  }, [data, selectedCategory, selectedMAStatus]);

  // 格式化倒计时
  const formatCountdown = (ms: number) => {
    const totalSec = Math.ceil(ms / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  };

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-4 font-mono">
      <div className="max-w-screen-2xl mx-auto space-y-3">

        {/* 实盘/模拟数据状态横幅 */}
        <DataSourceBanner source={dataSource} updatedAt={remoteUpdatedAt} />

        {/* 头部：概览统计 + 刷新控制 */}
        <DashboardHeader
          data={data}
          lastRefresh={lastRefresh}
          autoRefresh={autoRefresh}
          onToggleAutoRefresh={() => setAutoRefresh((v) => !v)}
          onManualRefresh={handleManualRefresh}
          isLoading={isLoading}
          nextRefreshIn={autoRefresh ? formatCountdown(nextRefreshIn) : null}
        />

        {/* 筛选工具栏 */}
        <FilterBar
          selectedCategory={selectedCategory}
          selectedMAStatus={selectedMAStatus}
          onCategoryChange={setSelectedCategory}
          onMAStatusChange={setSelectedMAStatus}
          totalCount={data.length}
          filteredCount={filteredData.length}
        />

        {/* 交易信号面板 */}
        <SignalPanel data={data} />

        {/* 主数据表格 */}
        {isLoading && data.length === 0 ? (
          <LoadingState />
        ) : (
          <div className="relative">
            {isLoading && (
              <div className="absolute top-2 right-2 z-30 flex items-center gap-1.5 px-2 py-1 bg-gray-900/90 border border-gray-700 rounded text-xs text-gray-400">
                <div className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-pulse" />
                正在拉取 AKShare 数据...
              </div>
            )}
            <FuturesTable data={filteredData} />
          </div>
        )}

        {/* 底部说明 */}
        <footer className="flex items-center justify-between text-[10px] text-gray-700 pt-2 border-t border-gray-800">
          <div className="flex gap-4">
            <span>数据源: AKShare 期货分钟行情</span>
            <span>周期: 30min K 线</span>
            <span>MA20/60 · MACD(12,26,9) · Vol·MA5 · OI·MA5</span>
          </div>
          <div className="flex gap-4">
            <LegendItem color="bg-red-500" label="上涨/上行/增仓" />
            <LegendItem color="bg-green-500" label="下跌/下行/减仓" />
            <LegendItem color="bg-gray-500" label="持平/静默" />
          </div>
        </footer>
      </div>
    </div>
  );
}

// 数据来源横幅
function DataSourceBanner({
  source,
  updatedAt,
}: {
  source: DataSource;
  updatedAt: string | null;
}) {
  // 格式化 ISO 时间为本地时间
  const fmtTime = (iso: string | null) => {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString("zh-CN", {
        month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit",
      });
    } catch { return ""; }
  };

  if (source === "github-actions") {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-emerald-950/50 border border-emerald-800/60 rounded text-xs text-emerald-400">
        <Database size={13} />
        <span className="font-semibold">实盘数据</span>
        <span className="text-emerald-600">
          — GitHub Actions 定时抓取 · 新浪财经接口
        </span>
        {updatedAt && (
          <span className="ml-auto text-emerald-700 font-mono">
            数据时间: {fmtTime(updatedAt)}
          </span>
        )}
      </div>
    );
  }

  if (source === "akshare") {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-emerald-950/50 border border-emerald-800/60 rounded text-xs text-emerald-400">
        <Database size={13} />
        <span className="font-semibold">实盘数据</span>
        <span className="text-emerald-600">— AKShare 本地服务已连接</span>
      </div>
    );
  }

  if (source === "mock") {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-amber-950/60 border border-amber-700 rounded text-xs text-amber-400">
        <WifiOff size={13} />
        <span className="font-semibold">模拟数据模式</span>
        <span className="text-amber-600 flex-1">
          — 未连接数据源，当前为演示用 Mock 数据
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 px-3 py-2 bg-gray-900 border border-gray-800 rounded text-xs text-gray-500">
      <div className="w-2 h-2 rounded-full bg-gray-600 animate-pulse" />
      正在加载数据...
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 10 }).map((_, i) => (
        <div
          key={i}
          className="h-12 bg-gray-900 rounded border border-gray-800 animate-pulse"
          style={{ opacity: 1 - i * 0.08 }}
        />
      ))}
    </div>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`w-2 h-2 rounded-full ${color}`} />
      {label}
    </span>
  );
}
