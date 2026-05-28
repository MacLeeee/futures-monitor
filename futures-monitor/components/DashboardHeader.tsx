"use client";
// ============================================================
// 概览栏 — Redesign v2
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
  timeframe?: "30min" | "daily";
}

export default function DashboardHeader({
  data,
  lastRefresh,
  autoRefresh,
  onToggleAutoRefresh,
  onManualRefresh,
  isLoading,
  nextRefreshIn,
  timeframe = "30min",
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
    <div className="space-y-3">
      {/* 状态栏: 刷新 + 时钟 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-white rounded-md border border-gray-200">
            <Clock size={12} className="text-gray-500" />
            <span className="text-xs font-mono text-gray-500" suppressHydrationWarning>
              {now ? formatTime(now) : "--:--:--"}
            </span>
          </div>
          <span className="text-[10px] text-gray-400 font-mono" suppressHydrationWarning>
            更新于 {now ? formatTime(lastRefresh) : "--:--:--"}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {timeframe === "30min" && (
            <button
              onClick={onToggleAutoRefresh}
              className={`px-3 py-1.5 text-xs rounded-md font-medium transition-all ${
                autoRefresh
                  ? "bg-blue-50/90 text-blue-500 ring-1 ring-blue-300/50"
                  : "text-gray-400 hover:text-gray-500"
              }`}
            >
              {autoRefresh ? `● ${nextRefreshIn ?? "自动"}` : "○ 暂停"}
            </button>
          )}
          <button
            onClick={onManualRefresh}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-white border border-gray-200 rounded-md text-gray-500 hover:text-gray-900 hover:border-gray-300 transition-all disabled:opacity-50"
          >
            <RefreshCw size={11} className={isLoading ? "animate-spin" : ""} />
            刷新
          </button>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-6 gap-2">
        <StatCard label="均线上行" value={upCount} total={data.length} accent="emerald" Icon={TrendingUp} />
        <StatCard label="均线下行" value={downCount} total={data.length} accent="red" Icon={TrendingDown} />
        <StatCard label="均线静默" value={silentCount} total={data.length} accent="muted" Icon={Minus} />
        <StatCard label="放量品种" value={surgeCount} total={data.length} accent="amber" Icon={BarChart3} />
        <StatCard label="增仓品种" value={oiIncCount} total={data.length} accent="amber" Icon={TrendingUp} />
        <StatCard label="水上金叉" value={goldenCross} total={data.length} accent="sky" Icon={TrendingUp} />
      </div>
    </div>
  );
}

const ACCENT_MAP = {
  emerald: { text: "text-emerald-600", bg: "bg-emerald-400", cardBg: "bg-emerald-50/60" },
  red:    { text: "text-red-600",    bg: "bg-red-400",    cardBg: "bg-red-500/5" },
  amber:  { text: "text-blue-500",  bg: "bg-blue-500",  cardBg: "bg-blue-50/40" },
  sky:    { text: "text-sky-600",    bg: "bg-sky-400",    cardBg: "bg-sky-500/5" },
  muted:  { text: "text-gray-400",  bg: "bg-gray-400",  cardBg: "bg-white" },
};

function StatCard({
  label, value, total, accent, Icon,
}: {
  label: string; value: number; total: number; accent: keyof typeof ACCENT_MAP;
  Icon?: React.ElementType;
}) {
  const a = ACCENT_MAP[accent];
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;

  return (
    <div className={`rounded-lg px-3 py-2.5 border border-gray-200 shadow-sm ${a.cardBg} transition-colors hover:shadow-md`}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] text-gray-400 font-medium tracking-wide uppercase">{label}</span>
        {Icon && <Icon size={11} className={a.text} />}
      </div>
      <div className="flex items-baseline gap-1">
        <span className={`text-xl font-bold font-mono tracking-tight ${a.text}`}>{value}</span>
        <span className="text-gray-400 text-[10px] font-mono">/ {total}</span>
      </div>
      <div className="mt-2 h-0.5 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${a.bg} transition-all duration-700`}
          style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
