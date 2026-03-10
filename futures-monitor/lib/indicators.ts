// ============================================================
// 期货监控系统 - 指标计算引擎
// 严格遵循 Prompt 中的数学定义
// ============================================================

import { KLineData, MaStatus, MacdSign, VolumeStatus, OIStatus } from "./types";

// --- 均线计算 ---
export function calcMA(closes: number[], period: number): number[] {
  const result: number[] = new Array(closes.length).fill(NaN);
  for (let i = period - 1; i < closes.length; i++) {
    const sum = closes.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
    result[i] = sum / period;
  }
  return result;
}

// 均线状态判定 (基于最新 K 线)
export function calcMAStatus(klines: KLineData[]): { status: MaStatus; cumulative: number } {
  if (klines.length < 60) return { status: "Silent", cumulative: 0 };

  const closes = klines.map((k) => k.close);
  const ma20 = calcMA(closes, 20);
  const ma60 = calcMA(closes, 60);

  const getStatus = (i: number): MaStatus => {
    const c = closes[i];
    const m20 = ma20[i];
    const m60 = ma60[i];
    if (isNaN(m20) || isNaN(m60)) return "Silent";
    if (c > m20 && c > m60) return "Upward";
    if (c < m20 && c < m60) return "Downward";
    return "Silent";
  };

  const lastIdx = klines.length - 1;
  const currentStatus = getStatus(lastIdx);

  let cumulative = 1;
  for (let i = lastIdx - 1; i >= 0; i--) {
    if (getStatus(i) === currentStatus) {
      cumulative++;
    } else {
      break;
    }
  }

  return { status: currentStatus, cumulative };
}

// --- MACD 计算 (12, 26, 9) ---
export function calcEMA(values: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const result: number[] = [];
  for (let i = 0; i < values.length; i++) {
    if (i === 0) {
      result.push(values[0]);
    } else {
      result.push(values[i] * k + result[i - 1] * (1 - k));
    }
  }
  return result;
}

export function calcMACD(
  closes: number[],
  fast = 12,
  slow = 26,
  signal = 9
): { diff: number[]; dea: number[]; hist: number[] } {
  const emaFast = calcEMA(closes, fast);
  const emaSlow = calcEMA(closes, slow);
  const diff = emaFast.map((v, i) => v - emaSlow[i]);
  const dea = calcEMA(diff, signal);
  const hist = diff.map((v, i) => v - dea[i]);
  return { diff, dea, hist };
}

export function calcMACDStatus(klines: KLineData[]): {
  sign: MacdSign;
  rapidExpanding: boolean;
  expansionRate: number;
  cumulative: number;
} {
  if (klines.length < 30) {
    return { sign: "negative", rapidExpanding: false, expansionRate: 0, cumulative: 0 };
  }

  const closes = klines.map((k) => k.close);
  const { diff, dea, hist } = calcMACD(closes);
  const n = klines.length;

  // ── 方向（持续状态）：diff - dea 的正负 ──
  // positive = 金叉区（DIFF > DEA，多头柱），negative = 死叉区（DIFF < DEA，空头柱）
  const curHist = hist[n - 1];
  const sign: MacdSign = curHist >= 0 ? "positive" : "negative";

  // ── 连续同向根数 ──
  const getSign = (i: number): MacdSign => (hist[i] >= 0 ? "positive" : "negative");
  let cumulative = 1;
  for (let i = n - 2; i >= 0; i--) {
    if (getSign(i) === sign) cumulative++;
    else break;
  }

  // ── 快速走扩：|hist| 的逐根变化速率 vs 近10期均值 ──
  // delta[i] = |hist[i]| - |hist[i-1]|（正=扩口，负=缩口）
  const LOOKBACK = 10;
  const histAbs = hist.map(Math.abs);
  const deltas: number[] = [];
  for (let i = Math.max(1, n - LOOKBACK); i < n; i++) {
    deltas.push(histAbs[i] - histAbs[i - 1]);
  }
  const currentDelta = deltas[deltas.length - 1];
  // 用前 N-1 根的绝对变化量均值作为基准（排除当根，避免自我比较）
  const prevDeltas = deltas.slice(0, deltas.length - 1);
  const avgAbsDelta =
    prevDeltas.length > 0
      ? prevDeltas.reduce((s, v) => s + Math.abs(v), 0) / prevDeltas.length
      : 0;

  // 快速走扩 = 当根在扩口（delta > 0）且速度超过均值
  const rapidExpanding = currentDelta > 0 && (avgAbsDelta === 0 || currentDelta > avgAbsDelta);
  const expansionRate =
    avgAbsDelta > 0 ? Math.round((currentDelta / avgAbsDelta) * 100) / 100 : (currentDelta > 0 ? 1 : 0);

  return { sign, rapidExpanding, expansionRate, cumulative };
}

// --- 成交量状态（环比上一根 K 线） ---
export function calcVolumeStatus(klines: KLineData[]): {
  status: VolumeStatus;
  cumulative: number;
  value: number;
  change: number;
  changePct: number;
} {
  if (klines.length < 2) {
    return { status: "Shrink", cumulative: 0, value: 0, change: 0, changePct: 0 };
  }

  const n = klines.length;

  // 环比：当前成交量 vs 上一根
  const getStatus = (data: KLineData[], i: number): VolumeStatus => {
    if (i < 1) return "Shrink";
    return data[i].volume > data[i - 1].volume ? "Surge" : "Shrink";
  };

  const curVol = klines[n - 1].volume;
  const prevVol = klines[n - 2].volume;
  const change = curVol - prevVol;
  const changePct = prevVol !== 0 ? (change / prevVol) * 100 : 0;
  const currentStatus = getStatus(klines, n - 1);

  let cumulative = 1;
  for (let i = n - 2; i >= 1; i--) {
    if (getStatus(klines, i) === currentStatus) {
      cumulative++;
    } else {
      break;
    }
  }

  return {
    status: currentStatus,
    cumulative,
    value: curVol,
    change,
    changePct: Math.round(changePct * 100) / 100,
  };
}

// --- 持仓量状态（环比上一根 K 线） ---
export function calcOIStatus(klines: KLineData[]): {
  status: OIStatus;
  cumulative: number;
  value: number;
  prevValue: number;
  change: number;
  changePct: number;
} {
  if (klines.length < 2) {
    return { status: "Decreasing", cumulative: 0, value: 0, prevValue: 0, change: 0, changePct: 0 };
  }

  const n = klines.length;

  // 环比：当前 OI 与上一根 K 线 OI 比较
  const getStatus = (data: KLineData[], i: number): OIStatus => {
    if (i < 1) return "Decreasing";
    return data[i].openInterest > data[i - 1].openInterest ? "Increasing" : "Decreasing";
  };

  const currentValue = klines[n - 1].openInterest;
  const prevValue = klines[n - 2].openInterest;
  const change = currentValue - prevValue;
  const changePct = prevValue !== 0 ? (change / prevValue) * 100 : 0;
  const currentStatus = getStatus(klines, n - 1);

  // 连续同向计数
  let cumulative = 1;
  for (let i = n - 2; i >= 1; i--) {
    if (getStatus(klines, i) === currentStatus) {
      cumulative++;
    } else {
      break;
    }
  }

  return {
    status: currentStatus,
    cumulative,
    value: currentValue,
    prevValue,
    change,
    changePct: Math.round(changePct * 100) / 100,
  };
}
