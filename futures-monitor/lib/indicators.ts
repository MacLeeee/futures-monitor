// ============================================================
// 期货监控系统 - 指标计算引擎
// 严格遵循 Prompt 中的数学定义
// ============================================================

import { KLineData, MaStatus, SpreadStatus, VolumeStatus, OIStatus } from "./types";

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
  crossStatus: string;
  spreadStatus: SpreadStatus;
  cumulative: number;
  region: "水上" | "水下" | "中性";
} {
  if (klines.length < 30) {
    return { crossStatus: "无", spreadStatus: "Shrinking", cumulative: 0, region: "中性" };
  }

  const closes = klines.map((k) => k.close);
  const { diff, dea, hist } = calcMACD(closes);
  const n = klines.length;

  const prevDiff = diff[n - 2];
  const curDiff = diff[n - 1];
  const prevDea = dea[n - 2];
  const curDea = dea[n - 1];

  // 金叉/死叉：仅在穿越当根标注（事件型）
  let crossStatus = "无";
  if (curDiff > 0 && curDea > 0 && prevDiff < prevDea && curDiff > curDea) {
    crossStatus = "水上金叉";
  } else if (curDiff < 0 && curDea < 0 && prevDiff > prevDea && curDiff < curDea) {
    crossStatus = "水下死叉";
  }

  // 区域（持续状态）：DIFF 与 DEA 的相对位置
  // 水上区：DIFF > DEA 且 DIFF > 0（多头主导）
  // 水下区：DIFF < DEA 且 DIFF < 0（空头主导）
  let region: "水上" | "水下" | "中性";
  if (curDiff > curDea && curDiff > 0) {
    region = "水上";
  } else if (curDiff < curDea && curDiff < 0) {
    region = "水下";
  } else {
    region = "中性";
  }

  // 开口扩大/缩小
  const curAbs = Math.abs(hist[n - 1]);
  const prevAbs = Math.abs(hist[n - 2]);
  const sameSign = hist[n - 1] * hist[n - 2] > 0;
  const spreadStatus: SpreadStatus =
    sameSign && curAbs > prevAbs ? "Expanding" : "Shrinking";

  const getSpread = (i: number): SpreadStatus => {
    if (i < 1) return "Shrinking";
    const ca = Math.abs(hist[i]);
    const pa = Math.abs(hist[i - 1]);
    const ss = hist[i] * hist[i - 1] > 0;
    return ss && ca > pa ? "Expanding" : "Shrinking";
  };

  let cumulative = 1;
  for (let i = n - 2; i >= 1; i--) {
    if (getSpread(i) === spreadStatus) {
      cumulative++;
    } else {
      break;
    }
  }

  return { crossStatus, spreadStatus, cumulative, region };
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
