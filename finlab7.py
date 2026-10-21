from finlab import data

print("=== noticed_stock_filter ===")
try:
    df = data.get('noticed_stock_filter', start='20231201', end='20231231')
    print(f"Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(df.head(10))
    print(f"\nData types:")
    print(df.dtypes)
except Exception as e:
    print(f"Error: {e}")

print("\n=== day_trade_short_suspension ===")
try:
    df2 = data.get('day_trade_short_suspension', start='20231201', end='20231231')
    print(f"Shape: {df2.shape}")
    print(f"Columns: {list(df2.columns)}")
    print(df2.head(10))
except Exception as e:
    print(f"Error: {e}")
