"""Decide whether nDayTrade=0 is an exchange rule or a broker product setting.

The exchange publishes, per stock, the day-trade volume actually executed. If a code the
broker marks 0 has real day-trade volume, the exchange allows it and the block is 群益-side.
Also maps the broker buckets against the exchange permission flag to show what nDayTrade
actually is.
"""
import io, json, warnings, collections
warnings.filterwarnings("ignore")
import finlab, pandas as pd, numpy as np
finlab.login("Vww04G2yj5qcHkqX6yNCKIOw/GE2oJ9dIlFftXoeN3NqjQTv0YAqWujox5k/ilKd#vip_m")
import finlab.data as D

out = io.open("_dt_decide.txt", "w", encoding="utf-8")
def w(*a):
    out.write(" ".join(str(x) for x in a) + "\n")

vol = D.get("intraday_trading:當日沖銷交易成交股數", start="2026-09-01", end="2026-10-28")
w("exchange day-trade volume panel:", vol.shape, vol.index[0].date(), "->", vol.index[-1].date())
last20 = vol.tail(20)
tot = last20.fillna(0).sum()
days_active = (last20.fillna(0) > 0).sum()

j = json.load(open("_dt_explain.json", encoding="utf-8"))
zeros, fcd_today = set(j["zeros"]), set(j["fcd"])
unexplained = zeros - fcd_today
uni = {l.strip() for l in open("valid_stocks.txt", encoding="utf-8") if l.strip()}
ok = uni - zeros

def prof(name, codes):
    c = sorted(codes & set(tot.index))
    t = tot.reindex(c)
    a = days_active.reindex(c)
    w(f"\n  {name}  (n={len(c)})")
    w(f"    codes with ANY day-trade volume in the last 20 sessions: {int((t > 0).sum())} "
      f"({(t > 0).mean() * 100:.1f}%)")
    w(f"    sessions with day-trade volume: median {a.median():.0f} / 20, p90 {a.quantile(.9):.0f}")
    w(f"    20-session day-trade shares: median {t[t > 0].median() if (t > 0).any() else 0:,.0f} "
      f"| total {t.sum():,.0f}")
    return c

w("=== does the exchange itself show day trading for these codes? ===")
z = prof("broker nDayTrade=0, full-cash-delivery part", fcd_today)
u = prof("broker nDayTrade=0, UNEXPLAINED part", unexplained)
p = prof("broker nDayTrade=2 (allowed)", ok)

w("\n=== what nDayTrade actually maps to ===")
ex = D.get("intraday_trading:得先賣後買當沖", start="2026-10-20", end="2026-10-28").iloc[-1]
probe = json.load(open("_daytrade_probe_permissive.json", encoding="utf-8"))
g = {k: v for k, v in probe.items() if k in uni}
tab = collections.Counter()
for code, flag in g.items():
    v = ex.get(code, np.nan)
    tab[(flag, "1" if v == 1 else ("0" if v == 0 else "absent"))] += 1
w(f"{'broker nDayTrade':<18}{'exchange 得先賣後買=1':>22}{'=0 (暫停)':>12}{'absent':>10}")
for flag in (0, 1, 2):
    w(f"{flag:<18}{tab[(flag, '1')]:>22}{tab[(flag, '0')]:>12}{tab[(flag, 'absent')]:>10}")
out.close()
print("ok")
