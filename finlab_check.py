from finlab.data import Data
import pandas as pd

# finlab Data might have trading restriction info
data = Data()

# Check what columns are available
print("=== finlab Data columns ===")
# Try to get a day's data and see what fields exist
try:
    df = data.get('20261016', '20261017')
    print(f"Shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    # Check for any restriction-related columns
    for col in df.columns:
        if any(k in col.lower() for k in ['restrict', 'deal', 'method', 'suspend', 'chuzhi', 'notice']):
            print(f"  FOUND: {col}")
except Exception as e:
    print(f"Error: {e}")

# Check finlab's other modules
print("\n=== Checking finlab modules ===")
import finlab
print(dir(finlab))

# Check if there's a trading calendar or restriction module
try:
    from finlab.data.provider import TWSEDataProvider
    print("\nTWSEDataProvider available")
except:
    pass

try:
    from finlab.tools import get_trading_days
    print("get_trading_days available")
except:
    pass
