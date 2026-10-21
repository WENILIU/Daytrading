from finlab import data
import inspect

# Check what data fields are available
print("=== data.entries (available fields) ===")
try:
    entries = data.entries()
    print(f"Type: {type(entries)}")
    if isinstance(entries, dict):
        for k, v in list(entries.items())[:30]:
            print(f"  {k}: {v}")
    elif isinstance(entries, list):
        for e in entries[:30]:
            print(f"  {e}")
    else:
        print(str(entries)[:1000])
except Exception as e:
    print(f"Error: {e}")

# Check catalog
print("\n=== data.catalog ===")
try:
    cat = data.catalog()
    print(f"Type: {type(cat)}")
    print(str(cat)[:2000])
except Exception as e:
    print(f"Error: {e}")

# Check search
print("\n=== data.search ===")
try:
    result = data.search('restrict')
    print(f"restrict: {result}")
except Exception as e:
    print(f"Error: {e}")
try:
    result = data.search('suspend')
    print(f"suspend: {result}")
except Exception as e:
    print(f"Error: {e}")
try:
    result = data.search('notice')
    print(f"notice: {result}")
except Exception as e:
    print(f"Error: {e}")
try:
    result = data.search('trade')
    print(f"trade: {result}")
except Exception as e:
    print(f"Error: {e}")
