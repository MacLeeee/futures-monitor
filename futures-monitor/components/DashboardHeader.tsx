"use client";
// ============================================================
// Dashboard 头部组件 - 状态概览、刷新控制、市场时钟
// ============================================================

import React, { useEffect, useState } from "react";
import { Activity, RefreshCw, Clock, TrendingUp, TrendingDown, Minus, AlertTriangle, CheckCircle } from "lucide-react";
import { FuturesStatus, GapAlert, GapCheckInfo } from "@/lib/types";

interface DashboardHeaderProps {
  data: FuturesStatus[];
  gapAlerts: GapAlert[];
  gapCheckInfo: GapCheckInfo | null;
  lastRefresh: Date;
  autoRefresh: boolean;
  onToggleAutoRefresh: () => void;
  onManualRefresh: () => void;
  isLoading: boolean;
  nextRefreshIn: string | null;
}

export default function DashboardHeader({
  data,
  gapAlerts,
  gapCheckInfo,
  lastRefresh,
  autoRefresh,
  onToggleAutoRefresh,
  onManualRefresh,
  isLoading,
  nextRefreshIn,
}: DashboardHeaderProps) {
  // 初始值为 null，避免 SSR 与客户端水合时的时间不一致（Hydration mismatch）
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date()); // 仅在客户端挂载后才初始化
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // 统计各均线状态数量
  const upCount = data.filter((d) => d.ma.status === "Upward").length;
  const downCount = data.filter((d) => d.ma.status === "Downward").length;
  const silentCount = data.filter((d) => d.ma.status === "Silent").length;

  // 放量统计
  const surgeCount = data.filter((d) => d.volume.status === "Surge").length;
  // 增仓统计
  const oiIncCount = data.filter((d) => d.openInterest.status === "Increasing").length;
  // 金叉区品种（diff-dea > 0）
  const goldenCross = data.filter((d) => d.macd.sign === "positive").length;

  const formatTime = (d: Date) =>
    `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;

  return (
    <header className="flex flex-col gap-3 mb-4">
      {/* 开盘跳空横幅：有跳空时显示预警，无跳空但扫描过时显示确认 */}
      {gapAlerts.length > 0 ? (
        <div className="rounded-lg border border-yellow-600/60 bg-yellow-950/30 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-1.5 border-b border-yellow-700/40 bg-yellow-900/20">
            <AlertTriangle size={13} className="text-yellow-400 flex-shrink-0" />
            <span className="text-xs font-bold text-yellow-300">
              开盘跳空预警 · {gapAlerts[0].session}
            </span>
            <span className="text-[10px] text-yellow-700 ml-1">
              共 {gapAlerts.length} 个品种跳空幅度 ≥ 0.2%
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5 px-3 py-2">
            {gapAlerts.map((g) => {
              const isUp = g.direction === "up";
              return (
                <span
                  key={g.symbol}
                  className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-mono border ${
                    isUp
                      ? "text-red-300 bg-red-950/60 border-red-700/60"
                      : "text-green-300 bg-green-950/60 border-green-700/60"
                  }`}
                >
                  {isUp ? "↑" : "↓"}
                  <span className="font-semibold">{g.symbol}</span>
                  <span className={isUp ? "text-red-400" : "text-green-400"}>
                    {isUp ? "+" : ""}{g.gapPct.toFixed(2)}%
                  </span>
                  <span className="text-gray-600 text-[10px]">
                    开{g.openPrice} / 前收{g.prevClose}
                  </span>
                </span>
              );
            })}
          </div>
        </div>
      ) : gapCheckInfo ? (
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-700/50 bg-gray-900/40 text-xs text-gray-500">
          <CheckCircle size={12} className="text-gray-600 flex-shrink-0" />
          <span>
            <span className="text-gray-400 font-medium">{gapCheckInfo.session}</span>
            {" "}开盘跳空扫描完成
            <span className="ml-1 text-gray-600">({gapCheckInfo.checkedAt})</span>
            <span className="ml-2 text-gray-600">— 无显著跳空（阈值 0.2%）</span>
          </span>
        </div>
      ) : null}

      {/* 顶部标题栏 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Activity className="text-blue-400" size={20} />
            <h1 className="text-lg font-bold text-white tracking-tight">
              期货品种监控
              <span className="ml-2 text-xs font-normal text-gray-500 tracking-widest">
                FUTURES MONITOR · 30MIN
              </span>
            </h1>
          </div>
          {/* 实时时钟 */}
          <div className="flex items-center gap-1.5 px-3 py-1 bg-gray-900 border border-gray-700 rounded font-mono text-sm text-gray-300">
            <Clock size={13} className="text-gray-500" />
            {/* suppressHydrationWarning + 仅客户端渲染时钟，防止 SSR mismatch */}
            <span suppressHydrationWarning>
              {now ? formatTime(now) : "--:--:--"}
            </span>
          </div>
        </div>

        {/* 操作按钮组 */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-600 font-mono" suppressHydrationWarning>
            最后更新: {now ? formatTime(lastRefresh) : "--:--:--"}
          </span>
          <button
            onClick={onToggleAutoRefresh}
            className={`px-3 py-1.5 text-xs rounded border transition-all ${
              autoRefresh
                ? "bg-blue-900/60 border-blue-600 text-blue-300"
                : "bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500"
            }`}
          >
            {autoRefresh
              ? nextRefreshIn
                ? `● 自动刷新 ${nextRefreshIn}`
                : "● 自动刷新 30min"
              : "○ 自动刷新 30min"}
          </button>
          <button
            onClick={onManualRefresh}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-gray-800 border border-gray-700 rounded text-gray-300 hover:bg-gray-700 hover:border-gray-500 transition-all disabled:opacity-50"
          >
            <RefreshCw size={12} className={isLoading ? "animate-spin" : ""} />
            刷新
          </button>
        </div>
      </div>

      {/* 市场统计概览栏 */}
      <div className="grid grid-cols-6 gap-2">
        <StatCard
          label="均线上行"
          value={upCount}
          total={data.length}
          color="text-red-400"
          bg="bg-red-950/30 border-red-800/40"
          Icon={TrendingUp}
        />
        <StatCard
          label="均线下行"
          value={downCount}
          total={data.length}
          color="text-green-400"
          bg="bg-green-950/30 border-green-800/40"
          Icon={TrendingDown}
        />
        <StatCard
          label="均线静默"
          value={silentCount}
          total={data.length}
          color="text-gray-400"
          bg="bg-gray-800/50 border-gray-700/40"
          Icon={Minus}
        />
        <StatCard
          label="放量品种"
          value={surgeCount}
          total={data.length}
          color="text-orange-400"
          bg="bg-orange-950/30 border-orange-800/40"
        />
        <StatCard
          label="增仓品种"
          value={oiIncCount}
          total={data.length}
          color="text-amber-400"
          bg="bg-amber-950/30 border-amber-800/40"
        />
        <StatCard
          label="水上金叉"
          value={goldenCross}
          total={data.length}
          color="text-red-300"
          bg="bg-red-950/40 border-red-700/50"
        />
      </div>
    </header>
  );
}

function StatCard({
  label,
  value,
  total,
  color,
  bg,
  Icon,
}: {
  label: string;
  value: number;
  total: number;
  color: string;
  bg: string;
  Icon?: React.ElementType;
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className={`rounded border px-3 py-2 ${bg}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-gray-500 tracking-wide">{label}</span>
        {Icon && <Icon size={11} className={color} />}
      </div>
      <div className="flex items-baseline gap-1">
        <span className={`text-xl font-bold font-mono ${color}`}>{value}</span>
        <span className="text-gray-600 text-xs font-mono">/{total}</span>
      </div>
      {/* 进度条 */}
      <div className="mt-1.5 h-0.5 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color.replace("text-", "bg-")}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
