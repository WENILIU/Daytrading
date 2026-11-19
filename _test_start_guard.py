"""The paper start guard must refuse 13:37 (the run that produced the false pass)
and still let 08:58 and 13:20 through. The parent run() is replaced by a sentinel
so "passed the guard" is observed directly instead of inferred from a crash."""
import sys, warnings, logging, datetime as dt
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

real = G.datetime
PROCEEDED = "PROCEEDED-PAST-GUARD"
G.GapFadeAutoTrader.run = lambda self: PROCEEDED

t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
t.config = G.Config()
lg = logging.getLogger("g"); lg.addHandler(logging.NullHandler())
t.log = lg


class FakeDT(dt.datetime):
    _fake = None

    @classmethod
    def now(cls, tz=None):
        return cls._fake


def at(hh, mm):
    FakeDT._fake = dt.datetime(2026, 10, 29, hh, mm, 0)
    G.datetime = FakeDT
    try:
        return t.run()
    finally:
        G.datetime = real


cases = [(13, 37, False), (13, 26, False), (8, 44, False),
         (8, 45, True), (8, 58, True), (9, 0, True), (13, 20, True), (13, 25, True)]
ok = True
for hh, mm, should_pass in cases:
    got = at(hh, mm)
    passed = got == PROCEEDED
    mark = "OK" if passed == should_pass else "WRONG"
    if mark == "WRONG":
        ok = False
    print(f"  {hh:02d}:{mm:02d} expect={'pass' if should_pass else 'refuse':<6} "
          f"got={'pass' if passed else 'refuse':<6} {mark}")
print("ALL OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
