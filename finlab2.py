import finlab
print("finlab version:", finlab.__version__)
print("Modules:", [x for x in dir(finlab) if not x.startswith('_')])

from finlab import data
print("\ndata module:", [x for x in dir(data) if not x.startswith('_')])

# Try to get data
try:
    df = data.get('20261016', '20261017')
    print(f"\nData shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
except Exception as e:
    print(f"data.get error: {e}")

# Try other approaches
try:
    from finlab.data.data import Data
    d = Data()
    df = d.get('20261016', '20261017')
    print(f"\nData() shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
except Exception as e:
    print(f"Data() error: {e}")

# Check for stock status/restriction
try:
    from finlab.data.provider import TWSEDataProvider
    provider = TWSEDataProvider()
    print("\nTWSEDataProvider methods:", [x for x in dir(provider) if not x.startswith('_')])
except Exception as e:
    print(f"Provider error: {e}")
