import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

signals = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl', 'rb'))
signals['date'] = pd.to_datetime(signals['date'])

# Calculate PnL for each signal with different SL/TP
def calc_pnl(row, sl_pct, tp_pct):
    entry = row['entry']
    direction = row['direction']
    
    if direction == 'SHORT':
        sl_price = entry * (1 + sl_pct)
        tp_price = entry * (1 - tp_pct)
        # Check if SL hit (day_high >= sl_price)
        sl_hit = row['day_high'] >= sl_price
        tp_hit = row['day_low'] <= tp_price
        
        if sl_hit and tp_hit:
            # Both hit - use close to determine (conservative: SL)
            if row['day_close'] >= entry:
                return -sl_pct  # SL hit first
            else:
                return tp_pct   # TP hit first
        elif sl_hit:
            return -sl_pct
        elif tp_hit:
            return tp_pct
        else:
            # Neither hit - force close at close
            return (entry - row['day_close']) / entry
    else:  # LONG
        sl_price = entry * (1 - sl_pct)
        tp_price = entry * (1 + tp_pct)
        sl_hit = row['day_low'] <= sl_price
        tp_hit = row['day_high'] >= tp_price
        
        if sl_hit and tp_hit:
            if row['day_close'] <= entry:
                return -sl_pct
            else:
                return tp_pct
        elif sl_hit:
            return -sl_pct
        elif tp_hit:
            return tp_pct
        else:
            return (row['day_close'] - entry) / entry

# Test different SL/TP combos on 16-year data
print("=== SL/TP Optimization (16-year daily data) ===")
print(f"Signals: {len(signals)}")

results = []
for sl in [0.03, 0.04, 0.05, 0.06, 0.07, 0.08]:
    for tp in [0.03, 0.04, 0.05, 0.06, 0.07, 0.08]:
        pnl = signals.apply(lambda r: calc_pnl(r, sl, tp), axis=1)
        signals['_pnl'] = pnl
        
        # Simple equal-weight backtest
        daily = signals.groupby('date')['_pnl'].mean()  # avg per signal
        daily_ret = daily * 0.05  # assume 5% position per trade
        
        cum = (1 + daily_ret).cumprod()
        years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
        cagr = cum.iloc[-1] ** (1/years) - 1
        mdd = ((cum - cum.cummax()) / cum.cummax()).min()
        wr = (pnl > 0).mean()
        sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
        
        results.append({
            'sl': sl, 'tp': tp, 'cagr': cagr, 'mdd': mdd,
            'sharpe': sharpe, 'win_rate': wr,
            'calmar': cagr / abs(mdd) if mdd != 0 else 0,
            'avg_pnl': pnl.mean(),
        })

res_df = pd.DataFrame(results)
print("\nTop by Calmar:")
for _, r in res_df.nlargest(10, 'calmar').iterrows():
    print(f"  SL={r['sl']*100:.0f}% TP={r['tp']*100:.0f}% CAGR={r['cagr']*100:.0f}% "
          f"MDD={r['mdd']*100:.1f}% Sharpe={r['sharpe']:.1f} WR={r['win_rate']*100:.0f}% "
          f"avg_pnl={r['avg_pnl']*100:.3f}%")

print("\nTop by Sharpe:")
for _, r in res_df.nlargest(10, 'sharpe').iterrows():
    print(f"  SL={r['sl']*100:.0f}% TP={r['tp']*100:.0f}% CAGR={r['cagr']*100:.0f}% "
          f"MDD={r['mdd']*100:.1f}% Sharpe={r['sharpe']:.1f} WR={r['win_rate']*100:.0f}%")

# Also test gap threshold
print("\n\n=== Gap Threshold Optimization ===")
for threshold in [0.03, 0.04, 0.05, 0.06, 0.07, 0.08]:
    subset = signals[abs(signals['adj_gap']) >= threshold]
    if len(subset) < 100:
        continue
    pnl = subset.apply(lambda r: calc_pnl(r, 0.05, 0.05), axis=1)
    daily = subset.groupby('date').apply(lambda g: g.apply(lambda r: calc_pnl(r, 0.05, 0.05), axis=1).mean())
    daily_ret = daily * 0.05
    cum = (1 + daily_ret).cumprod()
    years = (daily_ret.index[-1] - daily_ret.index[0]).days / 365.25
    cagr = cum.iloc[-1] ** (1/years) - 1
    mdd = ((cum - cum.cummax()) / cum.cummax()).min()
    wr = (pnl > 0).mean()
    print(f"  Gap>={threshold*100:.0f}%: signals={len(subset)}, WR={wr*100:.1f}%, "
          f"CAGR={cagr*100:.0f}%, MDD={mdd*100:.1f}%, avg_pnl={pnl.mean()*100:.3f}%")
