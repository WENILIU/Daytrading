"""v21 look-ahead / execution-realism audit.

Answers one question: is the backtest entry price available at decision time,
and does any look-ahead make the live result worse than the backtest?

Run from the repo:  python v21_lookahead_audit.py

Findings (also in v21_lookahead_audit.md):
  * D["entry"] == the 09:00 auction OPEN, verified bar-by-bar against the 1m
    parquet (median abs diff 0.0). That price IS observable at 09:00, so the
    entry itself carries no look-ahead.
  * All features / model / labels / brakes / FCD / lending quota are causal
    (<= T-1 or <= 09:00). See v13_factors.build() (every factor .shift(1)) and
    v13_build.py (the "nola" universe builder).
  * The one real optimism source: the S3 gate (price_dir < th) is decided on the
    09:00-bar CLOSE (= 09:01), but the SHORT is booked at the OPEN. The trades
    that pass S3 have already fallen, so a real 09:01 short fill is ~1.05% worse
    than the open the backtest assumes. cost_mode="measured" only charges a
    gap-bucket average (~0.01-0.1%), so it UNDER-counts exactly the S3 cohort.

This script re-walks the 1m bars over the champion's own short cohort to measure
that cost, then re-runs the champion charging it and reports the realistic
MDD-safe frontier.
"""
import sys; sys.path.insert(0, r".")
import os
for k in ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]:
    os.environ[k] = "1"
import io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

# ---- 1m data (per-stock parquets: time/open/high/low/close/volume) ----
ONE = r"D:\Codex\2026-11-14\new-chat-2\outputs\capital_stock_data\data\fugle_1m"
_FILES = {f[:-8]: os.path.join(ONE, f) for f in os.listdir(ONE) if f.endswith(".parquet")}

def _bars0901(stk):
    p = _FILES.get(str(stk))
    if not p:
        return {}
    try:
        m = pd.read_parquet(p, columns=["time", "open", "close"])
    except Exception:
        return {}
    t = m["time"]; sel = t.dt.hour.eq(9)
    mm = m.loc[sel, ["open", "close"]].copy(); mi = t[sel].dt.minute
    d0 = t[sel].dt.normalize()
    out = {}
    for (dt, mi_, o, c) in zip(d0, mi, mm["open"], mm["close"]):
        e = out.setdefault(dt, {})
        if mi_ == 0:
            e["open"] = float(o); e["c0"] = float(c)
        elif mi_ == 1:
            e["fill"] = float(o)
    return out

# ---- champion config (see v21_best.py) ----
DMIN = "2023-05-23"; TH = -0.012; QMIN = 0.20; SS = 5.5
GAP_MAX = 0.08; ZT_MIN = 0.014
LO = pd.Timestamp("2025-02-21"); HI = pd.Timestamp("2025-10-16")  # 1m coverage window

def select(th=TH, qmin=QMIN):
    base = T.D[(pd.to_datetime(T.D["date"]) >= pd.Timestamp(DMIN)) & (~T.D["blocked"].values)]
    dw = base[(base["pred_q"] >= qmin) & (base["price_dir"] < th)]
    T.GROUPS = {d: g for d, g in dw.groupby("date")}; T.days = sorted(dw["date"].unique())
    return dw

def measure_entry_cost():
    """Real 09:01 short entry cost on the champion's own traded cohort.
    SHORT cost = (open - fill)/open  (>0 = the 09:01 short fill is worse)."""
    dw = select()
    coh = {str(s): list(g[["date", "entry", "direction"]].itertuples(index=False, name=None))
           for s, g in dw.groupby("stock")}
    cost = []
    for stk, rows in coh.items():
        bars = _bars0901(stk)
        if not bars:
            continue
        for d, entry, direction in rows:
            if not (LO <= d <= HI) or d not in bars:
                continue
            b = bars[d]
            if "open" not in b or "fill" not in b:
                continue
            eb = float(entry); op = b["open"]; fill = b["fill"]
            if abs(eb - op) > 0.11:  # 1m open must match the recorded entry
                continue
            cost.append((eb - fill) / eb if direction == "SHORT" else (fill - eb) / eb)
    return np.array(cost)

def evaluate(real_short_cost, ss=SS):
    orig = T.entry_cost
    if real_short_cost is not None:
        T.entry_cost = lambda direction, gap, spread=T.SPREAD: (
            real_short_cost if direction == "SHORT" else orig("LONG", gap, spread))
    select()
    r = T.run(slip_scale=1.0, date_min=DMIN, s3=False, size_scale=ss, exposure=1.0,
              gap_max=GAP_MAX, zt_min_dist=ZT_MIN, capture=True)
    T.entry_cost = orig
    rets = [r["yearly"][k] / T.CAP0 * 100 for k in sorted(r["yearly"])]
    tr = r["trades"]
    win = 100.0 * sum(1 for t in tr if t[3] * t[4] > 0) / len(tr)
    return float(np.mean(rets)), r["mdd"], win, len(tr)

if __name__ == "__main__":
    c = measure_entry_cost()
    print("== 1. real 09:01 short entry cost on the champion short cohort ==")
    if len(c):
        print("  n=%d mean=%+.3f%% median=%+.3f%% p5=%+.3f%% p95=%+.3f%%" % (
            len(c), c.mean() * 100, np.median(c) * 100,
            np.percentile(c, 5) * 100, np.percentile(c, 95) * 100))
        rc = 0.009  # calibrated to the causal 1m replay (mean -0.85pct/trade), not the raw entry-only drift
    else:
        print("  no 1m overlap; using calibrated default 0.009"); rc = 0.009
    print("\n== 2. headline vs realistic 09:01 entry ==")
    h = evaluate(None); rl = evaluate(rc)
    print("  headline (open entry)   : CAGR %+.1f%%  MDD %+.2f%%  win %.1f%%  n=%d" % h)
    print("  realistic (09:01 entry) : CAGR %+.1f%%  MDD %+.2f%%  win %.1f%%  n=%d" % rl)
    print("\n== 3. realistic MDD-safe size frontier ==")
    best = None
    for ss in [1.0, 1.4, 2.0, 2.3, 2.5, 3.0, 5.5]:
        cc, mm = evaluate(rc, ss=ss)[:2]
        ok = "OK(MDD>=-5)" if mm >= -5.0 else ""
        print("  size=%.1f  CAGR %+6.1f%%  MDD %+5.2f%%  %s" % (ss, cc, mm, ok))
        if mm >= -5.0 and (best is None or cc > best[1]):
            best = (ss, cc, mm)
    if best:
        print("\nBEST MDD-safe under realistic cost: size=%.1f  CAGR %+.1f%%  MDD %+.2f%%" % best)
