import sys, os
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\SKDLLPythonTester")
os.add_dll_directory(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
from SKDLLPython import SK

SK.OnReplyMessage(lambda a, b: None)
result = SK.Login("D121280815", "Zaq582811@")
print(f"Login: {result.Code}")

# Check error 1095
msg = SK.GetMessage(1095)
print(f"Error 1095: {msg}")

# Also check what happens with RequestStockList
try:
    sl = SK.RequestStockList(0)
    print(f"StockList type: {type(sl)}")
    print(f"StockList dir: {[a for a in dir(sl) if not a.startswith('_')]}")
    # Try to access data
    if hasattr(sl, 'All'):
        lines = sl.All.split('\n')
        print(f"StockList lines: {len(lines)}")
        if lines:
            print(f"First: {lines[0]}")
except Exception as e:
    print(f"RequestStockList error: {e}")

# Try GetStockByStockNo and check its actual attributes
try:
    data = SK.SKQuoteLib_GetStockByStockNo(0, "2330")
    print(f"\nGetStockByStockNo type: {type(data)}")
    attrs = [a for a in dir(data) if not a.startswith('_')]
    print(f"Attributes: {attrs[:30]}")
    # Try accessing fields
    for field in ['nOpen', 'nRef', 'nClose', 'strStockNo', 'bstrStockNo']:
        if hasattr(data, field):
            print(f"  {field} = {getattr(data, field)}")
except Exception as e:
    print(f"GetStockByStockNo error: {e}")
