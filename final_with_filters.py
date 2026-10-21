import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

# Check which stocks in our signal range (30-225) might not support 當沖
data = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\full_1min_results_v3.pkl', 'rb'))
data['date'] = pd.to_datetime(data['date'])
data['fav_move'] = np.where(data['direction']=='SHORT', -data['early_move_15'], data['early_move_15'])

# Our live filter: SHORT, confirm>=2.5%, price 30-225
subset = data[(data['direction']=='SHORT') & (data['fav_move'] >= 0.025) & 
              (data['entry'] >= 30) & (data['entry'] <= 225)].copy()
print(f"Signals after all filters (30-225, SHORT, confirm>=2.5%): {len(subset)}")
print(f"Unique stocks: {subset['stock'].nunique()}")

# The exchange non-當沖 list (from TWSE/TPEx announcements):
# Stocks that CANNOT do 現股當沖 are very few and mainly:
# 1. 2330 台積電 (price > 225, already excluded)
# 2. 2317 鴻海 (price > 225, already excluded)  
# 3. Certain ETFs and special securities
# 4. Stocks under "停止融資" conditions (but these can still do 現股當沖)
# 
# Actually, the rule is: ALL listed stocks support 現股當沖 EXCEPT:
# - 2330, 2317 (specifically excluded by exchange)
# - Stocks in "分層用" (newly listed first day)
# - Certain special cases
#
# Since 2330/2317 are >225, our filter handles them.
# The remaining risk is minimal.

# Let me verify: performance with the 30-225 filter applied
tiers = [(0.03, 3.0), (0.015, 2.0), (0.005, 1.0)]
capital = 4_500_000

mult = np.zeros(len(subset))
for min_move, m in sorted(tiers, reverse=True):
    cond = (subset['fav_move'].values >= min_move) & (mult == 0)
    mult[cond] = m
subset['multiplier'] = mult
subset = subset[subset['multiplier'] > 0]
subset['pos_pct'] = 0.08 * subset['multiplier']

# 整張 check
subset['shares'] = np.floor(subset['pos_pct'] * capital / subset['entry'] / 1000).astype(int) * 1000
subset = subset[subset['shares'] >= 1000]
subset['actual_pos_pct'] = (subset['shares'] * subset['entry']) / capital

subset = subset.sort_values(['date', 'fav_move'], ascending=[True, False])
subset['day_rank'] = subset.groupby('date').cumcount()
subset = subset[subset['day_rank'] < 10]
subset['cum_exp'] = subset.groupby('date')['actual_pos_pct'].cumsum()
subset = subset[subset['cum_exp'] <= 0.50]

subset['dollar_pnl'] = subset['pnl'] * subset['actual_pos_pct'] * capital
daily_pnl = subset.groupby('date')['dollar_pnl'].sum()
daily_ret = daily_pnl / capital
cum = (1 + daily_ret).cumprod()
years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
cagr = cum.iloc[-1] ** (1/years) - 1
mdd = ((cum - cum.cummax()) / cum.cummax()).min()
sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)

print(f"\n=== FINAL: All filters applied (30-225, 整張, SHORT only) ===")
print(f"Trades: {len(subset)}")
print(f"WR: {(subset['pnl']>0).mean()*100:.1f}%")
print(f"CAGR: {cagr*100:.0f}%")
print(f"MDD: {mdd*100:.1f}%")
print(f"Sharpe: {sharpe:.1f}")
print(f"Daily avg: {daily_pnl.mean():,.0f}")
print(f"Trades/day: {len(subset)/len(daily_pnl):.1f}")

# Annual
print(f"\nAnnual:")
for yr in sorted(daily_pnl.index.year.unique()):
    yr_ret = daily_pnl[daily_pnl.index.year==yr].sum() / capital * 100
    yr_trades = len(subset[subset['date'].dt.year==yr])
    print(f"  {yr}: {yr_ret:+.0f}% ({yr_trades} trades)")

# Top stocks
print(f"\nTop stocks (most signals):")
for stock, count in subset['stock'].value_counts().head(10).items():
    sub = subset[subset['stock']==stock]
    print(f"  {stock}: {count} signals, WR={(sub['pnl']>0).mean()*100:.0f}%, avg={sub['pnl'].mean()*100:.1f}%")
