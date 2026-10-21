import pandas as pd, numpy as np

df = pd.read_pickle('gap_fade_signals_2010.pkl')
df['date'] = pd.to_datetime(df['date'])
feat = pd.read_csv('volume_features.csv', parse_dates=['date'])
feat['vol5_vs_prev'] = feat['vol_first5'] / feat['vol_prev']
feat['date_str'] = feat['date'].dt.strftime('%Y-%m-%d')
df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
merged = df.merge(
    feat[['date_str','stock','direction','price_chg_5min','vol5_vs_prev','vol_conc_5']],
    on=['date_str','stock','direction'], how='left'
)
has_data = merged[merged['price_chg_5min'].notna()].copy()

COST = 0.0017; SL = 0.06; TP = 0.04

def sim(row):
    entry = row['entry']; d = row['direction']
    hi = row['day_high']; lo = row['day_low']; cl = row['day_close']
    if d == 'SHORT':
        sl_p = entry*(1+SL); tp_p = entry*(1-TP)
        ep = sl_p if hi>=sl_p else (tp_p if lo<=tp_p else cl)
        return (entry-ep)/entry - 2*COST
    else:
        sl_p = entry*(1-SL); tp_p = entry*(1+TP)
        ep = sl_p if lo<=sl_p else (tp_p if hi>=tp_p else cl)
        return (ep-entry)/entry - 2*COST

has_data['pnl'] = has_data.apply(sim, axis=1)
has_data['win'] = (has_data['pnl'] > 0).astype(int)
has_data['year'] = has_data['date'].dt.year

# Kelly sizing: confirmed=7%, default=5%, negative-EV=3%
has_data['pos_pct'] = 0.05
has_data.loc[(has_data['direction']=='SHORT') & (has_data['price_chg_5min'] < -0.005), 'pos_pct'] = 0.07
has_data.loc[(has_data['direction']=='LONG') & (has_data['price_chg_5min'] > 0.01), 'pos_pct'] = 0.07
has_data.loc[(has_data['direction']=='SHORT') & (has_data['price_chg_5min'] > 0.01), 'pos_pct'] = 0.03
has_data.loc[(has_data['direction']=='LONG') & (has_data['price_chg_5min'] < -0.01), 'pos_pct'] = 0.03

# Compute daily returns with position sizing
has_data['trade_ret'] = has_data['pnl'] * has_data['pos_pct']

def compound(trades, ret_col, label):
    trades = trades.copy().sort_values('date')
    daily = trades.groupby(trades['date'].dt.date)[ret_col].sum().sort_index()
    
    cap = 4_500_000; peak = cap; mdd = 0
    yearly_cap = {}
    for date, ret in daily.items():
        cap *= (1 + ret)
        if cap > peak: peak = cap
        dd = (cap - peak) / peak
        if dd < mdd: mdd = dd
        yearly_cap[date.year] = cap
    
    years = len(set(d.year for d in daily.index))
    cagr = ((cap / 4_500_000) ** (1/max(years,1)) - 1) * 100
    print(f"\n{label}:")
    print(f"  CAGR: {cagr:.1f}% | MDD: {mdd*100:.2f}% | Final: {cap:,.0f}")
    prev = 4_500_000
    for yr in sorted(yearly_cap.keys()):
        yr_ret = (yearly_cap[yr]/prev - 1)*100
        n = len(trades[trades['year']==yr])
        wr = (trades[trades['year']==yr]['pnl']>0).mean()*100
        print(f"  {yr}: {n:4d} trades, WR={wr:.1f}%, Return={yr_ret:+.1f}%")
        prev = yearly_cap[yr]
    return cagr, mdd

# 1. Baseline (uniform 5%)
has_data['ret_uniform'] = has_data['pnl'] * 0.05
compound(has_data, 'ret_uniform', "A) BASELINE (uniform 5%)")

# 2. Reject negative-EV only
reject = (
    ((has_data['direction']=='SHORT') & (has_data['price_chg_5min'] > 0.01)) |
    ((has_data['direction']=='LONG') & (has_data['price_chg_5min'] < -0.01))
)
kept = has_data[~reject].copy()
kept['ret'] = kept['pnl'] * 0.05
compound(kept, 'ret', "B) REJECT negative-EV (SHORT rise>1%, LONG drop>1%)")

# 3. Kelly sizing (all trades, variable position)
compound(has_data, 'trade_ret', "C) KELLY SIZING (confirmed=7%, normal=5%, bad=3%)")

# 4. Best combo: reject worst + Kelly for rest
kept2 = has_data[~reject].copy()
kept2['pos_pct2'] = 0.05
kept2.loc[(kept2['direction']=='SHORT') & (kept2['price_chg_5min'] < -0.005), 'pos_pct2'] = 0.07
kept2.loc[(kept2['direction']=='LONG') & (kept2['price_chg_5min'] > 0.01), 'pos_pct2'] = 0.07
kept2['ret2'] = kept2['pnl'] * kept2['pos_pct2']
compound(kept2, 'ret2', "D) REJECT bad + KELLY upsize confirmed (best of both)")
