// ============================================================
// 期货监控系统 - Mock 数据生成器
// 根据真实的数学逻辑生成 K 线序列，再反推指标状态
// ============================================================

import {
  FuturesStatus,
  KLineData,
} from "./types";
import {
  calcMAStatus,
  calcMACDStatus,
  calcVolumeStatus,
  calcOIStatus,
} from "./indicators";

// 所有监控品种定义（品种名 + 板块 + 基准价格）
export const FUTURES_SYMBOLS: { symbol: string; category: string; basePrice: number }[] = [
  // 贵金属
  { symbol: "黄金", category: "贵金属", basePrice: 620 },
  { symbol: "白银", category: "贵金属", basePrice: 7200 },
  // 有色
  { symbol: "铜", category: "有色", basePrice: 78000 },
  { symbol: "铝", category: "有色", basePrice: 20000 },
  { symbol: "镍", category: "有色", basePrice: 128000 },
  { symbol: "锡", category: "有色", basePrice: 250000 },
  { symbol: "碳酸锂", category: "有色", basePrice: 95000 },
  { symbol: "氧化铝", category: "有色", basePrice: 4300 },
  // 黑色
  { symbol: "铁矿石", category: "黑色", basePrice: 820 },
  { symbol: "螺纹钢", category: "黑色", basePrice: 3400 },
  { symbol: "焦煤", category: "黑色", basePrice: 1700 },
  { symbol: "锰硅", category: "黑色", basePrice: 5800 },
  { symbol: "硅铁", category: "黑色", basePrice: 6200 },
  // 农产品
  { symbol: "生猪", category: "农产品", basePrice: 14500 },
  { symbol: "玉米", category: "农产品", basePrice: 2350 },
  { symbol: "棉花", category: "农产品", basePrice: 15200 },
  { symbol: "白糖", category: "农产品", basePrice: 6100 },
  // 油脂
  { symbol: "豆油", category: "油脂", basePrice: 8200 },
  { symbol: "菜油", category: "油脂", basePrice: 9100 },
  { symbol: "棕榈油", category: "油脂", basePrice: 8500 },
  { symbol: "豆粕", category: "油脂", basePrice: 3150 },
  { symbol: "菜粕", category: "油脂", basePrice: 2950 },
  // 能化
  { symbol: "原油", category: "能化", basePrice: 540 },
  { symbol: "燃油", category: "能化", basePrice: 3800 },
  { symbol: "苯乙烯", category: "能化", basePrice: 9200 },
  { symbol: "烧碱", category: "能化", basePrice: 2700 },
  { symbol: "橡胶", category: "能化", basePrice: 14800 },
  { symbol: "PVC", category: "能化", basePrice: 5200 },
  // 建材
  { symbol: "玻璃", category: "建材", basePrice: 1450 },
  { symbol: "纯碱", category: "建材", basePrice: 1650 },
  // 股指
  { symbol: "中证1000", category: "股指", basePrice: 5800 },
];

// 用种子生成伪随机数（保证每次刷新数据一致性，加随机偏移模拟刷新）
function seededRand(seed: number): () => number {
  let s = seed;
  return function () {
    s = (s * 1664525 + 1013904223) & 0xffffffff;
    return (s >>> 0) / 0xffffffff;
  };
}

// 生成带有特定趋势偏向的 K 线序列
function generateKLines(
  basePrice: number,
  count: number,
  seed: number,
  trend: "up" | "down" | "sideways" = "sideways"
): KLineData[] {
  const rand = seededRand(seed);
  const klines: KLineData[] = [];
  let price = basePrice;
  const trendBias = trend === "up" ? 0.0003 : trend === "down" ? -0.0003 : 0;

  for (let i = 0; i < count; i++) {
    const volatility = 0.008;
    const change = (rand() - 0.5) * 2 * volatility + trendBias;
    const open = price;
    const close = open * (1 + change);
    const high = Math.max(open, close) * (1 + rand() * 0.003);
    const low = Math.min(open, close) * (1 - rand() * 0.003);
    const baseVol = basePrice * 50;
    const volume = baseVol * (0.5 + rand() * 1.5);
    const baseOI = basePrice * 200;
    const openInterest = baseOI * (0.8 + rand() * 0.4);

    klines.push({
      time: Date.now() - (count - i) * 30 * 60 * 1000,
      open,
      high,
      low,
      close,
      volume,
      openInterest,
    });
    price = close;
  }
  return klines;
}

// 将指标计算结果打包成 FuturesStatus
function buildFuturesStatus(
  symbol: string,
  category: string,
  klines: KLineData[],
  seed: number
): FuturesStatus {
  const rand = seededRand(seed + 9999);
  const n = klines.length;
  const latestClose = klines[n - 1].close;
  const prevClose = klines[n - 2].close;
  const change = ((latestClose - prevClose) / prevClose) * 100;

  const maResult = calcMAStatus(klines);
  const macdResult = calcMACDStatus(klines);
  const volResult = calcVolumeStatus(klines);
  const oiResult = calcOIStatus(klines);

  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");

  const price = Math.round(latestClose * 100) / 100;

  return {
    symbol,
    category,
    timeframe: "30min",
    triggerTf: "15m",
    lastUpdate: `${hh}:${mm}:${ss}`,
    barTime: `${hh}:${mm}:00`,
    price,
    curOpen: Math.round(price * 0.998 * 100) / 100,
    change: Math.round(change * 100) / 100,
    atr: Math.round(price * 0.015 * 100) / 100,
    curLow: Math.round(price * 0.994 * 100) / 100,
    curHigh: Math.round(price * 1.003 * 100) / 100,
    prevLow: Math.round(price * 0.995 * 100) / 100,
    prevHigh: Math.round(price * 1.002 * 100) / 100,
    prevClose: Math.round(prevClose * 100) / 100,
    kdj30: { k: 50, d: 50, j: 50 },
    ma: { ...maResult, slope60Pct: maResult.slope20Pct * 0.6 },  // mock: MA60斜率约为MA20的60%
    // mock 中 macd/volume/oi 字段模拟 15min 数据（结构相同）
    macd: {
      sign:           macdResult.sign,
      rapidExpanding: macdResult.rapidExpanding,
      expansionRate:  macdResult.expansionRate,
      cumulative:     macdResult.cumulative,
    },
    volume: {
      status:      volResult.status,
      cumulative:  volResult.cumulative,
      value:       Math.round(volResult.value),
      change:      Math.round(volResult.change),
      changePct:   volResult.changePct,
      aboveVolMa:      volResult.status === "Surge",
      prevAboveVolMa:  volResult.status === "Surge",
      volMa:           Math.round(volResult.value * 0.8),
    },
    openInterest: {
      value: Math.round(oiResult.value),
      prevValue: Math.round(oiResult.prevValue),
      change: Math.round(oiResult.change),
      changePct: oiResult.changePct,
      status: oiResult.status,
      cumulative: oiResult.cumulative,
    },
    breakoutSignal: null,  // mock 不预生成信号
    pullbackSignal: null,
  };
}

// 趋势分配：让不同品种有不同状态，增加 Mock 多样性
const trendMap: Record<string, "up" | "down" | "sideways"> = {
  黄金: "up", 白银: "up", 铜: "up", 铝: "sideways", 镍: "down",
  锡: "up", 碳酸锂: "down", 氧化铝: "sideways", 铁矿石: "down", 螺纹钢: "down",
  焦煤: "sideways", 锰硅: "sideways", 硅铁: "up",
  生猪: "down", 玉米: "sideways", 棉花: "up", 白糖: "up",
  豆油: "up", 菜油: "up", 棕榈油: "sideways",
  豆粕: "down", 菜粕: "down",
  原油: "sideways", 燃油: "sideways", 苯乙烯: "up",
  烧碱: "down", 橡胶: "up", PVC: "down",
  玻璃: "down", 纯碱: "sideways", 中证1000: "up",
};

// 主导出：生成全部品种的 Mock 数据
export function generateAllMockData(refreshSeed = 0): FuturesStatus[] {
  return FUTURES_SYMBOLS.map(({ symbol, category, basePrice }, idx) => {
    const trend = trendMap[symbol] ?? "sideways";
    const klines = generateKLines(basePrice, 120, idx * 1000 + refreshSeed, trend);
    return buildFuturesStatus(symbol, category, klines, idx + refreshSeed);
  });
}

// 按板块分组
export function groupByCategory(data: FuturesStatus[]) {
  const groups: Record<string, FuturesStatus[]> = {};
  for (const item of data) {
    if (!groups[item.category]) groups[item.category] = [];
    groups[item.category].push(item);
  }
  return groups;
}
