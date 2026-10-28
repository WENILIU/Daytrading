"""Refresh the two panels that decide whether a signal may be day traded at all.

Both come from the exchange via finlab and both are standing facts, not model inputs:

  full-cash-delivery  - settlement status. Cannot be day traded. ~29-64 names a day.
  day-trade volume    - per-stock 當沖 volume. "zero for the last 20 sessions" is the
                        fallback used when the broker's nDayTrade read is PARTIAL.

They go stale silently: an old panel still answers, it just stops covering names that
changed since. So this prints the as-of date of each panel and exits non-zero if either
one did not arrive - the 08:55 chain treats a non-zero exit as a real blocker.

Run: python refresh_executability_panels.py
"""
import sys, os, pickle, warnings, datetime
warnings.filterwarnings("ignore")
import pandas as pd

FINLAB_TOKEN = "Vww04G2yj5qcHkqX6yNCKIOw/GE2oJ9dIlFftXoeN3NqjQTv0YAqWujox5k/ilKd#vip_m"
FCD_KEY = "etl:full_cash_delivery_stock_filter"
VOL_KEY = "intraday_trading:當日沖銷交易成交股數"
DEAD_SESSIONS = 20
START = "2014-01-01"
OUT_FCD = r"D:\gapfade_data\fcd_panel_full.pkl"
OUT_DEAD = r"D:\gapfade_data\daytrade_dead_list.pkl"


def main():
    end = datetime.date.today().isoformat()
    try:
        import finlab
        finlab.login(FINLAB_TOKEN)
        from finlab import data as D
    except Exception as exc:
        print(f"FAIL  finlab unreachable: {type(exc).__name__}: {exc}")
        return 1

    failed = 0

    # 1. full-cash-delivery: keep the raw flag, the live reader decides per date.
    try:
        fcd = D.get(FCD_KEY, start=START, end=end)
        bad = (fcd == False)
        bad.to_pickle(OUT_FCD)
        last = bad.iloc[-1]
        print(f"OK    full-cash-delivery  panel ends {pd.Timestamp(bad.index[-1]).date()} "
              f"| {bad.shape[0]} days | {int(last.sum())} names on the last day "
              f"| {os.path.getsize(OUT_FCD):,} bytes")
    except Exception as exc:
        print(f"FAIL  full-cash-delivery: {type(exc).__name__}: {str(exc)[:160]}")
        failed += 1

    # 2. day-trade volume: ship the precomputed dead list, not the 60MB frame. The live
    #    path only ever asks "which names were not day traded before today", and a 60MB
    #    frame read at 08:58 is time spent doing nothing. shift(1) keeps it a T-1 fact.
    try:
        vol = D.get(VOL_KEY, start=START, end=end)
        dead = (vol.fillna(0).rolling(DEAD_SESSIONS, min_periods=DEAD_SESSIONS)
                .sum().shift(1) <= 0)
        days = {}
        for d, row in dead.iterrows():
            hit = [c for c in row.index[row.values]]
            if hit:
                days[str(pd.Timestamp(d).date())] = hit
        with open(OUT_DEAD, "wb") as fh:
            pickle.dump({"sessions": DEAD_SESSIONS,
                         "asof": str(pd.Timestamp(vol.index[-1]).date()),
                         "days": days}, fh)
        print(f"OK    day-trade volume    panel ends {pd.Timestamp(vol.index[-1]).date()} "
              f"| dead-list days {len(days)} | {len(days[max(days)])} names on the newest day "
              f"| {os.path.getsize(OUT_DEAD):,} bytes")
    except Exception as exc:
        print(f"FAIL  day-trade volume: {type(exc).__name__}: {str(exc)[:160]}")
        failed += 1

    if failed:
        print(f"\n{failed} panel(s) did not refresh. The live path will still run, but it "
              f"will log STALE for the missing one - do not read that as 'no names are "
              f"blocked'.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
