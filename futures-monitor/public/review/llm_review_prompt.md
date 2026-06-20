# 期货监控系统 · 策略复盘 Prompt

你是期货策略的复盘分析师。请基于以下数据，给出策略参数优化建议。

## 规则约束

1. 你的输出必须是「建议 diff」格式，例如：
   ```diff
   - "expansion_rate_min": 1.2
   + "expansion_rate_min": 1.4
   ```
2. 每个建议必须给出理由（基于数据，不是猜测）
3. 参数修改必须在 strategy_params.json 的有效范围内
4. 标注每个建议的「风险等级」：低/中/高
5. 优先关注连亏品种的针对性优化

---

## 数据概览

- 统计范围: 2026-05-20 ~ 2026-06-16
- 总交易: 31 笔
- 胜率: 25.8%
- 盈亏比: 0.08
- 盈利因子: 0.03
- 期望值: -564.08 点/笔
- 累计盈亏: -17486.46 点
- 最大连亏: 14 笔

## 分策略统计
- breakout: 20笔, 胜率20.0%, 盈亏比0.15, EV-573.01, PF0.04
- pullback: 11笔, 胜率36.4%, 盈亏比0.01, EV-547.84, PF0.01

## 分方向统计
- 做空: 19笔, 胜率36.8%, 盈亏比1.18, EV-11.06
- 做多: 12笔, 胜率8.3%, 盈亏比0.01, EV-1439.69

## ⚠️ 品种连亏预警
- 锡: 连亏3笔 (-15954.29点)

## 滚动窗口表现 (最近20笔)
- 近期胜率: 20.0% (全期: 25.8%)
- 近期EV: -357.93 (全期: -564.08)
- ⚠️ 近期胜率显著下降，策略可能退化

## 当前参数 (完整)
```json
{
  "_comment": "期货监控系统 - 策略参数配置。修改参数 → 重启抓取即生效。改前备份此文件以便回滚。",
  "version": "1.0",
  "updatedAt": "2026-06-11",
  "pullback": {
    "_desc": "旧版回踩参数（已弃用，保留兼容）",
    "bounce_tol_pct": 1.5,
    "atr_factor": 0.8,
    "adaptive_min_pct": 0.3,
    "approach_tol_pct": 0.3,
    "min_slope20_pct": 0.05,
    "min_slope60_pct": 0.02,
    "ma_entanglement_threshold_pct": 0.15
  },
  "mtf_pullback": {
    "_desc": "H-005 MTF回踩状态机（日线趋势×30min结构回踩）",
    "_design": "状态机: IDLE→ARMED(等回踩)→QUALIFYING(质量审查)→TRIGGER_WAIT→SIGNAL",
    "zone_tol_atr30": 0.3,
    "zone_tol_atr_d": 0.5,
    "overheat_atr_d": 2.0,
    "max_retrace": 0.618,
    "shrink_ratio": 0.8,
    "max_oi_increase": 3.0,
    "min_pb_bars": 2,
    "max_pb_bars": 20,
    "trigger_wait": 8,
    "stop_buffer_atr": 0.5,
    "swing_lookback": 5,
    "use_tet": true,
    "ats_min": 0.3,
    "ei_washout": 0.3,
    "ti_entry": 0.5,
    "trend_score_version": 2,
    "tet_variant": "V1",
    "_tet_note": "V1=期货最优(IC5≈0,IC20=-0.018,翻转8.6%); V3=指数最优(跨资产不稳定,按事前规则用V1)",
    "fib_zones": true,
    "sweep_trigger": true,
    "sweep_pierce_atr": 0.1
  },
  "breakout": {
    "_desc": "突破信号参数",
    "body_atr_ratio_min": 1.0,
    "kd_cooling": {
      "long_k_max": 80,
      "long_d_max": 80,
      "short_k_min": 20,
      "short_d_min": 20
    }
  },
  "macd": {
    "_desc": "MACD 指标参数",
    "fast": 12,
    "slow": 26,
    "signal": 9,
    "expansion_rate_min": 1.2,
    "expansion_lookback_bars": 10
  },
  "volume": {
    "_desc": "成交量参数",
    "surge_ma_mult": 1.5,
    "ma_window": 10
  },
  "risk": {
    "_desc": "风控参数",
    "min_risk_pct": 0.15,
    "min_price_gap_pct": 0.01,
    "stop_loss_atr_entry": 2,
    "stop_loss_atr_prev_bar": 1,
    "take_profit_risk_ratio": 2,
    "breakeven_r": 1,
    "trailing_activate_r": 1.5,
    "trailing_atr_mult": 1.2
  },
  "position": {
    "_desc": "持仓管理参数",
    "cooldown_minutes": 60,
    "max_wait_bars": 12
  },
  "trading_hours": {
    "_desc": "交易时段守卫 (北京时间)",
    "morning": [
      "08:50",
      "11:40"
    ],
    "afternoon": [
      "13:20",
      "15:10"
    ],
    "night": [
      "20:50",
      "23:40"
    ],
    "daily_k_window": [
      "23:00",
      "23:15"
    ]
  },
  "fetch": {
    "_desc": "数据抓取参数",
    "max_workers": 4,
    "kline_rows": 200,
    "request_delay_seconds": 0.8,
    "max_retries": 3
  }
}
```

---

## 请输出

1. **总体诊断**: 策略当前处于什么阶段（稳定/退化/进化中）？
2. **参数建议 diff**: 最多5条，按优先级排序
3. **连亏品种处置**: 对每个预警品种给出具体建议
4. **下周关注**: 哪些品种/方向需要重点观察？