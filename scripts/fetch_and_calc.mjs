#!/usr/bin/env node
// ============================================================
// 期货监控系统 - GitHub Actions 数据抓取与指标计算脚本
// 运行环境: Node.js 20+ (内置 fetch，无需 npm install)
// 数据源:   新浪财经 futures_zh_minute 接口（AKShare 同源）
// 输出:     futures-monitor/public/data.json
// ============================================================

import { writeFileSync, readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUTPUT = join(__dirname, "..", "futures-monitor", "public", "data.json");

// ── 品种定义 ────────────────────────────────────────────────
const SYMBOLS = [
  { symbol: "黄金",     category: "贵金属", code: "AU0" },
  { symbol: "白银",     category: "贵金属", code: "AG0" },
  { symbol: "铜",       category: "有色",   code: "CU0" },
  { symbol: "铝",       category: "有色",   code: "AL0" },
  { symbol: "镍",       category: "有色",   code: "NI0" },
  { symbol: "锡",       category: "有色",   code: "SN0" },
  { symbol: "碳酸锂",   category: "有色",   code: "LC0" },
  { symbol: "铁矿石",   category: "黑色",   code: "I0"  },
  { symbol: "螺纹钢",   category: "黑色",   code: "RB0" },
  { symbol: "焦煤",     category: "黑色",   code: "JM0" },
  { symbol: "锰硅",     category: "黑色",   code: "SM0" },
  { symbol: "硅铁",     category: "黑色",   code: "SF0" },
  { symbol: "生猪",     category: "农产品", code: "LH0" },
  { symbol: "玉米",     category: "农产品", code: "C0"  },
  { symbol: "棉花",     category: "农产品", code: "CF0" },
  { symbol: "白糖",     category: "农产品", code: "SR0" },
  { symbol: "豆油",     category: "油脂",   code: "Y0"  },
  { symbol: "菜油",     category: "油脂",   code: "OI0" },
  { symbol: "棕榈油",   category: "油脂",   code: "P0"  },
  { symbol: "豆粕",     category: "油脂",   code: "M0"  },
  { symbol: "菜粕",     category: "油脂",   code: "RM0" },
  { symbol: "原油",     category: "能化",   code: "SC0" },
  { symbol: "燃油",     category: "能化",   code: "FU0" },
  { symbol: "苯乙烯",   category: "能化",   code: "EB0" },
  { symbol: "烧碱",     category: "能化",   code: "SH0" },
  { symbol: "橡胶",     category: "能化",   code: "RU0" },
  { symbol: "PVC",      category: "能化",   code: "V0"  },
  { symbol: "玻璃",     category: "建材",   code: "FG0" },
  { symbol: "纯碱",     category: "建材",   code: "SA0" },
  { symbol: "中证1000", category: "股指",   code: "IM0" },
];

// ── K 线获取 ─────────────────────────────────────────────────
/**
 * 调用新浪财经 JSONP 接口获取 30 分钟 K 线数据。
 * 返回格式: [{ time, open, high, low, close, volume, openInterest }]
 */
async function fetchKlines(code, retries = 3) {
  const url =
    `https://stock2.finance.sina.com.cn/futures/api/jsonp.php` +
    `/var%20_=/FuturesService.getMinuteData?symbol=${code}&type=30`;

  for (let attempt = 1; attempt <= retries; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 12_000);

    try {
      const res = await fetch(url, {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
          Referer: "https://finance.sina.com.cn/",
        },
        signal: ctrl.signal,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const text = await res.text();
      // 剥离 JSONP 包装: "var _=({...})" → 取花括号内容
      const s = text.indexOf("{");
      const e = text.lastIndexOf("}");
      if (s === -1 || e === -1) throw new Error("JSONP parse failed");

      const json = JSON.parse(text.slice(s, e + 1));
      const rows = json?.result?.data;
      if (!Array.isArray(rows) || rows.length < 30) {
        throw new Error(`Data insufficient: ${rows?.length ?? 0} rows`);
      }

      return rows.map((r) => ({
        time:          new Date(r.d).getTime(),
        open:          parseFloat(r.o) || 0,
        high:          parseFloat(r.h) || 0,
        low:           parseFloat(r.l) || 0,
        close:         parseFloat(r.c) || 0,
        volume:        parseFloat(r.v) || 0,
        openInterest:  parseFloat(r.i) || 0,
      }));
    } catch (err) {
      clearTimeout(timer);
      const isLast = attempt === retries;
      console.warn(`  [Retry ${attempt}/${retries}] ${code}: ${err.message}`);
      if (isLast) throw err;
      await sleep(2000 * attempt);
    } finally {
      clearTimeout(timer);
    }
  }
}

// ── 指标计算 ──────────────────────────────────────────────────

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** 简单移动平均 */
function sma(arr, n) {
  return arr.map((_, i) => {
    if (i < n - 1) return NaN;
    let s = 0;
    for (let j = i - n + 1; j <= i; j++) s += arr[j];
    return s / n;
  });
}

/** 指数移动平均 */
function ema(arr, n) {
  const k = 2 / (n + 1);
  const out = [arr[0]];
  for (let i = 1; i < arr.length; i++) {
    out.push(arr[i] * k + out[i - 1] * (1 - k));
  }
  return out;
}

/** 均线状态 (Close vs MA20/MA60) */
function calcMA(klines) {
  const closes = klines.map((k) => k.close);
  const ma20 = sma(closes, 20);
  const ma60 = sma(closes, 60);
  const n = klines.length;

  const st = (i) => {
    const [c, m20, m60] = [closes[i], ma20[i], ma60[i]];
    if (isNaN(m20) || isNaN(m60)) return "Silent";
    if (c > m20 && c > m60) return "Upward";
    if (c < m20 && c < m60) return "Downward";
    return "Silent";
  };

  const cur = st(n - 1);
  let cnt = 1;
  for (let i = n - 2; i >= 0; i--) {
    if (st(i) === cur) cnt++;
    else break;
  }
  return { status: cur, cumulative: cnt };
}

/** MACD 状态 (12,26,9) — 含 region */
function calcMACD(klines) {
  const closes = klines.map((k) => k.close);
  const diff = ema(closes, 12).map((v, i) => v - ema(closes, 26)[i]);
  const dea = ema(diff, 9);
  const hist = diff.map((v, i) => v - dea[i]);
  const n = klines.length;

  // 金叉/死叉（事件型，仅当根）
  let crossStatus = "无";
  if (
    diff[n-1] > 0 && dea[n-1] > 0 &&
    diff[n-2] < dea[n-2] && diff[n-1] > dea[n-1]
  ) crossStatus = "水上金叉";
  else if (
    diff[n-1] < 0 && dea[n-1] < 0 &&
    diff[n-2] > dea[n-2] && diff[n-1] < dea[n-1]
  ) crossStatus = "水下死叉";

  // 区域（持续状态）
  const region =
    diff[n-1] > dea[n-1] && diff[n-1] > 0 ? "水上" :
    diff[n-1] < dea[n-1] && diff[n-1] < 0 ? "水下" : "中性";

  // 开口扩大/缩小
  const curAbs = Math.abs(hist[n-1]);
  const prevAbs = Math.abs(hist[n-2]);
  const sameSign = hist[n-1] * hist[n-2] > 0;
  const spreadStatus = sameSign && curAbs > prevAbs ? "Expanding" : "Shrinking";

  const getSpread = (i) => {
    if (i < 1) return "Shrinking";
    const ss = hist[i] * hist[i-1] > 0;
    return ss && Math.abs(hist[i]) > Math.abs(hist[i-1]) ? "Expanding" : "Shrinking";
  };
  let cnt = 1;
  for (let i = n - 2; i >= 1; i--) {
    if (getSpread(i) === spreadStatus) cnt++;
    else break;
  }

  return { crossStatus, spreadStatus, cumulative: cnt, region };
}

/** 成交量状态（环比上一根） */
function calcVolume(klines) {
  const n = klines.length;
  if (n < 2) return { status: "Shrink", cumulative: 0, value: 0, change: 0, changePct: 0 };

  const st = (i) => i >= 1 && klines[i].volume > klines[i-1].volume ? "Surge" : "Shrink";
  const cur = st(n - 1);
  const change = klines[n-1].volume - klines[n-2].volume;
  const changePct = klines[n-2].volume
    ? round2(change / klines[n-2].volume * 100)
    : 0;

  let cnt = 1;
  for (let i = n - 2; i >= 1; i--) {
    if (st(i) === cur) cnt++;
    else break;
  }
  return {
    status: cur, cumulative: cnt,
    value: Math.round(klines[n-1].volume),
    change: Math.round(change),
    changePct,
  };
}

/** 持仓量状态（环比上一根） */
function calcOI(klines) {
  const n = klines.length;
  const empty = { value: 0, prevValue: 0, change: 0, changePct: 0, status: "Decreasing", cumulative: 0 };
  if (n < 2) return empty;

  const st = (i) => i >= 1 && klines[i].openInterest > klines[i-1].openInterest
    ? "Increasing" : "Decreasing";
  const cur = st(n - 1);
  const change = klines[n-1].openInterest - klines[n-2].openInterest;
  const changePct = klines[n-2].openInterest
    ? round2(change / klines[n-2].openInterest * 100)
    : 0;

  let cnt = 1;
  for (let i = n - 2; i >= 1; i--) {
    if (st(i) === cur) cnt++;
    else break;
  }
  return {
    value:     Math.round(klines[n-1].openInterest),
    prevValue: Math.round(klines[n-2].openInterest),
    change:    Math.round(change),
    changePct,
    status:    cur,
    cumulative: cnt,
  };
}

function round2(n) {
  return Math.round(n * 100) / 100;
}

// ── 品种处理 ──────────────────────────────────────────────────

async function processSymbol({ symbol, category, code }) {
  try {
    const klines = await fetchKlines(code);
    const n = klines.length;
    const last = klines[n - 1].close;
    const prev = klines[n - 2].close;

    return {
      symbol,
      category,
      timeframe: "30min",
      lastUpdate: new Date().toTimeString().slice(0, 8),
      price:  round2(last),
      change: round2((last - prev) / prev * 100),
      ma:            calcMA(klines),
      macd:          calcMACD(klines),
      volume:        calcVolume(klines),
      openInterest:  calcOI(klines),
    };
  } catch (err) {
    console.error(`  [SKIP] ${symbol}(${code}): ${err.message}`);
    return null;
  }
}

// ── 主流程 ────────────────────────────────────────────────────

async function main() {
  console.log(`[${new Date().toISOString()}] Fetching ${SYMBOLS.length} symbols...`);

  const results = [];
  // 每批 5 个并发，批间间隔 1s，避免新浪限流
  for (let i = 0; i < SYMBOLS.length; i += 5) {
    const batch = SYMBOLS.slice(i, i + 5);
    const batch_results = await Promise.all(batch.map(processSymbol));
    results.push(...batch_results.filter(Boolean));
    if (i + 5 < SYMBOLS.length) await sleep(1000);
  }

  if (results.length === 0) {
    console.error("[FATAL] No data fetched. Aborting write.");
    process.exit(1);
  }

  // 保留上次数据中本次失败的品种（防止接口偶发故障清空数据）
  let merged = results;
  if (existsSync(OUTPUT)) {
    try {
      const prev = JSON.parse(readFileSync(OUTPUT, "utf-8"));
      const prevMap = Object.fromEntries((prev.data ?? []).map((d) => [d.symbol, d]));
      const newSymbols = new Set(results.map((d) => d.symbol));
      const kept = Object.values(prevMap).filter((d) => !newSymbols.has(d.symbol));
      merged = [...results, ...kept];
    } catch { /* ignore */ }
  }

  const output = {
    source:    "github-actions",
    updatedAt: new Date().toISOString(),
    data:      merged,
  };

  writeFileSync(OUTPUT, JSON.stringify(output, null, 2), "utf-8");
  console.log(`✓ ${results.length}/${SYMBOLS.length} symbols → ${OUTPUT}`);
}

main().catch((err) => {
  console.error("[FATAL]", err);
  process.exit(1);
});
