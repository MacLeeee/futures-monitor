"use client";
// ============================================================
// 状态徽章组件 - 统一的状态颜色与标签渲染
// 色彩规范：上涨=红色, 下跌=绿色, 持平=灰色（中国金融惯例）
// ============================================================

import React from "react";
import { TrendingUp, TrendingDown, Minus, Zap, ZapOff, ArrowUpCircle, ArrowDownCircle } from "lucide-react";

// ---------- 均线状态 ----------
export function MABadge({ status, cumulative }: { status: string; cumulative: number }) {
  const cfg = {
    Upward:   { label: "上行", color: "text-red-600",   bg: "bg-red-50",   border: "border-red-200",   Icon: TrendingUp },
    Downward: { label: "下行", color: "text-emerald-600", bg: "bg-emerald-50", border: "border-emerald-200", Icon: TrendingDown },
    Silent:   { label: "静默", color: "text-gray-400",  bg: "bg-gray-100",  border: "border-gray-300",  Icon: Minus },
  }[status] ?? { label: status, color: "text-gray-400", bg: "bg-gray-100", border: "border-gray-300", Icon: Minus };

  const { label, color, bg, border, Icon } = cfg;

  return (
    <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium border ${bg} ${border} ${color}`}>
      <Icon size={11} />
      <span>{label}</span>
      <span className="text-gray-500 font-mono">×{cumulative}</span>
    </div>
  );
}

// ---------- MACD 状态 ----------
export function MACDBadge({
  sign,
  rapidExpanding,
  expansionRate,
  cumulative,
}: {
  sign: string;           // "positive" = 金叉区, "negative" = 死叉区
  rapidExpanding: boolean;
  expansionRate: number;  // 走扩倍率
  cumulative: number;
}) {
  const isPositive = sign === "positive";

  // 方向标签样式
  const signCfg = isPositive
    ? { label: "金叉区", color: "text-red-700",   bg: "bg-red-50/90",   border: "border-red-300" }
    : { label: "死叉区", color: "text-emerald-700", bg: "bg-emerald-50/90", border: "border-green-700" };

  // 走扩/粘合颜色：走扩=橙色高亮，粘合=天蓝
  const expandColor = rapidExpanding ? "text-blue-500" : "text-sky-600";
  const expandLabel = rapidExpanding ? "走扩" : "粘合";

  return (
    <div className="flex flex-col gap-0.5">
      {/* 方向标签 + 连续根数 */}
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold border ${signCfg.bg} ${signCfg.border} ${signCfg.color}`}>
        {isPositive ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
        {signCfg.label}
        <span className="text-gray-500 font-mono font-normal">×{cumulative}</span>
      </span>

      {/* 走扩状态 + 倍率 */}
      <span className={`inline-flex items-center gap-1 text-xs font-mono ${expandColor}`}>
        {rapidExpanding ? <Zap size={10} /> : <ZapOff size={10} />}
        {expandLabel}
        {expansionRate > 0 && (
          <span className="text-gray-500 text-[10px]">
            {expansionRate.toFixed(1)}x
          </span>
        )}
      </span>
    </div>
  );
}

// ---------- 成交量状态（环比上一根 K 线） ----------
export function VolumeBadge({
  status,
  cumulative,
  value = 0,
  change = 0,
  changePct = 0,
}: {
  status: string;
  cumulative: number;
  value?: number;
  change?: number;
  changePct?: number;
}) {
  const isSurge = status === "Surge";

  const fmtVol = (v: number) => {
    if (v == null || isNaN(v)) return "--";
    if (Math.abs(v) >= 10000) return `${(v / 10000).toFixed(1)}万`;
    return v.toLocaleString();
  };

  const pctSign = (change ?? 0) > 0 ? "+" : "";
  const absPct = Math.abs(changePct ?? 0);
  const pctColor = isSurge ? "text-orange-600" : "text-sky-600";

  return (
    <div className="flex flex-col gap-0.5">
      {/* 状态标签 + 连续计数 */}
      <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium border ${
        isSurge
          ? "text-orange-600 bg-orange-50 border-orange-200"
          : "text-sky-600 bg-sky-50 border-sky-200"
      }`}>
        {isSurge ? <ArrowUpCircle size={11} /> : <ArrowDownCircle size={11} />}
        <span>{isSurge ? "放量" : "缩量"}</span>
        <span className="text-gray-500 font-mono">×{cumulative}</span>
      </span>

      {/* 环比幅度 */}
      <div className="flex items-center gap-1.5 pl-1">
        <span className={`font-mono text-[11px] font-semibold ${pctColor}`}>
          {pctSign}{absPct.toFixed(1)}%
        </span>
        <span className="text-gray-400 font-mono text-[10px]">
          ({pctSign}{fmtVol(change ?? 0)})
        </span>
      </div>
    </div>
  );
}

// ---------- 持仓量状态（环比上一根 K 线） ----------
export function OIBadge({
  value = 0,
  prevValue = 0,
  change = 0,
  changePct = 0,
  status,
  cumulative,
}: {
  value?: number;
  prevValue?: number;
  change?: number;
  changePct?: number;
  status: string;
  cumulative: number;
}) {
  const isInc = status === "Increasing";

  // 格式化持仓量显示（万手），防御 undefined/NaN
  const fmtOI = (v: number) => {
    if (v == null || isNaN(v)) return "--";
    return Math.abs(v) >= 10000
      ? `${(v / 10000).toFixed(2)}万`
      : v.toLocaleString();
  };

  // 变化幅度颜色：增仓红，减仓绿
  const pctColor = isInc ? "text-red-600" : "text-emerald-600";
  const pctSign = (change ?? 0) > 0 ? "+" : "";
  const absPct = Math.abs(changePct ?? 0);

  return (
    <div className="flex flex-col gap-0.5">
      {/* 状态标签 + 连续计数 */}
      <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium border ${
        isInc
          ? "text-red-600 bg-red-50 border-red-200"
          : "text-emerald-600 bg-emerald-50 border-emerald-200"
      }`}>
        {isInc ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
        <span>{isInc ? "增仓" : "减仓"}</span>
        <span className="text-gray-500 font-mono">×{cumulative}</span>
      </span>

      {/* 环比幅度：变化量 + 百分比 */}
      <div className="flex items-center gap-1.5 pl-1">
        <span className={`font-mono text-[11px] font-semibold ${pctColor}`}>
          {pctSign}{absPct.toFixed(2)}%
        </span>
        <span className="text-gray-400 font-mono text-[10px]">
          ({pctSign}{fmtOI(change)})
        </span>
      </div>

      {/* 当前持仓量 */}
      <span className="text-gray-400 font-mono text-[10px] pl-1">
        持仓 {fmtOI(value)}手
      </span>
    </div>
  );
}

// ---------- 价格涨跌 ----------
export function PriceCell({ price, change }: { price: number; change: number }) {
  const isUp = change > 0;
  const isDown = change < 0;
  const color = isUp ? "text-red-600" : isDown ? "text-emerald-600" : "text-gray-400";

  return (
    <div className="text-right">
      <div className={`font-mono font-semibold text-sm ${color}`}>
        {price.toLocaleString("zh-CN")}
      </div>
      <div className={`font-mono text-xs ${color}`}>
        {isUp ? "+" : ""}{change.toFixed(2)}%
      </div>
    </div>
  );
}
