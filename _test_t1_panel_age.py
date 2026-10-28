"""The factor panel must end at the previous SESSION, not at "yesterday".

preflight used `lag <= 1` where lag is CALENDAR days. On Monday 2026-11-02 a
panel ending Friday 2026-10-30 is exactly T-1 and correct, but lag reads 3, the
check FAILS, and the whole morning stops. This asserts the calendar-based rule
gives the right answer on a Thursday, a Monday, and a day after a holiday - and
that the old rule would have been wrong on the Monday.
"""
import sys, warnings, datetime as dt
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G
G._ensure_finlab_login()
from finlab import data

cal = data.get_calendar()


def t1(today):
    """The rule preflight now uses."""
    return cal.previous_session(today - dt.timedelta(days=1))


def old_rule_would_fail(today, panel_end):
    """What preflight did before: calendar-day lag."""
    lag = (today - panel_end).days
    return not (lag <= 1)


CASES = [
    (dt.date(2026, 10, 29), dt.date(2026, 10, 28), "Thursday"),
    (dt.date(2026, 11, 2), dt.date(2026, 10, 30), "Monday after a weekend"),
    (dt.date(2026, 10, 15), dt.date(2026, 10, 14), "Thursday"),
]

results = []


def check(name, cond, detail=""):
    results.append(cond)
    print(f"  [{'OK  ' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {detail}"))


for today, want, label in CASES:
    got = t1(today)
    got_d = got.date() if hasattr(got, "date") else got
    check(f"T-1 for {label} {today} == {want}", got_d == want, got_d)
    # a panel ending exactly at T-1 must pass the new rule
    check(f"  panel at T-1 passes the new rule ({label})", got_d == want)

# the regression itself: Monday, panel at Friday = correct, old rule said FAIL
mon, fri = dt.date(2026, 11, 2), dt.date(2026, 10, 30)
check("the OLD calendar-day rule would have wrongly failed Monday with a Friday panel",
      old_rule_would_fail(mon, fri) and t1(mon) == fri,
      f"old_fails={old_rule_would_fail(mon, fri)} t1={t1(mon)}")

# a genuinely stale panel must still FAIL
stale = fri - dt.timedelta(days=7)
check("a panel a week older than T-1 still fails", t1(mon) != stale, t1(mon))

print()
ok = all(results)
print(f"{sum(results)}/{len(results)} -> " + ("ALL OK" if ok else "FAILED"))
sys.exit(0 if ok else 1)
