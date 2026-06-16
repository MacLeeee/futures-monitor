"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Zap, TrendingUp, Users, AlertTriangle } from "lucide-react";

// ── 类型 ─────────────────────────────────────────────────
interface FactionSlot {
  long: number;
  longChg: number;
  short: number;
  shortChg: number;
  net: number;
  netChg: number;
  label: string;
  bias: number;
}

interface SeatEntry {
  symbol: string;
  code: string;
  factions: Record<string, FactionSlot>;
  divergence?: boolean;
}

interface SeatData {
  date: string;
  updatedAt: string;
  factions: Record<string, string[]>;
  minChgLots: number;
  data: SeatEntry[];
}

const FACTION_ORDER = ["杭州帮", "外资", "机构", "家人"];

const FACTION_COLORS: Record<string, string> = {
  "杭州帮": "text-purple-700 bg-purple-50 border-purple-200",
  "外资":   "text-sky-700 bg-sky-50 border-sky-200",
  "机构":   "text-emerald-700 bg-emerald-50 border-emerald-200",
  "家人":   "text-amber-700 bg-amber-50 border-amber-200",
};

const GITHUB_RAW =
  "https://raw.githubusercontent.com/MacLeeee/futures-monitor/main/futures-monitor/public";

function getDataUrl(): string {
  const isLocalhost =
    typeof window !== "undefined" && window.location.port !== "";
  return isLocalhost ? "/seat_positions.json" : `${GITHUB_RAW}/seat_positions.json`;
}

// ── 格式化手数 ──────────────────────────────────────────
function fmtLots(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 10000) return (n / 10000).toFixed(1) + "万";
  if (abs >= 1000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}

function fmtNet(n: number): string {
  const sign = n > 0 ? "+" : n < 0 ? "" : " ";
  return `${sign}${fmtLots(n)}`;
}

// ── 标签颜色 ────────────────────────────────────────────
function labelColor(label: string): string {
  if (label.includes("加多")) return "text-emerald-600 font-semibold";
  if (label.includes("减空")) return "text-emerald-500";
  if (label.includes("加空")) return "text-red-600 font-semibold";
  if (label.includes("减多")) return "text-red-500";
  return "text-stone-400";
}

export default function SeatMonitor() {
  const [data, setData] = useState<SeatData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const url = `${getDataUrl()}?t=${Date.now()}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: SeatData = await res.json();
      setData(json);
    } catch (e: any) {
      setError(e.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── 背离汇总 ──────────────────────────────────────────
  const divergences = useMemo(() => {
    if (!data) return [];
    return data.data.filter((e) => e.divergence).map((e) => {
      const fam = e.factions["家人"];
      const inst = FACTION_ORDER.filter((f) => f !== "家人")
        .map((f) => e.factions[f])
        .filter(Boolean);
      const famBias = fam?.bias ?? 0;
      const smartBias = famBias > 0 ? "偏空" : "偏多";
      const famLabel = famBias > 0 ? "加多" : "加空";
      return `${e.symbol}: 家人${famLabel} vs 机构/外资${smartBias}`;
    });
  }, [data]);

  // ── 统计 ──────────────────────────────────────────────
  const stats = useMemo(() => {
    if (!data) return null;
    const total = data.data.length;
    const divCount = divergences.length;
    return { total, divCount };
  }, [data, divergences]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#faf8f5] flex items-center justify-center">
        <p className="text-stone-400 text-sm font-mono">加载席位数据…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#faf8f5] flex items-center justify-center">
        <div className="text-center space-y-2">
          <p className="text-red-500 text-sm font-mono">⚠ {error}</p>
          <button
            onClick={loadData}
            className="px-3 py-1.5 text-xs bg-white border border-stone-200 rounded-md hover:border-stone-300"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  if (!data || !data.data.length) {
    return (
      <div className="min-h-screen bg-[#faf8f5] flex items-center justify-center">
        <p className="text-stone-400 text-sm font-mono">暂无席位数据（非交易日或接口未更新）</p>
      </div>
    );
  }

  const dateStr = data.date.replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3");

  return (
    <div className="min-h-screen bg-[#faf8f5] text-stone-900 font-sans">
      <div className="max-w-screen-2xl mx-auto p-4 space-y-3">

        {/* ── 顶栏 ───────────────── */}
        <header className="flex items-center gap-3 pb-2 border-b border-stone-200">
          <Users size={18} className="text-purple-600" />
          <span className="text-sm font-bold tracking-tight text-purple-600">
            席位持仓
          </span>
          <span className="text-[10px] text-stone-400">
            前20会员 · {dateStr}
          </span>

          <div className="flex-1" />

          <Link
            href="/"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-all text-stone-500 hover:text-amber-500 hover:bg-amber-50/70"
          >
            <Zap size={12} />
            期货监控
          </Link>
          <Link
            href="/gold"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-all text-stone-500 hover:text-amber-500 hover:bg-amber-50/70"
          >
            <TrendingUp size={12} />
            黄金监控
          </Link>
          <Link
            href="/copper"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-all text-stone-500 hover:text-orange-500 hover:bg-orange-50/70"
          >
            <Zap size={12} />
            铜状态机
          </Link>
        </header>

        {/* ── 统计条 ───────────────── */}
        {stats && (
          <div className="flex items-center gap-2 text-[10px] text-stone-500 font-mono">
            <span className="px-2 py-0.5 bg-white border border-stone-200 rounded">
              覆盖 {stats.total} 品种
            </span>
            {stats.divCount > 0 && (
              <span className="px-2 py-0.5 bg-amber-50 border border-amber-200 text-amber-700 rounded flex items-center gap-1">
                <AlertTriangle size={10} />
                {stats.divCount} 个背离
              </span>
            )}
            <span className="text-stone-300">|</span>
            <span>增减阈值 ≥{data.minChgLots}手</span>
          </div>
        )}

        {/* ── 红榜表格 ───────────────── */}
        <div className="overflow-x-auto rounded-lg border border-stone-200 bg-white shadow-sm">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-stone-200 bg-stone-50">
                <th className="text-left px-3 py-2 font-medium text-stone-500 sticky left-0 bg-stone-50 z-10 min-w-[80px]">
                  品种
                </th>
                {FACTION_ORDER.map((f) => (
                  <th
                    key={f}
                    className={`text-center px-2.5 py-2 font-medium min-w-[110px] ${FACTION_COLORS[f]?.split(" ")[0] ?? "text-stone-500"}`}
                  >
                    {f}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {data.data.map((entry) => (
                <tr
                  key={entry.code}
                  className={`hover:bg-stone-50/50 transition-colors ${
                    entry.divergence ? "bg-amber-50/30" : ""
                  }`}
                >
                  <td className="px-3 py-2.5 sticky left-0 bg-white z-10">
                    <div className="flex items-center gap-1.5">
                      <span className="font-medium text-stone-800">
                        {entry.symbol}
                      </span>
                      {entry.divergence && (
                        <span title="家人vs聪明钱背离" className="text-amber-500">
                          ⚡
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] text-stone-400 font-mono">
                      {entry.code}
                    </span>
                  </td>
                  {FACTION_ORDER.map((f) => {
                    const s = entry.factions[f];
                    if (!s) {
                      return (
                        <td key={f} className="text-center px-2.5 py-2.5 text-stone-300">
                          –
                        </td>
                      );
                    }
                    return (
                      <td key={f} className="text-center px-2.5 py-2.5">
                        <div className={`text-xs ${labelColor(s.label)}`}>
                          {s.label || "–"}
                        </div>
                        <div className="text-[10px] text-stone-400 font-mono mt-0.5">
                          {fmtNet(s.net)}
                        </div>
                        {s.netChg !== 0 && (
                          <div className={`text-[10px] font-mono mt-0.5 ${
                            s.netChg > 0 ? "text-emerald-500" : "text-red-400"
                          }`}>
                            {s.netChg > 0 ? "+" : ""}{fmtLots(s.netChg)}
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ── 背离明细 ───────────────── */}
        {divergences.length > 0 && (
          <div className="p-3 rounded-lg border border-amber-200 bg-amber-50/70">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle size={14} className="text-amber-600" />
              <span className="text-xs font-bold text-amber-700">
                ⚡ 家人 vs 聪明钱 背离
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-1">
              {divergences.map((d) => (
                <span
                  key={d}
                  className="text-[11px] text-amber-800 font-mono px-2 py-0.5 rounded bg-amber-100/70"
                >
                  {d}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* ── 图例 ───────────────── */}
        <div className="flex items-center gap-3 text-[10px] text-stone-400 flex-wrap pb-4">
          <span className="font-medium text-stone-500">图例:</span>
          <span className="text-emerald-600 font-semibold">加多</span>
          <span className="text-emerald-500">减空</span>
          <span className="text-red-600 font-semibold">加空</span>
          <span className="text-red-500">减多</span>
          <span className="text-stone-300">|</span>
          <span>括号内: 净持仓(多-空)</span>
          <span className="text-stone-300">|</span>
          <span>⚡ 家人与机构/外资方向相反</span>
        </div>
      </div>
    </div>
  );
}
