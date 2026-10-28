"""Cache the exchange's full-cash-delivery status as a daily panel (2014 -> today).

full_cash_delivery_stock_filter is True = passes the filter (normal settlement), False = the
stock IS full-cash-delivery that day. Full-cash-delivery names cannot be day traded, and
every one of today's 29 lands in the broker's nDayTrade=0 bucket, so the mapping is real.
This is per-date exchange data, so unlike the broker snapshot it can be applied to history.
"""
import io, warnings, pickle
warnings.filterwarnings("ignore")
import finlab, pandas as pd
finlab.login("Vww04G2yj5qcHkqX6yNCKIOw/GE2oJ9dIlFftXoeN3NqjQTv0YAqWujox5k/ilKd#vip_m")
import finlab.data as D

df = D.get("etl:full_cash_delivery_stock_filter", start="2014-01-01", end="2026-10-28")
print("shape", df.shape, "range", df.index[0].date(), "->", df.index[-1].date())
bad = (df == False)
print("rows with any full-cash-delivery name:", int(bad.any(axis=1).sum()), "of", len(bad))
per_day = bad.sum(axis=1)
print("names flagged per day: min %d median %.0f max %d" % (per_day.min(), per_day.median(), per_day.max()))
print("first day any appears:", per_day[per_day > 0].index[0] if (per_day > 0).any() else None)
bad.to_pickle("_fcd_panel.pkl")
print("cached _fcd_panel.pkl", bad.shape)
