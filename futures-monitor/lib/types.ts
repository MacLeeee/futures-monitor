// ============================================================
// 期货监控系统 - 核心类型定义
// ============================================================

export type MaStatus = "Upward" | "Downward" | "Silent";
export type VolumeStatus = "Surge" | "Shrink";
export type OIStatus = "Increasing" | "Decreasing";
// MACD 方向：diff-dea > 0 为金叉区(positive)，< 0 为死叉区(negative)
export type MacdSign = "positive" | "negative";

export type MaSlopeType = "steep" | "gentle" | "declining" | "flat";

// 突破信号：30min MA排列（价格在MA20/MA60上/下方）+ 15min MACD扩口 + 15min量>均量
// 增仓(OI)为或有加分项
export interface BreakoutSignal {
  type: "long" | "short";
  maCumulative: number;      // 30min MA 排列方向持续 K 数
  macdSign: "positive" | "negative";
  expansionRate: number;     // 15min MACD 走扩倍率
  oiConfirmed: boolean;      // 15min 持仓量增仓（或有加分项）
}

// 回踩信号：30min MA60 锚定方向 + 价格从正确方向回踩均线 + 15min MACD扩口 + 15min放量
export interface PullbackSignal {
  type: "long" | "short";   // 做多回踩（从上方） / 做空反抽（从下方）
  target: "MA20" | "MA60";  // 回踩/反抽的目标均线
  support: number;           // 目标均线当前值
  distPct: number;           // 距均线的 % 距离（绝对值）
  aboveMa: boolean;          // 做多: true=价格仍在均线上方; 做空: true=已轻微突破
  slopeType: MaSlopeType;    // 30min MA20 斜率类型
  ma20: number;              // 30min MA20 当前值
  ma60: number;              // 30min MA60 当前值
  bounceTol: number;         // 自适应回踩容忍阈值%（按 ATR 收缩）
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
  marketRegime?: MarketRegime | null;     // 市场状态（趋势/震荡判定）
  boxSignal?: BoxSignal | null;           // 箱体信号（震荡行情触及通道边沿）
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
  score: number;           // 0~100, >=55=趋势
  donchian: DonchianChannel;
  pivot: PivotStructure;
  emaRibbon: EmaRibbon;
}

export interface BoxSignal {
  type: "long" | "short";
  boundary: "upper" | "lower";
  boundaryPrice: number;
  distPct: number;
  boxUpper: number;
  boxLower: number;
}

// ── 持仓记录 ─────────────────────────────────────────────────

export type PositionStatus = "open" | "closed_sl" | "closed_tp";
export type PositionDirection = "long" | "short";
export type SignalType = "breakout" | "pullback";
export type ExitReason = "initial_sl" | "break_even_sl" | "trailing_sl" | "fixed_tp";

export interface Position {
  id: string;
  symbol: string;
  direction: PositionDirection;
  signalType: SignalType;
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
