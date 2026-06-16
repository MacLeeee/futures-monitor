"use client";
// ============================================================
// 期货监控主表格 — 状态机视图 + 行内持仓
// ============================================================

import React from "react";
import { FuturesStatus, Position } from "@/lib/types";
import { PriceCell } from "./StatusBadge";

// ── 状态定义 ─────────────────────────────────────────────────

type PipelineState = "SIGNAL" | "PENDING" | "APPROACHING" | "TRENDING" | "IDLE";

interface SymbolState {
  level: PipelineState;
  label: string;
  detail: string;
  subDetail: string;
  borderClass: string;
  bgClass: string;
  textClass: string;
}

function computeState(
  row: FuturesStatus,
  pendingSet: Set<string>,
): SymbolState {
  const bo = row.breakoutSignal;
  const pb = row.pullbackSignal;
  const ma = row.ma;
  const macd = row.macd;
  const vol = row.volume;
  const oi = row.openInterest;
  const rg = row.marketRegime;

  // ── 优先级 1: 信号触发 ──
  if (bo || pb) {
    if (pb) {
      const isLong = pb.type === "long";
      const isSweep = pb.trigger === "sweep";
      const tetStr = pb.tet
        ? ` TET:ATS${pb.tet.ats.toFixed(1)} TI${pb.tet.ti.toFixed(1)}`
        : "";
      return {
        level: "SIGNAL",
        label: `${isLong ? "🔵" : "🟠"} 回踩${isLong ? "做多" : "做空"}`,
        detail: `${isSweep ? "⚡" : ""}${pb.trigger}@${pb.zone} entry=${pb.entry} SL=${pb.stopLoss} risk=${pb.riskPct}%`,
        subDetail: `pb${pb.quality.pbBars}K ret${pb.quality.retrace} vr${pb.quality.volRatio}${tetStr}`,
        borderClass: isLong ? "border-teal-200" : "border-orange-200",
        bgClass: isLong ? "bg-teal-50/50" : "bg-orange-50/50",
        textClass: isLong ? "text-teal-600" : "text-orange-600",
      };
    }
    if (bo) {
      const isLong = bo.type === "long";
      const extra = bo.level
        ? ` lv${bo.level}${bo.extAtr ? ` ext${bo.extAtr}` : ""}`
        : "";
      return {
        level: "SIGNAL",
        label: `${isLong ? "🔴" : "🟢"} 突破${isLong ? "做多" : "做空"}`,
        detail: `MA×${bo.maCumulative} MACD${bo.expansionRate.toFixed(1)}x${bo.oiConfirmed ? " +OI" : ""}${extra}`,
        subDetail: bo.boxBreakout ? "已破箱体" : "",
        borderClass: isLong ? "border-red-200" : "border-emerald-200",
        bgClass: isLong ? "bg-red-50/40" : "bg-emerald-50/40",
        textClass: isLong ? "text-red-600" : "text-emerald-600",
      };
    }
  }

  // ── 优先级 2: 突破待确认 ──
  if (pendingSet.has(row.symbol)) {
    return {
      level: "PENDING",
      label: "⚫ 突破待确认",
      detail: "等待 30m KD 冷却",
      subDetail: "最多12K",
      borderClass: "border-stone-300",
      bgClass: "bg-stone-100/50",
      textClass: "text-stone-500",
    };
  }

  // ── 优先级 3: 接近信号 ──
  const maOk = ma.status === "Upward" || ma.status === "Downward";
  const macdOk = macd.sign === (ma.status === "Upward" ? "positive" : "negative") && macd.rapidExpanding;
  const volOk = vol.status === "Surge";
  const oiOk = oi.status === "Increasing";
  const score = [maOk, macdOk, volOk, oiOk].filter(Boolean).length;

  if (score >= 3 && !bo) {
    const missing: string[] = [];
    if (!maOk) missing.push("MA");
    if (!macdOk) missing.push("MACD");
    if (!volOk) missing.push("量");
    if (!oiOk) missing.push("仓");
    const isLong = ma.status === "Upward";
    return {
      level: "APPROACHING",
      label: `🟡 接近${isLong ? "突破" : "跌破"}`,
      detail: `缺:${missing.join("/")}`,
      subDetail: `MA×${ma.cumulative} MACD×${macd.cumulative} ${vol.status === "Surge" ? "放量" : ""}`,
      borderClass: "border-amber-200",
      bgClass: "bg-amber-50/40",
      textClass: "text-amber-600",
    };
  }

  // ── 优先级 4: 趋势就绪 ──
  if (rg && rg.regime === "trending" && maOk) {
    const isBull = rg.direction === "bullish" || ma.status === "Upward";
    const emoji = isBull ? "🔵" : "🟠";
    const dirLabel = isBull ? "多头趋势" : "空头趋势";
    const macdStr = macd.sign === (isBull ? "positive" : "negative")
      ? (macd.rapidExpanding ? "MACD扩口" : "MACD同向")
      : "MACD背离";
    return {
      level: "TRENDING",
      label: `${emoji} ${dirLabel}`,
      detail: `MA×${ma.cumulative} ${macdStr}  (${rg.bullCount}/${rg.bearCount})`,
      subDetail: "等回踩结构",
      borderClass: isBull ? "border-blue-200" : "border-orange-200",
      bgClass: isBull ? "bg-blue-50/30" : "bg-orange-50/30",
      textClass: isBull ? "text-blue-600" : "text-orange-600",
    };
  }

  // ── 优先级 5: 观望 ──
  const rgLabel = rg
    ? (rg.regime === "ranging" ? "震荡" : `${rg.bullCount > rg.bearCount ? rg.bullCount : rg.bearCount}/3`)
    : "";
  return {
    level: "IDLE",
    label: "⬜ 观望",
    detail: rgLabel ? `${rgLabel} ${ma.status === "Silent" ? "均线静默" : ""}` : "无方向",
    subDetail: macd.sign === "positive" ? "MACD金叉" : macd.sign === "negative" ? "MACD死叉" : "",
    borderClass: "border-stone-200",
    bgClass: "bg-stone-50/30",
    textClass: "text-stone-400",
  };
}

// ── 表格列 ───────────────────────────────────────────────────

const COLUMNS = [
  { key: "symbol",   label: "品种",       width: "w-20",  align: "text-left" },
  { key: "price",    label: "价格/涨跌",   width: "w-24",  align: "text-right" },
  { key: "state",    label: "状态",       width: "flex-1", align: "text-left" },
  { key: "position", label: "持仓",       width: "w-36",  align: "text-left" },
  { key: "update",   label: "更新",       width: "w-14",  align: "text-right" },
];

// ── 板块色 ───────────────────────────────────────────────────

const CATEGORY_COLORS: Record<string, string> = {
  贵金属: "border-l-yellow-500",
  有色:   "border-l-orange-500",
  黑色:   "border-l-gray-500",
  农产品: "border-l-lime-500",
  油脂:   "border-l-yellow-500",
  能化:   "border-l-purple-500",
  建材:   "border-l-cyan-500",
  股指:   "border-l-blue-500",
};

const CATEGORY_TEXT: Record<string, string> = {
  贵金属: "text-yellow-600",
  有色:   "text-orange-600",
  黑色:   "text-stone-400",
  农产品: "text-lime-600",
  油脂:   "text-amber-500",
  能化:   "text-purple-600",
  建材:   "text-cyan-400",
  股指:   "text-amber-600",
};

// ── 组件 ─────────────────────────────────────────────────────

interface FuturesTableProps {
  data: FuturesStatus[];
  pendingSet: Set<string>;
  positions: Position[];
  currentPrices: Record<string, number>;
  seatMap: Record<string, { jia: string; inst: string; foreign: string; alert: boolean }>;
}

export default function FuturesTable({ data, pendingSet, positions, currentPrices, seatMap }: FuturesTableProps) {
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
    <div className="w-full overflow-x-auto rounded-lg border border-stone-200 shadow-sm">
      <table className="w-full min-w-[700px] border-collapse">
        <thead className="sticky top-0 z-20">
          <tr className="bg-white border-b border-stone-300">
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                className={`
                  px-3 py-2.5 text-[11px] font-semibold tracking-widest uppercase
                  text-stone-500 whitespace-nowrap
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
              <tr className="bg-white/90 border-t border-stone-200">
                <td
                  colSpan={COLUMNS.length}
                  className={`px-3 py-1.5 text-xs font-bold tracking-wider ${CATEGORY_TEXT[cat] ?? "text-stone-400"}`}
                >
                  ▸ {cat}
                  <span className="ml-2 text-stone-400 font-normal">{items.length} 个品种</span>
                </td>
              </tr>
              {items.map((row, idx) => (
                <DataRow
                  key={row.symbol}
                  row={row}
                  idx={idx}
                  cat={cat}
                  pendingSet={pendingSet}
                  position={positions.find((p) => p.symbol === row.symbol && p.status === "open")}
                  curPrice={currentPrices[row.symbol]}
                  seat={seatMap[row.symbol]}
                />
              ))}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── 单行 ─────────────────────────────────────────────────────

function DataRow({ row, idx, cat, pendingSet, position, curPrice, seat }: {
  row: FuturesStatus; idx: number; cat: string; pendingSet: Set<string>;
  position?: Position; curPrice?: number;
  seat?: { jia: string; inst: string; foreign: string; alert: boolean };
}) {
  const borderColor = CATEGORY_COLORS[cat] ?? "border-l-gray-700";
  const st = computeState(row, pendingSet);

  return (
    <tr
      className={`
        border-b border-stone-200 transition-colors duration-150
        hover:bg-stone-100
        ${idx % 2 === 0 ? "bg-white" : "bg-stone-50/60"}
        ${position ? "bg-amber-50/30" : ""}
      `}
    >
      {/* 品种 */}
      <td className={`px-3 py-2 border-l-2 ${borderColor}`}>
        <div className="font-semibold text-sm text-stone-900 whitespace-nowrap">
          {row.symbol}
        </div>
        <div className="text-[10px] text-stone-400 font-mono">30min</div>
      </td>

      {/* 价格 */}
      <td className="px-3 py-2">
        <PriceCell price={row.price} change={row.change} />
      </td>

      {/* 状态机 */}
      <td className="px-3 py-2">
        <div className={`rounded border ${st.borderClass} ${st.bgClass} px-2.5 py-1.5`}>
          <div className="flex items-center gap-1.5">
            <span className={`text-xs font-bold ${st.textClass}`}>{st.label}</span>
            {row.marketRegime?.action && (
              <span className="text-[9px] font-mono text-stone-500">
                📐{row.marketRegime.action}({row.marketRegime.bullCount}/{row.marketRegime.bearCount})
              </span>
            )}
          </div>
          <div className="text-[10px] text-stone-600 font-mono mt-0.5">{st.detail}</div>
          {st.subDetail && (
            <div className="text-[9px] text-stone-400 font-mono">{st.subDetail}</div>
          )}
          {seat && (seat.alert || position) && (
            <div className={`text-[8px] font-mono mt-0.5 flex items-center gap-1 ${seat.alert ? "text-amber-600" : "text-stone-300"}`}>
              {seat.alert && <span className="font-bold">⚡背离</span>}
              <span>家人{seat.jia || "–"}</span>
              <span className="text-stone-300">·</span>
              <span>机构{seat.inst || "–"}</span>
              <span className="text-stone-300">·</span>
              <span>外资{seat.foreign || "–"}</span>
            </div>
          )}
        </div>
      </td>

      {/* 持仓 */}
      <td className="px-2 py-2">
        {position ? (
          <PositionCell pos={position} curPrice={curPrice ?? position.entryPrice} />
        ) : (
          <span className="text-[10px] text-stone-300">—</span>
        )}
      </td>

      {/* 更新 */}
      <td className="px-2 py-2 text-right">
        <span className="text-[10px] font-mono text-stone-400">{row.lastUpdate}</span>
      </td>
    </tr>
  );
}

// ── 行内持仓 ─────────────────────────────────────────────────

function PositionCell({ pos, curPrice }: { pos: Position; curPrice: number }) {
  const isLong = pos.direction === "long";
  const pts = isLong ? curPrice - pos.entryPrice : pos.entryPrice - curPrice;
  const pnlPct = (pts / pos.entryPrice) * 100;
  const isProfit = pts >= 0;

  const dirEmoji = isLong ? "▲" : "▼";
  const dirColor = isLong ? "text-emerald-600" : "text-red-600";
  const pnlColor = isProfit ? "text-emerald-600" : "text-red-600";
  const pnlSign = isProfit ? "+" : "";

  // 止损状态
  let slTag = "";
  let slColor = "text-stone-400";
  if (pos.trailingActive) {
    slTag = "移动";
    slColor = "text-amber-500";
  } else if (pos.breakEvenMoved) {
    slTag = "保本";
    slColor = "text-sky-500";
  }

  return (
    <div className="rounded border border-amber-200/60 bg-amber-50/30 px-2 py-1">
      <div className="flex items-center gap-1 text-[10px]">
        <span className={`font-bold ${dirColor}`}>{dirEmoji}</span>
        <span className="text-stone-700 font-mono font-semibold">{pos.entryPrice.toFixed(1)}</span>
        <span className={`font-mono font-semibold ${pnlColor}`}>
          {pnlSign}{pnlPct.toFixed(2)}%
        </span>
      </div>
      <div className="flex items-center gap-1.5 text-[9px] text-stone-400 mt-0.5">
        <span>SL{pos.stopLoss.toFixed(1)}</span>
        {slTag && (
          <span className={`font-semibold ${slColor}`}>{slTag}</span>
        )}
        <span className="text-stone-300">|</span>
        <span className={pnlColor}>{pnlSign}{pts.toFixed(1)}pts</span>
      </div>
    </div>
  );
}
