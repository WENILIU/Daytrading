"""Sizing lab: what happens when the live order size differs from the backtest design.

The backtest asks for a target weight per signal; a real 4,500,000 account can only
place whole lots, and a human placing orders by hand will round differently again.
This measures the cost of every practical variant, so the answer to "do I have to
change the strategy?" is a number rather than an opinion.

Usage: python v13_sizing_lab.py [--since 2014-01-01] [--until 2026-12-31]
"""
import sys, argparse
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
import v13_engine as E
from v13_engine import exit_of_legal, COST

ap = argparse.ArgumentParser()
ap.add_argument("--since", default="2014-01-01")
ap.add_argument("--until", default="2026-12-31")
ap.add_argument("--capital", type=float, default=4_500_000)
a = ap.parse_args()
CAP = a.capital

print("loading design intents %s..%s ..." % (a.since, a.until))
cv, got, _ = E.run_backtest(capture=(a.since, a.until), capital=CAP,
                            min_weight=0.005, kmode="one", tmode="on", min_range=0.001)
A = got["D"].copy()
A["stock"] = A["stock"].astype(str)
DESIGN_TRADES = len(A)
print("design intents: %d over %d days" % (len(A), A["date"].nunique()))

rows = []
for _, r in A.iterrows():
    ex, slp, tpp, reason, gross = exit_of_legal(r["direction"], float(r["entry"]), float(r["day_high"]),
                                                float(r["day_low"]), float(r["day_close"]), float(r["lu"]),
                                                float(r["ld"]), float(r["tick"]), float(r["tp"]))
    rows.append((str(pd.Timestamp(r["date"]).date()), int(r["_rank"]), r["stock"], r["direction"],
                 float(r["entry"]), float(r["_weight"]), gross - 2 * COST, float(r["p"])))
D = pd.DataFrame(rows, columns=["date", "rank", "stock", "dir", "px", "w", "net", "net_bt"])
D = D.sort_values(["date", "rank"]).reset_index(drop=True)
# Impact proxy: T own turnover does not exist yet at 09:00, so use T-1.
# Same panel the backtest prices come from, shifted one session.
TO = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
Ts = TO.stack().dropna()   # pandas 2.x: stack() no longer takes dropna
Ts.index = pd.MultiIndex.from_arrays(
    [pd.to_datetime(Ts.index.get_level_values(0)).strftime("%Y-%m-%d"),
     Ts.index.get_level_values(1).astype(str)])
D["dv1"] = Ts.reindex(pd.MultiIndex.from_arrays([D["date"], D["stock"]])).to_numpy()
print("T-1 turnover matched: %d / %d rows" % (int(np.isfinite(D["dv1"]).sum()), len(D)))

G = {d: g for d, g in D.groupby("date", sort=True)}
DAYS = sorted(G)


def lots_for(rule, w, px, cash_left, dv1=np.nan):
    """whole lots a rule would place for one signal given remaining cash"""
    lot = px * 1000.0
    if rule["scale"] != 1.0:
        w = w * rule["scale"]
    tgt = w * CAP
    if rule.get("cap") is not None:
        tgt = min(tgt, rule["cap"])
    if rule.get("dv_cap") is not None and np.isfinite(dv1) and dv1 > 0:
        tgt = min(tgt, rule["dv_cap"] * float(dv1))
    if rule.get("dv_skip") is not None and np.isfinite(dv1) and dv1 > 0 and lot > rule["dv_skip"] * float(dv1):
        return 0

    if rule.get("floor_lot") and lot > rule["floor_lot"]:
        return 0
    if rule.get("fixed") is not None:
        tgt = rule["fixed"]
    n = int(round(tgt / lot)) if rule.get("round") else int(tgt // lot)
    if rule.get("max_lots"):
        n = min(n, rule["max_lots"])
    if n * lot > cash_left + 1e-9:
        n = int(cash_left // lot)
    return max(n, 0)


def run(rule, day_list=None):
    """Fixed-capital view, identical to the engine's C mode: every day sizes against
    4,500,000 and the daily return is pnl/CAP, compounded. Variant 1 must therefore
    reproduce the published C numbers - that is the self-check for this whole lab."""
    daily = []
    ntr = []
    notional = []
    sh1 = []
    for d in (day_list if day_list is not None else DAYS):
        g = G[d]
        left = CAP
        pnl = 0.0
        k = 0
        tot = 0.0
        for _, r in g.iterrows():
            n = lots_for(rule, r["w"], r["px"], left, r["dv1"])
            if n <= 0:
                continue
            sh = n * 1000
            cost = sh * r["px"]
            left -= cost
            pnl += cost * (r["net_bt"] if rule.get("bt_net") else r["net"])
            k += 1
            tot += cost
            notional.append(cost)
            if np.isfinite(r["dv1"]) and r["dv1"] > 0:
                sh1.append(cost / float(r["dv1"]))
        daily.append((d, pnl / CAP, k, tot / CAP))
        ntr.append(k)
    ser = pd.Series([x[1] for x in daily], index=pd.to_datetime([x[0] for x in daily]))
    st = E.stats(ser)
    nn = np.array(ntr)
    nt = np.array(notional) if notional else np.array([0.0])
    return {"name": rule["name"], "cagr": st["cagr"], "mdd": st["mdd"],
            "sharpe": st["sharpe"], "calmar": st["calmar"], "nperday": nn.mean(),
            "trades": int(nn.sum()), "avg_notional_w": nt.mean() / 1e4,
            "p90_notional_w": np.percentile(nt, 90) / 1e4,
            "max_notional_w": nt.max() / 1e4,
            "fill_rate": int(nn.sum()) / DESIGN_TRADES * 100,
            "total": (float((1.0 + ser).prod()) - 1.0) * 100.0,
            "p95_share1": (np.percentile(sh1, 95) * 100 if len(sh1) else np.nan),
            "max_share1": (max(sh1) * 100 if len(sh1) else np.nan),
            "expo": np.mean([x[3] for x in daily]) * 100}


RULES = [
    {"name": "A 設計面（無整張，複利）", "design": True},
    {"name": "0 self-check: floor 到張 + 回測 p 值", "scale": 1.0, "bt_net": True},
    {"name": "1 floor 到張（現行回測）", "scale": 1.0},
    {"name": "2 round 到最近張", "scale": 1.0, "round": True},
    {"name": "3 floor + 單筆上限 100萬", "scale": 1.0, "cap": 1_000_000},
    {"name": "4 floor + 單筆上限 75萬", "scale": 1.0, "cap": 750_000},
    {"name": "5 floor + 單筆上限 50萬", "scale": 1.0, "cap": 500_000},
    {"name": "6 floor + 單筆上限 30萬", "scale": 1.0, "cap": 300_000},
    {"name": "7 模型倉位 x0.5（只打一半）", "scale": 0.5},
    {"name": "8 模型倉位 x0.25（只打1/4）", "scale": 0.25},
    {"name": "9 固定每筆 30萬（floor 到張）", "scale": 1.0, "fixed": 300_000},
    {"name": "10 固定每筆 20萬（floor 到張）", "scale": 1.0, "fixed": 200_000},
    {"name": "11 固定每筆 10萬（floor 到張）", "scale": 1.0, "fixed": 100_000},
    {"name": "12 每訊號固定 1 張", "scale": 1.0, "max_lots": 1},
    {"name": "13 現行但最多 5 張", "scale": 1.0, "max_lots": 5},
    {"name": "14 現行 + 跳過1張>10萬的標的", "scale": 1.0, "floor_lot": 100_000},
    {"name": "15 現行 + 跳過1張>25萬的標的", "scale": 1.0, "floor_lot": 250_000},
    {"name": "R1 round + 單筆上限100萬", "scale": 1.0, "round": True, "cap": 1_000_000},
    {"name": "R2 round + 上限100萬 + 跳過1張>25萬", "scale": 1.0, "round": True, "cap": 1_000_000,
     "floor_lot": 250_000},
    {"name": "R3 = R2 但只打一半", "scale": 0.5, "round": True, "cap": 1_000_000, "floor_lot": 250_000},
    {"name": "R4 = R2 但只打1/4", "scale": 0.25, "round": True, "cap": 1_000_000, "floor_lot": 250_000},
    {"name": "R5 round + 上限75萬 + 跳過1張>25萬", "scale": 1.0, "round": True, "cap": 750_000,
     "floor_lot": 250_000},
    {"name": "R6 floor + 上限100萬 + 跳過1張>25萬", "scale": 1.0, "cap": 1_000_000, "floor_lot": 250_000},
    {"name": "R7 = R6 但只打一半（起手式）", "scale": 0.5, "cap": 1_000_000, "floor_lot": 250_000},
    {"name": "R8 = R6 但單筆上限75萬", "scale": 1.0, "cap": 750_000, "floor_lot": 250_000},
    # Impact control. T's own turnover is unknown at 09:00, so the only legal proxy is
    # T-1 dollar turnover. These cap one trade at a fraction of yesterday's turnover.
    {"name": "R9 = R6 + 單筆≤T-1成交額10%", "scale": 1.0, "cap": 1_000_000, "floor_lot": 250_000,
     "dv_cap": 0.10},
    {"name": "R10 = R6 + 單筆≤T-1成交額5%", "scale": 1.0, "cap": 1_000_000, "floor_lot": 250_000,
     "dv_cap": 0.05},
    {"name": "R11 = R10 + 1張>T-1成交額5%就跳過", "scale": 1.0, "cap": 1_000_000, "floor_lot": 250_000,
     "dv_cap": 0.05, "dv_skip": 0.05},
]

out = []
for rule in RULES:
    if rule.get("design"):
        s = cv.loc[pd.Timestamp(a.since):pd.Timestamp(a.until), "A_pnl"]
        st = E.stats(s)
        out.append({"name": rule["name"], "cagr": st["cagr"], "mdd": st["mdd"], "sharpe": st["sharpe"],
                    "calmar": st["calmar"], "nperday": cv["A_n"].mean(), "trades": int(cv["A_n"].sum()),
                    "avg_notional_w": np.nan, "p90_notional_w": np.nan, "max_notional_w": np.nan,
                    "fill_rate": 100.0, "expo": cv["A_expo"].mean() * 100})
    else:
        out.append(run(rule))

T = pd.DataFrame(out)
print()
print("=== 450 萬、一律整張、零融資：各種「實務下單法則」的實測結果 ===")
T["ev_per_trade_bp"] = np.nan
print(T.to_string(index=False, float_format=lambda v: "%.1f" % v))
T.to_csv("v13_sizing_lab.csv", index=False, encoding="utf-8-sig")
print("\nsaved v13_sizing_lab.csv")

# --- independent cross-check for the published daytrading.csv -----------------
# v13_daytrading_csv.py implements R6 a second time (row by row over the captured
# design list). Both must agree on the same window, otherwise one of them is wrong.
WS, WU = "2026-07-23", "2026-10-22"
WD = [d for d in DAYS if WS <= d <= WU]
print("\n=== 近 3 個月窗口 %s ~ %s：本腳本獨立實作（供 daytrading.csv 對照）===" % (WS, WU))
for rule in RULES:
    nm = rule.get("name", "")
    if nm.startswith("1 ") or nm.startswith("R6") or nm.startswith("R7"):
        r = run(rule, WD)
        print("  %-40s 筆數 %5d  區間報酬 %8.2f%%  單筆最大 %6.1f 萬  曝險 %.1f%%"
              % (r["name"], r["trades"], r["total"], r["max_notional_w"], r["expo"]))
