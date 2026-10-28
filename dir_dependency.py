import pandas as pd, numpy as np
df = pd.read_pickle("signals_v13.pkl")
df = df[df["pred"].notna()].copy()
df = df[df["pred_q"] >= 0.20].copy()
df["year"] = pd.to_datetime(df["date"]).dt.year

print("=== ALL model-selected signals (pred_q>=0.20) ===")
g = df.groupby("direction").agg(n=("p", "size"), mean_pnl=("p", "mean"),
                                win=("p", lambda s: (s > 0).mean() * 100),
                                total_pnl=("p", "sum"))
g["mean_pnl"] *= 100; g["total_pnl"] *= 100
print(g.round(2).to_string())
tot = df["p"].sum() * 100
print(f"\nTOTAL pnl-units (sum of per-trade pct): {tot:,.0f}")
for d in ["SHORT", "LONG"]:
    s = df[df["direction"] == d]["p"].sum() * 100
    print(f"  {d:>5}: {s:,.0f}  = {s/tot*100:.1f}% of total")

# What the strategy ACTUALLY trades: top-10 per day by pred, as in the live path
top = df.sort_values("pred", ascending=False).groupby("date").head(10)
print("\n=== What the book actually takes (top-10 pred per day) ===")
g2 = top.groupby("direction").agg(n=("p", "size"), mean_pnl=("p", "mean"),
                                  win=("p", lambda s: (s > 0).mean() * 100),
                                  total_pnl=("p", "sum"))
g2["mean_pnl"] *= 100; g2["total_pnl"] *= 100
print(g2.round(2).to_string())
tot2 = top["p"].sum() * 100
print(f"\nTOTAL: {tot2:,.0f}")
for d in ["SHORT", "LONG"]:
    s = top[top["direction"] == d]["p"].sum() * 100
    print(f"  {d:>5}: n={len(top[top.direction==d]):>6}  pnl={s:,.0f}  = {s/tot2*100:5.1f}% of total")

print("\n=== LONG-only book (if 無券當沖 never opens) ===")
lo = top[top["direction"] == "LONG"]
print(f"  trades {len(lo)} over {lo['date'].nunique()} days | mean pnl {lo['p'].mean()*100:+.3f}% "
      f"| win {(lo['p']>0).mean()*100:.1f}%")
print("\n=== SHORT-only book ===")
so = top[top["direction"] == "SHORT"]
print(f"  trades {len(so)} over {so['date'].nunique()} days | mean pnl {so['p'].mean()*100:+.3f}% "
      f"| win {(so['p']>0).mean()*100:.1f}%")

print("\n=== per-year SHORT share of the taken book ===")
pv = top.pivot_table(index="year", columns="direction", values="p", aggfunc="sum") * 100
pv["short_share%"] = pv["SHORT"] / (pv["SHORT"] + pv["LONG"]) * 100
print(pv.round(1).to_string())
