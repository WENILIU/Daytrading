# -*- coding: utf-8 -*-
r"""How many signal rows have a price outside the panel's own price limits?

Every stop in this strategy is placed relative to 漲停/跌停, so a row whose limit
is wrong is a row where the live order would have been armed at a price the
exchange does not use. calc_price_limits' own docstring says the corrected rule
leaves 922 bad stock-days out of 8.15M (除權息 reference adjustments and first-day
listings). This checks the same thing on the population that actually matters -
the 100k signal rows the book trades - and prices what they are worth.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import v13_target as T

D = T.D
eps = 1e-9
bad_close = (D["day_close"] > D["lu"] + eps) | (D["day_close"] < D["ld"] - eps)
bad_high = D["day_high"] > D["lu"] + eps
bad_low = D["day_low"] < D["ld"] - eps
bad = bad_close | bad_high | bad_low
D2 = D.copy(); D2["year"] = [int(pd.Timestamp(x).year) for x in D["date"]]
print("訊號列 %d 筆，其中價格超出面板漲跌停的：%d 筆（%.3f%%）" % (len(D), bad.sum(), bad.mean() * 100))
print("   收盤越界 %d｜最高越界 %d｜最低越界 %d" % (bad_close.sum(), bad_high.sum(), bad_low.sum()))
print("\n逐年：")
for y, g in D2.groupby("year"):
    b = bad[D2.index.isin(g.index)]
    print("   %d  %5d 筆訊號  越界 %3d（%.3f%%）" % (y, len(g), b.sum(), b.mean() * 100))
print("\n越界那批的每筆毛損益 vs 整體：")
g_all = np.where(D["direction"].values == "SHORT",
                 (D["entry"].values - D["day_close"].values) / D["entry"].values,
                 (D["day_close"].values - D["entry"].values) / D["entry"].values)
print("   全部 %+.4f%%   越界 %+.4f%%   差 %.4f pp" % (
    g_all.mean() * 100, g_all[bad.values].mean() * 100,
    (g_all[bad.values].mean() - g_all.mean()) * 100))
print("   越界那批占全部訊號的毛損益比重：%.4f%%" % (
    g_all[bad.values].sum() / g_all.sum() * 100))
