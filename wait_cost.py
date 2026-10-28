# -*- coding: utf-8 -*-
"""What does waiting T seconds after the open cost, on the trades the strategy
actually takes?

LIVE_READINESS.md 11.15: the live path scans once at ~09:00:06-10 and only sees
part of the day's signals. Waiting sees more signals but pays for the move. The
visibility half is measured by risk1_signals.py; this is the price half.

Two traps found while building this, both of which silently produced wrong
numbers before they were fixed:
  1. A file named 1472_2025-03-26.json contains 2025-02-26 .. 2025-03-25 - the
     filename is the DOWNLOAD date and the data stops the day before. Bars from
     nineteen different days all sit at 09:00, so keying by clock time alone
     mixes days. Bars are filtered to the signal's own date.
  2. The cross-check against the signal's own entry price is kept as the gate.
     It is what caught this: 98% mismatch meant the alignment was wrong, not the
     market. A run where that check is not near 100% reports nothing.

cost = dir * (p_T - p_open) / p_open, dir=+1 LONG (paying more is a cost),
       dir=-1 SHORT (selling lower is a cost). Positive = waiting hurt.
"""
import json, os, pickle, re, sys, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")

N_DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 8

IDX = pickle.load(open("_min_index.pkl", "rb"))
daily = IDX["daily"]
by_code = {}
for (code, fdate), path in daily.items():
    by_code.setdefault(code, []).append((fdate, path))
for v in by_code.values():
    v.sort()

df = pd.read_pickle("signals_v13.pkl")
df = df[df["pred"].notna()].copy()
df["stock"] = df["stock"].astype(str)
df = df[df["pred_q"] >= 0.20]
df["dstr"] = df["date"].dt.strftime("%Y-%m-%d")
sig_days = set(df["dstr"])
have = sorted({d for c, v in by_code.items() for d, _ in v})
pick = [d for d in have if d in sig_days][::max(1, len(have) // N_DAYS)][:N_DAYS]
print("sampled days:", ", ".join(pick))

TS = re.compile(r"T(\d{2}):(\d{2}):")


def bars_for(code, day):
    """Bars for one stock on one day. The file that covers a day is the first one
    whose download date is AFTER it, and it may still not contain the day."""
    out = {}
    for fdate, path in by_code.get(code, []):
        if fdate <= day:
            continue
        try:
            data = json.load(open(path, encoding="utf-8")).get("data", [])
        except Exception:
            continue
        got = 0
        for b in data:
            ts = b.get("date", "")
            if ts[:10] != day:
                continue
            m = TS.search(ts)
            if not m:
                continue
            out[(int(m.group(1)), int(m.group(2)))] = b
            got += 1
        if got:
            return out
        # otherwise keep looking at the next file
    return out


rows, matched, mismatch = [], 0, 0
for d in pick:
    for _, s in df[df["dstr"] == d].iterrows():
        at = bars_for(s["stock"], d)
        b0 = at.get((9, 0))
        if not b0:
            continue
        p_open = float(b0["open"])
        entry = float(s["entry"])
        if p_open <= 0 or entry <= 0:
            continue
        if abs(p_open - entry) / entry <= 0.002:
            matched += 1
        else:
            mismatch += 1
            continue          # do not measure on a bar we cannot identify
        dsign = 1.0 if s["direction"] == "LONG" else -1.0
        for T, hh, mm in ((60, 9, 1), (120, 9, 2), (180, 9, 3)):
            b = at.get((hh, mm))
            if not b:
                continue
            p = float(b["open"])
            if p > 0:
                rows.append({"dir": s["direction"], "wait_s": T,
                             "cost_pct": dsign * (p - p_open) / p * 100.0})

tot = matched + mismatch
print(f"\ncross-check the 09:00 bar against the signal entry: "
      f"{matched}/{tot} match within 0.2% ({matched/max(1,tot)*100:.1f}%)")
if matched / max(1, tot) < 0.95:
    print("ALIGNMENT NOT PROVEN - reporting nothing rather than a wrong number.")
    sys.exit(1)

R = pd.DataFrame(rows)
print(f"signals measured: {len(R)//3} | rows {len(R)}\n")
print(f"{'wait':>6} {'n':>6} {'mean%':>8} {'median%':>8} {'p90%':>8} {'helped%':>8} {'hurt>0.3%':>10}")
for T in (60, 120, 180):
    v = R[R["wait_s"] == T]["cost_pct"].values
    if len(v) < 20:
        print(f"{T:>6} {len(v):>6}  too few"); continue
    print(f"{T:>6} {len(v):>6} {v.mean():>8.3f} {np.median(v):>8.3f} "
          f"{np.percentile(v,90):>8.3f} {(v<0).mean()*100:>8.1f} {(v>0.3).mean()*100:>10.1f}")
for dr in ("SHORT", "LONG"):
    v = R[(R["wait_s"] == 60) & (R["dir"] == dr)]["cost_pct"].values
    if len(v) >= 20:
        print(f"  {dr:<6} wait 60s: n={len(v)} mean {v.mean():+.3f}% "
              f"median {np.median(v):+.3f}% helped {100*(v<0).mean():.1f}%")
