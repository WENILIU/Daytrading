"""Shared reader for the local 1-minute corpus.

Two facts this module exists to keep straight, both verified on real files:

1. The volume column is in 張 (1000 shares), not shares. Checked against finlab
   daily 成交股數 on 8 names: ratios 1003x-1016x. dollar() applies the x1000.
2. Filenames are DOWNLOAD dates, and each download carries a ~21-session window
   ending the session before it. Verified: 2330_2025-09-01.json holds 2025-08-01
   .. 2025-08-29, and 2330_2025-09-08.json holds 2025-08-08 .. 2025-09-05. So the
   file that contains day T is the SMALLEST filename strictly greater than T, not
   T or T+1. Getting this wrong looks like missing data: it is why an earlier
   version of this analysis resolved only 7.5% of orders. Never trust a filename
   for the bar date - filter on the bar's own "date" field.

Bars inside a file are in DESCENDING time order. Files are parsed into compact
(date, dollar-volume, bar-open, bar-close) tuples and held in a bounded LRU: an unbounded cache of raw
JSON dicts exhausted RAM once coverage was fixed (1575 orders resolved, then
numpy._core._exceptions._ArrayMemoryError building the result frame).
"""
import pickle, json, bisect
from collections import OrderedDict

IDX = pickle.load(open("_min_index.pkl", "rb"))
DAILY, MONTHLY = IDX["daily"], IDX["monthly"]

# code -> sorted download dates, so "smallest filename > T" is a bisect
BY_CODE = {}
for _c, _d in IDX["daily"]:
    BY_CODE.setdefault(_c, []).append(_d)
for _c in BY_CODE:
    BY_CODE[_c].sort()

CACHE = OrderedDict()
CACHE_MAX = 24

OFFSETS = ["09:00", "09:01", "09:02", "09:03", "09:05", "09:10", "09:15", "09:30", "10:00"]


def _load(p):
    """Parsed file as sorted [(bar datetime, dollar volume)], or None if unreadable."""
    if p in CACHE:
        CACHE.move_to_end(p)
        return CACHE[p]
    try:
        raw = json.load(open(p, encoding="utf-8"))["data"]
    except Exception:
        bs = None
    else:
        bs = []
        for b in raw:
            o = float(b["open"]); h = float(b["high"]); l = float(b["low"]); c = float(b["close"])
            v = float(b["volume"]) * 1000.0
            bs.append((b["date"], v * ((h + l + c) / 3.0), o, c, h, l))
        bs.sort()
    CACHE[p] = bs
    CACHE.move_to_end(p)
    while len(CACHE) > CACHE_MAX:
        CACHE.popitem(last=False)
    return bs


def bars_for(code, day):
    """(bar datetime, dollar volume) for one stock-day, or None if not covered."""
    keys = []
    ds = BY_CODE.get(code)
    if ds:
        i = bisect.bisect_right(ds, day)
        # one candidate should be enough; take two in case a window is short
        for f in ds[i:i + 2]:
            keys.append(DAILY[(code, f)])
    mk = (code, day[:7])
    if mk in MONTHLY:
        keys.append(MONTHLY[mk])
    for p in keys:
        bs = _load(p)
        if not bs:
            continue
        sel = [b for b in bs if b[0][:10] == day]
        if sel:
            return sel
    return None


def curve(code, day):
    """(cumulative share of full-day dollar volume by each OFFSET, full-day value).

    We trade ~10s after the open (RISK1 measured p50 9-10s), and minute bars
    cannot resolve that. Two brackets instead of one point estimate:

      09:00 cumulative - the auction print at 09:00:00 plus the first minute of
        continuous trading. Verified NOT a single auction print: the 09:00 bar for
        2330 on 2025-09-01 has high 1155 / low 1145, so it spans a range. This is
        the LOWER bound on liquidity available to us, i.e. the UPPER bound on our
        impact. Use this one when sizing.
      09:01 cumulative - adds a second minute. UPPER bound on liquidity, so
        participation against it is the optimistic reading.

    The true number is between them, and closer to the 09:00 one than the 09:01
    one, because our order goes out inside the first minute.
    """
    bs = bars_for(code, day)
    if not bs:
        return None
    tot = 0.0
    acc = {}
    for b in bs:
        tot += b[1]
        acc[b[0][11:16]] = tot
    if tot <= 0:
        return None
    out = {}
    for off in OFFSETS:
        ks = [k for k in acc if k <= off]
        out[off] = acc[max(ks)] / tot if ks else 0.0
    return out, tot


def open_ticks(code, day):
    """(open, close of 09:00 bar, close of 09:01 bar, high of 09:00, low of 09:00).

    Indices 2..5 of the cached tuples carry bar OHLC, which curve() does not need.
    Returns None when the 09:00 bar is missing - which is itself a finding: that
    name had no opening trade at all.

    high == low on the 09:00 bar means the only print in that minute was the
    auction: no continuous trading happened, so the bar close IS the opening price
    and any "slippage" measured against it is zero by construction, not evidence
    of a good fill. Callers must exclude those before quoting a fill-cost curve.
    """
    bs = bars_for(code, day)
    if not bs:
        return None
    got = {}
    bs0 = None
    for b in bs:
        hm = b[0][11:16]
        if hm == "09:00":
            bs0 = (b[2], b[3], b[4], b[5])
        elif hm == "09:01":
            got[hm] = (b[2], b[3])
    if bs0 is None:
        return None
    o0, c0, h0, l0 = bs0
    return o0, c0, (got["09:01"][1] if "09:01" in got else None), h0, l0
