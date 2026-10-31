"""Floor vs round when converting a target weight into whole lots.

R9 floors: int(target / lot). That is what makes the "design weight cannot make one
lot" gate bite - a name whose target is 12% (540k) and whose lot costs 600k is
skipped entirely. Rounding to nearest instead buys one lot at 600k, i.e. 13.3%
instead of 12%, and that is the whole trade: more of the model's top names get
placed, at weights above target, and cash is committed faster so fewer names fit.

Three rules, same engine, same signals, same day-by-day cash loop:
  R9      floor (current, live)
  R9R     round to nearest
  R9R_CAP round to nearest, but drop back to floor if the lot breaches the 25%
          single-name cap - the version that keeps the risk limit intact
Usage: python v13_lot_round.py [--since 2014-01-01]
"""
import argparse, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from v13_engine import run_backtest, stats, exit_of_legal, CAP0, COST
import v13_sizing as S

ap = argparse.ArgumentParser()
ap.add_argument("--since", default="2014-01-01")
ap.add_argument("--until", default="2026-12-31")
a = ap.parse_args()
CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)

R9R = dict(S.R9); R9R["round"] = True
R9R_CAP = dict(R9R); R9R_CAP["recap"] = True
RULES = {"R9 無條件捨去（現行）": S.R9, "R9R 四捨五入": R9R, "R9R+守住25%上限": R9R_CAP}

def lots(rule, w, px, cash_left, dv1):
    n = S.lots_for(rule, w, px, cash_left, dv1, capital=CAP0)
    if rule.get("recap") and n > 0:
        if n * 1000.0 * px > 0.25 * CAP0 + 1e-9:
            n = int((min(w * CAP0, 0.25 * CAP0)) // (px * 1000.0))
            if n * 1000.0 * px > cash_left + 1e-9:
                n = int(cash_left // (px * 1000.0))
    return max(n, 0)

_, got, _ = run_backtest(capture=(a.since, a.until), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
print("design intents: %d over %d sessions" % (len(D), D["date"].nunique()))

days = sorted(D["date"].unique())
out = {}
for nm, rule in RULES.items():
    rows = []
    over_cap = 0; placed = 0; top20_ok = 0; top20_n = 0
    for d in days:
        g = D[D["date"] == d].sort_values("_rank")
        rem = CAP0; yuan = 0.0; n_day = 0
        t20 = min(20, len(g))
        top20_n += t20
        for _, r in g.iterrows():
            pr = float(r["entry"]); code = str(r["stock"])
            dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
            n = lots(rule, float(r["_weight"]), pr, rem, dv1)
            if n <= 0:
                continue
            if r["_rank"] <= 20:
                top20_ok += 1
            sh = n * 1000.0
            ex, slp, tpp, reason, gross = exit_of_legal(
                r["direction"], pr, float(r["day_high"]), float(r["day_low"]), float(r["day_close"]),
                float(r["lu"]), float(r["ld"]), float(r["tick"]), float(r["tp"]))
            rem -= sh * pr
            yuan += sh * pr * (gross - 2 * COST)
            n_day += 1; placed += 1
            if sh * pr > 0.25 * CAP0 + 1e-9:
                over_cap += 1
        rows.append((d, yuan / CAP0, n_day))
    cv = pd.DataFrame(rows, columns=["date", "r", "n"]).set_index("date")["r"]
    e = (1 + cv).cumprod()
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    st = dict(cagr=((e.iloc[-1]/e.iloc[0])**(1/yrs)-1)*100, mdd=((e/e.cummax())-1).min()*100,
              sharpe=cv.mean()/cv.std()*np.sqrt(244), final=e.iloc[-1])
    out[nm] = (st, cv)
    print("%-22s CAGR %7.1f%%  MDD %6.2f%%  Sharpe %5.2f  期末 %8.1f萬  筆/日 %5.1f  總筆數 %6d" %
          (nm, st["cagr"], st["mdd"], st["sharpe"], st["final"]/1e4, placed/len(days), placed))
    print("%-22s 前20名可下率 %.1f%%   超過單檔25%%上限的單 %d 筆（%.2f%% of placed）" %
          ("", top20_ok/top20_n*100, over_cap, over_cap/placed*100))

print()
print("=== 逐年（固定 450 萬、每日重設，整張）===")
tbl = {nm: (cv.groupby(cv.index.year).apply(lambda s: ((1+s).prod()-1)*100)).round(1) for nm, (st, cv) in out.items()}
print(pd.DataFrame(tbl).to_string())
print()
print("=== 2026 分段 ===")
for nm, (st, cv) in out.items():
    seg = cv.loc["2026-01-01":]
    print("  %-22s 交易日 %3d  期間 %+7.1f%%  段內MDD %6.2f%%" % (nm, len(seg), ((1+seg).prod()-1)*100, (((1+seg).cumprod()/(1+seg).cumprod().cummax())-1).min()*100))
