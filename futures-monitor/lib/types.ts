// ============================================================
// 期货监控系统 - 核心类型定义
// ============================================================

export type MaStatus = "Upward" | "Downward" | "Silent";
export type VolumeStatus = "Surge" | "Shrink";
export type OIStatus = "Increasing" | "Decreasing";
// MACD 方向：diff-dea > 0 为金叉区(positive)，< 0 为死叉区(negative)
export type MacdSign = "positive" | "negative";

export interface FuturesStatus {
  symbol: string;         // 品种名称，如 "苯乙烯"
  category: string;       // 板块分类
  timeframe: "30min";
  lastUpdate: string;     // 最后更新时间
  price: number;          // 当前价格
  change: number;         // 涨跌幅 %
  ma: {
    status: MaStatus;
    cumulative: number;   // 连续持续 K 线数
  };
  macd: {
    sign: MacdSign;           // diff-dea 正负：positive=金叉区 / negative=死叉区
    rapidExpanding: boolean;  // |diff-dea| 是否快速走扩（当前变化速率 > 近10期均值）
    expansionRate: number;    // 走扩倍率（当前 delta / 均值 delta，>1 代表超均速）
    cumulative: number;       // 当前 sign 方向连续 K 线数
  };
  volume: {
    status: VolumeStatus;
    cumulative: number;   // 连续同向 K 线数
    value: number;        // 当前成交量
    change: number;       // 环比变化量 = value - prevValue
    changePct: number;    // 环比变化幅度（%）
  };
  openInterest: {
    value: number;        // 当前持仓量（手）
    prevValue: number;    // 上一根 K 线持仓量（手）
    change: number;       // 环比变化量（手）= value - prevValue
    changePct: number;    // 环比变化幅度（%）
    status: OIStatus;     // 增仓 or 减仓（由环比正负决定）
    cumulative: number;   // 连续同向 K 线数
  };
}

// 板块分组，用于表格分组渲染
export interface CategoryGroup {
  name: string;
  symbols: FuturesStatus[];
}

// K 线原始数据（用于计算指标）
export interface KLineData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  openInterest: number;
}

// AKShare API 响应格式
export interface AKShareResponse {
  symbol: string;
  data: KLineData[];
}
