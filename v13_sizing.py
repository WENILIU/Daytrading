"""Single implementation of the live order-sizing rule (R9).

The same rule is needed by the backtest lab, the published trade list and the
per-day audit charts. It has already drifted apart three times (a shares/lots
confusion, a cap applied after the lot count, a skipped status never assigned),
so it lives here once and everyone else calls it.

Rule R9, measured 2026-10-27, impact term corrected 2026-11-01 (see STRATEGY.md
section 2, sizing lab):
  target = weight x capital x scale
  target = min(target, cap)                       # absolute notional per order
  target = min(target, dv_cap x T-1 turnover)     # impact cap; T-1 is the only
                                                  # legal proxy at 09:00. dv_cap =
                                                  # k_open x 25 pct = 25 pct of the
                                                  # opening auction, measured
  skip if 1 lot > floor_lot                       # lot granularity too coarse
  skip if 1 lot > dv_skip x T-1 turnover
  n = floor(target / lot)                         # whole lots only
  n = min(n, cash_left // lot)                    # zero margin

min_turnover_factor is retired. It was 5.0, i.e. a floor of 5 x equity on the
name's T-1 turnover, which was meant to hold participation at 5 pct. It does the
opposite of an impact cap: as the book grows it removes names, so the trade count
falls (14.4 -> 4.7 a day) instead of the order size. Measured on a 4.5M book it
costs 9 pct a year and makes the drawdown worse (-5.04 -> -5.21 pct). The
liquidity base is the fixed 10M in v13_build.py, which is not a multiple of
capital and does not move with it.
"""
import numpy as np

# adopted for live trading
K_OPEN = 0.1497          # median opening value / T-1 dollar turnover, measured
R9 = {"name": "R9", "scale": 1.0, "cap": None, "cap_pct": 0.25, "floor_lot": None,
      "floor_lot_pct": 0.25, "dv_cap": K_OPEN * 0.25, "min_turnover_factor": None}
R6 = {"name": "R6", "scale": 1.0, "cap": 1_000_000, "floor_lot": 250_000}
R7 = {"name": "R7", "scale": 0.5, "cap": 1_000_000, "floor_lot": 250_000}
FLOOR_ONLY = {"name": "floor", "scale": 1.0}


def lots_for(rule, w, px, cash_left, dv1=np.nan, capital=4_500_000):
    """Whole lots one order may take. `w` is the model target weight, `px` the entry
    price, `cash_left` the uncommitted cash for the day, `dv1` the name's T-1 dollar
    turnover (np.nan when unknown). Returns 0 when the order must be skipped."""
    lot = px * 1000.0
    if rule.get("scale", 1.0) != 1.0:
        w = w * rule["scale"]
    tgt = w * capital
    if rule.get("cap") is not None:
        tgt = min(tgt, rule["cap"])
    if rule.get("cap_pct") is not None:
        tgt = min(tgt, rule["cap_pct"] * capital)
    if rule.get("min_turnover_factor") is not None and np.isfinite(dv1) and dv1 > 0:
        if float(dv1) < rule["min_turnover_factor"] * capital:
            return 0
    if rule.get("dv_cap") is not None and np.isfinite(dv1) and dv1 > 0:
        tgt = min(tgt, rule["dv_cap"] * float(dv1))
    if rule.get("dv_skip") is not None and np.isfinite(dv1) and dv1 > 0 and lot > rule["dv_skip"] * float(dv1):
        return 0
    if rule.get("floor_lot") and lot > rule["floor_lot"]:
        return 0
    if rule.get("floor_lot_pct") is not None and lot > rule["floor_lot_pct"] * capital:
        return 0
    if rule.get("fixed") is not None:
        tgt = rule["fixed"]
    n = int(round(tgt / lot)) if rule.get("round") else int(tgt // lot)
    if rule.get("max_lots"):
        n = min(n, rule["max_lots"])
    if n * lot > cash_left + 1e-9:
        n = int(cash_left // lot)
    return max(n, 0)


def skip_reason(rule, w, px, dv1=np.nan, capital=4_500_000):
    """Why an order is not placed, or None when the target is simply too small to
    make a whole lot. Reporting only - lots_for() is the one that decides."""
    lot = px * 1000.0
    if rule.get("floor_lot") and lot > rule["floor_lot"]:
        return "1張市值過高"
    if rule.get("floor_lot_pct") is not None and lot > rule["floor_lot_pct"] * capital:
        return "1張市值超過單檔%d%%上限" % int(rule["floor_lot_pct"] * 100)
    if rule.get("dv_skip") is not None and np.isfinite(dv1) and dv1 > 0 and lot > rule["dv_skip"] * float(dv1):
        return "1張超過T-1成交額上限"
    tgt = w * capital
    if rule.get("cap") is not None:
        tgt = min(tgt, rule["cap"])
    if rule.get("cap_pct") is not None:
        tgt = min(tgt, rule["cap_pct"] * capital)
    if rule.get("min_turnover_factor") is not None and np.isfinite(dv1) and dv1 > 0:
        if float(dv1) < rule["min_turnover_factor"] * capital:
            return "T-1成交額低於淨值%d倍(參與率上限)" % rule["min_turnover_factor"]
    if rule.get("dv_cap") is not None and np.isfinite(dv1) and dv1 > 0:
        tgt = min(tgt, rule["dv_cap"] * float(dv1))
    if tgt < lot:
        return "整張不足"
    return None
