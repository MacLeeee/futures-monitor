"use client";
// ============================================================
// 概览栏 — v4 状态分布版：时钟 + 状态计数 pills
// ============================================================

import React, { useEffect, useState } from "react";
import { RefreshCw, Clock } from "lucide-react";

interface StateCounts {
  signal: number;
  pending: number;
  approaching: number;
  trending: number;
  idle: number;
}

interface DashboardHeaderProps {
  stateCounts: StateCounts;
  lastRefresh: Date;
  autoRefresh: boolean;
  onToggleAutoRefresh: () => void;
  onManualRefresh: () => void;
  isLoading: boolean;
  nextRefreshIn: string | null;
}

export default function DashboardHeader({
  stateCounts,
  lastRefresh,
  autoRefresh,
  onToggleAutoRefresh,
  onManualRefresh,
  isLoading,
  nextRefreshIn,
}: DashboardHeaderProps) {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date());
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const formatTime = (d: Date) =>
    `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;

  return (
    <div className="flex items-center gap-3 flex-wrap">
      {/* 时钟 */}
      <div className="flex items-center gap-2 px-2.5 py-1.5 bg-white rounded-md border border-stone-200">
        <Clock size={12} className="text-stone-500" />
        <span className="text-xs font-mono text-stone-500" suppressHydrationWarning>
          {now ? formatTime(now) : "--:--:--"}
        </span>
      </div>

      {/* 状态分布 pills */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <StatePill label="🎯 信号" value={stateCounts.signal} active={stateCounts.signal > 0}
          activeClass="bg-amber-100 border-amber-400 text-amber-700" />
        <StatePill label="⚫ 冷却" value={stateCounts.pending} active={stateCounts.pending > 0}
          activeClass="bg-stone-200 border-stone-500 text-stone-700" />
        <StatePill label="🟡 接近" value={stateCounts.approaching} active={stateCounts.approaching > 0}
          activeClass="bg-amber-50 border-amber-300 text-amber-600" />
        <StatePill label="🔵 趋势" value={stateCounts.trending} active={stateCounts.trending > 0}
          activeClass="bg-blue-50 border-blue-300 text-blue-600" />
        <StatePill label="⬜ 观望" value={stateCounts.idle} />
      </div>

      {/* 右侧：更新信息 + 刷新按钮 */}
      <div className="flex-1" />
      <span className="text-[10px] text-stone-400 font-mono" suppressHydrationWarning>
        更新 {now ? formatTime(lastRefresh) : "--:--:--"}
      </span>
      <button
        onClick={onToggleAutoRefresh}
        className={`px-2.5 py-1 text-[10px] rounded-md font-medium transition-all ${
          autoRefresh
            ? "bg-amber-50/90 text-amber-500 ring-1 ring-amber-300/50"
            : "text-stone-400 hover:text-stone-500"
        }`}
      >
        {autoRefresh ? `● ${nextRefreshIn ?? ""}` : "○ 暂停"}
      </button>
      <button
        onClick={onManualRefresh}
        disabled={isLoading}
        className="flex items-center gap-1 px-2.5 py-1 text-[10px] bg-white border border-stone-200 rounded-md text-stone-500 hover:text-stone-900 hover:border-stone-300 transition-all disabled:opacity-50"
      >
        <RefreshCw size={10} className={isLoading ? "animate-spin" : ""} />
        刷新
      </button>
    </div>
  );
}

function StatePill({
  label, value, active, activeClass,
}: {
  label: string; value: number; active?: boolean;
  activeClass?: string;
}) {
  const isActive = active && value > 0;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded border text-[10px] font-medium font-mono transition-all ${
      isActive
        ? activeClass
        : "text-stone-300 bg-stone-50 border-stone-200"
    }`}>
      {label} <span className="font-bold">{value}</span>
    </span>
  );
}
