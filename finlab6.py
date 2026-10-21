from finlab import data
import inspect

print("=== data.get signature ===")
print(inspect.signature(data.get))

print("\n=== Trying noticed_stock_filter ===")
try:
    df = data.get('noticed_stock_filter', '20231201', '20231231')
    print(f"Type: {type(df)}")
    if hasattr(df, 'shape'):
        print(f"Shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print(df.head(10))
except Exception as e:
    print(f"Error: {e}")

print("\n=== day_trade_short_suspension ===")
try:
    df2 = data.get('day_trade_short_suspension', '20231201', '20231231')
    print(f"Type: {type(df2)}")
    if hasattr(df2, 'shape'):
        print(f"Shape: {df2.shape}")
        print(f"Columns: {list(df2.columns)}")
        print(df2.head(10))
except Exception as e:
    print(f"Error: {e}")
