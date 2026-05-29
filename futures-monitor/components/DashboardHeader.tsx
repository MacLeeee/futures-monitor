"use client";
// ============================================================
// 概览栏 — v3 紧凑版：时钟 + 刷新 + 统计 pills
// ============================================================

import React, { useEffect, useState } from "react";
import { RefreshCw, Clock, TrendingUp, TrendingDown, Minus, BarChart3 } from "lucide-react";
import { FuturesStatus } from "@/lib/types";

interface DashboardHeaderProps {
  data: FuturesStatus[];
  lastRefresh: Date;
  autoRefresh: boolean;
  onToggleAutoRefresh: () => void;
  onManualRefresh: () => void;
  isLoading: boolean;
  nextRefreshIn: string | null;
}

export default function DashboardHeader({
  data,
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

  const upCount = data.filter((d) => d.ma.status === "Upward").length;
  const downCount = data.filter((d) => d.ma.status === "Downward").length;
  const silentCount = data.filter((d) => d.ma.status === "Silent").length;
  const surgeCount = data.filter((d) => d.volume.status === "Surge").length;
  const oiIncCount = data.filter((d) => d.openInterest.status === "Increasing").length;
  const goldenCross = data.filter((d) => d.macd.sign === "positive").length;

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

      {/* 统计 pills */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <StatPill label="上行" value={upCount} accent="emerald" Icon={TrendingUp} />
        <StatPill label="下行" value={downCount} accent="red" Icon={TrendingDown} />
        <StatPill label="静默" value={silentCount} accent="muted" Icon={Minus} />
        <span className="text-stone-200 mx-0.5">|</span>
        <StatPill label="放量" value={surgeCount} accent="amber" Icon={BarChart3} />
        <StatPill label="增仓" value={oiIncCount} accent="amber" />
        <StatPill label="金叉" value={goldenCross} accent="sky" />
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

const ACCENT = {
  emerald: "text-emerald-500 bg-emerald-50 border-emerald-200",
  red:     "text-red-500 bg-red-50 border-red-200",
  amber:   "text-amber-500 bg-amber-50 border-amber-200",
  sky:     "text-sky-500 bg-sky-50 border-sky-200",
  muted:   "text-stone-400 bg-stone-100 border-stone-200",
};

function StatPill({
  label, value, accent, Icon,
}: {
  label: string; value: number; accent: keyof typeof ACCENT;
  Icon?: React.ElementType;
}) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded border text-[10px] font-medium font-mono ${ACCENT[accent]}`}>
      {Icon && <Icon size={10} />}
      {label} <span className="font-bold">{value}</span>
    </span>
  );
}
