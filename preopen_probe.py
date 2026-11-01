"""盘前三分量探测（08:44-09:00:30，零风险：只送不可能成交的价格）。

要回答三个问题，它们一起决定"能不能用开盘竞价进场"。2026-11-01 之前这个脚本只
问第一个的一半（Fugle 的 referencePrice 会不会动），那是错的：Fugle 的
intraday.quote 只有 24 个字段、其中只有 referencePrice，**没有委买委卖量**，
所以量能这件事只能走群益自己的 quote。

1. 指示价与竞价量准不准。读 SKCOM 的 nRef（参考价格）、nTBc/nTAc（委买/委卖
   总量），08:44 到 09:00 每 2 秒一轮，09:00 之后再读一次实际开盘价 nOpen。
   从这份轨迹算两条结论：
     - nRef vs nOpen 的误差分布 -> 限价缓冲要多宽，不是我拍的
     - nRef 与 min(nTBc,nTAc) 最后一次大幅变动在几点 -> 事实上的承诺点。
       "08:45 之后不可撤单"这条规则 2026-11-01 查证失败（TWSE 三个页面都回
       101 字元的 JS 空壳），而盘前随时可改单意味着任何规则都不如直接量出来的
       变动点。
2. 券商能不能在 09:00 前收一般委托。08:55 用 SendStockOrder 送 1 张在不可能
   成交的价格，记 ack code 与完整讯息。这是整条盘前进场路的前提。
3. 智慧单能不能在 09:00 前送。08:56 用 SendStockStrategyDayTrade 送同样一张。
   如果可以，盘前进场仍能保持"进场+停损+停利一张单"，不用付"开盘后才挂停损"
   那段无保护窗口。判准是 ack 文字里的「交易日:YYYYMMDD」：2026-10-26 盘后送的
   那批回的是「预约单已送出」且交易日写隔天，所以这个栏位会直接告诉我们这张单
   被排到哪一天。

用法：
  python preopen_probe.py            # 自己等到 08:44 开始
  python preopen_probe.py --now      # 立刻跑一轮（盘后也能跑，用来看字段与送单结果）
"""
import sys, os, csv, time, re, math, datetime, warnings
warnings.filterwarnings("ignore")
import pandas as pd
import gap_fade_auto as G
from gap_fade_auto import pump_messages, _parse_smart_key, cancel_smart_order
import comtypes.gen.SKCOMLib as sk
from fugle_marketdata import RestClient

# 大型股、中型股、策略常挑的低价股，加上 0050（大盘基准，必须是同一来源的指示价）
SYMS = ["0050", "2330", "2454", "2395", "3189", "2426", "5284", "6547", "9938", "2409"]
ORDER_SYM = "2409"          # 送单测试用：低价、流动性够、不太可能锁死
INTERVAL = 2.0
START = (8, 44, 0)
STOP = (9, 0, 30)
NOW = "--now" in sys.argv
FUGLE_KEY = "MmRkMTA5OWUtNjM3OS00YmQ5LTk4ZWMtNTYzOGQyMjY5MWY2IGIyYTNhYWY5LTcxY2ItNGUyMy04NTVhLTU0ZDhkNzE2ZjM1Mw=="


def row_of(p, market_no):
    """Pull the fields this probe cares about out of a quote struct.

    Shared by both readers below, so a field added here cannot silently be missing
    from one of them. sDecimal is the struct's own claim about the price scale; it
    is recorded, never trusted (see detect_scale).
    """
    def i(v):
        try:
            return int(v)
        except Exception:
            return 0
    return {"market": market_no, "ref": i(p.nRef), "open": i(p.nOpen),
            "close": i(p.nClose), "high": i(p.nHigh), "low": i(p.nLow),
            "tbc": i(p.nTBc), "tac": i(p.nTAc), "yqty": i(p.nYQty),
            "tqty": i(p.nTQty), "deal_time": str(p.nDealTime or ""),
            "sdecimal": i(p.sDecimal)}


def walk(trader, want):
    """One pass of the SKCOM quote cache, picking out the symbols we care about.

    Returns (found, scanned). The counter is not decoration: the quote cache is
    empty outside a session (every after-hours scan on this machine has returned 0
    valid quotes), so without it "found 0" cannot be told apart from a broken walk.
    """
    out = {}
    scanned = 0
    for market_no in (0, 1, 2):
        idx = 0
        while idx < 6000:
            p = sk.SKSTOCKLONG()
            try:
                p, code = trader.quote_lib.SKQuoteLib_GetStockByIndexLONG(market_no, idx, p)
                if code != 0:
                    break
            except Exception:
                break
            sym = str(p.bstrStockNo or "")
            if sym in want and sym not in out:
                out[sym] = row_of(p, market_no)
            idx += 1
            scanned += 1
            if want <= set(out):
                return out, scanned
    return out, scanned


def code_msg(trader, code):
    """The broker's own words for a return code. A bare 3030 tells the next reader
    nothing; this is the same call the connection path already uses."""
    try:
        return str(trader.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(int(code)))
    except Exception:
        return ""


def subscribe(trader, syms):
    """Ask the quote server for these codes directly instead of waiting for its list.

    The monitor's own stock list is empty outside a session - measured 2026-11-01, a
    walk straight after connect scans 0 rows - so at 08:44 a walk can find nothing
    even though the server would answer a direct request. test_scan_speed.py v6 is
    the proof: RequestStocks on 15 codes returned real prices in the same session
    where the index walk returned 0. RequestStocks is paged (first argument is the
    page number) and the examples start it at either 0 or 1 without saying which is
    correct, so both are tried and every attempt is reported. These symbols fit on one
    page either way.
    """
    tries = []
    for page in (0, 1):
        try:
            got, code = trader.quote_lib.SKQuoteLib_RequestStocks(page, ",".join(syms))
            tries.append((page, int(code)))
            if int(code) == 0:
                return {"api": "RequestStocks(page=%d)" % page, "code": 0,
                        "tries": tries}
        except Exception as e:
            tries.append((page, "EXC %s" % type(e).__name__))
    return {"api": "RequestStocks", "code": tries[-1][1] if tries else None,
            "tries": tries}


def read_by_no(trader, want):
    """Per-symbol read, for the case where there is no list to walk.

    GetStockByNoLONG takes the code rather than an index, so it returns a subscribed
    symbol even when GetStockByIndexLONG enumerates nothing. Same struct, same
    fields - the two readers are interchangeable, which is why one feeds the other.
    """
    out = {}
    for sym in sorted(want):
        try:
            p = sk.SKSTOCKLONG()
            p, code = trader.quote_lib.SKQuoteLib_GetStockByNoLONG(sym, p)
            if code != 0:
                continue
        except Exception:
            continue
        if str(p.bstrStockNo or "") != sym:
            continue
        out[sym] = row_of(p, str(p.bstrMarketNo or ""))
    return out


def detect_scale(rows, prev_close):
    """SKCOM stores prices as scaled integers. Pick the power of ten that makes
    nRef agree with the previous close held in the local price store. Guessing this
    would put
    a 1000x error into every percentage in the file, so measure it."""
    cands = []
    for sym, r in rows.items():
        pc = prev_close.get(sym)
        if not pc or r["ref"] <= 0:
            continue
        ratio = r["ref"] / float(pc)
        if ratio < 0.5:
            continue
        e = round(__import__("math").log10(ratio))
        if 0 <= e <= 4:
            cands.append(10 ** e)
    if not cands:
        return None
    cands.sort()
    return cands[len(cands) // 2]




PRICE_STORE = r"D:\gapfade_data\price_close.pkl"


def local_prev_close():
    """The authoritative previous close: the last row of our own price store.

    Returned with the store's own last date so a stale file cannot masquerade as
    yesterday. 102 MB, a few seconds, and it runs before 09:00 where that is fine.
    """
    try:
        px = pd.read_pickle(PRICE_STORE)
        d = px.index.max()
        return ({str(k): float(v) for k, v in px.loc[d].dropna().items() if float(v) > 0},
                str(pd.Timestamp(d).date()))
    except Exception as e:
        return {}, "unavailable (%s: %s)" % (type(e).__name__, e)


def send_plain(trader, sym, price):
    try:
        msg, code = trader.send_order(sym, buy_sell=0, flag=0, price=price, qty=1000)
        return {"api": "SendStockOrder", "code": int(code), "msg": str(msg)}
    except Exception as e:
        return {"api": "SendStockOrder", "code": None, "msg": "EXC %s: %s" % (type(e).__name__, e)}


def send_smart(trader, sym, price, sl, tp):
    """The same ticket live sends, built field for field from _place_entry_order."""
    o = sk.STOCKSTRATEGYORDER()
    o.bstrFullAccount = trader.account
    o.bstrStockNo = sym
    o.nQty = 1
    o.bstrOrderPrice = str(price)
    o.nOrderPriceType = 2                      # LIMIT
    o.nOrderPriceCond = 0
    o.nBuySell = 0                             # 现股买
    o.nInnerOrderIsMIT = 0
    o.nMITDir = 0
    o.bstrMITTriggerPrice = "0"
    o.bstrMITDealPrice = "0"
    o.nStopLossFlag = 1
    o.nRDOSLPercent = 0
    o.bstrSLTrigger = str(sl)
    o.bstrSLPercent = "0"
    o.bstrSLOrderPrice = "0"
    o.nRDSLMarketPriceType = 1
    o.nStopLossOrderCond = 0
    o.nTakeProfitFlag = 1
    o.nRDOTPPercent = 0
    o.bstrTPTrigger = str(tp)
    o.bstrTPPercent = "0"
    o.bstrTPOrderPrice = "0"
    o.nRDTPMarketPriceType = 1
    o.nTakeProfitOrderCond = 0
    o.nClearAllFlag = 1
    o.bstrClearCancelTime = "1320"
    o.nClearAllPriceType = 1
    o.bstrClearAllOrderPrice = "0"
    o.nClearOrderCond = 0
    o.nFinalClearFlag = 0
    try:
        msg, code = trader.m_pSKOrder.SendStockStrategyDayTrade(trader.user_id, False, o)
        return {"api": "SendStockStrategyDayTrade", "code": int(code), "msg": str(msg)}
    except Exception as e:
        return {"api": "SendStockStrategyDayTrade", "code": None, "msg": "EXC %s: %s" % (type(e).__name__, e)}


def cancel_plain(trader, sym):
    """Best effort. These prices cannot fill, so failing to cancel costs nothing -
    but report it, because an order left sitting until 13:20 is a real side effect."""
    for name in ("CancelOrderByStockNo", "CancelOrderBySeqNo"):
        try:
            fn = getattr(trader.m_pSKOrder, name)
            msg, code = fn(trader.user_id, 1, sym)
            return {"api": name, "code": int(code), "msg": str(msg)}
        except Exception as e:
            last = "EXC %s: %s" % (type(e).__name__, e)
    return {"api": "none worked", "code": None, "msg": last}


def booked_day(msg):
    m = re.search(r"交易日[：:]\s*(\d{8})", msg or "")
    return m.group(1) if m else ""


def main():
    now = datetime.datetime.now()
    if not NOW:
        target = now.replace(hour=START[0], minute=START[1], second=0, microsecond=0)
        while now < target:
            time.sleep(min(20, (target - now).total_seconds()))
            now = datetime.datetime.now()

    out = "trading_logs/preopen_%s.csv" % datetime.date.today().isoformat()
    os.makedirs("trading_logs", exist_ok=True)
    print("=" * 74)
    print("PREOPEN THREE-PART PROBE  %s%s" % (datetime.datetime.now().isoformat(), "  (--now)" if NOW else ""))
    print("=" * 74)

    print("[1] login SKCOM ...")
    cfg = G.Config()
    trader = G.GapFadeAutoTrader(cfg)
    trader.connect()

    f = open(out, "w", newline="", encoding="utf-8-sig")
    w = csv.writer(f)
    w.writerow(["wall_clock", "symbol", "market", "nRef", "nOpen", "nClose", "nTBc", "nTAc",
                "matched_est", "yqty", "tqty", "deal_time", "ref_vs_prev_pct", "scale",
                "prev_close_used", "baseline_date"])
    print("[2] writing %s" % out)

    prev_close, baseline_date = local_prev_close()
    print("[2b] previous-close baseline: %s (%d symbols)" % (baseline_date, len(prev_close)))
    missing = [x for x in SYMS if x not in prev_close]
    if missing:
        print("     not in the store: %s" % ",".join(missing))

    client = RestClient(api_key=FUGLE_KEY).stock
    fugle_date = {}

    def read_fugle():
        """Cross-check only, and a filler for symbols the store does not have.
        Measured 2026-11-01 21:13, Fugle's intraday.quote reports date=2026-10-30 with
        previousClose = the 10/29 close - one session behind. That makes it useless as
        a baseline at 08:44, but if the store and Fugle ever agree on the SESSION then
        the store is stale and every percentage in this file is off by one day, so the
        comparison is printed instead of swallowed."""
        for s in SYMS:
            try:
                q = client.intraday.quote(symbol=s)
            except Exception:
                continue
            fugle_date[s] = str(q.get("date") or "")
            for k in missing:
                pc = float(q.get("previousClose") or 0)
                if pc > 0:
                    prev_close[k] = pc

    read_fugle()
    print("     Fugle cross-check (it is expected to be one session behind; if the store"
          " is ALSO")
    print("     behind the last session, every percentage here is off by one day):")
    for s in SYMS[:4]:
        print("       %-6s store_prev=%s [store %s]   fugle session=%s"
              % (s, prev_close.get(s), baseline_date, fugle_date.get(s)))

    want = set(SYMS)
    base, scanned = walk(trader, want)
    print("    first pass: %d rows scanned, %d/%d wanted found"
          % (scanned, len(base), len(want)))
    subres = None
    if not base:
        # Nothing readable. Two different things produce that, and the counter above
        # is what tells them apart: scanned == 0 means the monitor handed back no
        # stock list at all (the known behaviour outside a session), while scanned > 0
        # with no matches means the list is there and the walk is broken.
        if scanned == 0:
            print("    the walk found no stock list. Asking for these codes directly:")
            subres = subscribe(trader, SYMS)
            for page, code in subres.get("tries", []):
                print("    RequestStocks(page=%s) -> %s %s"
                      % (page, code, code_msg(trader, code)))
            for _ in range(6):
                pump_messages(1.0)
                base = read_by_no(trader, want)
                if base:
                    break
            print("    after subscribing: %d/%d readable by code"
                  % (len(base), len(want)))
            if subres.get("code") != 0:
                print("    the request itself was refused, so this path is still"
                      " unproven here.")
                print("    08:44 on a trading day is the real test - outside a session"
                      " the server")
                print("    has no reason to accept a subscription.")
        else:
            print("    the cache has %d rows but none of the wanted symbols. THAT is a"
                  " bug in the walk." % scanned)
    # The scale is pinned from the first snapshot that has a price, not once here:
    # at 08:44 the cache can be empty, and a silent fallback to 1000 would put a
    # 1000x error into every percentage in the file without anything looking wrong.
    scale = detect_scale(base, prev_close) if base else None
    if scale:
        print("[3] price scale pinned: 1 unit = 1/%d TWD" % scale)
    else:
        print("[3] price scale NOT YET pinned - no priced row yet. It will be pinned"
              " from the first")
        print("    snapshot that carries one. Until then every price column is RAW"
              " integers.")
    for s in SYMS:
        r = base.get(s)
        if r:
            print("    %-6s ref=%s prev=%s"
                  % (s, r["ref"] / (scale or 1), prev_close.get(s)))
        else:
            print("    %-6s NOT IN QUOTE CACHE (pre-open the monitor may not have it yet)" % s)

    orders = []
    stop = (datetime.datetime.now() + datetime.timedelta(seconds=25)) if NOW else \
           datetime.datetime.now().replace(hour=STOP[0], minute=STOP[1], second=STOP[2], microsecond=0)
    did_plain = did_smart = said_empty = False
    n = 0
    while datetime.datetime.now() < stop:
        t0 = time.time()
        pump_messages(0.05)
        snap, _ = walk(trader, want)
        if not snap and subres and subres.get("code") == 0:
            snap = read_by_no(trader, want)
        stamp = datetime.datetime.now()
        if scale is None:
            scale = detect_scale(snap, prev_close)
            if scale:
                print("[3] price scale pinned at %s: 1 unit = 1/%d TWD"
                      % (stamp.strftime("%H:%M:%S"), scale))
                dec = sorted({r.get("sdecimal", 0) for r in snap.values()})
                print("    (the structs report sDecimal=%s; the official examples divide"
                      " by 100 and this")
                print("     feed has returned 1/1000, so the measured value is what"
                      " gets used)")
        sc = scale or 1000
        for sym, r in snap.items():
            pc = prev_close.get(sym) or 0
            ref = r["ref"] / sc
            pct = (100.0 * (ref - pc) / pc) if pc else ""
            w.writerow([stamp.isoformat(), sym, r["market"], r["ref"], r["open"], r["close"],
                        r["tbc"], r["tac"], min(r["tbc"], r["tac"]), r["yqty"], r["tqty"],
                        r["deal_time"], ("%.3f" % pct) if pct != "" else "",
                        scale if scale else "UNVERIFIED", pc, baseline_date])
            n += 1
        f.flush()

        hhmm = stamp.strftime("%H%M")
        if not NOW and not said_empty and hhmm >= "0852" and not snap:
            # Eight minutes before the open with nothing readable is itself the
            # answer to question 1: there is no pre-open indicative price to size a
            # limit against, so the plan has to change rather than the probe retry.
            said_empty = True
            print("[!] 08:52 and still no quotes. That is a CONCLUSION, not a failure:")
            print("    SKCOM carries no pre-open indicative price or auction depth, so")
            print("    the limit buffer cannot be sized from the feed and the auction")
            print("    entry has to be priced from the gap rule alone.")
        if not NOW and not did_plain and hhmm >= "0855":
            did_plain = True
            px = round(prev_close.get(ORDER_SYM, 100) * 0.90, 2)
            print("[4] 08:55 plain order: buy 1 zhang %s @ %s (跌停附近, 不会成交)" % (ORDER_SYM, px))
            r = send_plain(trader, ORDER_SYM, px)
            r["ts"] = stamp.isoformat(); r["price"] = px
            orders.append(r)
            print("    code=%s msg=%s" % (r["code"], r["msg"][:200]))
        if not NOW and not did_smart and hhmm >= "0856":
            did_smart = True
            px = round(prev_close.get(ORDER_SYM, 100) * 0.90, 2)
            print("[5] 08:56 smart order: same ticket live sends, 1 zhang @ %s" % px)
            r = send_smart(trader, ORDER_SYM, px, round(px * 1.04, 2), round(px * 0.93, 2))
            r["ts"] = stamp.isoformat(); r["price"] = px
            r["smart_key"] = _parse_smart_key(r["msg"]); r["booked_day"] = booked_day(r["msg"])
            orders.append(r)
            print("    code=%s key=%s booked_day=%s msg=%s"
                  % (r["code"], r["smart_key"], r["booked_day"], r["msg"][:200]))

        time.sleep(max(0.5, INTERVAL - (time.time() - t0)))

    # after the open: the actual print, for the error distribution
    final, _ = walk(trader, want)
    if not final and subres and subres.get("code") == 0:
        final = read_by_no(trader, want)
    if scale is None:
        scale = detect_scale(final, prev_close)
    if scale is None:
        print("!! price scale never pinned (no priced row all session). Every price in the"
              " CSV is a RAW integer.")
        scale = 1000
    stamp = datetime.datetime.now()
    for sym, r in final.items():
        pc = prev_close.get(sym) or 0
        op = r["open"] / scale
        w.writerow([stamp.isoformat() + " FINAL", sym, r["market"], r["ref"], r["open"], r["close"],
                    r["tbc"], r["tac"], min(r["tbc"], r["tac"]), r["yqty"], r["tqty"],
                    r["deal_time"], ("%.3f" % (100.0 * (op - pc) / pc)) if pc else "",
                    scale, pc, baseline_date])
    f.close()

    # Did the exchange roll over to today's session while we were watching? If Fugle's
    # date moves to today, the store was the right baseline for the open. If it never
    # moves, the store's date is the only thing we ever measured against, and that has
    # to be visible rather than assumed.
    before = dict(fugle_date)
    read_fugle()
    rolled = {k: (before.get(k), fugle_date.get(k)) for k in SYMS
              if before.get(k) and fugle_date.get(k) and before[k] != fugle_date[k]}
    if rolled:
        a, b = list(rolled.values())[0]
        print("!! Fugle rolled to a new session mid-run: %s -> %s. The store baseline (%s)"
              " was one" % (a, b, baseline_date))
        print("   day behind what the open is actually measured against. Recompute"
              " ref_vs_prev_pct")
        print("   against the new previous close before using any percentage in this file.")
    else:
        print("Fugle stayed on session %s all run. The baseline used throughout is the"
              " store's %s"
              % (sorted(set(v for v in fugle_date.values() if v))[:1], baseline_date))

    print()
    print("=" * 74)
    print("RESULTS")
    print("=" * 74)
    print("[A] quote rows: %d -> %s" % (n, out))
    print()
    print("[B] indicative price vs the actual open (this is what sizes the limit buffer):")
    moved = {}
    for sym in SYMS:
        pc = prev_close.get(sym) or 0
        fr = final.get(sym)
        if not fr or not pc:
            print("    %-6s no data" % sym)
            continue
        op = fr["open"] / (scale or 1000)
        if op <= 0:
            print("    %-6s nOpen still 0 at %s - the cache had no print yet" % (sym, stamp.strftime("%H:%M:%S")))
            continue
        print("    %-6s open=%s  open_vs_prev=%+.2f%%" % (sym, op, 100.0 * (op - pc) / pc))
        moved[sym] = op
    print()
    print("[C] pre-open order capability:")
    if not orders:
        print("    not tested (this run was --now, or the clock passed 08:56)")
    for o in orders:
        print("    %-28s code=%s %s" % (o["api"], o["code"], o["msg"][:180]))
        if o.get("booked_day"):
            print("        booked_day=%s  (today is %s)" % (o["booked_day"], datetime.date.today().strftime("%Y%m%d")))
        if o.get("smart_key"):
            code, msg = cancel_smart_order(trader.m_pSKOrder, trader.user_id, trader.account, o["smart_key"])
            print("        cancel smart %s -> code=%s %s" % (o["smart_key"], code, str(msg)[:120]))
        elif o["api"] == "SendStockOrder":
            r = cancel_plain(trader, ORDER_SYM)
            print("        cancel plain -> %s" % r)
    print()
    print("Read the CSV for the trajectory. The two numbers to take from it:")
    print("  1. max |nRef - nOpen| per symbol  -> the limit buffer")
    print("  2. the last timestamp where nRef or min(nTBc,nTAc) moved a lot -> the real")
    print("     commitment point, which is what the unverifiable 08:45 rule was standing in for")
    trader.disconnect()


if __name__ == "__main__":
    main()
