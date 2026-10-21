from finlab import data
import inspect

# Check is_tradable
print("=== is_tradable ===")
print(inspect.signature(data.is_tradable))
print(inspect.getdoc(data.is_tradable))

# Check get_role
print("\n=== get_role ===")
print(inspect.signature(data.get_role))
print(inspect.getdoc(data.get_role))

# Check suggested_tradable_time
print("\n=== suggested_tradable_time ===")
print(inspect.signature(data.suggested_tradable_time))
print(inspect.getdoc(data.suggested_tradable_time))

# Try to use is_tradable
print("\n\n=== Testing is_tradable ===")
try:
    result = data.is_tradable('20261017', '20261017')
    print(f"Result type: {type(result)}")
    if hasattr(result, 'shape'):
        print(f"Shape: {result.shape}")
        print(result.head())
    else:
        print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")

# Try get_role
print("\n=== Testing get_role ===")
try:
    result = data.get_role('20261017')
    print(f"Result type: {type(result)}")
    if hasattr(result, 'shape'):
        print(f"Shape: {result.shape}")
        print(f"Columns: {list(result.columns) if hasattr(result, 'columns') else 'N/A'}")
        print(result.head())
    else:
        print(f"Result: {str(result)[:500]}")
except Exception as e:
    print(f"Error: {e}")
