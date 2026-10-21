import pandas as pd, numpy as np

df = pd.read_csv('volume_features.csv', parse_dates=['date'])
df['vol5_vs_prev'] = df['vol_first5'] / df['vol_prev']

print("=" * 70)
print("STRATEGY IMPACT ANALYSIS: 9:05 Confirmation Filter")
print("=" * 70)
print()

# SHORT filter: price must drop >0.5% in first 5min
short = df[df['direction']=='SHORT'].copy()
short_take = short[short['price_chg_5min'] < -0.005]
short_skip = short[short['price_chg_5min'] >= -0.005]

print("SHORT (all market conditions):")
print(f"  Original: {len(short)} signals, WR={short['win'].mean()*100:.1f}%, PnL={short['pnl'].mean()*100:+.2f}%")
print(f"  TAKE (drop>0.5%): {len(short_take)} signals, WR={short_take['win'].mean()*100:.1f}%, PnL={short_take['pnl'].mean()*100:+.2f}%")
print(f"  SKIP:             {len(short_skip)} signals, WR={short_skip['win'].mean()*100:.1f}%, PnL={short_skip['pnl'].mean()*100:+.2f}%")
print()

# LONG filter: price must rise >1% in first 5min
long_df = df[df['direction']=='LONG'].copy()
long_take = long_df[long_df['price_chg_5min'] > 0.01]
long_skip = long_df[long_df['price_chg_5min'] <= 0.01]

print("LONG (all market conditions):")
print(f"  Original: {len(long_df)} signals, WR={long_df['win'].mean()*100:.1f}%, PnL={long_df['pnl'].mean()*100:+.2f}%")
print(f"  TAKE (rise>1%): {len(long_take)} signals, WR={long_take['win'].mean()*100:.1f}%, PnL={long_take['pnl'].mean()*100:+.2f}%")
print(f"  SKIP:           {len(long_skip)} signals, WR={long_skip['win'].mean()*100:.1f}%, PnL={long_skip['pnl'].mean()*100:+.2f}%")
print()

# Combined strategy
combined_take = pd.concat([short_take, long_take])
combined_skip = pd.concat([short_skip, long_skip])
print("COMBINED (with 9:05 filter):")
print(f"  TAKE: {len(combined_take)} signals, WR={combined_take['win'].mean()*100:.1f}%, PnL={combined_take['pnl'].mean()*100:+.2f}%")
print(f"  SKIP: {len(combined_skip)} signals, WR={combined_skip['win'].mean()*100:.1f}%, PnL={combined_skip['pnl'].mean()*100:+.2f}%")
print()

# Monthly performance comparison
print("=== MONTHLY COMPARISON ===")
combined_take['month'] = combined_take['date'].dt.to_period('M')
combined_skip['month'] = combined_skip['date'].dt.to_period('M')
df['month'] = df['date'].dt.to_period('M')

monthly_orig = df.groupby('month').agg(
    trades=('pnl','count'),
    total_pnl=('pnl','sum'),
    wr=('win','mean')
)
monthly_filtered = combined_take.groupby('month').agg(
    trades=('pnl','count'),
    total_pnl=('pnl','sum'),
    wr=('win','mean')
)

# Compare by year
df['year'] = df['date'].dt.year
combined_take['year'] = combined_take['date'].dt.year

print(f"{'Year':<6} {'Orig Trades':>11} {'Orig WR':>8} {'Orig PnL':>9} | {'Filt Trades':>11} {'Filt WR':>8} {'Filt PnL':>9} | {'Improvement':>11}")
print("-" * 95)
for year in sorted(df['year'].unique()):
    orig = df[df['year']==year]
    filt = combined_take[combined_take['year']==year]
    if len(orig)==0: continue
    o_wr = orig['win'].mean()*100
    o_pnl = orig['pnl'].sum()*100
    if len(filt)==0:
        print(f"{year:<6} {len(orig):>11} {o_wr:>7.1f}% {o_pnl:>+8.1f}% | {'0':>11} {'N/A':>8} {'N/A':>9}")
        continue
    f_wr = filt['win'].mean()*100
    f_pnl = filt['pnl'].sum()*100
    diff = f_pnl - o_pnl
    print(f"{year:<6} {len(orig):>11} {o_wr:>7.1f}% {o_pnl:>+8.1f}% | {len(filt):>11} {f_wr:>7.1f}% {f_pnl:>+8.1f}% | {diff:>+10.1f}%")
print()

# Key metrics
print("=== KEY METRICS ===")
print(f"Trade reduction: {len(df)} -> {len(combined_take)} ({(1-len(combined_take)/len(df))*100:.0f}% fewer trades)")
print(f"WR improvement:  {df['win'].mean()*100:.1f}% -> {combined_take['win'].mean()*100:.1f}%")
print(f"Avg PnL/trade:   {df['pnl'].mean()*100:.2f}% -> {combined_take['pnl'].mean()*100:.2f}%")
print(f"Total PnL:       {df['pnl'].sum()*100:.1f}% -> {combined_take['pnl'].sum()*100:.1f}%")
print()

# What about the gap-and-go reject as additional filter?
print("=== ADDITIONAL: Gap-and-Go reject (vol5/prev>50% + price up) ===")
gag = combined_take[(combined_take['price_chg_5min'] > 0) & (combined_take['vol5_vs_prev'] > 0.5)]
clean = combined_take[~((combined_take['price_chg_5min'] > 0) & (combined_take['vol5_vs_prev'] > 0.5))]
if len(gag) > 0:
    print(f"  Gap-and-Go: {len(gag)} signals, WR={gag['win'].mean()*100:.1f}%, PnL={gag['pnl'].mean()*100:+.2f}%")
    print(f"  Clean:      {len(clean)} signals, WR={clean['win'].mean()*100:.1f}%, PnL={clean['pnl'].mean()*100:+.2f}%")
