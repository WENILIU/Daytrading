import sys, os
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
os.add_dll_directory(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
import comtypes.client as cc
cc.GetModule(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll")
import comtypes.gen.SKCOMLib as sk

m = cc.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)
methods = sorted([a for a in dir(m) if 'Request' in a or 'Get' in a or 'Enter' in a or 'Set' in a])
for m_name in methods:
    print(m_name)
