"""Preflight: run the LIVE_READINESS section 6 checklist as an executed check.

The checklist used to be something the user reads at 08:55 and hopes they applied.
Every item here goes through the SAME code path live/paper will use, so a PASS
means "this exact dependency answered correctly just now", not "the file looks
like it should work".

Sends no orders. Safe at 08:55. Exits non-zero if anything essential failed.

    python preflight.py
"""
import sys, json, time
import pandas as pd
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, ".")
from gap_fade_auto import (Config, GapFadeAutoTrader, get_borrowable_stocks,
                          _ensure_finlab_login, _from_finlab, DISPOSAL_PANEL)

cfg = Config()
results = []


def add(name, ok, detail, level=None):
    lvl = level or ("PASS" if ok else "FAIL")
    results.append((lvl, name, detail))


t = GapFadeAutoTrader(cfg)

# 1. is today even a trading day
try:
    import finlab
    from finlab import data as fdata
    if _ensure_finlab_login():
        cal = fdata.get_calendar()
        # is_session wants a real datetime.date, not an ISO string
        session = bool(cal.is_session(date.today()))
        nxt = None
        try:
            nxt = cal.next_session(date.today())
        except Exception:
            pass
        add("trading calendar", session,
            f"{date.today().isoformat()} is_session={session}"
            + (f" | next session {nxt}" if nxt else ""),
            "PASS" if session else "WARN")
    else:
        add("trading calendar", False, "finlab login failed", "FAIL")
except Exception as e:
    add("trading calendar", False, f"{type(e).__name__}: {e}", "WARN")

# 2. the model and its inputs
try:
    mp = Path(cfg.model_path)
    add("v13 model file", mp.exists(),
        f"{mp.name} {'exists' if mp.exists() else 'MISSING'} "
        f"(mtime {datetime.fromtimestamp(mp.stat().st_mtime):%Y-%m-%d %H:%M} "
        f"{mp.stat().st_size/1e6:.1f}MB)" if mp.exists() else f"{mp} missing")
except Exception as e:
    add("v13 model file", False, f"{type(e).__name__}: {e}")

# 3. factor panel age - the single most expensive silent failure
#    (panel stopped at 2026-08-19 once = 68 days = ~11 pct of the edge lost)
try:
    t._load_reference_panels()
    lag = getattr(t, "_factor_lag", None)
    n_keys = len(getattr(t, "_t1_turnover", {}))
    degraded = getattr(t, "_factor_row", None) is None
    if lag is None:
        add("factor panel age", False,
            "panel did not load at all - the model would score with NaN factors", "FAIL")
    else:
        asof = (pd.Timestamp(date.today()) - pd.Timedelta(days=int(lag))).date()
        ok = (not degraded) and lag <= 1
        detail = (f"as-of {asof} lag {lag}d, turnover keys {n_keys}; "
                  f"factors {'WILL be used' if not degraded else 'REPLACED BY NaN'} "
                  f"(stale limit {cfg.max_factor_lag_days}d). Measured cost of the panel "
                  f"going away: 2023-25 segment 1692% -> 260%. Fix: "
                  f"`python v13_factors.py --refresh`")
        add("factor panel age", ok, detail, "PASS" if ok else "FAIL")
except Exception as e:
    add("factor panel age", False, f"{type(e).__name__}: {e}")

# 4. disposal / day-trade restriction source must be finlab, not a fallback
try:
    n = len(_from_finlab(date.today().isoformat()))
    add("disposal source (finlab)", n > 0,
        f"finlab returned {n} restricted codes for today "
        f"(a fallback source silently covers 上市 only)", "PASS" if n > 0 else "FAIL")
except Exception as e:
    add("disposal source (finlab)", False, f"{type(e).__name__}: {e}")

# 5. borrowable list (SHORT needs a lending quota)
try:
    b = get_borrowable_stocks()
    nb = len(b[0]) if isinstance(b, tuple) else len(b)
    add("borrowable / lending quota", nb > 100, f"{nb} codes with a T-1 quota",
        "PASS" if nb > 100 else "WARN")
except Exception as e:
    add("borrowable / lending quota", False, f"{type(e).__name__}: {e}", "WARN")

# 6. the scan feed must answer for BOTH markets
try:
    codes = t._load_stock_list()
    add("stock list", len(codes) > 1500, f"{len(codes)} codes",
        "PASS" if len(codes) > 1500 else "FAIL")
    sample = codes[:400]
    rows, source = t._batch_scan(sample)
    by_ex = {}
    for r in rows:
        by_ex[r.get("x") or "?"] = by_ex.get(r.get("x") or "?", 0) + 1
    both = by_ex.get("TWSE", 0) > 0 and by_ex.get("TPEx", 0) > 0
    add("scan feed (both markets)", both,
        f"via {source}: {len(rows)} rows for a {len(sample)}-code sample, {by_ex}",
        "PASS" if both else "FAIL")
except Exception as e:
    add("scan feed (both markets)", False, f"{type(e).__name__}: {e}")

# 7. the Capital account itself: login, reply host, quote server, certificate
try:
    t.connect()
    ok = bool(t._logged_in and t.account and t.m_pSKOrder)
    add("Capital SKCOM", ok,
        f"login={t._logged_in} account={t.account} order_lib={'OK' if t.m_pSKOrder else 'None'}")
except Exception as e:
    add("Capital SKCOM", False, f"{type(e).__name__}: {e}")

# 8. equity state: live has never traded, so this file must not exist
try:
    p = Path(cfg.equity_state_path)
    if p.exists():
        st = json.loads(p.read_text(encoding="utf-8"))
        add("equity state (live)", False,
            f"{p.name} exists: peak={st.get('peak_equity'):,.0f} "
            f"current={st.get('current_equity'):,.0f} updated={st.get('updated')} - "
            f"if that came from a simulated day the drawdown brake starts wrong",
            "WARN")
    else:
        add("equity state (live)", True,
            f"{p.name} absent -> live/paper start flat at {cfg.capital:,.0f}, "
            "no drawdown brake", "PASS")
except Exception as e:
    add("equity state (live)", False, f"{type(e).__name__}: {e}", "WARN")

try:
    t.disconnect()
except Exception:
    pass

print("\n" + "=" * 78)
print(f"PREFLIGHT - {datetime.now():%Y-%m-%d %H:%M:%S}")
print("=" * 78)
for lvl, name, detail in results:
    print(f"  [{lvl:<4}] {name}")
    print(f"           {detail}")
fails = [r for r in results if r[0] == "FAIL"]
warns = [r for r in results if r[0] == "WARN"]
print("-" * 78)
print(f"  {len(results)} checks | {len(fails)} FAIL | {len(warns)} WARN")
if fails:
    print("  VERDICT: do NOT start paper/live. Fix the FAIL items first.")
    sys.exit(1)
if warns:
    print("  VERDICT: usable, but read the WARN lines before deciding.")
else:
    print("  VERDICT: clear. Next: python gap_fade_auto.py scan   then   "
          "python gap_fade_auto.py paper")
