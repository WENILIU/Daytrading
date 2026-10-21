import pickle, pandas as pd, numpy as np

OUTPUT_DIR = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs'

sig = pd.read_pickle(f'{OUTPUT_DIR}/gap_fade_signals_2010.pkl')
sig['date'] = pd.to_datetime(sig['date'])

CAPITAL = 4_500_000
SL_PCT = 0.06
TP_PCT = 0.04
GAP_THRESHOLD = 0.05
MIN_PRICE = 30
MAX_PRICE = 225
MAX_POS = 10
MAX_EXP = 0.50
COST = 0.0017

# Filter
subset = sig[sig['direction'] == 'SHORT'].copy()
subset = subset[subset['adj_gap'] >= GAP_THRESHOLD]
subset = subset[(subset['entry'] >= MIN_PRICE) & (subset['entry'] <= MAX_PRICE)]

# PnL
sl_price = subset['entry'] * (1 + SL_PCT)
tp_price = subset['entry'] * (1 - TP_PCT)
hit_sl = subset['day_high'] >= sl_price
hit_tp = subset['day_low'] <= tp_price
pnl = np.where(hit_tp, TP_PCT, np.where(hit_sl, -SL_PCT, (subset['entry'] - subset['day_close']) / subset['entry']))
subset['pnl'] = pnl - COST

# === 1 張 ONLY ===
print('=' * 70)
print('COMPARISON: 1張 only vs 多張 (450萬)')
print('=' * 70)

# Scenario A: 1 張 only
subset['shares_1z'] = 1000
subset['pos_1z'] = (subset['shares_1z'] * subset['entry']) / CAPITAL

# Scenario B: 5%/2.5% sizing (original)
subset['base_pos'] = np.where(subset['adj_gap'] > 0.07, 0.05, 0.025)
subset['shares_multi'] = np.floor(subset['base_pos'] * CAPITAL / subset['entry'] / 1000).astype(int) * 1000
subset['pos_multi'] = (subset['shares_multi'] * subset['entry']) / CAPITAL
# Remove if < 1 張
valid_multi = subset['shares_multi'] >= 1000

# Daily limits for 1張 scenario
s1 = subset.copy()
s1 = s1.sort_values(['date', 'adj_gap'], ascending=[True, False])
s1['day_rank'] = s1.groupby('date').cumcount()
s1 = s1[s1['day_rank'] < MAX_POS]
s1['cum_exp'] = s1.groupby('date')['pos_1z'].cumsum()
s1 = s1[s1['cum_exp'] <= MAX_EXP]
s1['dollar_pnl'] = s1['pnl'] * s1['pos_1z'] * CAPITAL

# Daily limits for multi-張 scenario
s2 = subset[valid_multi].copy()
s2 = s2.sort_values(['date', 'adj_gap'], ascending=[True, False])
s2['day_rank'] = s2.groupby('date').cumcount()
s2 = s2[s2['day_rank'] < MAX_POS]
s2['cum_exp'] = s2.groupby('date')['pos_multi'].cumsum()
s2 = s2[s2['cum_exp'] <= MAX_EXP]
s2['dollar_pnl'] = s2['pnl'] * s2['pos_multi'] * CAPITAL

def calc_metrics(dollar_pnl_series, trades_df, label):
    daily_pnl = dollar_pnl_series.groupby(trades_df['date']).sum()
    daily_ret = daily_pnl / CAPITAL
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    cagr = cum.iloc[-1] ** (1/years) - 1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
    
    print(f'\n  [{label}]')
    print(f'    Trades: {len(trades_df)} | Days: {len(daily_pnl)} | Trades/day: {len(trades_df)/len(daily_pnl):.1f}')
    print(f'    WR: {(trades_df["pnl"]>0).mean()*100:.1f}%')
    print(f'    CAGR: {cagr*100:.1f}% | MDD: {mdd*100:.1f}% | Sharpe: {sharpe:.1f}')
    print(f'    Total PnL: {daily_pnl.sum():,.0f}')
    print(f'    Avg position: {trades_df.iloc[:, [c for c in trades_df.columns if c.startswith("pos_")][0]].mean()*100:.2f}%')
    print(f'    Avg dollar/trade: {trades_df["dollar_pnl"].abs().mean()/trades_df["pnl"].abs().mean() if (trades_df["pnl"].abs().mean()>0) else 0:,.0f}')
    
    # Annual
    print(f'    Annual:')
    for yr in sorted(daily_pnl.index.year.unique()):
        yr_pnl = daily_pnl[daily_pnl.index.year == yr]
        yr_ret = yr_pnl.sum() / CAPITAL * 100
        yr_n = len(trades_df[trades_df['date'].dt.year == yr])
        print(f'      {yr}: {yr_ret:+6.1f}% ({yr_n} trades)')
    
    return cagr, mdd, sharpe

# Position size analysis for 1張
print(f'\n  1張 position sizes by stock price:')
for price_range in [(30,50), (50,100), (100,150), (150,200), (200,225)]:
    mask = (subset['entry'] >= price_range[0]) & (subset['entry'] < price_range[1])
    n = mask.sum()
    if n > 0:
        avg_pos = (1000 * subset.loc[mask, 'entry'].mean()) / CAPITAL * 100
        print(f'    {price_range[0]}-{price_range[1]} TWD: {n} signals, 1張={1000*subset.loc[mask,"entry"].mean():,.0f} ({avg_pos:.2f}% of capital)')

print(f'\n  Multi-張 position sizes:')
for price_range in [(30,50), (50,100), (100,150), (150,200), (200,225)]:
    mask = (subset['entry'] >= price_range[0]) & (subset['entry'] < price_range[1]) & valid_multi
    n = mask.sum()
    if n > 0:
        avg_shares = subset.loc[mask, 'shares_multi'].mean()
        avg_pos = subset.loc[mask, 'pos_multi'].mean() * 100
        print(f'    {price_range[0]}-{price_range[1]} TWD: {n} signals, avg {avg_shares/1000:.1f} 張 ({avg_pos:.2f}%)')

# Run both
c1 = calc_metrics(s1['dollar_pnl'], s1, '1張 ONLY (realistic)')
c2 = calc_metrics(s2['dollar_pnl'], s2, 'Multi-張 (backtest assumption)')

# Key difference
print(f'\n{"=" * 70}')
print('KEY DIFFERENCE')
print(f'{"=" * 70}')
print(f'  CAGR: 1張={c1[0]*100:.1f}% vs Multi={c2[0]*100:.1f}% (diff: {(c2[0]-c1[0])*100:.0f}%)')
print(f'  MDD:  1張={c1[1]*100:.1f}% vs Multi={c2[1]*100:.1f}%')
print(f'  Sharpe: 1張={c1[2]:.1f} vs Multi={c2[2]:.1f}')
print(f'  Trades: 1張={len(s1)} vs Multi={len(s2)}')
print(f'  Avg pos: 1張={s1["pos_1z"].mean()*100:.2f}% vs Multi={s2["pos_multi"].mean()*100:.2f}%')
