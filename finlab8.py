from finlab import data

print("=== etl:disposal_stock_filter (處置股) ===")
try:
    df = data.get('etl:disposal_stock_filter', start='20231201', end='20231231')
    print(f"Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(df.head(10))
    print(f"\nDtypes:\n{df.dtypes}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== etl:noticed_stock_filter (觀察股) ===")
try:
    df2 = data.get('etl:noticed_stock_filter', start='20231201', end='20231231')
    print(f"Shape: {df2.shape}")
    print(f"Columns: {list(df2.columns)}")
    print(df2.head(10))
except Exception as e:
    print(f"Error: {e}")

print("\n=== day_trade_short_suspension (no date filter) ===")
try:
    df3 = data.get('day_trade_short_suspension')
    print(f"Shape: {df3.shape}")
    print(f"Columns: {list(df3.columns)}")
    print(df3.head(10))
except Exception as e:
    print(f"Error: {e}")
