"""
AKShare 期货实盘数据微服务
=====================================
为 Next.js Dashboard 提供 30 分钟 K 线数据及指标计算结果。

安装依赖:
    pip install akshare fastapi uvicorn pandas numpy

启动命令:
    uvicorn akshare_service:app --host 0.0.0.0 --port 8000

Next.js 配置 (.env.local):
    AKSHARE_SERVICE_URL=http://localhost:8000

说明:
  - AKShare 的 futures_zh_minute_sina 接口返回近期分钟数据
  - 持仓量字段来源于 futures_zh_daily_sina 的 hold 列（部分交易所可用）
  - 股指期货 (IM0) 使用 futures_index_zh_sina 接口
"""

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

import akshare as ak
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AKShare 期货数据服务", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------
# 品种映射：symbol（中文） -> AKShare 代码
# ----------------------------------------------------------------
SYMBOL_MAP: dict[str, str] = {
    # 贵金属（上期所）
    "黄金":     "AU0",
    "白银":     "AG0",
    # 有色（上期所）
    "铜":       "CU0",
    "铝":       "AL0",
    "镍":       "NI0",
    "锡":       "SN0",
    "氧化铝":   "AO0",
    # 有色（广期所）
    "碳酸锂":   "LC0",
    # 黑色（大商所）
    "铁矿石":   "I0",
    "焦煤":     "JM0",
    # 黑色（上期所）
    "螺纹钢":   "RB0",
    # 黑色（郑商所）
    "锰硅":     "SM0",
    "硅铁":     "SF0",
    # 农产品（大商所）
    "生猪":     "LH0",
    "玉米":     "C0",
    # 农产品（郑商所）
    "棉花":     "CF0",
    "白糖":     "SR0",
    # 油脂（大商所）
    "豆油":     "Y0",
    "棕榈油":   "P0",
    "豆粕":     "M0",
    # 油脂（郑商所）
    "菜油":     "OI0",
    "菜粕":     "RM0",
    # 能化（上期所 / INE）
    "原油":     "SC0",
    "燃油":     "FU0",
    "橡胶":     "RU0",
    # 能化（大商所）
    "苯乙烯":   "EB0",
    "PVC":      "V0",
    # 能化（郑商所）
    "烧碱":     "SH0",
    # 建材（郑商所）
    "玻璃":     "FG0",
    "纯碱":     "SA0",
    # 股指（中金所）
    "中证1000": "IM0",
}

CATEGORY_MAP: dict[str, str] = {
    "黄金": "贵金属", "白银": "贵金属",
    "铜": "有色", "铝": "有色", "镍": "有色", "锡": "有色", "碳酸锂": "有色", "氧化铝": "有色",
    "铁矿石": "黑色", "螺纹钢": "黑色", "焦煤": "黑色", "锰硅": "黑色", "硅铁": "黑色",
    "生猪": "农产品", "玉米": "农产品", "棉花": "农产品", "白糖": "农产品",
    "豆油": "油脂", "菜油": "油脂", "棕榈油": "油脂", "豆粕": "油脂", "菜粕": "油脂",
    "原油": "能化", "燃油": "能化", "苯乙烯": "能化",
    "烧碱": "能化", "橡胶": "能化", "PVC": "能化",
    "玻璃": "建材", "纯碱": "建材",
    "中证1000": "股指",
}

# ----------------------------------------------------------------
# 指标计算
# ----------------------------------------------------------------

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calc_ma_status(closes: pd.Series) -> dict:
    if len(closes) < 60:
        return {"status": "Silent", "cumulative": 0}
    ma20 = closes.rolling(20).mean()
    ma60 = closes.rolling(60).mean()

    def status_at(i: int) -> str:
        c, m20, m60 = closes.iloc[i], ma20.iloc[i], ma60.iloc[i]
        if pd.isna(m20) or pd.isna(m60):
            return "Silent"
        if c > m20 and c > m60:
            return "Upward"
        if c < m20 and c < m60:
            return "Downward"
        return "Silent"

    n = len(closes)
    cur = status_at(n - 1)
    cnt = 1
    for i in range(n - 2, -1, -1):
        if status_at(i) == cur:
            cnt += 1
        else:
            break
    return {"status": cur, "cumulative": cnt}


def calc_macd_status(closes: pd.Series) -> dict:
    if len(closes) < 30:
        return {"crossStatus": "无", "spreadStatus": "Shrinking", "cumulative": 0}

    diff = ema(closes, 12) - ema(closes, 26)
    dea = ema(diff, 9)
    hist = diff - dea
    n = len(closes)

    cross = "无"
    if (diff.iloc[-1] > 0 and dea.iloc[-1] > 0
            and diff.iloc[-2] < dea.iloc[-2] and diff.iloc[-1] > dea.iloc[-1]):
        cross = "水上金叉"
    elif (diff.iloc[-1] < 0 and dea.iloc[-1] < 0
            and diff.iloc[-2] > dea.iloc[-2] and diff.iloc[-1] < dea.iloc[-1]):
        cross = "水下死叉"

    def spread_at(i: int) -> str:
        if i < 1:
            return "Shrinking"
        same_sign = hist.iloc[i] * hist.iloc[i - 1] > 0
        expanding = abs(hist.iloc[i]) > abs(hist.iloc[i - 1])
        return "Expanding" if (same_sign and expanding) else "Shrinking"

    cur_spread = spread_at(n - 1)
    cnt = 1
    for i in range(n - 2, 0, -1):
        if spread_at(i) == cur_spread:
            cnt += 1
        else:
            break
    # 区域（持续状态）：DIFF 与 DEA 的相对位置
    # 水上区：DIFF > DEA 且 DIFF > 0（多头主导）
    # 水下区：DIFF < DEA 且 DIFF < 0（空头主导）
    cur_diff_val = float(diff.iloc[-1])
    cur_dea_val = float(dea.iloc[-1])
    if cur_diff_val > cur_dea_val and cur_diff_val > 0:
        region = "水上"
    elif cur_diff_val < cur_dea_val and cur_diff_val < 0:
        region = "水下"
    else:
        region = "中性"

    return {"crossStatus": cross, "spreadStatus": cur_spread, "cumulative": cnt, "region": region}


def calc_volume_status(volumes: pd.Series) -> dict:
    """成交量状态：环比上一根 K 线增减，标注幅度。"""
    if len(volumes) < 2:
        return {"status": "Shrink", "cumulative": 0, "value": 0, "change": 0, "changePct": 0.0}

    n = len(volumes)
    cur_vol = float(volumes.iloc[-1])
    prev_vol = float(volumes.iloc[-2])
    change = cur_vol - prev_vol
    change_pct = round((change / prev_vol) * 100, 1) if prev_vol != 0 else 0.0

    def vs_at(i: int) -> str:
        if i < 1:
            return "Shrink"
        return "Surge" if volumes.iloc[i] > volumes.iloc[i - 1] else "Shrink"

    cur = vs_at(n - 1)
    cnt = 1
    for i in range(n - 2, 0, -1):
        if vs_at(i) == cur:
            cnt += 1
        else:
            break

    return {
        "status": cur,
        "cumulative": cnt,
        "value": int(cur_vol),
        "change": int(change),
        "changePct": change_pct,
    }


def calc_oi_status(oi: pd.Series) -> dict:
    """
    持仓量状态：环比上一根 K 线增减，同时标注变化量和幅度。
    """
    empty = {"value": 0, "prevValue": 0, "change": 0, "changePct": 0.0,
             "status": "Decreasing", "cumulative": 0}
    if len(oi) < 2 or oi.isna().all():
        return empty

    # 去 NaN 后取最后两根
    valid = oi.dropna()
    if len(valid) < 2:
        return empty

    cur_val = float(valid.iloc[-1])
    prev_val = float(valid.iloc[-2])
    change = cur_val - prev_val
    change_pct = round((change / prev_val) * 100, 2) if prev_val != 0 else 0.0

    # 环比判断：当前根 vs 上一根
    def oi_at(i: int) -> str:
        if i < 1 or pd.isna(oi.iloc[i]) or pd.isna(oi.iloc[i - 1]):
            return "Decreasing"
        return "Increasing" if oi.iloc[i] > oi.iloc[i - 1] else "Decreasing"

    n = len(oi)
    cur = oi_at(n - 1)
    cnt = 1
    for i in range(n - 2, 0, -1):
        if oi_at(i) == cur:
            cnt += 1
        else:
            break

    return {
        "value": int(cur_val),
        "prevValue": int(prev_val),
        "change": int(change),
        "changePct": change_pct,
        "status": cur,
        "cumulative": cnt,
    }


# ----------------------------------------------------------------
# K 线获取（兼容商品期货 + 股指期货）
# ----------------------------------------------------------------

def fetch_kline(symbol: str, code: str, rows: int = 200) -> Optional[pd.DataFrame]:
    """
    获取 30 分钟 K 线并附加持仓量字段
    持仓量来源：取日线数据最新持仓量（新浪接口含 hold 字段）
    """
    try:
        # 分钟 K 线（新浪财经接口）
        df = ak.futures_zh_minute_sina(symbol=code, period="30")
        if df is None or len(df) < 30:
            return None

        # 统一列名
        rename = {"datetime": "time"}
        df = df.rename(columns=rename)
        df.columns = df.columns.str.lower()

        # 确保必要字段存在
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                return None

        # 持仓量：AKShare 分钟 K 线的 hold 字段即为逐根持仓量（更精准）
        if "hold" in df.columns:
            df["open_interest"] = pd.to_numeric(df["hold"], errors="coerce")
        else:
            df["open_interest"] = float("nan")

        return df.tail(rows).reset_index(drop=True)
    except Exception as e:
        print(f"[FETCH] {symbol}({code}): {e}")
        return None


def build_status(symbol: str, df: pd.DataFrame) -> dict:
    n = len(df)
    last_close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2]) if n >= 2 else last_close
    change_pct = round((last_close - prev_close) / prev_close * 100, 2) if prev_close else 0.0

    return {
        "symbol": symbol,
        "category": CATEGORY_MAP.get(symbol, "其他"),
        "timeframe": "30min",
        "lastUpdate": datetime.now().strftime("%H:%M:%S"),
        "price": round(last_close, 2),
        "change": change_pct,
        "ma": calc_ma_status(df["close"]),
        "macd": calc_macd_status(df["close"]),
        "volume": calc_volume_status(df["volume"]),
        "openInterest": calc_oi_status(df["open_interest"]),
    }


# ----------------------------------------------------------------
# 并发拉取所有品种
# ----------------------------------------------------------------

def _fetch_one(item: tuple[str, str]) -> Optional[dict]:
    symbol, code = item
    df = fetch_kline(symbol, code)
    if df is None or len(df) < 60:
        print(f"[SKIP] {symbol}({code}): 数据不足")
        return None
    try:
        return build_status(symbol, df)
    except Exception as e:
        print(f"[CALC] {symbol}: {e}")
        return None


# ----------------------------------------------------------------
# API 路由
# ----------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "symbols": len(SYMBOL_MAP), "time": datetime.now().isoformat()}


@app.get("/futures/all")
async def get_all_futures():
    """
    批量获取所有品种 30 分钟 K 线的最新指标状态。
    使用线程池并发拉取，避免逐个阻塞。
    """
    loop = asyncio.get_event_loop()
    items = list(SYMBOL_MAP.items())

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures_tasks = [loop.run_in_executor(pool, _fetch_one, item) for item in items]
        results = await asyncio.gather(*futures_tasks)

    return [r for r in results if r is not None]


@app.get("/futures/{symbol}")
async def get_single_futures(symbol: str):
    """获取单个品种的最新指标状态"""
    code = SYMBOL_MAP.get(symbol)
    if not code:
        raise HTTPException(status_code=404, detail=f"未知品种: {symbol}")

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        df = await loop.run_in_executor(pool, fetch_kline, symbol, code)

    if df is None or len(df) < 60:
        raise HTTPException(status_code=503, detail="K 线数据不足（需至少 60 根）")

    return build_status(symbol, df)
