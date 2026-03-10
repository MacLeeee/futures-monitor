// ============================================================
// 期货监控系统 - 核心类型定义
// ============================================================

export type MaStatus = "Upward" | "Downward" | "Silent";
export type SpreadStatus = "Expanding" | "Shrinking";
export type VolumeStatus = "Surge" | "Shrink";
export type OIStatus = "Increasing" | "Decreasing";
export type CrossStatus = "水上金叉" | "水下死叉" | "无";

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
    crossStatus: CrossStatus;   // 当根是否发生金叉/死叉（事件型）
    spreadStatus: SpreadStatus; // 当前开口扩大/缩小
    cumulative: number;         // 连续扩口/缩口根数
    region: "水上" | "水下" | "中性"; // DIFF/DEA 所在区域（持续状态）
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
