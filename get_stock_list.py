import pandas as pd
import os

# Method 1: From stock_1min_index (2873 stocks)
idx = pd.read_pickle(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\stock_1min_index.pkl")
print(f"stock_1min_index: {len(idx)} stocks")
codes_from_index = sorted(str(k) for k in idx.keys() if str(k).isdigit() and len(str(k)) == 4)
print(f"  4-digit codes: {len(codes_from_index)}")

# Method 2: From local K-line data folders
data_path = r"D:\AI專案\STOCK\文義\股票資料\股票歷史資料\股票價格Ｋ線"
codes_from_files = set()
if os.path.exists(data_path):
    for company in os.listdir(data_path):
        company_path = os.path.join(data_path, company)
        if os.path.isdir(company_path):
            for period in os.listdir(company_path):
                period_path = os.path.join(company_path, period)
                if os.path.isdir(period_path):
                    for f in os.listdir(period_path):
                        if f.endswith('.json'):
                            code = f.split('_')[0]
                            if code.isdigit() and len(code) == 4:
                                codes_from_files.add(code)
print(f"\nLocal K-line files: {len(codes_from_files)} stocks")

# Combine
all_codes = sorted(set(codes_from_index) | codes_from_files)
print(f"\nCombined: {len(all_codes)} unique stock codes")

# Save
out = r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\all_stocks.txt"
with open(out, "w") as f:
    f.write('\n'.join(all_codes))
print(f"Saved: {out}")
print(f"Sample: {all_codes[:20]}")
