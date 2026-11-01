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
def risk_orders(n_probe=6):
    """Time the PRODUCTION order path: SendStockStrategyDayTrade, exactly as the
    live trader calls it, then cancel through CancelTSStrategyOrderV1.

    Test orders are 1 張 bought at the day's down-limit price, so they are valid
    (the exchange accepts them) but cannot fill unless the stock hits 跌停.
    A plain SendStockOrder is rejected with code 999 on this account, so measuring
    it would tell us nothing about the real pipeline.
    """
    import gap_fade_auto as G
    cfg = G.Config()
    tr = G.GapFadeAutoTrader(cfg)
    try:
        tr.connect()
    except Exception as e:
        print(f"[RISK3] cannot connect to SKCOM now ({str(e)[:150]}) - run during market hours")
        R["risk3"] = {"error": str(e)[:300]}
        return
    lat, keys = [], []
    try:
        import requests
        API = "http://mis.twse.com.tw/stock/api/getStockInfo.jsp"
        sess = requests.Session(); sess.headers["User-Agent"] = "Mozilla/5.0"
        watch = [l.strip() for l in (OUT / "valid_stocks.txt").read_text().split() if l.strip()]
        probe = [c for c in watch if c.isdigit()][:0]
        codes = ["2330", "2454", "2317", "2303", "2324", "2412", "2357", "3711"][:n_probe]
        for code in codes:
            r = sess.get(f"{API}?ex_ch=tse_{code}.tw&_={int(time.time()*1000)}", timeout=8)
            t = r.text; m = json.loads(t[t.find("{"):]).get("msgArray", [])[0]
            prev = float(m["y"])
            last = float(m.get("z") or m.get("o") or 0)
            ld = G.calc_price_limits(prev)[1]
            if not last or last <= ld * 1.02:
                print(f"  skip {code}: last={last} too close to the down limit {ld}")
                continue
            sig = G.Signal(symbol=code, name="PROBE", direction=G.Direction.LONG,
                           open_price=last, prev_close=prev, raw_gap=0.0, adj_gap=0.0)
            sig.shares = 1000                       # exactly 1 張
            sig.entry_price = ld
            sig.sl_price, sig._sl_pct, _lb = G.calc_effective_sl(
                ld, prev, G.Direction.LONG, cfg.stop_loss_pct)
            sig.tp_price = round(ld * 1.05, 2)
            sig._tp_pct = 0.05
            t0 = time.time()
            tr._place_entry_order(sig)
            dt = time.time() - t0
            lat.append(dt)
            keys.append((code, sig.smart_key, sig.ack_code))
            print(f"  {code} 1 張 @ {ld} (last {last}): ack {dt*1000:.0f}ms "
                  f"code={sig.ack_code} key={sig.smart_key}")
    except Exception as e:
        print(f"  order probe failed: {str(e)[:250]}")
    finally:
        ok = [k for k in keys if k[1]]
        cancelled, fail = 0, None
        for code, key, _ in ok:
            try:
                c, msg = G.cancel_smart_order(tr.m_pSKOrder, tr.user_id, tr.account, key)
                cancelled += 1 if c == 0 else 0
                if c != 0:
                    fail = f"{code}: {c} {msg}"
            except Exception as e:
                fail = f"{code}: {str(e)[:150]}"
                break
            time.sleep(0.4)
        print(f"  cancel via CancelTSStrategyOrderV1: {cancelled}/{len(ok)}"
              + (f" (last failure: {fail})" if fail else ""))
        if cancelled < len(ok):
            print("  NOTE: anything left armed shows up in your Capital App - cancel it manually")
        tr.disconnect()
    if lat:
        med = statistics.median(lat)
        print(f"\n[RISK3] submit->ack n={len(lat)} median={med*1000:.0f}ms "
              f"p95={_pct(lat,.95)*1000:.0f}ms max={max(lat)*1000:.0f}ms "
              f"-> {1/med:.1f} orders/s single-threaded")
        print(f"  22 orders sequentially: {med*22:.1f}s")
    R["risk3"] = {"ack_latency_s": lat,
                  "orders_per_second": (1/statistics.median(lat)) if lat else None,
                  "cancel_ok": cancelled if 'cancelled' in dir() else None}


def cancel_orphans():
    """Cancel day-trade smart orders left armed by an earlier probe run."""
    import gap_fade_auto as G
    import comtypes.client
    cfg = G.Config()
    center = comtypes.client.CreateObject(G.sk.SKCenterLib, interface=G.sk.ISKCenterLib)
    order = comtypes.client.CreateObject(G.sk.SKOrderLib, interface=G.sk.ISKOrderLib)
    reply = comtypes.client.CreateObject(G.sk.SKReplyLib, interface=G.sk.ISKReplyLib)

    class RE:
        def OnReplyMessage(self, u, m):
            return -1
    keep = [comtypes.client.GetEvents(reply, RE())]
    center.SKCenterLib_SetAuthority(0)
    n = center.SKCenterLib_Login(cfg.cust_cert_id, cfg.password)
    if n != 0:
        print(f"[cancel] login failed: {center.SKCenterLib_GetReturnCodeMessage(n)}")
        return
    order.SKOrderLib_Initialize()
    order.ReadCertByID(cfg.cust_cert_id)
    keys = [a for a in sys.argv[2:]]
    if not keys:
        print("[cancel] pass 條件單號 as arguments: python v13_live_risk.py cancel 27440214 ...")
        return
    for k in keys:
        code, msg = G.cancel_smart_order(order, cfg.cust_cert_id, "913R0438724", k)
        print(f"  cancel {k} -> {code} {msg}")
        time.sleep(0.6)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "cancel":
        cancel_orphans()
        sys.exit(0)
    if mode in ("quotes", "all"):
        risk_quotes()
    if mode in ("borrow", "all"):
        risk_borrow()
    if mode in ("orders", "all"):
        risk_orders()
    _save()
