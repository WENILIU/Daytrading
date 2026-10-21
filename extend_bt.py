import pickle, pandas as pd, numpy as np, json, os, time
from datetime import datetime, timedelta
from fugle_marketdata import RestClient
from finlab import data as fdata
import warnings
warnings.filterwarnings('ignore')

print("=" * 60)
print("EXTENDING BACKTEST: 2026-07 to 2026-10")
print("=" * 60)

# Step 1: Get daily data from finlab for gap detection
print("\n[1/4] Getting daily data from finlab...")
try:
    daily = fdata.get('twse_daily', start='20260601', end='20261019')
    print(f"  Daily data: {daily.shape}")
    print(f"  Columns: {list(daily.columns)[:10]}")
    print(f"  Date range: {daily.index.get_level_values(0).min()} to {daily.index.get_level_values(0).max()}")
except Exception as e:
    print(f"  finlab daily error: {e}")
    # Try alternative
    try:
        daily = fdata.get('twse_per_minute', start='20260601', end='20261019')
        print(f"  Alternative: {daily.shape}")
    except Exception as e2:
        print(f"  Also failed: {e2}")
        daily = None

if daily is None:
    print("\n  Trying data.get with different format...")
    try:
        daily = fdata.get('twse_daily')
        print(f"  Got: {daily.shape}")
        # Filter to our date range
        mask = daily.index.get_level_values(0) >= '2026-06-01'
        daily = daily[mask]
        print(f"  Filtered: {daily.shape}")
    except Exception as e:
        print(f"  Failed: {e}")
        daily = None

if daily is not None:
    print(f"\n  Sample data:")
    print(daily.head(3))
else:
    print("\n  Cannot get daily data. Checking available datasets...")
    result = fdata.search('daily')
    print(result)
