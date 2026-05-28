"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Position, PositionsData, PositionStatus } from "@/lib/types";

// ══════════════════════════════════════════════════════════════
// 合约规格表  [乘数, 保证金率, 单位, tick大小]
// ══════════════════════════════════════════════════════════════
const SPECS: Record<string, [number, number, string, number]> = {
  // SHFE
  "黄金":     [1000, 0.07, "克",  0.01],
  "白银":     [15,   0.07, "kg",  1.0 ],
  "铜":       [5,    0.10, "吨",  10.0],
  "铝":       [5,    0.08, "吨",  5.0 ],
  "锌":       [5,    0.08, "吨",  5.0 ],
  "锡":       [1,    0.10, "吨",  10.0],
  "镍":       [1,    0.10, "吨",  10.0],
  "螺纹钢":   [10,   0.07, "吨",  1.0 ],
  "橡胶":     [10,   0.09, "吨",  5.0 ],
  "合成橡胶": [5,    0.09, "吨",  5.0 ],
  "燃油":     [10,   0.10, "吨",  1.0 ],
  "低硫燃油": [10,   0.10, "吨",  1.0 ],
  // DCE
  "豆粕":     [10,   0.07, "吨",  1.0 ],
  "豆油":     [10,   0.07, "吨",  2.0 ],
  "棕榈油":   [10,   0.07, "吨",  2.0 ],
  "玉米":     [10,   0.05, "吨",  1.0 ],
  "铁矿石":   [100,  0.08, "吨",  0.5 ],
  "焦煤":     [60,   0.10, "吨",  0.5 ],
  "焦炭":     [100,  0.10, "吨",  0.5 ],
  "乙二醇":   [10,   0.08, "吨",  1.0 ],
  "苯乙烯":   [5,    0.08, "吨",  1.0 ],
  "生猪":     [16,   0.10, "吨",  5.0 ],
  // ZCE
  "白糖":     [10,   0.07, "吨",  1.0 ],
  "菜粕":     [10,   0.07, "吨",  1.0 ],
  "菜油":     [10,   0.07, "吨",  1.0 ],
  "纯碱":     [20,   0.08, "吨",  1.0 ],
  "锰硅":     [5,    0.10, "吨",  2.0 ],
  "硅铁":     [5,    0.10, "吨",  2.0 ],
  "甲醇":     [10,   0.07, "吨",  1.0 ],
  "对二甲苯": [5,    0.08, "吨",  2.0 ],
  "玻璃":     [20,   0.08, "吨",  1.0 ],
  "棉花":     [5,    0.07, "吨",  5.0 ],
  // INE
  "原油":     [1000, 0.10, "桶",  0.1 ],
  // GFEX
  "碳酸锂":   [1,    0.10, "吨",  50.0],
};

function getSpec(symbol: string): [number, number, string, number] {
  return SPECS[symbol] ?? [1, 0.10, "手", 1.0];
}

// ══════════════════════════════════════════════════════════════
// 账户参数
// ══════════════════════════════════════════════════════════════
const INITIAL_CAPITAL = 10_000_000;   // 1000万
const MARGIN_PER_TRADE = 200_000;     // 每笔保证金 20万（2%）
const EXCLUDE_IDS = new Set(["纯碱-L-20260407214545"]); // 数据异常

export interface TradeMetrics {
  pos: Position;
  mult: number;
  mgnRate: number;
  unit: string;
  tickVal: number;       // 元/tick/手 = tickSize × multiplier
  marginPerLot: number;  // 元/手
  lots: number;          // 实际手数
  marginUsed: number;    // 元
  pnlPerLot: number;     // 元/手（本次）
  pnlRmb: number;        // 元（本次）
  navAfter: number;      // 净值（累计）
  accountAfter: number;  // 账户余额（元）
  chgPct: number;        // 本次账户变动 %
}

function computeMetrics(positions: Position[]): {
  rows: TradeMetrics[];
  navPoints: number[];   // 含起点1.0
  ddPoints: number[];    // 回撤序列（%）
  finalNav: number;
  maxDd: number;
  wins: number;
  losses: number;
  totalPnl: number;
  avgWin: number;
  avgLoss: number;
} {
  const closed = positions
    .filter(
      (p) =>
        p.status !== "open" &&
        p.pnl !== null &&
        p.riskDist !== null &&
        p.riskDist !== 0 &&
        !EXCLUDE_IDS.has(p.id)
    )
    .sort((a, b) => (a.exitTime ?? "").localeCompare(b.exitTime ?? ""));

  let account = INITIAL_CAPITAL;
  const rows: TradeMetrics[] = [];
  const navPoints = [1.0];

  for (const pos of closed) {
    const [mult, mgnRate, unit, tickSz] = getSpec(pos.symbol);
    const marginPerLot = pos.entryPrice * mult * mgnRate;
    const lots = Math.max(1, Math.floor(MARGIN_PER_TRADE / marginPerLot));
    const marginUsed = lots * marginPerLot;
    const tickVal = tickSz * mult;
    const pnlPerLot = (pos.pnl ?? 0) * mult;
    const pnlRmb = pnlPerLot * lots;
    const prev = account;
    account += pnlRmb;
    const navAfter = account / INITIAL_CAPITAL;
    navPoints.push(navAfter);
    rows.push({
      pos,
      mult,
      mgnRate,
      unit,
      tickVal,
      marginPerLot,
      lots,
      marginUsed,
      pnlPerLot,
      pnlRmb,
      navAfter,
      accountAfter: account,
      chgPct: (pnlRmb / prev) * 100,
    });
  }

  // 回撤序列
  let peak = 1.0;
  let maxDd = 0;
  const ddPoints = navPoints.map((v) => {
    peak = Math.max(peak, v);
    const dd = ((v - peak) / peak) * 100;
    maxDd = Math.min(maxDd, dd);
    return dd;
  });

  const wRows = rows.filter((r) => r.pnlRmb > 0);
  const lRows = rows.filter((r) => r.pnlRmb < 0);
  const totalPnl = rows.reduce((s, r) => s + r.pnlRmb, 0);
  const avgWin  = wRows.length ? wRows.reduce((s, r) => s + r.pnlRmb, 0) / wRows.length : 0;
  const avgLoss = lRows.length ? lRows.reduce((s, r) => s + r.pnlRmb, 0) / lRows.length : 0;

  return {
    rows,
    navPoints,
    ddPoints,
    finalNav: account / INITIAL_CAPITAL,
    maxDd,
    wins: wRows.length,
    losses: lRows.length,
    totalPnl,
    avgWin,
    avgLoss,
  };
}

// ══════════════════════════════════════════════════════════════
// 净值曲线 SVG 组件
// ══════════════════════════════════════════════════════════════
function NavChart({
  navPoints,
  ddPoints,
  tradeRows,
}: {
  navPoints: number[];
  ddPoints: number[];
  tradeRows: TradeMetrics[];
}) {
  const W = 900, H_NAV = 220, H_DD = 60, PAD = { l: 60, r: 20, t: 18, b: 8 };
  const innerW = W - PAD.l - PAD.r;

  // 净值坐标变换
  const yMin = Math.min(...navPoints) * 0.999;
  const yMax = Math.max(...navPoints) * 1.001;
  const n = navPoints.length;

  const xScale = (i: number) => PAD.l + (i / (n - 1)) * innerW;
  const yScale = (v: number) =>
    PAD.t + ((yMax - v) / (yMax - yMin)) * (H_NAV - PAD.t - PAD.b);

  // 折线 path
  const linePath = navPoints
    .map((v, i) => `${i === 0 ? "M" : "L"}${xScale(i).toFixed(1)},${yScale(v).toFixed(1)}`)
    .join(" ");

  // 区域 path（填充）
  const baseline = yScale(1.0);
  const areaPath =
    linePath +
    ` L${xScale(n - 1).toFixed(1)},${baseline} L${xScale(0).toFixed(1)},${baseline} Z`;

  // 回撤
  const ddMin = Math.min(...ddPoints) * 1.1;
  const ddH = H_DD - 12;
  const ddY = (v: number) =>
    H_NAV + 4 + ((0 - v) / (0 - ddMin)) * ddH;

  const ddPath = ddPoints
    .map((v, i) => `${i === 0 ? "M" : "L"}${xScale(i).toFixed(1)},${ddY(v).toFixed(1)}`)
    .join(" ");
  const ddArea =
    ddPath +
    ` L${xScale(n - 1).toFixed(1)},${ddY(0)} L${xScale(0).toFixed(1)},${ddY(0)} Z`;

  // Y 轴刻度（净值）
  const yTicks = 5;
  const yStep = (yMax - yMin) / (yTicks - 1);
  const yTickVals = Array.from({ length: yTicks }, (_, i) => yMin + i * yStep).reverse();

  // 最大回撤位置
  const maxDdIdx = ddPoints.indexOf(Math.min(...ddPoints));

  return (
    <svg
      viewBox={`0 0 ${W} ${H_NAV + H_DD + 20}`}
      className="w-full"
      style={{ fontFamily: "inherit" }}
    >
      {/* 背景 */}
      <rect width={W} height={H_NAV + H_DD + 20} fill="none" />

      {/* 水平网格 */}
      {yTickVals.map((v) => (
        <g key={v}>
          <line
            x1={PAD.l} y1={yScale(v)} x2={W - PAD.r} y2={yScale(v)}
            stroke="#1c2535" strokeWidth="0.8"
          />
          <text
            x={PAD.l - 6} y={yScale(v)} textAnchor="end" dominantBaseline="middle"
            fill="#4a5a74" fontSize="10"
          >
            {v.toFixed(3)}
          </text>
        </g>
      ))}

      {/* 基准线 1.0 */}
      <line
        x1={PAD.l} y1={yScale(1.0)} x2={W - PAD.r} y2={yScale(1.0)}
        stroke="#253050" strokeWidth="1.2" strokeDasharray="4 3"
      />
      <text x={PAD.l - 6} y={yScale(1.0)} textAnchor="end" dominantBaseline="middle"
        fill="#344566" fontSize="10">1.000</text>

      {/* 净值填充区 */}
      <defs>
        <linearGradient id="navGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#26d981" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#26d981" stopOpacity="0.02" />
        </linearGradient>
        <linearGradient id="navGradDn" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#f15b63" stopOpacity="0.02" />
          <stop offset="100%" stopColor="#f15b63" stopOpacity="0.15" />
        </linearGradient>
        <clipPath id="aboveBaseline">
          <rect x={PAD.l} y={PAD.t} width={innerW} height={yScale(1.0) - PAD.t} />
        </clipPath>
        <clipPath id="belowBaseline">
          <rect x={PAD.l} y={yScale(1.0)} width={innerW} height={H_NAV - yScale(1.0)} />
        </clipPath>
      </defs>

      <path d={areaPath} fill="url(#navGrad)" clipPath="url(#aboveBaseline)" />
      <path d={areaPath} fill="url(#navGradDn)" clipPath="url(#belowBaseline)" />

      {/* 净值折线 */}
      <path d={linePath} fill="none" stroke="#4fc8e8" strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round" />

      {/* 交易点 */}
      {tradeRows.map((r, i) => (
        <circle
          key={r.pos.id}
          cx={xScale(i + 1)} cy={yScale(r.navAfter)}
          r="3.5"
          fill={r.pnlRmb >= 0 ? "#26d981" : "#f15b63"}
          stroke="none"
        />
      ))}

      {/* 最终净值标注 */}
      <text
        x={xScale(n - 1) + 4} y={yScale(navPoints[n - 1])}
        fill="#4fc8e8" fontSize="11" dominantBaseline="middle"
      >
        {navPoints[n - 1].toFixed(4)}
      </text>

      {/* 净值 Y 轴标签 */}
      <text
        x={8} y={(H_NAV) / 2} fill="#4a5a74" fontSize="10"
        transform={`rotate(-90, 8, ${H_NAV / 2})`} textAnchor="middle"
      >
        净值
      </text>

      {/* ── 回撤带 ─────────────────────────── */}
      <rect x={PAD.l} y={H_NAV + 4} width={innerW} height={H_DD - 4}
        fill="#10141c" />
      <path d={ddArea} fill="#f15b63" fillOpacity="0.35" />
      <path d={ddPath} fill="none" stroke="#f15b63" strokeWidth="1"
        strokeLinejoin="round" />
      {/* 0 线 */}
      <line x1={PAD.l} y1={ddY(0)} x2={W - PAD.r} y2={ddY(0)}
        stroke="#253050" strokeWidth="0.8" />

      {/* 最大回撤标注 */}
      {maxDdIdx > 0 && (
        <text
          x={xScale(maxDdIdx)} y={ddY(ddPoints[maxDdIdx]) - 4}
          fill="#f15b63" fontSize="9.5" textAnchor="middle"
        >
          {ddPoints[maxDdIdx].toFixed(2)}%
        </text>
      )}

      {/* 回撤 Y 轴 */}
      <text x={8} y={H_NAV + 4 + H_DD / 2} fill="#4a5a74" fontSize="10"
        transform={`rotate(-90, 8, ${H_NAV + 4 + H_DD / 2})`} textAnchor="middle">
        回撤
      </text>
    </svg>
  );
}

// ══════════════════════════════════════════════════════════════
// 数据加载
// ══════════════════════════════════════════════════════════════
const GITHUB_RAW =
  "https://raw.githubusercontent.com/MacLeeee/futures-monitor/main/futures-monitor/public";

const STATUS_LABEL: Record<PositionStatus, string> = {
  open:      "持仓中",
  closed_sl: "止损",
  closed_tp: "止盈",
};
const STATUS_COLOR: Record<PositionStatus, string> = {
  open:      "text-sky-600 bg-sky-900/30",
  closed_sl: "text-red-600 bg-red-900/30",
  closed_tp: "text-emerald-600 bg-emerald-900/30",
};
const DIR_LABEL: Record<string, string> = { long: "多 ▲", short: "空 ▼" };
const DIR_COLOR: Record<string, string> = {
  long:  "text-emerald-600",
  short: "text-red-600",
};
const SIG_LABEL: Record<string, string> = {
  breakout: "突破",
  pullback: "回踩",
  box:      "箱体",
};

type FilterStatus = "all" | PositionStatus;
type FilterDir    = "all" | "long" | "short";

// ══════════════════════════════════════════════════════════════
// 主组件
// ══════════════════════════════════════════════════════════════
export default function TradeLog() {
  const [data,        setData]        = useState<PositionsData | null>(null);
  const [loading,     setLoading]     = useState(true);
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [filterDir,    setFilterDir]    = useState<FilterDir>("all");
  const [updatedAt,    setUpdatedAt]    = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const isLocal = typeof window !== "undefined" && window.location.port !== "";
      const url = isLocal
        ? `/positions.json?t=${Date.now()}`
        : `${GITHUB_RAW}/positions.json?t=${Date.now()}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(15000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: PositionsData = await res.json();
      setData(json);
      if (json.updatedAt) {
        const d = new Date(json.updatedAt);
        setUpdatedAt(
          d.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false })
        );
      }
    } catch (e) {
      console.error("[TradeLog] 加载失败:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const positions = data?.positions ?? [];

  // 账户级指标（全量已平仓）
  const metrics = useMemo(() => computeMetrics(positions), [positions]);

  // 开仓中持仓（含规格信息，仅显示用）
  const openPositions = useMemo(
    () =>
      positions
        .filter((p) => p.status === "open")
        .sort((a, b) => b.entryTime.localeCompare(a.entryTime)),
    [positions]
  );

  // 构建 id → metrics 映射，方便表格查找
  const metricsMap = useMemo(
    () => new Map(metrics.rows.map((r) => [r.pos.id, r])),
    [metrics.rows]
  );

  // 过滤后的已平仓列表（保持按退出时间倒序）
  const filteredClosed = useMemo(() => {
    return [...metrics.rows]
      .reverse()
      .filter((r) => {
        if (filterStatus !== "all" && r.pos.status !== filterStatus) return false;
        if (filterDir    !== "all" && r.pos.direction !== filterDir)  return false;
        return true;
      });
  }, [metrics.rows, filterStatus, filterDir]);

  const winRate = metrics.wins + metrics.losses > 0
    ? ((metrics.wins / (metrics.wins + metrics.losses)) * 100).toFixed(1)
    : "—";
  const pr = metrics.avgLoss !== 0
    ? Math.abs(metrics.avgWin / metrics.avgLoss).toFixed(2)
    : "—";

  return (
    <div className="min-h-screen bg-[#10141c] text-gray-800 p-4 md:p-6 lg:p-8">
      {/* 顶部导航 */}
      <div className="mb-6 flex items-center gap-4">
        <a href="/" className="text-gray-400 hover:text-gray-400 text-sm transition-colors">
          ← 返回监控
        </a>
        <h1 className="text-xl font-bold text-gray-900">📒 交易记录</h1>
        <span className="ml-auto text-xs text-gray-400">
          初始1000万 · 每笔保证金20万
        </span>
      </div>

      {/* ── 统计卡片 ─────────────────────────────────────── */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
        <StatCard label="最终净值"
          value={metrics.rows.length ? metrics.finalNav.toFixed(4) : "—"}
          sub={metrics.rows.length ? `${((metrics.finalNav - 1) * 100) >= 0 ? "+" : ""}${((metrics.finalNav - 1) * 100).toFixed(2)}%` : ""}
          color={metrics.finalNav >= 1 ? "emerald" : "red"} />
        <StatCard label="账户资产"
          value={metrics.rows.length ? `${(metrics.rows[metrics.rows.length - 1].accountAfter / 10000).toFixed(1)}万` : "1000万"}
          color="sky" />
        <StatCard label="累计盈亏"
          value={metrics.rows.length ? `${metrics.totalPnl >= 0 ? "+" : ""}${(metrics.totalPnl / 10000).toFixed(1)}万` : "—"}
          color={metrics.totalPnl >= 0 ? "emerald" : "red"} />
        <StatCard label="最大回撤"
          value={metrics.rows.length ? `${metrics.maxDd.toFixed(2)}%` : "—"}
          color="red" />
        <StatCard label="已平仓"
          value={`${metrics.wins + metrics.losses}`} color="gray" />
        <StatCard label="胜率"
          value={winRate === "—" ? "—" : `${winRate}%`}
          color={parseFloat(winRate) >= 50 ? "emerald" : "red"} />
        <StatCard label="盈亏比"
          value={pr === "—" ? "—" : `${pr}:1`}
          color={parseFloat(pr) >= 1.5 ? "emerald" : "yellow"} />
        <StatCard label="持仓中"
          value={openPositions.length} color="sky" />
      </div>

      {/* ── 净值曲线图 ───────────────────────────────────── */}
      {!loading && metrics.navPoints.length > 1 && (
        <div className="mb-8 rounded-xl border border-gray-200 bg-gray-50 p-4">
          <p className="mb-3 text-xs text-gray-500">
            净值曲线  ·  {metrics.wins + metrics.losses} 笔已平仓
            {metrics.rows.length > 0 && (
              <>  ·  平均盈 <span className="text-emerald-600">+{(metrics.avgWin / 10000).toFixed(2)}万</span>
              &nbsp;·  平均亏 <span className="text-red-600">{(metrics.avgLoss / 10000).toFixed(2)}万</span></>
            )}
          </p>
          <NavChart
            navPoints={metrics.navPoints}
            ddPoints={metrics.ddPoints}
            tradeRows={metrics.rows}
          />
        </div>
      )}

      {/* ── 过滤器 ───────────────────────────────────────── */}
      <div className="mb-4 flex flex-wrap gap-2">
        {(["all", "closed_tp", "closed_sl"] as FilterStatus[]).map((s) => (
          <button key={s} onClick={() => setFilterStatus(s)}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              filterStatus === s
                ? "bg-blue-700 text-white"
                : "bg-[#1a2233] text-gray-500 hover:bg-[#1e2840]"
            }`}>
            {s === "all" ? "全部已平仓" : STATUS_LABEL[s as PositionStatus]}
          </button>
        ))}
        <div className="ml-2 flex gap-2">
          {(["all", "long", "short"] as FilterDir[]).map((d) => (
            <button key={d} onClick={() => setFilterDir(d)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                filterDir === d
                  ? "bg-gray-600 text-white"
                  : "bg-[#1a2233] text-gray-500 hover:bg-[#1e2840]"
              }`}>
              {d === "all" ? "多空全部" : DIR_LABEL[d]}
            </button>
          ))}
        </div>
        {updatedAt && (
          <span className="ml-auto text-xs text-gray-300 self-center">
            更新：{updatedAt}
          </span>
        )}
      </div>

      {loading && (
        <div className="py-16 text-center text-gray-400 text-sm">正在加载...</div>
      )}

      {/* ── 已平仓交易表格 ──────────────────────────────── */}
      {!loading && filteredClosed.length > 0 && (
        <div className="mb-8 overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-gray-500">
                <th className="px-3 py-2.5 text-left">品种</th>
                <th className="px-3 py-2.5 text-left">方向</th>
                <th className="px-3 py-2.5 text-left">类型</th>
                <th className="px-3 py-2.5 text-right">合约规格</th>
                <th className="px-3 py-2.5 text-right">每手保证金</th>
                <th className="px-3 py-2.5 text-right">手数</th>
                <th className="px-3 py-2.5 text-right">入场价</th>
                <th className="px-3 py-2.5 text-right">出场价</th>
                <th className="px-3 py-2.5 text-right">盈亏(元)</th>
                <th className="px-3 py-2.5 text-right">账户影响</th>
                <th className="px-3 py-2.5 text-right">净值</th>
                <th className="px-3 py-2.5 text-left">结果</th>
                <th className="px-3 py-2.5 text-left whitespace-nowrap">入场时间</th>
              </tr>
            </thead>
            <tbody>
              {filteredClosed.map((r) => (
                <ClosedTradeRow key={r.pos.id} m={r} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && filteredClosed.length === 0 && (
        <div className="py-12 text-center text-gray-400 text-sm">暂无已平仓记录</div>
      )}

      {/* ── 持仓中 ──────────────────────────────────────── */}
      {!loading && openPositions.length > 0 && (
        <>
          <h2 className="mb-3 text-sm font-semibold text-gray-400">
            持仓中 <span className="ml-1 text-sky-600">{openPositions.length}</span>
          </h2>
          <div className="overflow-x-auto rounded-xl border border-gray-200">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 text-gray-500">
                  <th className="px-3 py-2.5 text-left">品种</th>
                  <th className="px-3 py-2.5 text-left">方向</th>
                  <th className="px-3 py-2.5 text-left">类型</th>
                  <th className="px-3 py-2.5 text-right">合约规格</th>
                  <th className="px-3 py-2.5 text-right">每手保证金</th>
                  <th className="px-3 py-2.5 text-right">手数</th>
                  <th className="px-3 py-2.5 text-right">入场价</th>
                  <th className="px-3 py-2.5 text-right">止损</th>
                  <th className="px-3 py-2.5 text-right">止盈目标</th>
                  <th className="px-3 py-2.5 text-left whitespace-nowrap">入场时间</th>
                </tr>
              </thead>
              <tbody>
                {openPositions.map((pos) => {
                  const [mult, mgnRate, unit] = getSpec(pos.symbol);
                  const mpl = pos.entryPrice * mult * mgnRate;
                  const lots = Math.max(1, Math.floor(MARGIN_PER_TRADE / mpl));
                  return (
                    <tr key={pos.id}
                      className="border-b border-[#1a2233]/60 hover:bg-[#1a2233]/40 transition-colors">
                      <td className="px-3 py-2 font-medium text-gray-800">{pos.symbol}</td>
                      <td className={`px-3 py-2 font-medium ${DIR_COLOR[pos.direction]}`}>
                        {DIR_LABEL[pos.direction]}
                      </td>
                      <td className="px-3 py-2 text-gray-500">{SIG_LABEL[pos.signalType] ?? pos.signalType}</td>
                      <td className="px-3 py-2 text-right text-gray-500">{mult}{unit}</td>
                      <td className="px-3 py-2 text-right text-gray-400">
                        {mpl.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-300">{lots}</td>
                      <td className="px-3 py-2 text-right text-gray-300">{pos.entryPrice.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right text-red-600/80">{pos.stopLoss.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right text-emerald-600/80">{pos.takeProfit.toFixed(2)}</td>
                      <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{pos.entryTime}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      <p className="mt-4 text-right text-xs text-gray-300">
        共 {positions.length} 条 · 已平仓 {metrics.wins + metrics.losses} · 持仓中 {openPositions.length}
      </p>
    </div>
  );
}

// ── 已平仓行 ───────────────────────────────────────────────────
function ClosedTradeRow({ m }: { m: TradeMetrics }) {
  const { pos, mult, unit, marginPerLot, lots, pnlRmb, chgPct, navAfter } = m;
  const isWin = pnlRmb > 0;

  return (
    <tr className="border-b border-[#1a2233]/60 hover:bg-[#1a2233]/40 transition-colors">
      <td className="px-3 py-2 font-medium text-gray-800">{pos.symbol}</td>
      <td className={`px-3 py-2 font-medium ${DIR_COLOR[pos.direction]}`}>
        {DIR_LABEL[pos.direction]}
      </td>
      <td className="px-3 py-2 text-gray-500">{SIG_LABEL[pos.signalType] ?? pos.signalType}</td>
      <td className="px-3 py-2 text-right text-gray-500">{mult}{unit}</td>
      <td className="px-3 py-2 text-right text-gray-500">
        {marginPerLot.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}
      </td>
      <td className="px-3 py-2 text-right text-gray-300">{lots}</td>
      <td className="px-3 py-2 text-right text-gray-400">{pos.entryPrice.toFixed(2)}</td>
      <td className="px-3 py-2 text-right text-gray-400">
        {pos.exitPrice !== null ? pos.exitPrice.toFixed(2) : "—"}
      </td>
      <td className={`px-3 py-2 text-right font-semibold ${isWin ? "text-emerald-600" : "text-red-600"}`}>
        {pnlRmb >= 0 ? "+" : ""}
        {(pnlRmb / 10000).toFixed(2)}万
      </td>
      <td className={`px-3 py-2 text-right ${isWin ? "text-emerald-600/80" : "text-red-600/80"}`}>
        {chgPct >= 0 ? "+" : ""}{chgPct.toFixed(2)}%
      </td>
      <td className="px-3 py-2 text-right text-sky-300 font-mono text-[11px]">
        {navAfter.toFixed(4)}
      </td>
      <td className="px-3 py-2">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${STATUS_COLOR[pos.status]}`}>
          {STATUS_LABEL[pos.status]}
        </span>
      </td>
      <td className="px-3 py-2 text-gray-400 whitespace-nowrap">{pos.entryTime}</td>
    </tr>
  );
}

// ── 统计卡片 ───────────────────────────────────────────────────
type CardColor = "emerald" | "red" | "sky" | "yellow" | "gray";
const CARD_COLOR: Record<CardColor, string> = {
  emerald: "text-emerald-600",
  red:     "text-red-600",
  sky:     "text-sky-600",
  yellow:  "text-yellow-600",
  gray:    "text-gray-300",
};

function StatCard({
  label,
  value,
  sub,
  color = "gray",
}: {
  label: string;
  value: string | number;
  sub?: string;
  color?: CardColor;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5">
      <p className="text-[10px] text-gray-400 mb-0.5">{label}</p>
      <p className={`text-base font-bold leading-tight ${CARD_COLOR[color]}`}>{value}</p>
      {sub && <p className="text-[10px] text-gray-400 mt-0.5">{sub}</p>}
    </div>
  );
}
