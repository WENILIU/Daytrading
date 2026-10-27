"""What does the 10-25 second opening delay actually cost?

RISK1 measured on the strategy's own pool: the opening price is readable at
p50 +10s / p90 +18s / max +23.5s (LIVE_READINESS.md section 1). The backtest
fills at the 09:00:00 open. This measures the difference on real 1-minute data
instead of guessing.

Three variants, SAME exit engine, SAME 1-minute path, so the delta is purely
the entry:
  A  entry = the opening price            (what the backtest assumes)
  B  entry = close of the 09:00 bar      (act ~+10-25s: read the open, submit)
  C  entry = close of the 09:01 bar      (act ~+60s, pessimistic)

Exits are the live rules: SL 4 pct capped at 漲停-1 tick, TP from the model's
own tp column, force close at the 13:20 bar. A stop bar that reaches the price
limit fills at the limit, not at the stop price (the pinned case measured in the
rehearsal). Cost 0.109% per side.

Data: the local 1-minute library covers 2026-01-02 .. 2026-10-16 for ~979 names.
"""
import json, os, sys, pickle, glob, collections
import numpy as np, pandas as pd

sys.path.insert(0, ".")
from gap_fade_auto import calc_effective_sl, Direction

COST = 0.00109
IDX = pickle.load(open("stock_1min_index.pkl", "rb"))

df = pd.read_pickle("signals_v13.pkl")
df = df[df["pred"].notna()]
df = df[df["pred_q"] >= 0.20]
df = df[(df["date"] >= "2026-01-01") & (df["date"] <= "2026-10-16")]
print(f"signals in the 1-minute window (pred_q>=0.20): {len(df)}")

def day_bars(stock, want_days):
    """{date: bars} for ONE stock, only the days we need, then released.

    Loading every stock at once blew up memory (each monthly file carries
    190 days of 1-minute bars for ~979 names).
    """
    out = {}
    d = IDX.get(str(stock))
    if not d:
        return out
    for f in glob.glob(os.path.join(d, "*2026-01.json")):
        try:
            j = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        by = collections.defaultdict(list)
        for b in j.get("data", []):
            k = b["date"][:10]
            if k in want_days:
                by[k].append(b)
        for k, v in by.items():
            out[k] = sorted(v, key=lambda x: x["date"])
        del j
    return out


def simulate(bars, entry, sl, tp, direction, lu, ld):
    """Walk the 1-minute path. Returns (exit_price, reason)."""
    short = direction == "SHORT"
    for b in bars:
        t = b["date"][11:16]
        if t > "13:20":
            break
        hi, lo = b["high"], b["low"]
        if short:
            if hi >= sl:
                return (lu if hi >= lu else sl), "STOP_LOSS"
            if lo <= tp:
                return tp, "TAKE_PROFIT"
        else:
            if lo <= sl:
                return (ld if lo <= ld else sl), "STOP_LOSS"
            if hi >= tp:
                return tp, "TAKE_PROFIT"
    tail = [b for b in bars if b["date"][11:16] <= "13:20"]
    return (tail[-1]["close"] if tail else entry), "FORCE_CLOSE"


def pnl_pct(entry, exit_px, direction):
    raw = (entry - exit_px) / entry if direction == "SHORT" else (exit_px - entry) / entry
    return raw - 2 * COST


rows = []
n_no_file = 0
by_stock = {k: list(g.itertuples()) for k, g in df.groupby("stock")}
print(f"stocks to load: {len(by_stock)}")
for si, (stock, sigs) in enumerate(sorted(by_stock.items())):
    days = {str(r.date)[:10] for r in sigs}
    BB = day_bars(stock, days)
    for r in sigs:
        day = str(r.date)[:10]
        B = BB.get(day)
        if not B:
            n_no_file += 1
            continue
        if abs(B[0]["open"] - r.entry) > 1e-6:
            continue                    # data disagrees with the signal file
        if len(B) < 3:
            continue
        d = r.direction
        sl, _ = calc_effective_sl(
            r.entry, r.prev_close,
            Direction.SHORT if d == "SHORT" else Direction.LONG, 0.04)
        # SHORT take-profit is BELOW the entry, LONG above it.
        tp = round(r.entry * (1 - r.tp) if d == "SHORT" else r.entry * (1 + r.tp), 2)

        xA, rA = simulate(B, r.entry, sl, tp, d, r.lu, r.ld)
        eB = B[0]["close"]
        xB, rB = simulate(B[1:], eB, sl, tp, d, r.lu, r.ld)
        eC = B[1]["close"]
        xC, rC = simulate(B[2:], eC, sl, tp, d, r.lu, r.ld)

        def adverse(e):
            raw = (e - r.entry) / r.entry
            return raw if d == "LONG" else -raw

        rows.append({
            "date": day, "stock": str(stock), "dir": d, "zt_dist": r.zt_dist,
            "pred_q": r.pred_q,
            "entry": r.entry, "eB": eB, "eC": eC,
            "slipB": adverse(eB) * 100, "slipC": adverse(eC) * 100,
            "pnlA": pnl_pct(r.entry, xA, d) * 100,
            "pnlB": pnl_pct(eB, xB, d) * 100,
            "pnlC": pnl_pct(eC, xC, d) * 100,
            "reasonA": rA, "reasonB": rB,
        })
    del BB
    if (si + 1) % 100 == 0:
        print(f"  {si+1}/{len(by_stock)} stocks, {len(rows)} trades")

R = pd.DataFrame(rows)
print(f"simulated: {len(R)} | no 1-minute file for that day: {n_no_file}")
print(f"date range actually used: {R['date'].min()} .. {R['date'].max()}")


def q(v, p):
    v = np.sort(np.asarray(v, dtype=float))
    return v[min(len(v) - 1, int(p * len(v)))]


print("\n" + "=" * 78)
print("ENTRY SLIPPAGE vs the opening price (positive = worse than the backtest)")
print("=" * 78)
for d in ("SHORT", "LONG"):
    g = R[R["dir"] == d]
    if not len(g):
        continue
    print(f"\n{d}  n={len(g)}")
    for name, col in (("act at ~+10-25s (09:00 bar close)", "slipB"),
                      ("act at ~+60s   (09:01 bar close)", "slipC")):
        v = g[col].values
        print(f"  {name}: mean {v.mean():+.3f}% | median {np.median(v):+.3f}% | "
              f"p90 {q(v,0.9):+.3f}% | favourable {np.mean(v<0)*100:.1f}%")

print("\n" + "=" * 78)
print("P&L PER TRADE (% of notional, cost included) - same exit engine")
print("=" * 78)
print(f"{'variant':<34}{'n':>6}{'mean%':>8}{'median%':>9}{'win%':>7}{'sum%':>10}")
for name, col in (("A entry = opening price", "pnlA"),
                  ("B entry = +10-25s", "pnlB"),
                  ("C entry = +60s", "pnlC")):
    v = R[col].values
    print(f"{name:<34}{len(v):>6}{v.mean():>8.3f}{np.median(v):>9.3f}"
          f"{np.mean(v>0)*100:>7.1f}{v.sum():>10.0f}")

print("\n" + "=" * 78)
print("THE COST OF THE DELAY (B - A), by direction and by distance to 漲停")
print("=" * 78)
for d in ("SHORT", "LONG"):
    g = R[R["dir"] == d]
    if not len(g):
        continue
    dd = (g["pnlB"] - g["pnlA"]).values
    print(f"{d:<6} n={len(g):>5} | delay effect mean {dd.mean():+.3f}% | "
          f"median {np.median(dd):+.3f}% | hurts {np.mean(dd<0)*100:.1f}% of trades")
print("\nSHORT, split by zt_dist (how close the open was to 漲停):")
for lo_, hi_ in ((0, 0.015), (0.015, 0.045), (0.045, 9)):
    g = R[(R["dir"] == "SHORT") & (R["zt_dist"] >= lo_) & (R["zt_dist"] < hi_)]
    if not len(g):
        continue
    dd = (g["pnlB"] - g["pnlA"]).values
    print(f"  zt_dist {lo_*100:>4.1f}-{min(hi_,100)*100:>5.1f}%  n={len(g):>5}  "
          f"delay effect mean {dd.mean():+.3f}%  median {np.median(dd):+.3f}%")

print("\n" + "=" * 78)
print("THE ONLY SUBSET THAT MATTERS: the trades the strategy actually funds")
print("=" * 78)
print("The backtest ranks by pred and funds the top of the list; averaging over")
print("every passing signal understates the edge. Split by model quantile:")
print(f"{'pred_q bucket':<16}{'n':>6}{'A mean%':>9}{'B mean%':>9}{'delay%':>9}{'kept':>8}")
for lo_, hi_ in ((0.20, 0.60), (0.60, 0.80), (0.80, 0.90), (0.90, 0.95), (0.95, 1.01)):
    g = R[(R["pred_q"] >= lo_) & (R["pred_q"] < hi_)]
    if not len(g):
        continue
    a = g["pnlA"].mean(); b = g["pnlB"].mean()
    keep = (b / a * 100) if a else float("nan")
    print(f"{f'{lo_:.2f}-{hi_:.2f}':<16}{len(g):>6}{a:>9.3f}{b:>9.3f}{b-a:>+9.3f}{keep:>7.0f}%")

top = R[R["pred_q"] >= 0.90]
if len(top):
    a = top["pnlA"].mean(); b = top["pnlB"].mean()
    print(f"\n  funded-like (pred_q>=0.90): n={len(top)} | A {a:+.3f}% | B {b:+.3f}% | "
          f"delay {b-a:+.3f}% | {b/a*100:.0f}% of the edge survives")
    rt = 2 * 0.109
    print(f"  for scale: all fees together are {rt:.3f}% round trip, so the delay is "
          f"{abs(b-a)/rt*100:.0f}% as large as the entire fee bill")

print("\nexit-reason mix (A vs B) - does the delay change WHICH stop fires?")
ca = R["reasonA"].value_counts().to_dict()
cb = R["reasonB"].value_counts().to_dict()
for k in sorted(set(ca) | set(cb)):
    print(f"  {k:<14} A {ca.get(k,0):>5}   B {cb.get(k,0):>5}")

R.to_pickle("entry_lag_2026.pkl")
print("\nwrote entry_lag_2026.pkl")
