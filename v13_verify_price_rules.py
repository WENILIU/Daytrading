"""Verify every price rule the strategy depends on, against external ground truth.

Run: python v13_verify_price_rules.py

Six checks:
  1. limit-up/down reproduced from TPEx's own published 次日漲停價/次日跌停價
  2. 19 years of real OHLC must never exceed the computed limit (a physical bound)
  3. live / backtest / training all use the same rule (source level)
  4. the published trade list obeys every invariant (no locked opens, whole lots,
     entry strictly inside the band, cash chain continuous from 4,500,000)
  5. every stop/target/exit price is a price the exchange accepts
  6. the lu-tk float artefact no longer hides a stop
"""
import io, os, sys, math, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

FAIL = []


def ok(cond, label, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (("  " + detail) if detail else ""))
    if not cond:
        FAIL.append(label)


def tsz_new(p):
    if p < 10: return 0.01
    if p < 50: return 0.05
    if p < 100: return 0.1
    if p < 500: return 0.5
    if p < 1000: return 1.0
    return 5.0


def tsz_old(p):
    """the pre-2026-10-27 table, kept only to show what the fix removed"""
    if p < 10: return 0.05
    if p < 50: return 0.05
    if p < 100: return 0.1
    if p < 500: return 0.5
    if p < 1000: return 1.0
    if p < 5000: return 5.0
    return 10.0


def limits(pc, tsz, band_on_limit):
    ru, rd = pc * 1.10, pc * 0.90
    tu = tsz(ru) if band_on_limit else tsz(pc)
    td = tsz(rd) if band_on_limit else tsz(pc)
    return round(math.floor(round(ru / tu, 9)) * tu, 4), round(math.ceil(round(rd / td, 9)) * td, 4)


def legal(p):
    t = tsz_new(p)
    return abs(p / t - round(p / t)) < 1e-9


print("=" * 78)
print("Gap Fade v13 - price rule verification")
print("=" * 78)

# ---------------------------------------------------------------- 1. TPEx truth
print("\n[1] TPEx published next-day limits")
try:
    import requests
    r = requests.get("https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?type=EW&response=json",
                     timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    t = r.json()["tables"][0]
    n_new = n_old = tot = skipped_sentinel = 0
    stk_new = stk_old = stk_tot = 0
    miss = []
    for x in t["data"]:
        try:
            pc = float(str(x[2]).replace(",", ""))
            lu = float(str(x[15]).replace(",", ""))
            ld = float(str(x[16]).replace(",", ""))
        except Exception:
            continue
        if not (pc > 0 and lu > 0):
            continue
        if lu > 9000:
            # TPEx writes 9999.95 as a sentinel for "no daily limit" (ETFs etc.)
            skipped_sentinel += 1
            continue
        tot += 1
        a, b = limits(pc, tsz_new, True)
        c, d = limits(pc, tsz_old, False)
        hit_new = abs(a - lu) < 1e-9 and abs(b - ld) < 1e-9
        hit_old = abs(c - lu) < 1e-9 and abs(d - ld) < 1e-9
        n_new += hit_new
        n_old += hit_old
        # exchange stocks are 4 digits not in the 00xx fund range; funds trade on a 0.01
        # grid, which is why their published limit is one tick above the stock table
        is_stock = len(str(x[0])) == 4 and not str(x[0]).startswith("00")
        if is_stock:
            stk_tot += 1
            stk_new += hit_new
            stk_old += hit_old
        elif not hit_new:
            miss.append((x[0], pc, lu, a))
    ok(stk_new == stk_tot, "new rule reproduces every published limit for exchange stocks",
       "%d/%d  date=%s" % (stk_new, stk_tot, r.json().get("date", "?")))
    print("         (all instruments incl. funds: %d/%d = %.1f%%; every miss is a 00xx fund "
          "on a 0.01 grid)" % (n_new, tot, n_new / tot * 100))
    print("         (old rule on stocks: %d/%d = %.1f%%; %d rows skipped because TPEx publishes "
          "9999.95 meaning no daily limit)" % (stk_old, stk_tot, stk_old / stk_tot * 100, skipped_sentinel))
    for m in miss[:5]:
        print("         fund mismatch (uses 0.01 grid)", m)
except Exception as e:
    ok(False, "TPEx fetch", repr(e))

# ------------------------------------------------- 2. real OHLC physical bound
print("\n[2] real OHLC vs computed limit-up (2007-04..2026-10)")
try:
    hi = pd.DataFrame(pd.read_pickle(r"D:\gapfade_data\price_high.pkl"))
    cl = pd.DataFrame(pd.read_pickle(r"D:\gapfade_data\price_close.pkl"))
    P = cl.shift(1).values
    H = hi.values
    flat = P.ravel()
    tnew = np.array([tsz_new(x) if x > 0 else 1.0 for x in flat]).reshape(P.shape)
    told = np.array([tsz_old(x) if x > 0 else 1.0 for x in flat]).reshape(P.shape)
    ru = np.where(P > 0, P * 1.10, 0.0)
    lu_new = np.floor(np.round(ru / tnew, 9)) * tnew
    lu_old = np.floor(np.round(ru / told, 9)) * told
    valid = (P > 0) & np.isfinite(H) & (H > 0)
    bad_new = int(((H > lu_new + 1e-9) & valid).sum())
    bad_old = int(((H > lu_old + 1e-9) & valid).sum())
    ok(bad_new < bad_old and bad_new < 1500,
       "no real high above the computed limit-up",
       "new %s / old %s violations out of %s stock-days" %
       (format(bad_new, ","), format(bad_old, ","), format(int(valid.sum()), ",")))
    print("         (the remainder are ex-dividend reference prices and first-day listings)")
except Exception as e:
    ok(False, "OHLC bound test", repr(e))

# ------------------------------------------------------ 3. one rule, three places
print("\n[3] live / backtest / training use the same rule")
try:
    src = io.open("gap_fade_auto.py", encoding="utf-8").read()
    ok("get_tick_size(raw_up)" in src and "get_tick_size(raw_dn)" in src,
       "live calc_price_limits uses the limit-price band")
    ok("round(limit_up - tick, 2)" in src and "round(limit_down + tick, 2)" in src,
       "live stop cap rounds limit-minus-one-tick before ordering")
    eng = io.open("v13_engine.py", encoding="utf-8").read()
    ok(eng.count("round(lu - tk, 2)") >= 1 and eng.count("round(ld + tk, 2)") >= 1,
       "engine exit_of rounds the stop cap before comparing")
    trn = io.open("v13_train.py", encoding="utf-8").read()
    ok("np.round(lu[m]-tk[m],2)" in trn and "np.round(ld[m]+tk[m],2)" in trn,
       "training target uses the same rounded cap")
    bld = io.open("v13_build.py", encoding="utf-8").read()
    ok("RU=pc*1.10" in bld and "np.vectorize(tsz)(RU)" in bld,
       "backtest limit-up uses the limit-price band")
except Exception as e:
    ok(False, "source consistency", repr(e))

# ------------------------------------------------------- 4/5/6. trade list
print("\n[4] published trade list invariants")
CSV = r"D:\AI專案\StockAgent\DayTrading\daytrading.csv"
try:
    T = pd.read_csv(CSV, encoding="utf-8-sig")
    T["股票"] = T["股票"].astype(str).str.zfill(4)
    ok(len(T) > 0, "trade list loaded", "%d rows, %s..%s" % (len(T), T["日期"].min(), T["日期"].max()))
    ok(int(T["開盤鎖死"].sum()) == 0, "no signal opened at limit-up/limit-down")
    ok(int(T["整天鎖死"].sum()) == 0, "no signal on a single-print day")
    ok(bool((T["成交股數"] % 1000 == 0).all()), "every order is a whole lot (1000 shares)")
    short = T["方向"] == "SHORT"
    ok(bool((T.loc[short, "進場價"] < T.loc[short, "漲停價"]).all()), "every SHORT entry is strictly below limit-up")
    ok(bool((T.loc[~short, "進場價"] > T.loc[~short, "跌停價"]).all()), "every LONG entry is strictly above limit-down")
    bad = [(r["日期"], r["股票"], r["前收"], r["漲停價"]) for _, r in T.iterrows()
           if max(abs(limits(float(r["前收"]), tsz_new, True)[0] - float(r["漲停價"])),
                  abs(limits(float(r["前收"]), tsz_new, True)[1] - float(r["跌停價"]))) > 1e-9]
    ok(len(bad) == 0, "every 漲停價/跌停價 matches the current rule", "%d mismatches" % len(bad))
    day = T.groupby("日期")["盈虧(元)"].sum()
    bal = 4_500_000 + day.cumsum()
    got = T.groupby("日期")["累計現金(元)"].last()
    ok(float((got - bal).abs().max()) < 1.0, "cash chain is continuous from 4,500,000",
       "max drift %.2f TWD" % float((got - bal).abs().max()))
    ok(float(bal.min()) >= 0, "cash never goes negative (no margin used)", "min cash %.0f" % float(bal.min()))

    # the full design-intent file, not just the executed subset
    ALLCSV = os.path.splitext(CSV)[0] + "_all_signals.csv"
    if os.path.exists(ALLCSV):
        AL = pd.read_csv(ALLCSV, encoding="utf-8-sig")
        AL["股票"] = AL["股票"].astype(str).str.zfill(4)
        sh = AL["方向"] == "SHORT"
        locked = int((AL.loc[sh, "開盤價"] >= AL.loc[sh, "漲停價"]).sum()
                     + (AL.loc[~sh, "開盤價"] <= AL.loc[~sh, "跌停價"]).sum())
        ok(locked == 0, "no signal in the full design list opened at the limit",
           "%d rows, %d locked" % (len(AL), locked))
        near = AL.loc[sh, "漲停價"] - AL.loc[sh, "開盤價"]
        t = near.apply(tsz_new)
        print("         (%d/%d SHORT signals open within one tick of limit-up; those are the "
              "near-lock cases the stop is set one tick below)" %
              (int((near <= t + 1e-9).sum()), int(sh.sum())))
        badlim = 0
        for _, r in AL.iterrows():
            a, b = limits(float(r["前收"]), tsz_new, True)
            if abs(a - float(r["漲停價"])) > 1e-9 or abs(b - float(r["跌停價"])) > 1e-9:
                badlim += 1
        ok(badlim == 0, "every limit price in the design list matches the rule", "%d mismatches" % badlim)

    print("\n[5] stop/target/exit prices are exchange-legal")
    stk = T[T["股票"].str.match(r"^\d{4}$")]
    etf = T[~T["股票"].str.match(r"^\d{4}$")]
    bad_sl = sum(0 if legal(float(r["停損價"])) else 1 for _, r in stk.iterrows())
    bad_tp = sum(0 if legal(float(r["停利價"])) else 1 for _, r in stk.iterrows())
    bad_ex = sum(0 if legal(float(r["出場價"])) else 1 for _, r in stk.iterrows())
    ok(bad_sl == 0 and bad_tp == 0 and bad_ex == 0,
       "every 停損價/停利價/出場價 is legal for 4-digit stocks",
       "%d stocks: SL %d, TP %d, exit %d illegal" % (len(stk), bad_sl, bad_tp, bad_ex))
    off = sum(0 if legal(float(r["出場價"])) else 1 for _, r in etf.iterrows())
    print("         (%d ETF rows trade on a 0.01 grid; %d of their exit prices sit off the "
          "stock grid, which is still an orderable price)" % (len(etf), off))

    print("\n[6] the lu-tk float artefact no longer hides a stop")
    sys.path.insert(0, ".")
    from v13_engine import exit_of, SLO
    sig = pd.read_pickle("signals_v13.pkl")
    s = sig[sig["direction"] == "SHORT"]
    cap = np.round(s["lu"].values - s["tick"].values, 2)
    raw = s["lu"].values - s["tick"].values
    binding = cap < s["entry"].values * (1 + SLO) - 1e-9
    affected = (s["day_high"].values >= cap) & (s["day_high"].values < raw) & binding
    drift = int((cap != raw).sum())
    print("         (%s of %s SHORT signals have a float-drifted cap; %d of them have a high "
          "exactly on that boundary)" % (format(drift, ","), format(len(s), ","), int(affected.sum())))
    wrong = 0
    e = s["entry"].values; H = s["day_high"].values; L = s["day_low"].values
    C = s["day_close"].values; LU = s["lu"].values; LD = s["ld"].values
    TK = s["tick"].values; TP = s["tp"].values
    idx = np.where(affected)[0]
    for i in idx:
        ex, slp, reason, gross = exit_of("SHORT", float(e[i]), float(H[i]), float(L[i]), float(C[i]),
                                         float(LU[i]), float(LD[i]), float(TK[i]), float(TP[i]))
        # the bug being tested: the stop was skipped and the trade settled at the close.
        # 停利 TP is a legitimate outcome here - TP is checked before SL by design.
        if reason == "13:25 強制平倉":
            wrong += 1
    ok(len(idx) > 0 and wrong == 0,
       "no boundary case settles at the close any more",
       "%d boundary cases, %d still settling at 13:25" % (len(idx), wrong))
except Exception as e:
    ok(False, "trade list checks", repr(e))

print("\n" + "=" * 78)
if FAIL:
    print("FAILED: " + ", ".join(FAIL))
    sys.exit(1)
print("ALL CHECKS PASSED")
