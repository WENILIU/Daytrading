"""
Full compounding backtest: Fixed SL vs Dynamic SL
Position sizes grow with capital (realistic).
"""
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

def backtest_compound(df, use_dynamic_sl, capital=4_500_000, base_pct=0.05,
                      sl_pct=0.06, tp_pct=0.04, cost=0.0017,
                      max_positions=15, max_exposure=0.70):
    equity = capital
    daily_results = []
    
    for date, day_df in df.groupby("date"):
        day_pnl = 0
        day_trades = 0
        total_exposure = 0
        
        # Sort by |gap| descending (prioritize larger gaps)
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
            
            pos_value = equity * base_pct * mult
            shares = int(pos_value / entry / 1000) * 1000
            if shares < 1000:
                continue
            
            actual_val = shares * entry
            if total_exposure + actual_val > equity * max_exposure:
                continue
            total_exposure += actual_val
            
            # SL calculation
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
            
            # TP
            if direction == "SHORT":
                tp_price = entry * (1 - tp_pct)
            else:
                tp_price = entry * (1 + tp_pct)
            
            # Simulate
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
        
        equity += day_pnl
        daily_results.append({"date": date, "pnl": day_pnl, "equity": equity, "trades": day_trades})
    
    return pd.DataFrame(daily_results)

# Run both
print("Running Fixed SL 6% (compounding)...")
res_fixed = backtest_compound(df, use_dynamic_sl=False)
print("Running Dynamic SL (compounding)...")
res_dynamic = backtest_compound(df, use_dynamic_sl=True)

# Yearly breakdown
for label, res in [("Fixed SL 6%", res_fixed), ("Dynamic SL", res_dynamic)]:
    res["year"] = res["date"].dt.year
    yearly = res.groupby("year").agg(
        start_eq=("equity", "first"),
        end_eq=("equity", "last"),
        pnl=("pnl", "sum"),
        trades=("trades", "sum"),
    )
    yearly["ret%"] = (yearly["end_eq"] / yearly["start_eq"] - 1) * 100
    
    # MDD within year
    mdd_list = []
    for y in yearly.index:
        yr_data = res[res["year"] == y]
        peak = yr_data["equity"].cummax()
        dd = (yr_data["equity"] - peak) / peak
        mdd_list.append(dd.min() * 100)
    yearly["mdd%"] = mdd_list
    
    print(f"\n{'='*65}")
    print(f"  {label}")
    print(f"{'='*65}")
    print(f"{'Year':<6} {'Return%':>9} {'MDD%':>7} {'Trades':>7} {'End Equity':>15}")
    print("-" * 55)
    for y in yearly.index:
        r = yearly.loc[y]
        print(f"{y:<6} {r['ret%']:>+8.1f}% {r['mdd%']:>+6.1f}% {int(r['trades']):>7,} {r['end_eq']:>15,.0f}")
    
    # Overall
    years = (res["date"].iloc[-1] - res["date"].iloc[0]).days / 365.25
    total_ret = res["equity"].iloc[-1] / 4_500_000
    cagr = total_ret ** (1/years) - 1
    peak = res["equity"].cummax()
    mdd = ((res["equity"] - peak) / peak).min()
    daily_ret = res["pnl"] / res["equity"].shift(1).fillna(4_500_000)
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
    
    print("-" * 55)
    print(f"{'TOTAL':<6} {cagr*100:>+8.1f}% {mdd*100:>+6.1f}% {int(res['trades'].sum()):>7,} {res['equity'].iloc[-1]:>15,.0f}")
    print(f"  CAGR: {cagr*100:.1f}% | MDD: {mdd*100:.1f}% | Sharpe: {sharpe:.2f}")
