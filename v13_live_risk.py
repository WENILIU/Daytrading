"""
v13 LIVE-READINESS RISK PROBE
==============================
Measures the three things the backtest cannot tell us, before real money goes in.

  RISK 1  quote latency   - when does the 09:00 opening price actually become visible?
  RISK 2  borrowability   - can the SHORT leg (esp. the 1.5-3% band) actually be borrowed?
  RISK 3  order pipeline  - submit->ack latency, throughput, retry behaviour

Usage
    python v13_live_risk.py quotes      # run 08:58, measures RISK 1 live
    python v13_live_risk.py borrow      # any time, measures RISK 2
    python v13_live_risk.py orders      # during market hours, measures RISK 3
    python v13_live_risk.py all
"""
import sys, time, json, math, statistics
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np, pandas as pd

OUT = Path(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs")
sys.path.insert(0, str(OUT))
REPORT = OUT / "trading_logs" / f"live_risk_{datetime.now().strftime('%Y%m%d')}.json"
R = {"started": datetime.now().isoformat()}


def _save():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(R, default=str, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n[saved] {REPORT}")


def _pct(x, q):
    if not x:
        return None
    s = sorted(x)
    return s[min(len(s) - 1, int(len(s) * q))]


# ---------------------------------------------------------------- RISK 1
def risk_quotes():
    """Poll the TWSE quote API from just before 09:00 and record when each
    opening price first becomes readable. This is the real answer to
    'am I too late at 09:00:18?'."""
    import requests
    from concurrent.futures import ThreadPoolExecutor
    watch = [l.strip() for l in (OUT / "valid_stocks.txt").read_text().split() if l.strip()][:1200]
    API = "http://mis.twse.com.tw/stock/api/getStockInfo.jsp"
    target = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    if datetime.now() > target + timedelta(minutes=2):
        print("[RISK1] live window already passed today; measuring full-scan latency only")
    else:
        while datetime.now() < target - timedelta(seconds=2):
            time.sleep(0.5)
    t0 = time.time()
    sess = requests.Session(); sess.headers["User-Agent"] = "Mozilla/5.0"

    def one(c):
        try:
            r = sess.get(f"{API}?ex_ch=tse_{c}.tw&_={int(time.time()*1000)}", timeout=5)
            t = r.text; j = json.loads(t[t.find("{"):])
            m = j.get("msgArray", [])
            if not m:
                return c, None
            o = m[0].get("o", "-")
            return c, float(o) if o not in ("-", "", None) else None
        except Exception:
            return c, None

    first_seen, got = {}, 0
    for rnd in range(120):
        with ThreadPoolExecutor(max_workers=15) as ex:
            res = list(ex.map(one, watch))
        for c, o in res:
            if o and c not in first_seen:
                first_seen[c] = time.time() - t0
        got = len(first_seen)
        print(f"  round {rnd}: {got}/{len(watch)} have an open price, t={time.time()-t0:.1f}s", flush=True)
        if got >= len(watch) * 0.95:
            break
        time.sleep(0.5)
    lat = list(first_seen.values())
    R["risk1"] = {"watched": len(watch), "with_open": got,
                  "first_price_latency_s": {"median": _pct(lat, .5), "p95": _pct(lat, .95),
                                            "max": max(lat) if lat else None},
                  "full_scan_s": time.time() - t0}
    print(f"\n[RISK1] {got}/{len(watch)} readable; median {(_pct(lat,.5) or 0):.1f}s, "
          f"p95 {(_pct(lat,.95) or 0):.1f}s, full scan {time.time()-t0:.1f}s")
    print("  NOTE: 'readable at t' is the API side. Add your own submit->fill time (RISK 3).")


# ---------------------------------------------------------------- RISK 2
def risk_borrow():
    """Coverage of the SHORT leg by gap band. The 1.5-3% band is the new,
    untested part of v13 - that is what this measures."""
    import gap_fade_auto as G
    cfg = G.Config()
    borrow = G.get_borrowable_stocks()
    src = "finlab lending proxy" if borrow is not None else "UNAVAILABLE"
    print(f"[RISK2] borrow list source: {src}")

    # today's actual SHORT candidates, by band, from the live scan
    sig = pd.read_pickle(OUT / "signals_v13.pkl")
    sig = sig[(sig["direction"] == "SHORT") & (sig["date"] >= sig["date"].max() - pd.Timedelta(days=45))]
    sig["band"] = pd.cut(sig["abs_gap"], [0.015, 0.03, 0.05, 9], labels=["1.5-3%", "3-5%", "5%+"])
    tab = sig.groupby("band", observed=True).agg(n=("stock", "size"), stocks=("stock", "nunique"))
    if borrow is not None:
        sig["ok"] = sig["stock"].astype(str).isin(borrow)
        tab["borrowable_pct"] = sig.groupby("band", observed=True)["ok"].mean() * 100
    print(tab.to_string())
    R["risk2"] = {"source": src, "recent_short_signals_45d": tab.reset_index().astype(str).to_dict("records")}

    # Authoritative check: 群益 API 資券 query (credit_enquires).
    # Needs the API app credentials; set them in the environment.
    import os
    key, sec = os.getenv("YUANTA_APP_KEY"), os.getenv("YUANTA_APP_SECRET")
    if not key or not sec:
        R["risk2"]["credit_enquires"] = "skipped: set YUANTA_APP_KEY / YUANTA_APP_SECRET"
        print("  [RISK2] 群益 資券 query skipped - set YUANTA_APP_KEY / YUANTA_APP_SECRET")
    else:
        try:
            from shioaji import Shioaji
            api = Shioaji()
            api.connect(app_id=key, app_secret=sec)
            probe = [str(x) for x in sig["stock"].astype(str).drop_duplicates().head(60)]
            ok = stop = err = 0
            detail = []
            try:
                res = api.credit_enquires(probe)
                for row in (res if isinstance(res, (list, tuple)) else [res]):
                    err += 1
                    detail.append(str(row)[:200])
                print(f"  [RISK2] credit_enquires returned {len(detail)} rows")
            except Exception as e:
                print(f"  [RISK2] credit_enquires failed: {str(e)[:200]}")
            R["risk2"]["credit_enquires"] = {"probed": len(probe), "rows": len(detail),
                                             "sample": detail[:5]}
        except Exception as e:
            R["risk2"]["credit_enquires"] = f"failed: {str(e)[:250]}"
            print(f"  [RISK2] shioaji connect failed: {str(e)[:200]}")
    print("  ACTION: if the 1.5-3% band borrow rate is materially below the 5% band,")
    print("          the v13 breadth advantage is partly theoretical until confirmed with 群益.")


# ---------------------------------------------------------------- RISK 3
def risk_orders():
    """Submit non-filling test orders (limit at the down side) and time the ack."""
    import gap_fade_auto as G
    cfg = G.Config()
    tr = G.GapFadeAutoTrader(cfg)
    try:
        tr.connect()
    except Exception as e:
        print(f"[RISK3] cannot connect to SKCOM now ({str(e)[:150]}) - run during market hours")
        R["risk3"] = {"error": str(e)[:300]}
        return
    lat, seqs = [], []
    try:
        for code, px in (("2330", 1.0), ("2454", 1.0), ("2317", 1.0)):
            o = tr.m_pSKOrder
            oo = None
            import sk  # SKCOM types come from the trader module
            oo = sk.STOCKORDER()
            oo.bstrFullAccount = tr.account
            oo.bstrStockNo = code
            oo.bstrBuySell = "0"
            oo.nQty = 500
            oo.bstrPrice = str(px)      # absurdly low -> never fills
            oo.bstrOrderType = "KS"
            t = time.time()
            msg, code_ret = o.SendStockOrder(tr.user_id, oo)
            dt = time.time() - t
            lat.append(dt)
            seqs.append((code, msg, code_ret))
            print(f"  submit {code} x500 @ {px}: ack {dt*1000:.0f}ms code={code_ret}")
    except Exception as e:
        print(f"  order probe failed: {str(e)[:200]}")
    finally:
        try:
            for code, msg, cr in seqs:
                if cr == 0:
                    tr.cancel_order(msg, code)
        except Exception:
            pass
        tr.disconnect()
    if lat:
        print(f"\n[RISK3] submit->ack n={len(lat)} median={statistics.median(lat)*1000:.0f}ms "
              f"max={max(lat)*1000:.0f}ms -> {1/statistics.median(lat):.1f} orders/s single-threaded")
        print(f"  22 orders would take {statistics.median(lat)*22:.1f}s sequentially")
    R["risk3"] = {"ack_latency_s": lat,
                  "orders_per_second": (1/statistics.median(lat)) if lat else None}


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("quotes", "all"):
        risk_quotes()
    if mode in ("borrow", "all"):
        risk_borrow()
    if mode in ("orders", "all"):
        risk_orders()
    _save()
