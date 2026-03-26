// ============================================================
// 期货监控系统 - 核心类型定义
// ============================================================

export type MaStatus = "Upward" | "Downward" | "Silent";
export type VolumeStatus = "Surge" | "Shrink";
export type OIStatus = "Increasing" | "Decreasing";
// MACD 方向：diff-dea > 0 为金叉区(positive)，< 0 为死叉区(negative)
export type MacdSign = "positive" | "negative";

export type MaSlopeType = "steep" | "gentle" | "declining" | "flat";

// 突破信号：30min MA排列 + MA20/MA60斜率同向 + 15min MACD扩口 + 15min量>均量 + 增仓(宽松)
export interface BreakoutSignal {
  type: "long" | "short";
  maCumulative: number;      // 30min MA 方向持续 K 数
  macdSign: "positive" | "negative";
  expansionRate: number;     // 15min MACD 走扩倍率
  oiConfirmed: boolean;      // 15min 持仓量是否增仓（宽松条件）
  slope20: number;           // 触发时 MA20 斜率（%/3K）
  slope60: number;           // 触发时 MA60 斜率（%/3K）
}

// 回踩信号：30min MA60 锚定方向 + 价格从正确方向回踩均线 + 15min MACD缩窄 + 15min放量
export interface PullbackSignal {
  type: "long" | "short";   // 做多回踩（从上方） / 做空反抽（从下方）
  target: "MA20" | "MA60";  // 回踩/反抽的目标均线
  support: number;           // 目标均线当前值
  distPct: number;           // 距均线的 % 距离（绝对值）
  aboveMa: boolean;          // 做多: true=价格仍在均线上方; 做空: true=已轻微突破
  slopeType: MaSlopeType;    // 30min MA20 斜率类型
  ma20: number;              // 30min MA20 当前值
  ma60: number;              // 30min MA60 当前值
}

export interface FuturesStatus {
  symbol: string;         // 品种名称，如 "苯乙烯"
  category: string;       // 板块分类
  timeframe: "30min";
  lastUpdate: string;     // 最后更新时间
  price: number;          // 当前价格
  change: number;         // 涨跌幅 %
  ma: {
    status: MaStatus;
    cumulative: number;        // 连续持续 K 线数
    ma20: number | null;       // 当前 MA20 值
    ma60: number | null;       // 当前 MA60 值
    slope20Pct: number;        // MA20 斜率（3根K线内累计%变化）
    slope60Pct: number;        // MA60 斜率（3根K线内累计%变化）
    slopeType: MaSlopeType;    // steep=急速上行(≥45°) gentle=缓慢 declining=下行
  };
  breakoutSignal: BreakoutSignal | null;  // 突破信号（30m方向+15m触发）
  pullbackSignal: PullbackSignal | null;  // 回踩信号（30m MA60锚定+15m触发）
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
    aboveVolMa: boolean;  // 当前量 > 近10根均量（量MA10确认）
    volMa: number;        // 近10根均量
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
