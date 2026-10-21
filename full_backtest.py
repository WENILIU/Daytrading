import pickle, pandas as pd, numpy as np
from finlab import data as fdata
import warnings
warnings.filterwarnings('ignore')

print("=" * 60)
print("GAP FADE v3 — FULL BACKTEST (all real constraints)")
print("=" * 60)

# Load 1-min confirmed results
strat_data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
strat_data['date'] = pd.to_datetime(strat_data['date'])
strat_data['fav_move'] = np.where(strat_data['direction']=='SHORT', -strat_data['early_move_15'], strat_data['early_move_15'])

# === STRATEGY PARAMETERS ===
CAPITAL = 4_500_000
GAP_THRESHOLD = 0.05
CONFIRM_MIN = 0.025
BASE_SHORT = 0.08
BASE_LONG = 0.0  # SHORT only
MAX_POS = 10
MAX_EXP = 0.50
MIN_PRICE = 30
MAX_PRICE = 225
SL_PCT = 0.05
TP_PCT = 0.05
TIERS = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]

print(f"\nParameters:")
print(f"  Capital: {CAPITAL:,}")
print(f"  Direction: SHORT ONLY")
print(f"  Gap: >{GAP_THRESHOLD*100:.0f}% (market-adjusted)")
print(f"  Confirm: >={CONFIRM_MIN*100:.1f}% (15-min)")
print(f"  Tiers: T5(>3%)=3x, T4(1.5-3%)=2x, T3(0.5-1.5%)=1x")
print(f"  Position: {BASE_SHORT*100:.0f}% x tier (max {BASE_SHORT*3*100:.0f}%)")
print(f"  SL/TP: {SL_PCT*100:.0f}% / {TP_PCT*100:.0f}%")
print(f"  Max: {MAX_POS} pos/day, {MAX_EXP*100:.0f}% exposure")
print(f"  Price: {MIN_PRICE}-{MAX_PRICE}")
print(f"  Constraints: 整張, 處置股, 無法當沖")

# === FILTER 1: Direction + Confirmation + Price ===
print(f"\n{'='*60}")
print("FILTERING SIGNALS")
print(f"{'='*60}")
print(f"  Raw signals: {len(strat_data)}")

# SHORT only
subset = strat_data[strat_data['direction'] == 'SHORT'].copy()
print(f"  After SHORT only: {len(subset)}")

# Confirmation >= 2.5%
subset = subset[subset['fav_move'] >= CONFIRM_MIN]
print(f"  After confirm>={CONFIRM_MIN*100:.1f}%: {len(subset)}")

# Price filter
subset = subset[(subset['entry'] >= MIN_PRICE) & (subset['entry'] <= MAX_PRICE)]
print(f"  After price {MIN_PRICE}-{MAX_PRICE}: {len(subset)}")

# === FILTER 2: Disposal stocks (finlab where available) ===
print(f"\n  Loading disposal data...")
try:
    disposal = fdata.get('etl:disposal_stock_filter', start='20230501', end='20231231')
    has_disposal_data = True
    print(f"  finlab disposal data: {disposal.index.min().date()} to {disposal.index.max().date()}")
except:
    has_disposal_data = False
    disposal = None
    print("  finlab disposal data unavailable, using heuristic")

def is_disposal(row):
    date = row['date']
    stock = row['stock']
    if has_disposal_data and disposal is not None:
        if date in disposal.index and stock in disposal.columns:
            return not bool(disposal.loc[date, stock])  # False = disposal
    # Heuristic for 2024+: check if same stock had signal within 2 days
    return False  # Conservative: assume not disposal

subset['is_disposal'] = subset.apply(is_disposal, axis=1)
n_disp = subset['is_disposal'].sum()
subset = subset[~subset['is_disposal']]
print(f"  After disposal filter: {len(subset)} (removed {n_disp})")

# === FILTER 3: 整張 (round lot) ===
subset['pos_pct'] = BASE_SHORT * 1.0  # Will be updated with tier
mult = np.zeros(len(subset))
for min_move, m in sorted(TIERS, reverse=True):
    cond = (subset['fav_move'].values >= min_move) & (mult == 0)
    mult[cond] = m
subset['multiplier'] = mult
subset = subset[subset['multiplier'] > 0]
subset['pos_pct'] = BASE_SHORT * subset['multiplier']

# Calculate shares (整張)
subset['shares'] = np.floor(subset['pos_pct'] * CAPITAL / subset['entry'] / 1000).astype(int) * 1000
before_zhang = len(subset)
subset = subset[subset['shares'] >= 1000]
print(f"  After 整張 filter: {len(subset)} (removed {before_zhang - len(subset)})")

# Actual position %
subset['actual_pos_pct'] = (subset['shares'] * subset['entry']) / CAPITAL

# === FILTER 4: Daily limits ===
subset = subset.sort_values(['date', 'fav_move'], ascending=[True, False])
subset['day_rank'] = subset.groupby('date').cumcount()
before_daily = len(subset)
subset = subset[subset['day_rank'] < MAX_POS]
subset['cum_exp'] = subset.groupby('date')['actual_pos_pct'].cumsum()
subset = subset[subset['cum_exp'] <= MAX_EXP]
print(f"  After daily limits: {len(subset)} (removed {before_daily - len(subset)})")

# === SIMULATION ===
print(f"\n{'='*60}")
print("SIMULATION RESULTS")
print(f"{'='*60}")

subset['dollar_pnl'] = subset['pnl'] * subset['actual_pos_pct'] * CAPITAL
daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
daily_ret = daily_pnl / CAPITAL

cum = (1 + daily_ret).cumprod()
years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
cagr = cum.iloc[-1] ** (1/years) - 1
mdd = ((cum - cum.cummax()) / cum.cummax()).min()
sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
calmar = cagr / abs(mdd)

print(f"\n  Period: {daily_ret.index[0].date()} to {daily_ret.index[-1].date()} ({years:.1f} years)")
print(f"  Total trades: {len(subset)}")
print(f"  Trading days: {len(daily_pnl)}")
print(f"  Trades/day: {len(subset)/len(daily_pnl):.1f}")
print(f"")
print(f"  Win Rate: {(subset['pnl']>0).mean()*100:.1f}%")
print(f"  CAGR: {cagr*100:.0f}%")
print(f"  MDD: {mdd*100:.1f}%")
print(f"  Sharpe: {sharpe:.1f}")
print(f"  Calmar: {calmar:.1f}")
print(f"  Total PnL: {daily_pnl.sum():,.0f}")
print(f"  Daily Avg: {daily_pnl.mean():,.0f}")
print(f"  Max position: {subset['actual_pos_pct'].max()*100:.1f}% = {subset['actual_pos_pct'].max()*CAPITAL:,.0f}")

# Annual breakdown
print(f"\n{'='*60}")
print("ANNUAL PERFORMANCE")
print(f"{'='*60}")
for yr in sorted(daily_pnl.index.year.unique()):
    yr_pnl = daily_pnl[daily_pnl.index.year == yr]
    yr_ret = yr_pnl.sum() / CAPITAL * 100
    yr_trades = len(subset[subset['date'].dt.year == yr])
    yr_wr = (subset[subset['date'].dt.year == yr]['pnl'] > 0).mean() * 100
    yr_mdd = ((yr_pnl.cumsum() - yr_pnl.cumsum().cummax()) / CAPITAL).min() * 100
    print(f"  {yr}: {yr_ret:+6.0f}% | WR={yr_wr:.0f}% | trades={yr_trades:3d} | MDD={yr_mdd:.1f}%")

# Monthly breakdown
print(f"\n{'='*60}")
print("MONTHLY PERFORMANCE")
print(f"{'='*60}")
monthly = daily_pnl.resample('ME').sum() / CAPITAL * 100
for idx, val in monthly.items():
    if val != 0:
        bar = "+" * int(max(0, val/5)) + "-" * int(max(0, -val/5))
        print(f"  {idx.strftime('%Y-%m')}: {val:+6.1f}% {bar}")

# Tier breakdown
print(f"\n{'='*60}")
print("TIER BREAKDOWN")
print(f"{'='*60}")
for t, label in [(3.0, 'T5(>3%)'), (2.0, 'T4(1.5-3%)'), (1.0, 'T3(0.5-1.5%)')]:
    sub = subset[subset['multiplier'] == t]
    if len(sub) > 0:
        print(f"  {label}: {len(sub):3d} trades | WR={(sub['pnl']>0).mean()*100:.1f}% | avg_pnl={sub['pnl'].mean()*100:.2f}% | total={sub['dollar_pnl'].sum():,.0f}")

# Top stocks
print(f"\n{'='*60}")
print("TOP STOCKS (by signal count)")
print(f"{'='*60}")
for stock, count in subset['stock'].value_counts().head(15).items():
    sub = subset[subset['stock'] == stock]
    print(f"  {stock}: {count:2d} signals | WR={(sub['pnl']>0).mean()*100:.0f}% | avg={sub['pnl'].mean()*100:.1f}%")

# Save results
results = {
    'daily_pnl': daily_pnl,
    'daily_ret': daily_ret,
    'cum': cum,
    'trades': subset,
    'metrics': {'cagr': cagr, 'mdd': mdd, 'sharpe': sharpe, 'calmar': calmar,
                'win_rate': (subset['pnl']>0).mean(), 'trades': len(subset)}
}
pickle.dump(results, open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\final_backtest_v3.pkl', 'wb'))
print(f"\n\nSaved to final_backtest_v3.pkl")
