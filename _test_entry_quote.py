# -*- coding: utf-8 -*-
"""Offline test of the path-B entry price. No COM, no market, no orders.

The live path used to price the ticket at the open AFTER the 09:00 scan, which is
the arm measured to lose money (-0.43 pct per fill, -106 pct of the book PnL).
These assertions are what keeps the replacement from quietly becoming the same
thing again: the entry must come from the book, a missing quote must skip the
order rather than fall back to the open, and the cost against the open must be
recorded instead of assumed.
"""
import sys, time, warnings, logging
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

lg = logging.getLogger("t"); lg.addHandler(logging.StreamHandler(sys.stdout))
lg.setLevel(logging.INFO)


def trader(entry_delay=60.0):
    t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
    t.config = G.Config()
    t.config.entry_delay_sec = entry_delay
    t.log = lg
    t.exec_stats = {"orders": [], "entry_slippage": []}
    t.active_positions = {}
    return t


def sig(direction, open_price, prev_close=100.0):
    return G.Signal(symbol="1111", name="1111", direction=direction,
                    open_price=open_price, prev_close=prev_close,
                    raw_gap=0.0, adj_gap=0.0)


t = trader()

print("--- LONG buys at the best ask, SHORT sells at the best bid ---")
book = {"1111": {"last": 103.0, "bid": 102.5, "ask": 103.5}}
px, why, adv = t._entry_from_quote(sig(G.Direction.LONG, 100.0), book)
assert px == 103.5, f"LONG must cross to the ask, got {px} ({why})"
assert why == "" and abs(adv - 3.5) < 1e-9, (px, why, adv)
px2, why2, adv2 = t._entry_from_quote(sig(G.Direction.SHORT, 100.0), book)
assert px2 == 102.5, f"SHORT must cross to the bid, got {px2} ({why2})"
assert abs(adv2 + 2.5) < 1e-9, (px2, adv2)
print(f"  LONG entry {px} (adverse {adv:+.2f}%), SHORT entry {px2} "
      f"(favourable {adv2:+.2f}%)")

print("\n--- the cost is signed against us, not against the price going up ---")
# Buying above the open costs a LONG 3.5 pct. Selling above the open is a GAIN for a
# SHORT, so the same direction of price movement has to come out with the other sign.
assert adv > 0 and adv2 < 0, (adv, adv2)
print(f"  same book: LONG {adv:+.2f}% (paid) vs SHORT {adv2:+.2f}% (received). OK")

print("\n--- no quote means SKIP, never a silent fallback to the open ---")
for label, empty in [("no symbol in the book", {}),
                     ("empty book", {"1111": {"last": 0, "bid": 0, "ask": 0}})]:
    p, w, a = t._entry_from_quote(sig(G.Direction.LONG, 100.0), empty)
    assert p == 0.0 and w, (label, p, w)
    print(f"  {label}: price 0, reason '{w}' -> the caller skips it")

print("\n--- a price outside the day's limits is not an entry ---")
p, w, a = t._entry_from_quote(sig(G.Direction.LONG, 100.0, prev_close=100.0),
                              {"1111": {"last": 114.0, "bid": 113.5, "ask": 115.0}})
assert p == 0.0 and "outside limits" in w, (p, w)
print(f"  ask 115 against prev_close 100 (limit up 110): rejected - {w}")

print("\n--- best level is taken by value, so feed ordering cannot flip it ---")
shuffled = {"1111": {"last": 103.0,
                     "bid": 0, "ask": 0,
                     "bids": [{"price": 101.0}, {"price": 102.5}, {"price": 100.5}],
                     "asks": [{"price": 105.0}, {"price": 103.5}, {"price": 104.0}]}}
p, w, a = t._entry_from_quote(sig(G.Direction.LONG, 100.0), shuffled)
assert p == 103.5, f"best ask is the cheapest ask, got {p}"
p2, w2, a2 = t._entry_from_quote(sig(G.Direction.SHORT, 100.0), shuffled)
assert p2 == 102.5, f"best bid is the highest bid, got {p2}"
print(f"  LONG {p} / SHORT {p2} from deliberately unsorted levels: OK")

print("\n--- no book at all: cross the last price by a tick, and say so ---")
only_last = {"1111": {"last": 103.0, "bid": 0, "ask": 0}}
p, w, a = t._entry_from_quote(sig(G.Direction.LONG, 100.0), only_last)
assert p > 103.0 and abs(p - 103.0 - G.get_tick_size(103.0)) < 1e-9, p
p2, w2, a2 = t._entry_from_quote(sig(G.Direction.SHORT, 100.0), only_last)
assert p2 < 103.0, p2
print(f"  LONG {p} / SHORT {p2} around last 103.0, source=last_crossed: OK")

print("\n--- every entry records its cost against the open ---")
rows = t.exec_stats["entry_cost_vs_open"]
assert len(rows) == 6, rows
assert all(r["open"] == 100.0 and "adverse_pct" in r and r["source"] for r in rows)
print(f"  {len(rows)} rows recorded, each with open/last/bid/ask/entry/source/"
      f"adverse_pct")
print("  this is what gets compared against the measured ENTRY_COST table instead "
      "of assumed")

print("\n--- a session with no 09:00:00 anchor does not sleep a delay it cannot honour ---")
t2 = trader(entry_delay=60.0)
t0 = time.time()
assert t2._hold_until_entry_time() is False
took = time.time() - t0
assert took < 1.0, f"waited {took:.1f}s with no anchor"
assert t2.exec_stats["entry_delay_applied"] is False
print(f"  returned False in {took:.2f}s and recorded applied=False: OK")

print("\n--- the delay is measured against 09:00:00, and a late start says so ---")
t3 = trader(entry_delay=60.0)
t3.exec_stats["t_open"] = time.time() - 120.0
assert t3._hold_until_entry_time() is False
assert t3.exec_stats["entry_delay_applied"] is False
print("  120s past the open with a 60s delay: NOT applied, warned. OK")

print("\nOK: the entry price comes from the book, a missing quote skips the order,")
print("    and the cost against the open is recorded rather than assumed.")
