"""
期货账户净值曲线分析 —— 含合约规格（乘数 + 保证金）

账户参数:
  - 初始资金:    1000 万人民币
  - 每笔开仓保证金: 20 万（固定额度）
  - 开仓手数:    floor(20万 / 每手保证金)，至少 1 手
  - 每手保证金:  开仓价 × 合约乘数 × 保证金比率

核心公式:
  每手保证金 = entryPrice × multiplier × margin_rate
  实际开仓手数 n = max(1, floor(200,000 / 每手保证金))
  当笔盈亏(元) = pnl_pts × multiplier × n
  当笔保证金占用 = n × 每手保证金
"""

import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import numpy as np
from datetime import datetime
import os

# ── 中文字体 ────────────────────────────────────────────────
_font_candidates = [
    '/System/Library/Fonts/STHeiti Medium.ttc',
    '/System/Library/Fonts/STHeiti Light.ttc',
    '/Library/Fonts/Arial Unicode MS.ttf',
]
_font_path = next((p for p in _font_candidates if os.path.exists(p)), None)
assert _font_path, "找不到中文字体，请手动指定 _font_path"

plt.rcParams['axes.unicode_minus'] = False

def zf(size=10):
    return fm.FontProperties(fname=_font_path, size=size)

# ══════════════════════════════════════════════════════════════
# 合约规格表
# 格式: 品种名 → (multiplier, margin_rate, unit, exchange)
#   multiplier:  每手合约数量（单位见 unit）
#   margin_rate: 交易所最低保证金比率（实盘会稍高，此处用标准值）
#   unit:        计量单位
#   exchange:    交易所
# ══════════════════════════════════════════════════════════════
CONTRACT_SPECS: dict[str, tuple] = {
    # 格式: 品种 → (multiplier, margin_rate, unit, exchange, tick_size)
    #   multiplier : 每手合约数量（单位见 unit）
    #   margin_rate: 交易所最低保证金比率
    #   unit       : 每手计量单位
    #   exchange   : 交易所
    #   tick_size  : 最小价格变动单位（元/unit）
    #
    # 每tick盈亏(元) = tick_size × multiplier
    # 每1元/unit盈亏 = 1 × multiplier

    # ── 上期所 SHFE ──────────────────────────────────────────
    '黄金':     (1000,  0.07, '克',   'SHFE',  0.01),  # AU  1000克/手 每tick=0.01×1000=10元
    '白银':     (15,    0.07, 'kg',   'SHFE',  1.0 ),  # AG  15kg/手  每tick=1×15=15元
    '铜':       (5,     0.10, '吨',   'SHFE',  10.0),  # CU  5吨/手   每tick=10×5=50元
    '铝':       (5,     0.08, '吨',   'SHFE',  5.0 ),  # AL  5吨/手   每tick=5×5=25元
    '锌':       (5,     0.08, '吨',   'SHFE',  5.0 ),  # ZN
    '铅':       (5,     0.08, '吨',   'SHFE',  5.0 ),  # PB
    '锡':       (1,     0.10, '吨',   'SHFE',  10.0),  # SN  1吨/手   每tick=10×1=10元
    '镍':       (1,     0.10, '吨',   'SHFE',  10.0),  # NI  1吨/手   每tick=10×1=10元
    '螺纹钢':   (10,    0.07, '吨',   'SHFE',  1.0 ),  # RB  10吨/手  每tick=1×10=10元
    '热轧卷板': (10,    0.07, '吨',   'SHFE',  1.0 ),  # HC
    '橡胶':     (10,    0.09, '吨',   'SHFE',  5.0 ),  # RU  10吨/手  每tick=5×10=50元
    '合成橡胶': (5,     0.09, '吨',   'SHFE',  5.0 ),  # BR  5吨/手   每tick=5×5=25元
    '燃油':     (10,    0.10, '吨',   'SHFE',  1.0 ),  # FU
    '低硫燃油': (10,    0.10, '吨',   'SHFE',  1.0 ),  # LU

    # ── 大商所 DCE ───────────────────────────────────────────
    '豆粕':     (10,    0.07, '吨',   'DCE',   1.0 ),  # M   每tick=1×10=10元
    '豆油':     (10,    0.07, '吨',   'DCE',   2.0 ),  # Y   每tick=2×10=20元
    '棕榈油':   (10,    0.07, '吨',   'DCE',   2.0 ),  # P   每tick=2×10=20元
    '玉米':     (10,    0.05, '吨',   'DCE',   1.0 ),  # C   每tick=1×10=10元
    '铁矿石':   (100,   0.08, '吨',   'DCE',   0.5 ),  # I   100吨/手 每tick=0.5×100=50元
    '焦煤':     (60,    0.10, '吨',   'DCE',   0.5 ),  # JM  60吨/手  每tick=0.5×60=30元
    '焦炭':     (100,   0.10, '吨',   'DCE',   0.5 ),  # J
    '乙二醇':   (10,    0.08, '吨',   'DCE',   1.0 ),  # EG
    '苯乙烯':   (5,     0.08, '吨',   'DCE',   1.0 ),  # EB  5吨/手   每tick=1×5=5元
    '生猪':     (16,    0.10, '吨',   'DCE',   5.0 ),  # LH  16吨/手  每tick=5×16=80元

    # ── 郑商所 ZCE ───────────────────────────────────────────
    '白糖':     (10,    0.07, '吨',   'ZCE',   1.0 ),  # SR  每tick=1×10=10元
    '菜粕':     (10,    0.07, '吨',   'ZCE',   1.0 ),  # RM
    '菜油':     (10,    0.07, '吨',   'ZCE',   1.0 ),  # OI
    '纯碱':     (20,    0.08, '吨',   'ZCE',   1.0 ),  # SA  20吨/手  每tick=1×20=20元
    '锰硅':     (5,     0.10, '吨',   'ZCE',   2.0 ),  # SM  5吨/手   每tick=2×5=10元
    '硅铁':     (5,     0.10, '吨',   'ZCE',   2.0 ),  # SF
    '甲醇':     (10,    0.07, '吨',   'ZCE',   1.0 ),  # MA
    '对二甲苯': (5,     0.08, '吨',   'ZCE',   2.0 ),  # PX  5吨/手   每tick=2×5=10元
    '玻璃':     (20,    0.08, '吨',   'ZCE',   1.0 ),  # FG
    '棉花':     (5,     0.07, '吨',   'ZCE',   5.0 ),  # CF

    # ── 上期能源 INE ─────────────────────────────────────────
    '原油':     (1000,  0.10, '桶',   'INE',   0.1 ),  # SC  1000桶/手 每tick=0.1×1000=100元

    # ── 广期所 GFEX ──────────────────────────────────────────
    '碳酸锂':   (1,     0.10, '吨',   'GFEX',  50.0),  # LC  1吨/手   每tick=50×1=50元
}


def get_spec(symbol: str) -> tuple:
    """返回 (multiplier, margin_rate, unit, exchange, tick_size)，未知品种返回默认值。"""
    return CONTRACT_SPECS.get(symbol, (1, 0.10, '手', 'UNKNOWN', 1.0))


# ══════════════════════════════════════════════════════════════
# 读取数据
# ══════════════════════════════════════════════════════════════
_here = os.path.dirname(__file__)
_data_path = os.path.join(_here, '../futures-monitor/public/positions.json')

with open(_data_path, 'r', encoding='utf-8') as f:
    raw = json.load(f)

positions = raw['positions']

# ── 账户参数 ─────────────────────────────────────────────────
INITIAL_CAPITAL  = 10_000_000   # 1000万 RMB
MARGIN_PER_TRADE = 200_000      # 每笔固定保证金 20万

# 剔除数据异常的记录（纯碱-L-20260407214545 pnl数据有误）
EXCLUDE_IDS = {'纯碱-L-20260407214545'}

# ══════════════════════════════════════════════════════════════
# 已平仓交易按退出时间排序
# ══════════════════════════════════════════════════════════════
closed = [
    p for p in positions
    if p['status'] in ('closed_tp', 'closed_sl')
    and p['pnl']       is not None
    and p['riskDist']  is not None
    and p['riskDist']  != 0
    and p['id']        not in EXCLUDE_IDS
]
closed.sort(key=lambda x: x['exitTime'])

# ══════════════════════════════════════════════════════════════
# 逐笔模拟账户净值
# ══════════════════════════════════════════════════════════════
account     = float(INITIAL_CAPITAL)   # 当前账户余额(元)
nav         = 1.0                       # 净值(从1开始)
times       = ['开始']
navs        = [1.0]
trade_rows  = []

for tr in closed:
    sym    = tr['symbol']
    mult, mgn_rate, unit, exch, tick_sz = get_spec(sym)

    entry     = tr['entryPrice']
    risk_dist = tr['riskDist']
    pnl_pts   = tr['pnl']           # 点数盈亏 (与price同单位)

    # ── 每手保证金 ───────────────────────────────────────
    margin_per_lot = entry * mult * mgn_rate  # 元/手
    lot_value      = entry * mult             # 每手合约价值(元)

    # ── 手数：用固定20万保证金，至少1手 ─────────────────
    n = max(1, int(MARGIN_PER_TRADE // margin_per_lot))

    # ── 实际保证金 & 盈亏 ─────────────────────────────────
    actual_margin = n * margin_per_lot
    actual_pnl    = pnl_pts * mult * n    # 元
    # 若触止损的最大亏损
    sl_loss       = risk_dist * mult * n  # 元

    # ── 更新账户 ──────────────────────────────────────────
    prev_account = account
    account  += actual_pnl
    nav       = account / INITIAL_CAPITAL
    chg_pct   = actual_pnl / prev_account * 100

    exit_dt = datetime.strptime(tr['exitTime'], '%Y-%m-%d %H:%M')
    times.append(exit_dt.strftime('%m-%d %H:%M'))
    navs.append(nav)

    tick_val = tick_sz * mult          # 每tick盈亏(元/手)

    trade_rows.append({
        'symbol':        sym,
        'dir':           '多' if tr['direction'] == 'long' else '空',
        'result':        '止盈' if tr['status'] == 'closed_tp' else '止损',
        'mult':          mult,
        'unit':          unit,
        'exch':          exch,
        'tick_sz':       tick_sz,
        'tick_val':      tick_val,      # 元/tick/手
        'entry':         entry,
        'exit':          tr['exitPrice'],
        'risk_dist':     risk_dist,
        'pnl_pts':       pnl_pts,
        'lot_value':     lot_value,
        'mgn_rate':      mgn_rate,
        'n':             n,
        'margin_per_lot': margin_per_lot,
        'margin_used':   actual_margin,
        'sl_loss':       sl_loss,
        'pnl_per_lot':   pnl_pts * mult,  # 元/手（该笔）
        'pnl_rmb':       actual_pnl,
        'chg_pct':       chg_pct,
        'nav':           nav,
        'r_multiple':    pnl_pts / risk_dist,
        'exitTime':      tr['exitTime'],
    })

# ══════════════════════════════════════════════════════════════
# 统计指标
# ══════════════════════════════════════════════════════════════
total      = len(trade_rows)
wins       = [t for t in trade_rows if t['pnl_rmb'] > 0]
losses     = [t for t in trade_rows if t['pnl_rmb'] < 0]
win_rate   = len(wins) / total * 100 if total else 0
avg_r_win  = np.mean([t['r_multiple'] for t in wins])  if wins   else 0
avg_r_loss = np.mean([t['r_multiple'] for t in losses]) if losses else 0
avg_pnl_win  = np.mean([t['pnl_rmb'] for t in wins])   if wins   else 0
avg_pnl_loss = np.mean([t['pnl_rmb'] for t in losses]) if losses else 0
total_pnl    = sum(t['pnl_rmb'] for t in trade_rows)

# 最大回撤
peak, max_dd = 1.0, 0.0
dd_series = []
for n_ in navs:
    peak = max(peak, n_)
    dd   = (n_ - peak) / peak
    dd_series.append(dd * 100)
    max_dd = min(max_dd, dd)

open_count = sum(1 for p in positions if p['status'] == 'open')
excluded_count = len(EXCLUDE_IDS)

# ══════════════════════════════════════════════════════════════
# 控制台输出
# ══════════════════════════════════════════════════════════════
SEP = "=" * 90
sep = "-" * 90
print(SEP)
print(f"  期货账户复盘  |  初始1000万  |  每笔保证金20万（固定）")
print(f"  剔除数据异常: {excluded_count} 笔 {EXCLUDE_IDS}")
print(SEP)
print(f"  已平仓笔数:  {total}    持仓中: {open_count}")
print(f"  盈利: {len(wins)}笔   亏损: {len(losses)}笔   胜率: {win_rate:.1f}%")
print(f"  平均盈利: +{avg_pnl_win/10000:.2f}万    平均亏损: {avg_pnl_loss/10000:.2f}万")
print(sep)
print(f"  最终净值:  {navs[-1]:.4f}   ({(navs[-1]-1)*100:+.2f}%)")
print(f"  最终账户:  {account/10000:.2f} 万元  (初始1000万)")
print(f"  累计盈亏:  {total_pnl/10000:+.2f} 万元")
print(f"  最大回撤:  {max_dd*100:.2f}%")
print(SEP)

# 表头
hdr = (f"{'品种':7} {'方':1} {'结果':4} "
       f"{'乘数/单位':>10} {'每tick值':>8} {'每手保证金':>10} "
       f"{'手数':>5} {'保证金合计':>10} "
       f"{'每手盈亏(元)':>12} {'总盈亏(元)':>12} {'账户影响%':>9} {'净值':>7}")
print(hdr)
print(sep)
for t in trade_rows:
    lot_spec = f"{t['mult']}{t['unit']}"
    print(
        f"{t['symbol']:7} {t['dir']:1} {t['result']:4} "
        f"{lot_spec:>10} {t['tick_val']:>8.0f}元 {t['margin_per_lot']:>10,.0f} "
        f"{t['n']:>5} {t['margin_used']:>10,.0f} "
        f"{t['pnl_per_lot']:>+12,.1f} {t['pnl_rmb']:>+12,.0f} "
        f"{t['chg_pct']:>+9.2f}% {t['nav']:>7.4f}"
    )
print(SEP)

# ══════════════════════════════════════════════════════════════
# 专业风格净值图（左图：净值+回撤  右侧：统计面板）
# ══════════════════════════════════════════════════════════════
BG      = '#10141c'   # 深海蓝背景
PANEL   = '#161d2b'   # 面板背景
BORDER  = '#253050'   # 边框色
GRID_C  = '#1c2535'   # 网格线
C_UP    = '#26d981'   # 盈利绿
C_DN    = '#f15b63'   # 亏损红
C_LINE  = '#4fc8e8'   # 净值线蓝
C_TEXT  = '#c8d0e0'   # 主文字
C_DIM   = '#6a7a96'   # 次级文字

fig = plt.figure(figsize=(16, 9), facecolor=BG)

# 布局：左侧图表区 72%，右侧统计面板 28%
ax_nav = fig.add_axes([0.05, 0.30, 0.67, 0.62])   # 净值曲线
ax_dd  = fig.add_axes([0.05, 0.07, 0.67, 0.20])   # 回撤带（共享x轴）

for ax in [ax_nav, ax_dd]:
    ax.set_facecolor(BG)
    ax.tick_params(colors=C_DIM, labelsize=8.5, length=3, pad=4)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.spines['left'].set_visible(True)
    ax.spines['left'].set_edgecolor(BORDER)
    ax.spines['left'].set_linewidth(0.8)

# ── X 轴刻度（均匀分布 ~12 个）────────────────────────────
x    = list(range(len(navs)))
n_tk = min(12, len(x))
step = max(1, (len(x) - 1) // n_tk)
tick_x  = [0] + list(range(step, len(x), step))
if tick_x[-1] != len(x) - 1:
    tick_x.append(len(x) - 1)
tick_lb = [times[i] for i in tick_x]

# ── 净值曲线 ────────────────────────────────────────────────
baseline = [1.0] * len(navs)
ax_nav.fill_between(x, baseline, navs,
                    where=[v >= 1.0 for v in navs],
                    color=C_UP, alpha=0.10, interpolate=True)
ax_nav.fill_between(x, baseline, navs,
                    where=[v < 1.0 for v in navs],
                    color=C_DN, alpha=0.15, interpolate=True)

ax_nav.plot(x, navs, color=C_LINE, lw=2.2, zorder=5, solid_capstyle='round')
ax_nav.axhline(1.0, color=BORDER, lw=1.0, ls='-', zorder=3)

# 交易点
for i, t in enumerate(trade_rows, 1):
    c = C_UP if t['pnl_rmb'] > 0 else C_DN
    ax_nav.scatter(i, navs[i], color=c, s=42, zorder=6,
                   alpha=0.9, linewidths=0, edgecolors='none')

# 最终净值标注（右侧）
final = navs[-1]
ax_nav.annotate(
    f' {final:.4f} ({(final-1)*100:+.1f}%)',
    xy=(x[-1], final),
    xytext=(x[-1] + 0.5, final),
    fontproperties=zf(9.5), color=C_LINE,
    va='center', ha='left',
    xycoords='data', textcoords='data',
    annotation_clip=False,
)

ax_nav.set_xlim(-1, len(x) + 2)
y_lo = min(navs) * 0.997
y_hi = max(navs) * 1.003
ax_nav.set_ylim(y_lo, y_hi)
ax_nav.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.3f}'))
ax_nav.set_ylabel('净  值', fontproperties=zf(10), color=C_DIM, labelpad=10)
ax_nav.grid(axis='y', color=GRID_C, lw=0.8, linestyle='-')
ax_nav.set_xticks([])

# 标题
ax_nav.text(0.0, 1.04,
            '期货账户净值曲线',
            transform=ax_nav.transAxes,
            fontproperties=zf(14), color=C_TEXT, va='bottom')
ax_nav.text(0.0, 1.005,
            f'初始资金 1,000 万  ·  每笔固定保证金 20 万  ·  已平仓 {total} 笔  ·  持仓中 {open_count} 笔',
            transform=ax_nav.transAxes,
            fontproperties=zf(9), color=C_DIM, va='bottom')

# ── 回撤带 ──────────────────────────────────────────────────
ax_dd.fill_between(x, 0, dd_series, color=C_DN, alpha=0.45, interpolate=True)
ax_dd.plot(x, dd_series, color=C_DN, lw=1.0, alpha=0.7)
ax_dd.axhline(0, color=BORDER, lw=0.8)
ax_dd.set_xlim(-1, len(x) + 2)
y_dd_lo = min(dd_series) * 1.3
ax_dd.set_ylim(y_dd_lo, 0.4)
ax_dd.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.1f}%'))
ax_dd.set_ylabel('回  撤', fontproperties=zf(10), color=C_DIM, labelpad=10)
ax_dd.grid(axis='y', color=GRID_C, lw=0.8)
ax_dd.set_xticks(tick_x)
ax_dd.set_xticklabels(tick_lb, fontproperties=zf(8), color=C_DIM, rotation=40, ha='right')

# 最大回撤标注
min_dd_i = int(np.argmin(dd_series))
ax_dd.annotate(
    f' 最大回撤 {max_dd*100:.2f}%',
    xy=(min_dd_i, dd_series[min_dd_i]),
    xytext=(min_dd_i, dd_series[min_dd_i] * 0.5),
    fontproperties=zf(8.5), color=C_DN, va='center', ha='left',
    annotation_clip=False,
)

# ── 右侧统计面板 ─────────────────────────────────────────────
panel_l, panel_b = 0.755, 0.07
panel_w, panel_h = 0.225, 0.855

# 面板背景
from matplotlib.patches import FancyBboxPatch
panel_rect = FancyBboxPatch(
    (panel_l, panel_b), panel_w, panel_h,
    boxstyle="round,pad=0.005",
    transform=fig.transFigure,
    facecolor=PANEL, edgecolor=BORDER, linewidth=1.0,
    zorder=0, clip_on=False
)
fig.add_artist(panel_rect)

ax_stat = fig.add_axes([panel_l + 0.01, panel_b + 0.01,
                        panel_w - 0.02, panel_h - 0.02])
ax_stat.set_facecolor(PANEL)
ax_stat.axis('off')
for sp in ax_stat.spines.values():
    sp.set_visible(False)

# 数据行
wr = win_rate
pr = abs(avg_pnl_win / avg_pnl_loss) if avg_pnl_loss else 0
rows = [
    ('─── 账户概况 ───',   '',               True),
    ('初始资金',           '1,000.00 万',    False),
    ('最终资产',           f'{account/10000:.2f} 万', False),
    ('累计盈亏',           f'{total_pnl/10000:+.2f} 万', False),
    ('总收益率',           f'{(final-1)*100:+.2f}%', False),
    ('最大回撤',           f'{max_dd*100:.2f}%', False),
    ('',                   '',               False),
    ('─── 交易统计 ───',   '',               True),
    ('已平仓笔数',         f'{total}',       False),
    ('持仓中',             f'{open_count}',  False),
    ('盈利笔数',           f'{len(wins)}  ({wr:.1f}%)', False),
    ('亏损笔数',           f'{len(losses)}', False),
    ('平均盈利',           f'+{avg_pnl_win/10000:.2f} 万', False),
    ('平均亏损',           f'{avg_pnl_loss/10000:.2f} 万', False),
    ('盈亏比',             f'{pr:.2f} : 1',  False),
    ('',                   '',               False),
    ('─── 仓位参数 ───',   '',               True),
    ('每笔保证金',         '20 万（固定）',   False),
]

n_rows = len(rows)
row_h  = 1.0 / (n_rows + 1)

for i, (label, val, is_header) in enumerate(rows):
    y = 1.0 - (i + 0.8) * row_h
    if is_header:
        ax_stat.text(0.5, y, label,
                     fontproperties=zf(9), color='#5a8fc8',
                     ha='center', va='center',
                     transform=ax_stat.transAxes)
    elif label:
        ax_stat.text(0.04, y, label,
                     fontproperties=zf(9.5), color=C_DIM,
                     ha='left', va='center',
                     transform=ax_stat.transAxes)
        # 盈亏相关数值用颜色区分
        val_color = C_TEXT
        if '+' in val and '万' in val:
            val_color = C_UP
        elif val.startswith('-') and ('万' in val or '%' in val):
            val_color = C_DN
        ax_stat.text(0.97, y, val,
                     fontproperties=zf(9.5), color=val_color,
                     ha='right', va='center',
                     transform=ax_stat.transAxes)
        # 分割线（用 plot 代替 axhline，因 axhline 不支持 transform 参数）
        ax_stat.plot([0.04, 0.96], [y - row_h * 0.45, y - row_h * 0.45],
                     color=GRID_C, lw=0.5,
                     transform=ax_stat.transAxes)

# 面板标题
ax_stat.text(0.5, 0.985, '统 计 摘 要',
             fontproperties=zf(11), color=C_TEXT,
             ha='center', va='top',
             transform=ax_stat.transAxes)
ax_stat.plot([0, 1], [0.975, 0.975],
             color=BORDER, lw=1.0,
             transform=ax_stat.transAxes)

# ── 保存 ─────────────────────────────────────────────────────
out = os.path.join(_here, '../futures-monitor/public/nav_curve.png')
plt.savefig(out, dpi=160, bbox_inches='tight', facecolor=BG)
print(f"\n图表已保存 → {out}")
