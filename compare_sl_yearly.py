"""Non-compounding yearly comparison (fixed 4.5M capital each year)"""
import pandas as pd
import numpy as np

df = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")
df["date"] = pd.to_datetime(df["date"])

tiers = [
    (0.09, 999, 2.5), (0.08, 0.09, 2.0), (0.07, 0.08, 1.8),
    (0.065, 0.07, 1.5), (0.06, 0.065, 1.2), (0.05, 0.06, 1.0),
]

def get_tier_mult(gap):
    for lo, hi, mult in tiers:
        if lo <= abs(gap) < hi:
            return mult
    return 0

def get_tick(price):
    if price < 50: return 0.05
    elif price < 500: return 0.1
    elif price < 5000: return 0.5
    else: return 1.0

def calc_limit_up(prev_close):
    tick = get_tick(prev_close)
    return round(prev_close * 1.10 / tick) * tick

def calc_limit_down(prev_close):
    tick = get_tick(prev_close)
    return round(prev_close * 0.90 / tick) * tick

def backtest_fixed_capital(df, use_dynamic_sl, capital=4_500_000, base_pct=0.05,
                           sl_pct=0.06, tp_pct=0.04, cost=0.0017,
                           max_positions=15, max_exposure=0.70):
    """Each year starts fresh with 4.5M. No compounding."""
    daily_results = []
    
    for date, day_df in df.groupby("date"):
        day_pnl = 0
        day_trades = 0
        total_exposure = 0
        
        day_sorted = day_df.iloc[np.abs(day_df["adj_gap"]).values.argsort()[::-1]]
        
        for _, row in day_sorted.iterrows():
            gap = row["adj_gap"]
            direction = row["direction"]
            entry = row["entry"]
            prev_close = row.get("prev_close", entry / (1 + gap))
            day_high = row["day_high"]
            day_low = row["day_low"]
            day_close = row["day_close"]
            
            mult = get_tier_mult(gap)
            if mult == 0:
                continue
            if day_trades >= max_positions:
                break
            
            pos_value = capital * base_pct * mult
            shares = int(pos_value / entry / 1000) * 1000
            if shares < 1000:
                continue
            
            actual_val = shares * entry
            if total_exposure + actual_val > capital * max_exposure:
                continue
            total_exposure += actual_val
            
            if use_dynamic_sl:
                tick = get_tick(entry)
                if direction == "SHORT":
                    limit_up = calc_limit_up(prev_close)
                    sl_price = min(entry * (1 + sl_pct), limit_up - tick)
                else:
                    limit_down = calc_limit_down(prev_close)
                    sl_price = max(entry * (1 - sl_pct), limit_down + tick)
            else:
                if direction == "SHORT":
                    sl_price = entry * (1 + sl_pct)
                else:
                    sl_price = entry * (1 - sl_pct)
            
            if direction == "SHORT":
                tp_price = entry * (1 - tp_pct)
            else:
                tp_price = entry * (1 + tp_pct)
            
            if direction == "SHORT":
                sl_hit = day_high >= sl_price
                tp_hit = day_low <= tp_price
                if sl_hit:
                    exit_price = sl_price
                elif tp_hit:
                    exit_price = tp_price
                else:
                    exit_price = day_close
                pnl_pct = (entry - exit_price) / entry - 2 * cost
            else:
                sl_hit = day_low <= sl_price
                tp_hit = day_high >= tp_price
                if sl_hit:
                    exit_price = sl_price
                elif tp_hit:
                    exit_price = tp_price
                else:
                    exit_price = day_close
                pnl_pct = (exit_price - entry) / entry - 2 * cost
            
            pnl_dollar = pnl_pct * shares * entry
            day_pnl += pnl_dollar
            day_trades += 1
        
        daily_results.append({"date": date, "pnl": day_pnl, "trades": day_trades})
    
    return pd.DataFrame(daily_results)

print("Running Fixed SL 6%...")
res_f = backtest_fixed_capital(df, use_dynamic_sl=False)
print("Running Dynamic SL...")
res_d = backtest_fixed_capital(df, use_dynamic_sl=True)

capital = 4_500_000

for label, res in [("Fixed SL 6%", res_f), ("Dynamic SL", res_d)]:
    res["year"] = res["date"].dt.year
    yearly = res.groupby("year").agg(pnl=("pnl","sum"), trades=("trades","sum"))
    yearly["ret%"] = yearly["pnl"] / capital * 100
    
    # Yearly MDD (on cumulative P&L within year)
    mdd_list = []
    for y in yearly.index:
        yr = res[res["year"]==y].sort_values("date")
        cum = yr["pnl"].cumsum()
        peak = cum.cummax()
        dd = (cum - peak) / capital
        mdd_list.append(dd.min() * 100)
    yearly["mdd%"] = mdd_list
    
    print(f"\n{'='*60}")
    print(f"  {label} (fixed 4.5M, no compounding)")
    print(f"{'='*60}")
    print(f"{'Year':<6} {'Return%':>9} {'MDD%':>7} {'Trades':>7}")
    print("-" * 35)
    for y in yearly.index:
        r = yearly.loc[y]
        print(f"{y:<6} {r['ret%']:>+8.1f}% {r['mdd%']:>+6.1f}% {int(r['trades']):>7,}")
    
    total_pnl = res["pnl"].sum()
    print("-" * 35)
    print(f"{'TOTAL':<6} {total_pnl/capital*100:>+8.1f}%")

# Side by side
print(f"\n\n{'='*60}")
print("  SIDE BY SIDE")
print(f"{'='*60}")
res_f["year"] = res_f["date"].dt.year
res_d["year"] = res_d["date"].dt.year
yf = res_f.groupby("year").agg(pnl=("pnl","sum"), trades=("trades","sum"))
yd = res_d.groupby("year").agg(pnl=("pnl","sum"), trades=("trades","sum"))

print(f"{'Year':<6} {'Fixed SL':>10} {'Dynamic':>10} {'Diff':>8} {'Winner':>8}")
print("-" * 48)
for y in sorted(yf.index):
    f_r = yf.loc[y,"pnl"] / capital * 100
    d_r = yd.loc[y,"pnl"] / capital * 100
    winner = "Dynamic" if d_r > f_r else "Fixed"
    print(f"{y:<6} {f_r:>+9.1f}% {d_r:>+9.1f}% {d_r-f_r:>+7.1f}% {winner:>8}")
