"use client";

import { useCallback, useEffect, useState } from "react";
import { Position, PositionsData, PositionStatus } from "@/lib/types";

const GITHUB_RAW =
  "https://raw.githubusercontent.com/MacLeeee/futures-monitor/main/futures-monitor/public";

const STATUS_LABEL: Record<PositionStatus, string> = {
  open:       "持仓中",
  closed_sl:  "止损出",
  closed_tp:  "止盈出",
};
const STATUS_COLOR: Record<PositionStatus, string> = {
  open:       "text-blue-400 bg-blue-900/40",
  closed_sl:  "text-red-400 bg-red-900/40",
  closed_tp:  "text-emerald-400 bg-emerald-900/40",
};
const DIR_LABEL: Record<string, string> = { long: "做多 ▲", short: "做空 ▼" };
const DIR_COLOR: Record<string, string> = {
  long:  "text-emerald-400",
  short: "text-red-400",
};
const SIG_LABEL: Record<string, string> = { breakout: "突破", pullback: "回踩" };

type FilterStatus = "all" | PositionStatus;
type FilterDir    = "all" | "long" | "short";

export default function TradeLog() {
  const [data, setData]       = useState<PositionsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [filterDir,    setFilterDir]    = useState<FilterDir>("all");
  const [updatedAt, setUpdatedAt]       = useState<string>("");

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

  // 过滤
  const filtered = positions.filter((p) => {
    if (filterStatus !== "all" && p.status !== filterStatus) return false;
    if (filterDir    !== "all" && p.direction !== filterDir)  return false;
    return true;
  });

  // 统计（已关闭笔数）
  const closed   = positions.filter((p) => p.status !== "open");
  const wins     = closed.filter((p) => p.pnl !== null && p.pnl > 0);
  const winRate  = closed.length ? ((wins.length / closed.length) * 100).toFixed(1) : "—";
  const totalPnl = closed.reduce((s, p) => s + (p.pnlPct ?? 0), 0);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-200 p-4 md:p-8">
      {/* 顶部导航 */}
      <div className="mb-6 flex items-center gap-4">
        <a href="/" className="text-gray-500 hover:text-gray-300 text-sm transition-colors">
          ← 返回监控
        </a>
        <h1 className="text-xl font-bold text-gray-100">📒 交易记录</h1>
      </div>

      {/* 统计卡片 */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="总笔数"  value={positions.length} />
        <StatCard label="持仓中"  value={data?.openCount ?? 0} highlight="blue" />
        <StatCard
          label="胜率"
          value={winRate === "—" ? "—" : `${winRate}%`}
          highlight={parseFloat(winRate) >= 50 ? "green" : "red"}
        />
        <StatCard
          label="已结盈亏"
          value={closed.length ? `${totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)}%` : "—"}
          highlight={totalPnl >= 0 ? "green" : "red"}
        />
      </div>

      {/* 过滤器 */}
      <div className="mb-4 flex flex-wrap gap-2">
        {(["all", "open", "closed_tp", "closed_sl"] as FilterStatus[]).map((s) => (
          <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
              filterStatus === s
                ? "bg-blue-700 text-white"
                : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            {s === "all" ? "全部" : STATUS_LABEL[s as PositionStatus]}
          </button>
        ))}
        <div className="ml-2 flex gap-2">
          {(["all", "long", "short"] as FilterDir[]).map((d) => (
            <button
              key={d}
              onClick={() => setFilterDir(d)}
              className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                filterDir === d
                  ? "bg-gray-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:bg-gray-700"
              }`}
            >
              {d === "all" ? "多空全部" : DIR_LABEL[d]}
            </button>
          ))}
        </div>
      </div>

      {/* 更新时间 */}
      {updatedAt && (
        <p className="mb-3 text-xs text-gray-600">数据更新：{updatedAt}</p>
      )}

      {/* 加载状态 */}
      {loading && (
        <div className="py-12 text-center text-gray-600 text-sm">正在加载...</div>
      )}

      {/* 交易列表 */}
      {!loading && (
        <>
          {filtered.length === 0 ? (
            <div className="py-12 text-center text-gray-600 text-sm">暂无记录</div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-gray-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-800 bg-gray-900 text-xs text-gray-500">
                    <th className="px-3 py-2 text-left">品种</th>
                    <th className="px-3 py-2 text-left">方向</th>
                    <th className="px-3 py-2 text-left">类型</th>
                    <th className="px-3 py-2 text-right">入场价</th>
                    <th className="px-3 py-2 text-right">止损</th>
                    <th className="px-3 py-2 text-right">止盈</th>
                    <th className="px-3 py-2 text-right">出场价</th>
                    <th className="px-3 py-2 text-right">盈亏%</th>
                    <th className="px-3 py-2 text-left">状态</th>
                    <th className="px-3 py-2 text-left">入场时间</th>
                  </tr>
                </thead>
                <tbody>
                  {[...filtered].reverse().map((pos) => (
                    <TradeRow key={pos.id} pos={pos} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-3 text-right text-xs text-gray-700">
            共 {filtered.length} / {positions.length} 条
          </p>
        </>
      )}
    </div>
  );
}

function TradeRow({ pos }: { pos: Position }) {
  const pnl    = pos.pnlPct;
  const isWin  = pnl !== null && pnl > 0;
  const isLoss = pnl !== null && pnl < 0;

  return (
    <tr className="border-b border-gray-800/60 hover:bg-gray-800/30 transition-colors">
      <td className="px-3 py-2 font-medium text-gray-100">{pos.symbol}</td>
      <td className={`px-3 py-2 font-medium ${DIR_COLOR[pos.direction]}`}>
        {DIR_LABEL[pos.direction]}
      </td>
      <td className="px-3 py-2 text-gray-500 text-xs">
        {SIG_LABEL[pos.signalType]}
      </td>
      <td className="px-3 py-2 text-right text-gray-300">{pos.entryPrice.toFixed(2)}</td>
      <td className="px-3 py-2 text-right text-red-400/80">{pos.stopLoss.toFixed(2)}</td>
      <td className="px-3 py-2 text-right text-emerald-400/80">{pos.takeProfit.toFixed(2)}</td>
      <td className="px-3 py-2 text-right text-gray-400">
        {pos.exitPrice !== null ? pos.exitPrice.toFixed(2) : "—"}
      </td>
      <td className={`px-3 py-2 text-right font-semibold ${
        isWin ? "text-emerald-400" : isLoss ? "text-red-400" : "text-gray-500"
      }`}>
        {pnl !== null ? `${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}%` : "持仓中"}
      </td>
      <td className="px-3 py-2">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${STATUS_COLOR[pos.status]}`}>
          {STATUS_LABEL[pos.status]}
        </span>
      </td>
      <td className="px-3 py-2 text-gray-600 text-xs whitespace-nowrap">
        {pos.entryTime}
      </td>
    </tr>
  );
}

function StatCard({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string | number;
  highlight?: "blue" | "green" | "red";
}) {
  const color =
    highlight === "blue"  ? "text-blue-400"    :
    highlight === "green" ? "text-emerald-400" :
    highlight === "red"   ? "text-red-400"     :
    "text-gray-200";
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-bold ${color}`}>{value}</p>
    </div>
  );
}
