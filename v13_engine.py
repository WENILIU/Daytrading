"""Gap Fade v13 - per-trade audit / live plan generator.

Two sizing views, same signals, same day:
  A = published backtest sizing (compounding equity, the allocation loop of
      v13_dstune.run) -> reproduces the reported CAGR/MDD.
  C = what a fixed 4,500,000 TWD account can ACTUALLY place: whole lots
      (1,000 shares), no margin.

Usage
  python v13_audit_day.py --since 2026-07-27 --csv D:\\...\\daytrading.csv
  python v13_audit_day.py --date 2026-10-21 --out D:\\...\\DayTrading
"""
import argparse, os, sys, json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

CAP0 = 4_500_000
BP1, BP2, M1, M2, MP = 0.015, 0.045, 10.0, 2.5, 0.25
COST = 0.00109
SLO = 0.04


def allocate(pos, pr, base, lots=True):
    """Exact allocation loop used by the backtest engine."""
    rem = base
    sel = []
    for i in range(len(pos)):
        if pos[i] <= 0:
            continue
        if lots:
            sh = float(int(pos[i] * base / (pr[i] * 1000)) * 1000)
            if sh < 1000:
                continue
            if sh * pr[i] > rem:
                sh = float(int(rem / (pr[i] * 1000)) * 1000)
                if sh < 1000:
                    continue
        else:
            sh = pos[i] * base / pr[i]
            if sh * pr[i] > rem:
                sh = rem / pr[i]
        rem -= sh * pr[i]
        sel.append((i, sh))
    return sel


def tick_size(price):
    """TWSE/TPEx price increment at `price`.

    Same table as gap_fade_auto.get_tick_size, measured there against TPEx published
    limits and 8.15M observed stock-days. Kept here so the audit charts can show the
    prices an order would actually carry; gap_fade_auto.py stays the source of truth.
    """
    if price < 10:
        return 0.01
    elif price < 50:
        return 0.05
    elif price < 100:
        return 0.1
    elif price < 500:
        return 0.5
    elif price < 1000:
        return 1.0
    return 5.0


def snap_price(price):
    """Round to the nearest price the exchange accepts (41.44 in the 10-50 band is not)."""
    t = tick_size(price)
    return round(round(price / t) * t, 2)


def exit_of_legal(direction, entry, hi, lo, cl, lu, ld, tk, tp):
    """exit_of with SL/TP snapped to legal prices.

    exit_of is what the backtest and the model target are built on (continuous
    prices). This is what would actually be submitted to the broker. Branch order is
    identical. Measured effect on the 2026-07-23..10-22 4.5M trade list: -0.04% of
    total PnL, worst single trade 400 TWD - nothing economically, but 28.1% of the
    stop/target exits carried an unpriceable number and would have been rejected.
    Returns (exit_price, sl_price, tp_price, reason, gross).
    """
    if direction == "SHORT":
        tpp = snap_price(entry * (1 - tp))
        slp = min(snap_price(entry * (1 + SLO)), round(lu - tk, 2))
        if lo <= tpp:
            return tpp, slp, tpp, "停利 TP", (entry - tpp) / entry
        if hi >= slp:
            r = "停損(觸漲停上限)" if slp < entry * (1 + SLO) - 1e-9 else "停損 SL"
            return slp, slp, tpp, r, -(slp - entry) / entry
        return cl, slp, tpp, "13:25 強制平倉", (entry - cl) / entry
    tpp = snap_price(entry * (1 + tp))
    slp = max(snap_price(entry * (1 - SLO)), round(ld + tk, 2))
    if hi >= tpp:
        return tpp, slp, tpp, "停利 TP", (tpp - entry) / entry
    if lo <= slp:
        r = "停損(觸跌停下限)" if slp > entry * (1 - SLO) + 1e-9 else "停損 SL"
        return slp, slp, tpp, r, -(entry - slp) / entry
    return cl, slp, tpp, "13:25 強制平倉", (cl - entry) / entry


def exit_of(direction, entry, hi, lo, cl, lu, ld, tk, tp):
    """Reproduce v13_train.pnl() branch order -> (exit_price, sl_price, reason, gross)."""
    if direction == "SHORT":
        tpp = entry * (1 - tp); slp = min(entry * (1 + SLO), round(lu - tk, 2))
        if lo <= tpp:
            return tpp, slp, "停利 TP", tp
        if hi >= slp:
            return slp, slp, ("停損(觸漲停上限)" if slp < entry * (1 + SLO) - 1e-9 else "停損 SL"), -(slp - entry) / entry
        return cl, slp, "13:25 強制平倉", (entry - cl) / entry
    tpp = entry * (1 + tp); slp = max(entry * (1 - SLO), round(ld + tk, 2))
    if hi >= tpp:
        return tpp, slp, "停利 TP", tp
    if lo <= slp:
        return slp, slp, ("停損(觸跌停下限)" if slp > entry * (1 - SLO) + 1e-9 else "停損 SL"), -(entry - slp) / entry
    return cl, slp, "13:25 強制平倉", (cl - entry) / entry


def run_backtest(capture=None, capital=CAP0, min_lot_value=0.0, min_weight=0.0, kmode="pred", tmode="on", sig="signals_v13.pkl", scale=1.0, min_range=0.0):
    """capture: list of dates to record, or a (start,end) tuple, or None.
    capital: fixed account size for the C view. min_lot_value: skip stocks whose
    1 lot costs more than this. min_weight: skip designs below this weight."""
    d = pd.read_pickle(sig)
    d = d[d["pred"].notna()].copy()
    d["stock"] = d["stock"].astype(str)
    if min_range > 0:
        rng = (d["day_high"] - d["day_low"]).abs() / d["entry"]
        d = d[rng >= min_range]
    u = d[d["pred_q"] >= 0.20]
    tr = {}
    for direc in ["SHORT", "LONG"]:
        s = u[u["direction"] == direc].sort_values("date")
        if len(s) == 0:
            continue
        s["t30"] = s["p"].rolling(30, min_periods=30).mean().shift(1)
        for dt, x in zip(s["date"], s["t30"].values):
            tr[(dt, direc)] = x
    G = {dt: sub for dt, sub in u.groupby("date")}
    eq = CAP0; peak = CAP0
    curve = []
    got = {}
    for dt in sorted(G):
        sub = G[dt]
        cdd = (eq - peak) / peak
        rs = 0.12 if cdd < -0.012 else (0.3 if cdd < -0.006 else 1.0)
        zd = sub["zt_dist"].values
        zm = np.where(zd < BP1, M1, np.where(zd < BP2, M2, 1.0))
        p = np.asarray(sub["pred"].values, dtype=float)
        pq = np.asarray(sub["pred_q"].values, dtype=float)
        if kmode == "one":
            kM = np.ones(len(p))
        elif kmode == "rank":
            kM = np.clip(0.5 + 1.5 * (np.nan_to_num(pq, nan=0.2) - 0.2) / 0.8, 0.5, 2.0)
        else:
            kM = np.where(np.isfinite(p), np.clip(0.5 + np.nan_to_num(p) / 0.02, 0, 2), 1.0)
        p30 = np.array([tr.get((dt, x), np.nan) for x in sub["direction"]], dtype=float)
        kT = np.ones(len(p)) if tmode == "off" else np.where(np.isnan(p30), 1.0, np.clip(0.5 + p30 / 0.02, 0.3, 2.0))
        pos = np.minimum(np.asarray(sub["base_pos"].values, dtype=float) * scale * zm * rs * kM * kT, MP * scale)
        o = np.argsort(-np.nan_to_num(p, nan=-99))
        pos = pos[o]
        pn = np.asarray(sub["p"].values, dtype=float)[o]
        pr = np.asarray(sub["entry"].values, dtype=float)[o]
        if min_lot_value > 0 or min_weight > 0:
            keep = np.ones(len(pos), bool)
            if min_lot_value > 0:
                keep &= (pr * 1000) <= min_lot_value
            if min_weight > 0:
                keep &= (pos >= min_weight)
            pos = np.where(keep, pos, 0.0)
        ds = str(pd.Timestamp(dt).date())
        tgt = capture is not None and (ds in capture if not isinstance(capture, tuple)
                                       else capture[0] <= ds <= capture[1])
        res = {}
        caps = {"A": eq, "C": capital}
        for mode in ["A", "C"]:
            sel = allocate(pos, pr, caps[mode], lots=True)
            if sel:
                w = np.array([sh * pr[i] for i, sh in sel]); r = np.array([pn[i] for i, sh in sel])
                res[mode] = (float((w * r).sum() / caps[mode]), float(w.sum() / caps[mode]), sel)
            else:
                res[mode] = (0.0, 0.0, sel)
            if tgt:
                rows = []
                for k, (i, sh) in enumerate(sel):
                    rec = sub.iloc[o[i]].to_dict()
                    rec["_rank"] = k + 1
                    rec["_shares"] = sh
                    rec["_notional"] = sh * float(rec["entry"])
                    rec["_weight"] = float(pos[i])
                    rec["_rs"] = rs
                    rec["_zm"] = float(zm[o[i]])
                    rec["_kM"] = float(kM[o[i]])
                    rec["_kT"] = float(kT[o[i]])
                    rows.append(rec)
                got.setdefault(mode, []).extend(rows)
        eq *= 1 + res["A"][0]
        peak = max(peak, eq)
        curve.append((dt, eq, res["A"][0], res["A"][1], len(res["A"][2]),
                      res["C"][0], res["C"][1], len(res["C"][2]), cdd, rs,
                      float(sub["market_ret"].iloc[0]), len(sub)))
    cols = ["date", "eq", "A_pnl", "A_expo", "A_n", "C_pnl", "C_expo", "C_n", "cdd", "rs", "market_ret", "n_signals"]
    cv = pd.DataFrame(curve, columns=cols)
    cv["date"] = pd.to_datetime(cv["date"])
    cv = cv.set_index("date").sort_index()
    return cv, {m: (pd.DataFrame(v) if v else pd.DataFrame()) for m, v in got.items()}, d


def stats(s):
    e = (1 + s).cumprod()
    r = e.pct_change().fillna(0)
    ny = (e.index[-1] - e.index[0]).days / 365.25
    return dict(cagr=((e.iloc[-1] / e.iloc[0]) ** (1 / ny) - 1) * 100,
                mdd=((e - e.cummax()) / e.cummax()).min() * 100,
                sharpe=r.mean() / r.std() * (243 ** 0.5),
                calmar=abs((((e.iloc[-1] / e.iloc[0]) ** (1 / ny) - 1) * 100) / (((e - e.cummax()) / e.cummax()).min() * 100)),
                curve=e)
