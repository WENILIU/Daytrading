from finlab import data
import inspect

# Get details about noticed_stock_filter
print("=== noticed_stock_filter ===")
try:
    result = data.search('noticed_stock_filter', details=True)
    print(result.to_string())
except Exception as e:
    print(f"Error: {e}")

# Try to get the data
print("\n=== Getting noticed_stock_filter data ===")
try:
    df = data.get('noticed_stock_filter', start_date='20261010', end_date='20261017')
    print(f"Type: {type(df)}")
    if hasattr(df, 'shape'):
        print(f"Shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print(df.head(10))
    else:
        print(str(df)[:1000])
except Exception as e:
    print(f"Error: {e}")

# Try day_trade_short_suspension
print("\n=== day_trade_short_suspension ===")
try:
    result = data.search('day_trade_short_suspension', details=True)
    print(result.to_string())
except Exception as e:
    print(f"Error: {e}")

try:
    df2 = data.get('day_trade_short_suspension', start_date='20261010', end_date='20261017')
    print(f"Type: {type(df2)}")
    if hasattr(df2, 'shape'):
        print(f"Shape: {df2.shape}")
        print(f"Columns: {list(df2.columns)}")
        print(df2.head(10))
    else:
        print(str(df2)[:1000])
except Exception as e:
    print(f"Error: {e}")
