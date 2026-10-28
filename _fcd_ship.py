"""Ship the full-cash-delivery panel to the live data directory.

Same content as _fcd_panel.pkl (True = the stock IS full-cash-delivery that day), written
where gap_fade_auto.py reads its other panels. Kept separate from disposal_panel_full.pkl
because the two are different rules: disposal is temporary (5-7 sessions), full-cash-
delivery is a standing settlement status.
"""
import pandas as pd, shutil, os
src = "_fcd_panel.pkl"
dst = r"D:\gapfade_data\fcd_panel_full.pkl"
shutil.copyfile(src, dst)
p = pd.read_pickle(dst)
print("shipped", dst, p.shape, p.index[0].date(), "->", p.index[-1].date(),
      "| bytes", os.path.getsize(dst))
