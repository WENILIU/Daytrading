import sys, os, time
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\SKDLLPythonTester")
os.add_dll_directory(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
from SKDLLPython import SK
import inspect

# Check Login signature
print("Login source:")
src = inspect.getsource(SK.Login)
print(src[:2000])

print("\n\nManageServerConnection:")
try:
    src2 = inspect.getsource(SK.ManageServerConnection)
    print(src2[:1000])
except:
    print("Not available")

# Check LOGINGW
print(f"\nLOGINGW: {SK.LOGINGW}")
