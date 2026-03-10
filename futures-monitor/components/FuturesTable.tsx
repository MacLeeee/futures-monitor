"use client";
// ============================================================
// 期货监控主表格组件
// 高信息密度 Data Table，Bloomberg/Wind 金融终端风格
// ============================================================

import React from "react";
import { FuturesStatus } from "@/lib/types";
import { MABadge, MACDBadge, VolumeBadge, OIBadge, PriceCell } from "./StatusBadge";

interface FuturesTableProps {
  data: FuturesStatus[];
}

// 板块颜色标记
const CATEGORY_COLORS: Record<string, string> = {
  贵金属: "border-l-yellow-500",
  有色:   "border-l-orange-500",
  黑色:   "border-l-gray-500",
  农产品: "border-l-lime-500",
  油脂:   "border-l-amber-500",
  能化:   "border-l-purple-500",
  建材:   "border-l-cyan-500",
  股指:   "border-l-blue-500",
};

const CATEGORY_TEXT: Record<string, string> = {
  贵金属: "text-yellow-400",
  有色:   "text-orange-400",
  黑色:   "text-gray-400",
  农产品: "text-lime-400",
  油脂:   "text-amber-400",
  能化:   "text-purple-400",
  建材:   "text-cyan-400",
  股指:   "text-blue-400",
};

// 表格列定义
const COLUMNS = [
  { key: "symbol",       label: "品种",    width: "w-28",  align: "text-left" },
  { key: "price",        label: "价格/涨跌", width: "w-28", align: "text-right" },
  { key: "ma",           label: "均线状态 (MA20/60)", width: "w-44", align: "text-left" },
  { key: "macd",         label: "MACD (12,26,9)",     width: "w-44", align: "text-left" },
  { key: "volume",       label: "成交量",  width: "w-36", align: "text-left" },
  { key: "openInterest", label: "持仓量",  width: "w-40", align: "text-left" },
  { key: "lastUpdate",   label: "更新",    width: "w-20", align: "text-right" },
];

export default function FuturesTable({ data }: FuturesTableProps) {
  // 按板块分组
  const grouped = React.useMemo(() => {
    const order = ["贵金属", "有色", "黑色", "农产品", "油脂", "能化", "建材", "股指"];
    const map: Record<string, FuturesStatus[]> = {};
    for (const item of data) {
      if (!map[item.category]) map[item.category] = [];
      map[item.category].push(item);
    }
    return order.map((cat) => ({ cat, items: map[cat] ?? [] })).filter((g) => g.items.length > 0);
  }, [data]);

  return (
    <div className="w-full overflow-x-auto rounded-lg border border-gray-800 shadow-2xl">
      <table className="w-full min-w-[900px] border-collapse">
        {/* 固定表头 */}
        <thead className="sticky top-0 z-20">
          <tr className="bg-gray-900 border-b border-gray-700">
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                className={`
                  px-3 py-2.5 text-[11px] font-semibold tracking-widest uppercase
                  text-gray-400 whitespace-nowrap
                  ${col.align} ${col.width}
                `}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {grouped.map(({ cat, items }) => (
            <React.Fragment key={cat}>
              {/* 板块分组标题行 */}
              <tr className="bg-gray-900/80 border-t border-gray-700/50">
                <td
                  colSpan={COLUMNS.length}
                  className={`px-3 py-1.5 text-xs font-bold tracking-wider ${CATEGORY_TEXT[cat] ?? "text-gray-400"}`}
                >
                  ▸ {cat}
                  <span className="ml-2 text-gray-600 font-normal">{items.length} 个品种</span>
                </td>
              </tr>

              {/* 品种数据行 */}
              {items.map((row, idx) => (
                <DataRow key={row.symbol} row={row} idx={idx} cat={cat} />
              ))}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// 单行组件（拆分减少渲染压力）
function DataRow({ row, idx, cat }: { row: FuturesStatus; idx: number; cat: string }) {
  const borderColor = CATEGORY_COLORS[cat] ?? "border-l-gray-700";

  return (
    <tr
      className={`
        border-b border-gray-800/60 transition-colors duration-150
        hover:bg-gray-800/40
        ${idx % 2 === 0 ? "bg-gray-950" : "bg-gray-900/30"}
      `}
    >
      {/* 品种名称 */}
      <td className={`px-3 py-2.5 border-l-2 ${borderColor}`}>
        <div className="font-semibold text-sm text-gray-100 whitespace-nowrap">
          {row.symbol}
        </div>
        <div className="text-[10px] text-gray-600 font-mono">30min</div>
      </td>

      {/* 价格 */}
      <td className="px-3 py-2.5">
        <PriceCell price={row.price} change={row.change} />
      </td>

      {/* 均线状态 */}
      <td className="px-3 py-2.5">
        <MABadge status={row.ma.status} cumulative={row.ma.cumulative} />
      </td>

      {/* MACD 状态 */}
      <td className="px-3 py-2.5">
        <MACDBadge
          crossStatus={row.macd.crossStatus}
          spreadStatus={row.macd.spreadStatus}
          cumulative={row.macd.cumulative}
        />
      </td>

      {/* 成交量 */}
      <td className="px-3 py-2.5">
        <VolumeBadge
          status={row.volume.status}
          cumulative={row.volume.cumulative}
          value={row.volume.value}
          change={row.volume.change}
          changePct={row.volume.changePct}
        />
      </td>

      {/* 持仓量 */}
      <td className="px-3 py-2.5">
        <OIBadge
          value={row.openInterest.value}
          prevValue={row.openInterest.prevValue}
          change={row.openInterest.change}
          changePct={row.openInterest.changePct}
          status={row.openInterest.status}
          cumulative={row.openInterest.cumulative}
        />
      </td>

      {/* 更新时间 */}
      <td className="px-3 py-2.5 text-right">
        <span className="text-[11px] font-mono text-gray-600">{row.lastUpdate}</span>
      </td>
    </tr>
  );
}
