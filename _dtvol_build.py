"""Cache the exchange's per-stock day-trade volume, 2014 -> today.

intraday_trading:當日沖銷交易成交股數 is published by the exchange per stock per day, so
"this name has not been day traded in N sessions" is a T-1 fact knowable before the open -
unlike the broker's nDayTrade, which needs the quote cache to be warm at 09:00.

NaN is kept as-is here; the consumer decides. Absence from the exchange's own day-trade
table and a literal zero both mean "no day trading recorded", but they are different facts
and the caller should be able to tell them apart.
"""
import warnings
warnings.filterwarnings("ignore")
import finlab, pandas as pd
finlab.login("Vww04G2yj5qcHkqX6yNCKIOw/GE2oJ9dIlFftXoeN3NqjQTv0YAqWujox5k/ilKd#vip_m")
import finlab.data as D

v = D.get("intraday_trading:當日沖銷交易成交股數", start="2014-01-01", end="2026-10-28")
v.to_pickle("_dtvol_panel.pkl")
print("cached", v.shape, v.index[0].date(), "->", v.index[-1].date())
last = v.iloc[-1]
print("last row: non-null", int(last.notna().sum()), "zero", int((last == 0).sum()),
      "positive", int((last > 0).sum()), "of", v.shape[1])
