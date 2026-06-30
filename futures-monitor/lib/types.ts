// ============================================================
// 期货监控系统 - 核心类型定义
// ============================================================

export type MaStatus = "Upward" | "Downward" | "Silent";
export type VolumeStatus = "Surge" | "Shrink";
export type OIStatus = "Increasing" | "Decreasing";
// MACD 方向：diff-dea > 0 为金叉区(positive)，< 0 为死叉区(negative)
export type MacdSign = "positive" | "negative";

export type MaSlopeType = "steep" | "gentle" | "declining" | "flat";

// 突破信号：30min MA方向（价格在MA20/MA60上/下方）+ 15min MACD方向正确 + 量放量+超均量
// + 实体≥ATR + 结构位穿透。增仓(OI)为或有加分项。
export interface BreakoutSignal {
  type: "long" | "short";
  maCumulative: number;      // 30min MA 排列方向持续 K 数
  macdSign: "positive" | "negative";
  expansionRate: number;     // 15min MACD 走扩倍率
  oiConfirmed: boolean;      // 增仓确认（+OI标注，不参与门控）
  level: number | null;      // H-010: 前期关键位价格（近30根最高/最低）
}

// H-005 MTF回踩信号：日线趋势 × 30min结构回踩状态机
// 状态机: IDLE→ARMED(等回踩)→QUALIFYING(质量审查)→TRIGGER_WAIT→SIGNAL
export interface PullbackSignal {
  signal: string;            // "mtf_pullback"
  symbol: string;
  type: "long" | "short";
  trigger: string;           // "sweep"（扫损收回，最高级）| "structure_macd"（结构+MACD）
  zone: string;              // 回踩命中的区域名: "breakout_retest" | "pivot_retest" | "fib_0.382/0.5/0.618" | "daily_ema20"
  zoneLevel: number;         // 回踩区域价格
  entry: number;             // 入场价
  stopLoss: number;          // 结构止损价
  riskPct: number;           // 风险百分比
  quality: {                 // 回调质量审查
    pbBars: number;          // 回调K线根数
    retrace: number;         // 回调深度（占上一段升浪比例）
    volRatio: number;        // 回调段均量/升浪段均量
    oiChgPct: number;        // 回调段 OI 变化 %
    pbExtreme: number;       // 回调极值价格
    swingPx: number;         // 分型价格
    legBase: number;         // 升浪起点
  };
  tet?: {                    // TET 三元组（TET闸门通过时存在）
    ats: number;             // 锚定趋势分 [-1, 1]
    trendNow: number;        // 当前趋势强度
    eiNow: number;           // 当前情绪指数 [-1, 1]
    eiPbExtreme: number;     // 回调段情绪极值
    ti: number;              // 择时指标 = ATS - EI
    variant: string;         // 使用的TET变体 "V1"
  } | null;
  time: string;              // 信号时间
}

export interface FuturesStatus {
  symbol: string;         // 品种名称，如 "苯乙烯"
  category: string;       // 板块分类
  timeframe: "30min";
  triggerTf: string;      // 触发层时间框架 "15m" | "30m↓"
  lastUpdate: string;     // 最后更新时间
  barTime: string;        // 当前 30m K 线时间 "2026-06-03 14:00:00"
  price: number;          // 当前价格（收盘价）
  curOpen: number;        // 当前 30m K 线开盘价
  change: number;         // 涨跌幅 %
  atr: number;            // 14周期 ATR
  curLow: number;         // 当前K最低价
  curHigh: number;        // 当前K最高价
  prevLow: number;        // 前一根K最低价
  prevHigh: number;       // 前一根K最高价
  prevClose: number;      // 前一根K收盘价
  kdj30: {                // 30m KDJ 指标（保留兼容）
    k: number;
    d: number;
    j: number;
  };
  kdj15?: {               // 15m KDJ 指标（突破后KD冷却确认用）
    k: number;
    d: number;
    j: number;
  };
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
  marketRegime?: MarketRegime | null;     // MTF 多周期状态矩阵
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
    aboveVolMa: boolean;      // 当前量 > 均量（可能含未完结K线）
    prevAboveVolMa: boolean;  // 前一根完结量 > 均量（更可靠）
    volMa: number;            // 近10根均量
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

// ── 市场状态判定 ──────────────────────────────────────────────

export type RegimeType = "trending" | "ranging";
export type RegimeDirection = "bullish" | "bearish" | "neutral";
export type PivotStructure = "HH_HL" | "LL_LH" | "mixed";
export type EmaAlignment = "bull" | "bear" | "tangled";

export interface DonchianChannel {
  upper: number;
  lower: number;
  basis: number;
  widthPct: number;
  pricePos: number;       // 0=下轨, 0.5=中轴, 1=上轨
  flatRatio: number;
}

export interface EmaRibbon {
  alignment: EmaAlignment;
  ema20: number;
  ema50: number;
  ema120: number;
  slope20: number;
  slope50: number;
  slope120: number;
}

export interface MarketRegime {
  regime: RegimeType;
  direction: RegimeDirection;
  action: string;                // 操作建议，如 "顺势持有 / 趋势加仓"
  allowBreakout: boolean;        // MTF 门控：是否允许突破入场
  allowPullback: boolean;        // MTF 门控：是否允许回踩入场
  bullCount: number;             // Bull 对齐周期数 0-3
  bearCount: number;             // Bear 对齐周期数 0-3
  states: {                      // 每周期状态 1=Bull -1=Bear 0=Neutral
    "15m": number;
    "30m": number;
    "daily": number;
  };
}

// ── 持仓记录 ─────────────────────────────────────────────────

export type PositionStatus = "open" | "closed_sl" | "closed_tp";
export type PositionDirection = "long" | "short";
export type SignalType = "breakout" | "pullback";
export type ExitReason = "initial_sl" | "break_even_sl" | "trailing_sl" | "fixed_tp" | "inverse_sl" | "inverse_tp";

export interface Position {
  id: string;
  symbol: string;
  direction: PositionDirection;
  signalType: SignalType;
  source?: "inverse";           // 反指交易标记
  entryTime: string;          // "2026-03-30 13:33"
  entryPrice: number;
  atr: number;
  stopLoss: number;           // 当前止损价（可能被移动止损 / 保本更新）
  initialStopLoss: number;    // 初始止损价（入场时设定，不变）
  takeProfit: number;
  riskDist: number;           // 当前风险距离 = |entry - stopLoss|
  initialRiskDist: number;   // 初始风险距离（入场时设定）
  trailingActive: boolean;    // 是否已进入移动止损模式
  breakEvenMoved: boolean;   // 是否已推过保本（1R 后止损移至入场价）
  trailingActivatedAt?: string; // 移动止损激活时间 "2026-04-07 14:30"
  exitReason: ExitReason | null; // 出场原因
  breakoutConfirm?: {         // 突破信号经KD冷却后确认开仓的详情
    breakoutTime: string;     // 突破K时间
    breakoutOpen: number;     // 突破K开盘价
    breakoutClose: number;    // 突破K收盘价
    triggerLevel: number;     // 突破K实体50%位置
    barsWaited: number;       // 等待K线数
    confirmRule: string;      // 确认规则名称
  };
  status: PositionStatus;
  exitTime: string | null;
  exitPrice: number | null;
  pnl: number | null;         // 盈亏点数（正=盈利）
  pnlPct: number | null;      // 盈亏 %
}

export interface PositionsData {
  updatedAt: string;
  openCount: number;
  totalCount: number;
  positions: Position[];
}

// ── 突破待确认 ─────────────────────────────────────────────────

export interface PendingBreakout {
  id: string;                 // "黄金-long-2026-06-03 14:00:00"
  symbol: string;
  direction: PositionDirection;
  breakoutTime: string;       // 突破K时间
  breakoutOpen: number;       // 突破K开盘价
  breakoutClose: number;      // 突破K收盘价
  triggerLevel: number;       // 突破K实体50%位置
  lastCheckedBarTime: string; // 上次检查的K线时间
  barsWaited: number;         // 已等待K线数
  maxWaitBars: number;        // 最大等待K线数
}

export interface PendingBreakoutsData {
  updatedAt: string;
  count: number;
  pending: PendingBreakout[];
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

// ── 黄金宝宝巴士 ─────────────────────────────────────────────────

export type GoldRegime =
  | "Cash Liquidation"
  | "Rates-Dollar Bearish Gold"
  | "Clean Bullish Gold"
  | "Reflation Gold"
  | "Defensive Gold"
  | "Fiscal / Debasement Hedge"
  | "Bullish Price Override"
  | "Bearish Price Override"
  | "Mixed";

export type TrendSign = "Bull" | "Bear" | "Neutral";

export interface GoldStructureFlags {
  vwap_reclaim: boolean;
  vwap_reject: boolean;
  near_fib_618: boolean;
  near_key_fib?: boolean;
  bull_sweep?: boolean;
  bear_sweep?: boolean;
  double_bottom?: boolean;
  double_top?: boolean;
  above_vwap: boolean;
  below_vwap: boolean;
  higher_low: boolean;
  lower_high: boolean;
  insufficient_data?: boolean;
}

export interface GoldBusData {
  timestamp: string;
  regime: GoldRegime;
  regime_guide: string;
  liquidity_score: number;
  liquidity_state: string;
  trend_15m_1h_4h: {
    "15m": TrendSign;
    "1h": TrendSign;
    "4h": TrendSign;
  };
  structure: {
    long_score: number;
    short_score: number;
    flags: GoldStructureFlags;
  };
  advice: string;
  combo_advice?: string;
  regime_detail?: {
    dominant_theme: string;
    bull_max: number;
    bear_max: number;
    score_fiscal_hedge: number;
    score_debasement: number;
    score_real_yield_relief: number;
    score_reflation: number;
    score_defensive_gold: number;
    score_rates_dollar_bear: number;
    score_cash_liquidation: number;
    score_gold_rate_pressure: number;
    score_dollar_pressure: number;
  };
  error?: string;
  etf_snapshot?: {
    prices: Record<string, number>;
    chg_15m: Record<string, number | null>;
    chg_60m: Record<string, number | null>;
    chg_240m: Record<string, number | null>;
  };
}


