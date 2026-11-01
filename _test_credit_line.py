# -*- coding: utf-8 -*-
"""Offline test of the notional ceiling. No COM, no market.

The account was confirmed on 2026-11-01: the broker granted a 4,500,000 line and
extends NO financing - past that, an order simply is not accepted. So the ceiling
is min(equity x max_total_exposure, account_limit), where account_limit is an
ABSOLUTE amount that does not compound with the account.

These assertions exist because two different numbers were conflated in the docs for
a while: 8.55M is the NOTIONAL at 1.90x, 4.05M is the BORROWING implied by it, and
4.5M is the LINE. Only the third one is a fact about this account, and it rules
1.90x out entirely.
"""
import sys, warnings, logging
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

lg = logging.getLogger("t"); lg.addHandler(logging.StreamHandler(sys.stdout))
lg.setLevel(logging.INFO)


def trader(limit=4_500_000, exposure=1.00):
    t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
    t.config = G.Config()
    t.config.account_limit = limit
    t.config.max_total_exposure = exposure
    t.log = lg
    t.exec_stats = {"orders": [], "entry_slippage": []}
    return t


t = trader()
assert t.config.account_limit == 4_500_000, "the line the broker granted is 450 萬"
assert t.config.max_total_exposure == 1.00, "no financing, so notional is own cash"

print("--- at 450 萬 the two ceilings are equal, and nothing is borrowed ---")
eq = 4_500_000
c = t._effective_budget(eq)
assert c == 4_500_000, c
assert c - eq == 0, "zero financing means zero borrowing"
print(f"  equity {eq:,} -> ceiling {c:,.0f}, borrowing {c - eq:,.0f}")

print("\n--- below the line it is own cash that binds, so a loss shrinks the book ---")
for eq in (3_000_000, 4_000_000, 4_499_999):
    c = t._effective_budget(eq)
    assert c == eq, (eq, c)
    assert c < t.config.account_limit, "own cash binds before the line does"
    print(f"  equity {eq/10000:>5,.0f} 萬 -> ceiling {c/10000:>5,.0f} 萬（自有資金綁）")

print("\n--- above the line the broker's line binds, and the multiple falls by itself ---")
for eq, want in [(4_500_001, 4_500_000), (6_000_000, 4_500_000),
                 (10_000_000, 4_500_000), (20_000_000, 4_500_000)]:
    c = t._effective_budget(eq)
    assert c == want, (eq, c, want)
    assert c - eq <= 0, "never borrows: the line is not a loan"
    print(f"  equity {eq/10000:>5,.0f} 萬 -> ceiling {c/10000:>5,.0f} 萬 "
          f"= {c/eq:.2f}x（額度綁住，不是策略縮的）")
print("  利潤留在帳戶不會換來更大的部位：這是額度的性質，要的是額度不是報酬")

print("\n--- the boundary is exactly the line ---")
assert t._effective_budget(4_499_999) == 4_499_999
assert t._effective_budget(4_500_001) == 4_500_000
print("  449.9999 萬以下自有資金綁、450.0001 萬以上額度綁：OK")

print("\n--- what a real financing line would buy, if one is ever granted ---")
tf = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
tf.config = G.Config()
tf.config.account_limit = 8_550_000      # a line big enough for 1.90x at 450 萬
tf.config.max_total_exposure = 1.90
tf.log = lg
tf.exec_stats = {"orders": [], "entry_slippage": []}
c = tf._effective_budget(4_500_000)
assert c == 8_550_000, c
assert c - 4_500_000 == 4_050_000, "the number that has to fit a line is the borrowing"
print(f"  450 萬 + 1.90x + 額度 855 萬 -> 名義 {c:,.0f}，需借 {c - 4_500_000:,.0f}")
print("  855 萬是名義、405 萬才是借款：之前文件把前者當成額度，所以寫错了")

print("\n--- no line configured keeps the pure multiple (the knob is separate) ---")
t0 = trader(limit=0.0, exposure=1.90)
assert t0._effective_budget(4_500_000) == 8_550_000
print("  account_limit=0 -> 只由倍數決定：OK")

print("\nOK: the ceiling is min(equity x multiple, the broker's absolute line),")
print("    and this account has no financing, so it is own cash at 450 萬.")
