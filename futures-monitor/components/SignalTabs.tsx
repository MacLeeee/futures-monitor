"use client";
// ============================================================
// 统一信号面板 — 突破 / 回踩 Tab 切换
// 无信号时自动隐藏
// ============================================================

import React, { useState } from "react";
import { FuturesStatus } from "@/lib/types";
import { Zap, ArrowDownToLine } from "lucide-react";
import BreakoutContent from "./BreakoutContent";
import PullbackContent from "./PullbackContent";

interface SignalTabsProps { data: FuturesStatus[] }

export default function SignalTabs({ data }: SignalTabsProps) {
  const [tab, setTab] = useState<"breakout" | "pullback">("breakout");

  // 计算各 tab 的信号数量
  const breakoutCount = data.filter((d) => d.breakoutSignal != null).length;
  const pullbackCount = data.filter((d) => d.pullbackSignal != null).length;
  const total = breakoutCount + pullbackCount;
  const nearBreakout = data.filter(
    (d) => !d.breakoutSignal &&
      ((d.ma.status === "Upward" && d.macd.sign === "positive" && d.macd.rapidExpanding && d.volume.status === "Surge") ||
       (d.ma.status === "Downward" && d.macd.sign === "negative" && d.macd.rapidExpanding && d.volume.status === "Surge"))
  ).length;

  // 零信号且无待观察 → 自动隐藏整个面板
  if (total === 0 && nearBreakout === 0 && pullbackCount === 0) return null;

  // 如果当前 tab 没内容但另一个有，自动切换
  const hasBreakout = breakoutCount > 0 || nearBreakout > 0;
  const hasPullback = pullbackCount > 0;

  return (
    <div className="rounded-lg border border-stone-200 bg-white">
      {/* Tab 栏 */}
      <div className="flex border-b border-stone-200">
        <button
          onClick={() => setTab("breakout")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium transition-colors border-b-2 -mb-px ${
            tab === "breakout"
              ? "border-amber-500 text-amber-600"
              : "border-transparent text-stone-400 hover:text-stone-600"
          }`}
        >
          <Zap size={12} />
          突破信号
          {breakoutCount > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-amber-100 text-amber-600 font-bold">
              {breakoutCount}
            </span>
          )}
        </button>
        <button
          onClick={() => setTab("pullback")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium transition-colors border-b-2 -mb-px ${
            tab === "pullback"
              ? "border-teal-500 text-teal-600"
              : "border-transparent text-stone-400 hover:text-stone-600"
          }`}
        >
          <ArrowDownToLine size={12} />
          回踩信号
          {pullbackCount > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-teal-100 text-teal-600 font-bold">
              {pullbackCount}
            </span>
          )}
        </button>
      </div>

      {/* Tab 内容 */}
      <div className="p-4">
        {tab === "breakout" ? (
          hasBreakout ? (
            <BreakoutContent data={data} />
          ) : (
            <p className="text-xs text-stone-400 py-4 text-center">暂无突破信号</p>
          )
        ) : (
          hasPullback ? (
            <PullbackContent data={data} />
          ) : (
            <p className="text-xs text-stone-400 py-4 text-center">暂无回踩信号</p>
          )
        )}
      </div>
    </div>
  );
}
