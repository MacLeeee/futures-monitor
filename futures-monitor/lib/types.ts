// ============================================================
// 期货监控系统 - 核心类型定义
// ============================================================

export type MaStatus = "Upward" | "Downward" | "Silent";
export type VolumeStatus = "Surge" | "Shrink";
export type OIStatus = "Increasing" | "Decreasing";
// MACD 方向：diff-dea > 0 为金叉区(positive)，< 0 为死叉区(negative)
export type MacdSign = "positive" | "negative";

export type MaSlopeType = "steep" | "gentle" | "declining" | "flat";

export interface DipSignal {
  type: "MA20" | "MA60";   // 支撑均线
  support: number;          // 支撑位价格
  distPct: number;          // 距支撑位的 % 距离（≤0.5%）
  slopeType: MaSlopeType;
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
    cumulative: number;   // 连续持续 K 线数
    ma20: number | null;       // 当前 MA20 值
    ma60: number | null;       // 当前 MA60 值
    slope20Pct: number;        // MA20 斜率（3根K线内累计%变化）
    slopeType: MaSlopeType;    // steep=急速上行(≥45°) gentle=缓慢 declining=下行
  };
  dipSignal: DipSignal | null; // 抄底信号，null=无
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

// 开盘跳空预警
export interface GapAlert {
  symbol: string;
  category: string;
  gapPct: number;        // 正=跳涨，负=跳跌
  direction: "up" | "down";
  openPrice: number;     // 当前开盘价（最新K线开盘）
  prevClose: number;     // 上一根K线收盘价
  session: string;       // "早盘" | "午盘" | "夜盘"
}

// 跳空扫描确认信息（不论有无跳空，在开盘窗口内就记录）
export interface GapCheckInfo {
  checkedAt: string;     // 北京时间 "HH:MM"
  session: string;       // "早盘" | "午盘" | "夜盘"
  count: number;         // 检测到的跳空品种数
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
