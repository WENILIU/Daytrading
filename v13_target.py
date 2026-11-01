"""Search for a configuration that still clears CAGR 100 pct / MDD -5 pct once the
entry has to be paid for.

Frame, and why this frame: the book is pinned at 4_500_000 and every profit is
withdrawn. That is what live actually does with 450 萬, it is scale-invariant (a
bigger account is the same run with a bigger pin), and the drawdown it reports is
the position drawdown - the one you feel - not a wealth curve diluted by
withdrawals. In this frame "CAGR 100 pct" means "each year earns about one full
450 萬 on a 450 萬 book", which is the number the owner can verify against a broker
statement. The wealth-CAGR that v13_onebook prints is a different quantity and is
the reason the same strategy has looked like 22 pct and like 90 pct at once.

What is new here is that the entry cost is a search dimension, not a constant:
  slip_scale 0.33  optimistic, fill ~20s after the open
  slip_scale 1.00  the measured cost at the close of the 09:00 bar, i.e. arm B
The 2026-11-01 A/B test says the truth is 1.00 unless the opening auction turns
out to be reachable, so the target has to be met at 1.00.

Levers, all of which live can act on:
  liq        single-order cap as a share of estimated opening value
  gap_max    skip signals whose gap is larger than this (the A/B test showed the
             whole entry-cost tail sits in |gap| >= 7 pct)
  gap_scale  instead of skipping, shrink those orders
  exposure   gross exposure ceiling (>1 needs margin)
  order_cap  max orders per day
  brake      equity drawdown brake, on/off
Usage: python v13_target.py            # the comparison table
       python v13_target.py --grid     # search
"""
import warnings; warnings.filterwarnings("ignore")
import sys
import numpy as np, pandas as pd
from v13_engine import run_backtest, exit_of_legal, CAP0, COST
import v13_sizing as S
from v13_executable import slip_cost, K_OPEN, FC_COST, SL_COST

CFG = dict(kmode="one", tmode="on", min_weight=0.005, min_range=0.001)
_, got, _ = run_backtest(capture=("2014-01-01", "2026-12-31"), capital=CAP0, **CFG)
D = got["D"].copy(); D["stock"] = D["stock"].astype(str)
TO1 = pd.read_pickle(r"D:\gapfade_data\zt_turnover.pkl").shift(1)
BASE = {k: v for k, v in S.R9.items() if k not in ("min_turnover_factor", "dv_cap", "dv_skip")}

FCD = pd.DataFrame(pd.read_pickle("_fcd_panel.pkl")); FCD.index = pd.to_datetime(FCD.index)
DTV = pd.DataFrame(pd.read_pickle("_dtvol_panel.pkl")); DTV.index = pd.to_datetime(DTV.index)
FCD.columns = [str(c) for c in FCD.columns]; DTV.columns = [str(c) for c in DTV.columns]
days = sorted(D["date"].unique())
FCD = FCD.reindex(index=days, columns=sorted(D["stock"].unique()))
DTV = DTV.reindex(index=days, columns=sorted(D["stock"].unique()))
fcd = FCD.fillna(False).astype(bool).values; dtv = DTV.values
dp = {d: i for i, d in enumerate(FCD.index.values)}
fp = {c: j for j, c in enumerate(FCD.columns)}; gp = {c: j for j, c in enumerate(DTV.columns)}
ri = np.array([dp[d] for d in D["date"].values])
cj = D["stock"].map(fp).fillna(-1).astype(int).values
gj = D["stock"].map(gp).fillna(-1).astype(int).values
D["blocked"] = ((cj >= 0) & fcd[ri, np.clip(cj, 0, fcd.shape[1] - 1)]) | \
               ((gj >= 0) & (dtv[ri, np.clip(gj, 0, dtv.shape[1] - 1)] == 0))
GROUPS = {d: g[~g["blocked"]] for d, g in D.groupby("date")}

# Entry cost measured on 2026-11-01 by re-walking the whole exit path from a 09:01
# entry on 1,907 real orders (v13_entry_ab.py / v13_entry_wait.py). Fraction of
# notional; negative means entering at 09:01 is BETTER than the opening print.
#
# This replaces v13_executable.CURVE for this search, because that curve turned out
# to be close to a no-op: running the same book at slip_scale 0.33 and 1.00 changed
# the 2022-2026 return by 0.2 pct. Its negative value below 2 pct participation
# (65 pct of orders) cancels the positive value above 10 pct (8 pct of orders). The
# numbers below are notional-weighted, so they carry the concentration honestly.
#
# Not included: the participation surcharge. Orders above 10 pct of the real first
# minute cost +1.29 pct (SHORT 7-10 pct gap), but live cannot see the real first
# minute at 09:00 - its proxy is about 2x optimistic - so charging it through that
# proxy would be false precision. The fix is to size against the 09:00 bar itself,
# which is only knowable after the open, i.e. it is an argument for the 09:01 entry,
# not a cost of it.
ENTRY_COST = {
    ("SHORT", 0.00): -0.000942, ("SHORT", 0.05): 0.000270,
    ("SHORT", 0.07): 0.003530, ("SHORT", 0.10): 0.009944,
    ("LONG", 0.00): 0.003778, ("LONG", 0.05): 0.003778,
    ("LONG", 0.07): 0.002304, ("LONG", 0.10): 0.007244,
}
SPREAD = 0.00105   # closing half-spread, median of 11 names measured 2026-10-30


def entry_cost(direction, gap, spread=SPREAD):
    g = abs(float(gap))
    edge = 0.10 if g >= 0.10 else (0.07 if g >= 0.07 else (0.05 if g >= 0.05 else 0.00))
    return ENTRY_COST[(direction, edge)] + spread

print("signals %d, blocked by executability %d" % (len(D), int(D["blocked"].sum())), flush=True)


def run(liq=0.25, slip_scale=1.0, gap_max=None, gap_scale=1.0, exposure=1.0,
        order_cap=30, brake=((-0.03, 0.30), (-0.06, 0.12)), nozt=False,
        cost_mode="measured", spread=SPREAD):
    rule = dict(BASE); rule["dv_cap"] = K_OPEN * liq
    # brake is (t1, s1, t2, s2): below t1 scale to s1, below t2 scale to s2.
    # None disables it. Note what pinning the book does to this rule: the book is
    # capped at CAP0 every day, so peak is always CAP0 and cdd is the cumulative
    # loss since the book was last full. With daily PnL of +-several 萬 on 450 萬,
    # a -0.6 pct trigger (27,000 TWD) is effectively always pulled. That is why the
    # default thresholds below are much wider than live's; live's are calibrated for
    # a compounding book and do not survive a pinned one.
    b1, b2 = (brake if brake is not None else (0.0, 0.0))
    book = float(CAP0); peak = float(CAP0); withdrawn = 0.0
    yearly = {}; worst_dd = 0.0; n_all = 0; brake_days = 0; expo = []; parts = []
    # deployment against the BOOK, not against the ceiling. This is the
    # number that decides whether margin is needed at all: if the maximum
    # stays under 100 pct the exposure ceiling only stops the capital check
    # from starving later signals, and no borrowing happens.
    expo_book = []
    for d in days:
        cdd = (book - peak) / peak
        rs = 1.0
        if b1:
            rs = b1[1] if cdd < b1[0] else (b2[1] if (b2 and cdd < b2[0]) else 1.0)
        if rs < 1.0:
            brake_days += 1
        rem = book * exposure; n_day = 0; yuan = 0.0
        for _, r in GROUPS[d].sort_values("_rank").iterrows():
            if n_day >= order_cap:
                break
            ag = abs(float(r["adj_gap"]))
            if gap_max is not None and ag > gap_max:
                continue
            pr = float(r["entry"]); code = str(r["stock"])
            w = float(r["_weight"]) / (float(r["_rs"]) or 1.0) * rs
            if gap_scale != 1.0 and ag >= 0.07:
                w *= gap_scale
            dv1 = float(TO1.at[d, code]) if (code in TO1.columns and d in TO1.index) else np.nan
            n = S.lots_for(rule, w, pr, rem, dv1, capital=book)
            if n <= 0:
                continue
            notional = n * 1000.0 * pr
            ex, slp, tpp, reason, gross = exit_of_legal(
                r["direction"], pr, float(r["day_high"]), float(r["day_low"]),
                float(r["day_close"]), float(r["lu"]), float(r["ld"]),
                float(r["tick"]), float(r["tp"]))
            if nozt and reason.startswith("停損(觸"):
                dcl = float(r["day_close"])
                gross = ((pr - dcl) / pr if r["direction"] == "SHORT" else (dcl - pr) / pr) - FC_COST
            if reason == "13:25 強制平倉":
                gross -= FC_COST
            if reason.startswith("停損"):
                gross -= SL_COST
            pred = notional / (K_OPEN * dv1) if (np.isfinite(dv1) and dv1 > 0) else np.nan
            gross -= 2 * COST
            if cost_mode == "measured":
                gross -= entry_cost(r["direction"], r["adj_gap"], spread)
            else:
                gross -= slip_cost(pred, slip_scale)
            if np.isfinite(pred):
                parts.append(pred)
            rem -= notional; yuan += notional * gross; n_day += 1; n_all += 1
        book += yuan
        if book > CAP0:
            withdrawn += book - CAP0; book = CAP0
        peak = max(peak, book)
        dd = (book - peak) / peak
        worst_dd = min(worst_dd, dd)
        yearly[int(pd.Timestamp(d).year)] = yearly.get(int(pd.Timestamp(d).year), 0.0) + yuan
        expo.append((book * exposure - rem) / (book * exposure))
        expo_book.append((book * exposure - rem) / book)
    return dict(yearly=yearly, mdd=worst_dd * 100, n=n_all,
                per_day=n_all / len(days), n_days=len(days), brake_pct=brake_days / len(days) * 100,
                expo=float(np.mean(expo)) * 100, expo_max=float(np.max(expo_book)) * 100, part90=float(np.percentile(parts, 90)) * 100 if parts else 0.0,
                withdrawn=withdrawn)

def main():
    def show(label, cfg):
        r = run(**cfg)
        y = r["yearly"]; yrs = sorted(y)
        rets = [y[k] / CAP0 * 100 for k in yrs]
        print("  %-46s 部位MDD %+6.2f%%  年均 %+7.1f%%  中位 %+7.1f%%  最差年 %+7.1f%%  "
              "筆/日 %4.1f  曝險 %5.1f%%  參與p90 %5.1f%%" %
              (label, r["mdd"], np.mean(rets), np.median(rets), min(rets),
               r["per_day"], r["expo"], r["part90"]))
        return r, rets, yrs


    def line(r, yrs, rets):
        print("      逐年%：", " ".join("%d %+.0f" % (k, v) for k, v in zip(yrs, rets)))


    print()
    print("=" * 150)
    print("釘在 450 萬、每筆獲利出金。年均 = 每年在 450 萬上的報酬。部位MDD 是交易帳戶自己的回撤。")
    print("slip_scale 0.33 = 開盤後 20 秒成交（樂觀）；1.00 = 09:00 那根結束才成交（= 09:01 進場，實測）")
    print("=" * 150)
    base = {}
    for tag, sc in (("A 開盤價(20s 成交)", 0.33), ("B 09:01 成交(實測成本)", 1.00)):
        r, rets, yrs = show("%s 現行 live 流動性 25%%" % tag, dict(liq=0.25, slip_scale=sc))
        line(r, yrs, rets)
        base[tag] = r

    print()
    print("目標：年均 >= 100%% 且 部位MDD 不劣於 -5%%。以下在 slip_scale=1.00（必須付的進場成本）下搜尋。")
    print()
    GRID = []
    for liq in (0.10, 0.25, 0.50, 1.0):
        for gap_max in (None, 0.10, 0.07):
            for exposure in (1.0, 1.5, 2.0, 3.0):
                GRID.append(dict(liq=liq, slip_scale=1.0, gap_max=gap_max, exposure=exposure))
    for gap_scale in (0.5, 0.25):
        for exposure in (1.5, 2.0, 3.0):
            GRID.append(dict(liq=0.25, slip_scale=1.0, gap_scale=gap_scale, exposure=exposure))

    res = []
    for cfg in GRID:
        r = run(**cfg)
        y = r["yearly"]; rets = [y[k] / CAP0 * 100 for k in sorted(y)]
        res.append((cfg, r, np.mean(rets), np.median(rets), min(rets)))

    ok = [x for x in res if x[1]["mdd"] >= -5.0]
    print("  符合 MDD >= -5%% 的組合：%d / %d" % (len(ok), len(res)))
    ok.sort(key=lambda x: -x[2])
    print("  %-10s %-9s %-9s %-9s %9s %9s %9s %7s %7s %7s" %
          ("liq", "gap_max", "gap_scale", "exposure", "部位MDD%", "年均%", "中位%", "最差年%", "筆/日", "曝險%"))
    for cfg, r, mean, med, worst in ok[:18]:
        print("  %-10s %-9s %-9s %-9s %+9.2f %+9.1f %+9.1f %+9.1f %7.1f %7.1f" %
              (cfg["liq"], cfg.get("gap_max", "-"), cfg.get("gap_scale", "-"), cfg["exposure"],
               r["mdd"], mean, med, worst, r["per_day"], r["expo"]))
    print()
    hit = [x for x in ok if x[2] >= 100.0]
    print("  同時達成 年均>=100%% 且 MDD>=-5%%：%d 個" % len(hit))



if __name__ == "__main__":
    main()
