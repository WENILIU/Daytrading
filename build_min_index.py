"""Index the local 1-minute K-line files so wait_cost.py can find a
stock-day without walking the tree.

Writes _min_index.pkl: {"daily": {(code, filedate): path}, "monthly":
{(code, YYYY-MM): path}}. A file named 1234_2025-03-26.json holds data up
to 2025-03-25 - the filename is the download date - so callers must filter
bars by the bar's own date, not trust the filename. wait_cost.py does.
Takes ~5s over 130k files.
"""
import os, re, time, pickle, collections
root = r"D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線"
day_pat = re.compile(r"^(\d{4,5})_(\d{4}-\d{2}-\d{2})\.json$")
mon_pat = re.compile(r"^(\d{4,5})_(\d{4}-\d{2})\.json$")
daily, monthly = {}, {}
for dirpath, dirnames, filenames in os.walk(root):
    if not dirpath.endswith(os.sep + "1"):
        continue
    for fn in filenames:
        p = os.path.join(dirpath, fn)
        m = day_pat.match(fn)
        if m:
            daily[(m.group(1), m.group(2))] = p
            continue
        m = mon_pat.match(fn)
        if m:
            monthly[(m.group(1), m.group(2)[:7])] = p
print("daily files:", len(daily), "| month files:", len(monthly))
by_day = collections.Counter(k[1] for k in daily)
full = [d for d, c in by_day.items() if c >= 2000]
print("days with >=2000 stocks:", len(full), "range", min(full) if full else "-", max(full) if full else "-")
pickle.dump({"daily": daily, "monthly": monthly}, open("_min_index.pkl", "wb"))
