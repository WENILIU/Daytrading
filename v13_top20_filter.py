"""Does "how much of the top-20 can I actually place" predict which days pay?

Two metrics, because "can I place it" has two answers and they disagree:
  A structural - T-1 turnover >= 5x capital AND 1 lot <= 25% of capital.
    Neither gate reads the target weight, so A is independent of the equity path.
    It answers: is this name inside my tradable universe at all.
  B full R9 - A plus the third gate, "the design weight is too small to make one
    whole lot". B answers: can I execute what the model actually asked for.
    B reads the target weight, so it moves with equity drawdown and kT. At 09:00
    you do know your own equity, so B is not look-ahead, but it is self-referential:
    the backtest computes B from the unfiltered equity path and then filters, which
    is a mild approximation. It is reported, not hidden.
Ranking is by model score, which is fixed.

A fixed threshold is meaningless because the market's price level and turnover drift;
the filter therefore uses the percentile of today's rate inside the trailing 252
sessions - past data only. And because dropping days also just means trading less,
the same number of days is dropped at random for comparison.

Usage: python v13_top20_filter.py
"""
import argparse, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from v13_engine import run_backtest, stats, CAP0
import v13_sizing as S

ap = argparse.ArgumentParser()
ap.add_argument("--capital", type=float, default=CAP0)
ap.add_argument("--seeds", type=int, default=12)
a = ap.parse_args()
CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)

def dv1of(dt, code):
    return float(TO1.at[dt, code]) if (code in TO1.columns and dt in TO1.index) else np.nan

sig = pd.read_pickle("signals_v13.pkl")
sig = sig[sig["pred"].notna()].copy()
sig["date"] = pd.to_datetime(sig["date"]); sig["stock"] = sig["stock"].astype(str)

mA = []
for dt, g in sig.groupby("date"):
    g = g.sort_values("pred", ascending=False).head(20)
    ok = sum(1 for code, px in zip(g["stock"].values, g["entry"].values)
             if (np.isfinite(dv1of(dt, code)) and dv1of(dt, code) >= 5.0 * a.capital)
             and float(px) * 1000.0 <= 0.25 * a.capital)
    mA.append((dt, len(g), ok, ok / len(g)))
A = pd.DataFrame(mA, columns=["date", "n", "ok", "rate"]).set_index("date").sort_index()

base, got, _ = run_backtest(capture=("2013-01-01", "2026-12-31"), **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
mB = []
for dt, g in D.groupby("date"):
    g = g.sort_values("_rank").head(20)
    ok = sum(1 for _, r in g.iterrows()
             if S.lots_for(S.R9, float(r["_weight"]), float(r["entry"]), a.capital,
                           dv1of(dt, str(r["stock"])), capital=a.capital) > 0)
    mB.append((dt, len(g), ok, ok / len(g)))
B = pd.DataFrame(mB, columns=["date", "n", "ok", "rate"]).set_index("date").sort_index()
A.to_csv(r"D:\AI專案\StockAgent\DayTrading\top20_survival_A_structural.csv", encoding="utf-8-sig")
B.to_csv(r"D:\AI專案\StockAgent\DayTrading\top20_survival_B_fullR9.csv", encoding="utf-8-sig")

print("=== 兩個口徑的逐年均值（差額就是第三條閘門：設計權重湊不出一整張）===")
t = pd.DataFrame({"A 僅結構閘門": A["rate"], "B 含整張不足": B["rate"]})
t["差"] = (t["A 僅結構閘門"] - t["B 含整張不足"]) * 100
g = t.groupby(t.index.year).agg(A均值=("A 僅結構閘門", "mean"), B均值=("B 含整張不足", "mean"),
                               B低於30pct天数=("B 含整張不足", lambda s: int((s < 0.30).sum())))
g[["A均值", "B均值"]] = (g[["A均值", "B均值"]] * 100).round(1)
print(g.to_string())
print()

def rep(cv, tag=""):
    o = {}
    for col, v in (("A_pnl", "A 設計面"), ("C_pnl", "C 450萬")):
        s = stats(cv[col]); o[v] = s
        print("  %-10s CAGR %7.1f%%  MDD %6.2f%%  Sharpe %5.2f" % (v, s["cagr"], s["mdd"], s["sharpe"]))
    return o
print("=== 基準（無過濾，成本 0.111%%/邊）===")
b = rep(base); print()

def roll_pct(s, q):
    p = s.rolling(252, min_periods=120).apply(lambda x: float((x < x[-1]).mean()), raw=True)
    return set(s.index[(p < q) & p.notna()])

for nm, M in (("A 僅結構閘門", A), ("B 含整張不足", B)):
    print("=== 滾動分位數過濾：%s ===" % nm)
    for q in [0.05, 0.10, 0.20]:
        skip = roll_pct(M["rate"], q)
        cv, _, _ = run_backtest(skip_dates=skip, **CFG)
        dd = base.reindex(sorted(skip)).dropna(subset=["C_pnl"])
        print("  跳過過去一年最低 %.0f%% 的日子：%d 天（%.1f%%），剩 %d 天；被跳過天基準合計 %+.2f%%"
              % (q*100, len(skip), len(skip)/len(M)*100, len(cv), dd["C_pnl"].sum()*100))
        rep(cv)
    print()

skipB = roll_pct(B["rate"], 0.10)
k = len(skipB); rng = np.random.default_rng(0); pool = list(B.index)
cagrs, mdds = [], []
for i in range(a.seeds):
    sk = set(rng.choice(pool, size=k, replace=False))
    cv, _, _ = run_backtest(skip_dates=sk, **CFG)
    s = stats(cv["C_pnl"]); cagrs.append(s["cagr"]); mdds.append(s["mdd"])
cagrs = np.array(cagrs); mdds = np.array(mdds)
cvf, _, _ = run_backtest(skip_dates=skipB, **CFG)
f = stats(cvf["C_pnl"])
print("=== 對照組：同樣隨機跳過 %d 天 x %d 次 ===" % (k, a.seeds))
print("  隨機 CAGR mean %.1f%% sd %.1f 範圍 [%.1f, %.1f]" % (cagrs.mean(), cagrs.std(), cagrs.min(), cagrs.max()))
print("  隨機 MDD  mean %.2f%% 範圍 [%.2f, %.2f]" % (mdds.mean(), mdds.min(), mdds.max()))
print("  過濾(B,q=0.10) CAGR %.1f%% -> %d/%d 次隨機更好；MDD %.2f%% -> %d/%d 次隨機更好"
      % (f["cagr"], int((cagrs > f["cagr"]).sum()), a.seeds, f["mdd"], int((mdds > f["mdd"]).sum()), a.seeds))
print("  基準 CAGR %.1f%% MDD %.2f%%" % (b["C 450萬"]["cagr"], b["C 450萬"]["mdd"]))
print()
print("=== 2026 分段 ===")
for nm, cv in (("基準", base), ("過濾 B q=0.10", cvf)):
    seg = cv.loc["2026-01-01":]; r = seg["C_pnl"]
    e = (1+r).cumprod()
    print("  %-14s 交易日 %3d  期間 %+7.1f%%  最差單日 %+.2f%%  段內MDD %6.2f%%" %
          (nm, len(seg), (e.iloc[-1]-1)*100, r.min()*100, (e/e.cummax()-1).min()*100))
sk26 = [t for t in skipB if t >= pd.Timestamp("2026-01-01")]
sep = [t for t in sk26 if t.month == 9]
print("  2026 被跳過 %d 天合計 %+.2f%%；其中 9 月 %d 天合計 %+.2f%%" %
      (len(sk26), base.loc[sk26]["C_pnl"].sum()*100, len(sep), base.loc[sep]["C_pnl"].sum()*100))
