"""
Compare: Fixed SL 6% vs Dynamic SL (price-limit capped)
Uses the same signals and Kelly sizing, only SL logic differs.
"""
import pandas as pd
import numpy as np
from datetime import datetime

# Load signals
df = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl")
df["date"] = pd.to_datetime(df["date"])

# Kelly tiers
tiers = [
    (0.09, 999, 2.5),
    (0.08, 0.09, 2.0),
    (0.07, 0.08, 1.8),
    (0.065, 0.07, 1.5),
    (0.06, 0.065, 1.2),
    (0.05, 0.06, 1.0),
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

def backtest(df, use_dynamic_sl=True, capital=4_500_000, base_pct=0.05,
             sl_pct=0.06, tp_pct=0.04, cost=0.0017):
    """Run backtest with either fixed or dynamic SL."""
    results = []
    
    for date, day_df in df.groupby("date"):
        day_pnl = 0
        day_trades = []
        
        for _, row in day_df.iterrows():
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
            
            # Position size
            pos_value = capital * base_pct * mult
            shares = int(pos_value / entry / 1000) * 1000
            if shares < 1000:
                continue
            
            # Calculate SL
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
            
            # Calculate TP
            if direction == "SHORT":
                tp_price = entry * (1 - tp_pct)
            else:
                tp_price = entry * (1 + tp_pct)
            
            # Simulate: check if SL or TP hit (SL priority for conservatism)
            if direction == "SHORT":
                sl_hit = day_high >= sl_price
                tp_hit = day_low <= tp_price
                
                if sl_hit and tp_hit:
                    # Both hit - assume SL first (conservative)
                    exit_price = sl_price
                    reason = "SL"
                elif sl_hit:
                    exit_price = sl_price
                    reason = "SL"
                elif tp_hit:
                    exit_price = tp_price
                    reason = "TP"
                else:
                    exit_price = day_close
                    reason = "EOD"
                
                pnl_pct = (entry - exit_price) / entry - 2 * cost
            else:  # LONG
                sl_hit = day_low <= sl_price
                tp_hit = day_high >= tp_price
                
                if sl_hit and tp_hit:
                    exit_price = sl_price
                    reason = "SL"
                elif sl_hit:
                    exit_price = sl_price
                    reason = "SL"
                elif tp_hit:
                    exit_price = tp_price
                    reason = "TP"
                else:
                    exit_price = day_close
                    reason = "EOD"
                
                pnl_pct = (exit_price - entry) / entry - 2 * cost
            
            pnl_dollar = pnl_pct * shares * entry
            day_pnl += pnl_dollar
            day_trades.append({
                "date": date, "code": row["stock"], "direction": direction,
                "gap": gap, "entry": entry, "sl": sl_price, "tp": tp_price,
                "exit": exit_price, "reason": reason, "pnl_pct": pnl_pct,
                "pnl_dollar": pnl_dollar, "shares": shares,
            })
        
        results.append({"date": date, "pnl": day_pnl, "trades": len(day_trades)})
    
    return pd.DataFrame(results), pd.DataFrame([t for r in [] for t in r])

# Run both versions
print("Running backtest: Fixed SL 6%...")
res_fixed, _ = backtest(df, use_dynamic_sl=False)
print("Running backtest: Dynamic SL (price-limit capped)...")
res_dynamic, _ = backtest(df, use_dynamic_sl=True)

# Calculate metrics
def calc_metrics(res, capital=4_500_000):
    res = res.sort_values("date").reset_index(drop=True)
    res["cum_pnl"] = res["pnl"].cumsum()
    res["equity"] = capital + res["cum_pnl"]
    
    # CAGR
    years = (res["date"].iloc[-1] - res["date"].iloc[0]).days / 365.25
    total_return = res["equity"].iloc[-1] / capital
    cagr = total_return ** (1/years) - 1
    
    # MDD
    peak = res["equity"].cummax()
    dd = (res["equity"] - peak) / peak
    mdd = dd.min()
    
    # Sharpe (daily)
    daily_ret = res["pnl"] / capital
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
    
    # Win rate
    total_trades = res["trades"].sum()
    
    return {"CAGR": cagr*100, "MDD": mdd*100, "Sharpe": sharpe, 
            "TotalReturn": total_return, "Trades": total_trades,
            "FinalEquity": res["equity"].iloc[-1]}

m_fixed = calc_metrics(res_fixed)
m_dynamic = calc_metrics(res_dynamic)

print(f"\n{'='*60}")
print(f"{'Metric':<15} {'Fixed SL 6%':>15} {'Dynamic SL':>15} {'Diff':>10}")
print(f"{'='*60}")
print(f"{'CAGR':<15} {m_fixed['CAGR']:>14.1f}% {m_dynamic['CAGR']:>14.1f}% {m_dynamic['CAGR']-m_fixed['CAGR']:>+9.1f}%")
print(f"{'MDD':<15} {m_fixed['MDD']:>14.1f}% {m_dynamic['MDD']:>14.1f}% {m_dynamic['MDD']-m_fixed['MDD']:>+9.1f}%")
print(f"{'Sharpe':<15} {m_fixed['Sharpe']:>14.2f} {m_dynamic['Sharpe']:>14.2f} {m_dynamic['Sharpe']-m_fixed['Sharpe']:>+10.2f}")
print(f"{'Total Return':<15} {m_fixed['TotalReturn']:>13.0f}x {m_dynamic['TotalReturn']:>13.0f}x")
print(f"{'Trades':<15} {m_fixed['Trades']:>14,} {m_dynamic['Trades']:>14,}")
print(f"{'Final Equity':<15} {m_fixed['FinalEquity']:>14,.0f} {m_dynamic['FinalEquity']:>14,.0f}")
print(f"{'='*60}")

# Yearly comparison
print("\n--- Yearly Comparison ---")
res_fixed["year"] = res_fixed["date"].dt.year
res_dynamic["year"] = res_dynamic["date"].dt.year

yearly_f = res_fixed.groupby("year").agg(pnl=("pnl","sum"), trades=("trades","sum"))
yearly_d = res_dynamic.groupby("year").agg(pnl=("pnl","sum"), trades=("trades","sum"))

yearly_f["ret%"] = yearly_f["pnl"] / capital * 100
yearly_d["ret%"] = yearly_d["pnl"] / capital * 100

print(f"{'Year':<6} {'Fixed SL':>10} {'Dynamic SL':>10} {'Diff':>8}")
for y in sorted(yearly_f.index):
    f_ret = yearly_f.loc[y, "ret%"] if y in yearly_f.index else 0
    d_ret = yearly_d.loc[y, "ret%"] if y in yearly_d.index else 0
    print(f"{y:<6} {f_ret:>+9.1f}% {d_ret:>+9.1f}% {d_ret-f_ret:>+7.1f}%")
