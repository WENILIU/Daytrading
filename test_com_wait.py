import sys, os, time, ctypes
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
os.add_dll_directory(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")

import tkinter as tk
import comtypes.client as cc
cc.GetModule(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll")
import comtypes.gen.SKCOMLib as sk

CUST_ID = "D121280815"
PASSWORD = "Zaq582811@"
price_count = [0]
list_events = []

class ReplyEvent:
    def OnReplyMessage(self, b, m): return -1

class QuoteEvent:
    def OnConnection(self, nKind, nCode):
        print(f"  [EVENT] OnConnection kind={nKind} code={nCode}")
        return -1
    def OnNotifyStockList(self, sMarketNo, bstrStockData):
        list_events.append(sMarketNo)
        print(f"  [EVENT] StockList mkt={sMarketNo} len={len(bstrStockData)}")
        return -1
    def OnNotifyPriceLONG(self, *a):
        price_count[0] += 1
        return -1
    def OnNotifyTicksLONG(self, *a): return -1
    def OnNotifyBest5LONG(self, *a): return -1

root = tk.Tk()
root.withdraw()
skC = cc.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
skQ = cc.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)
skR = cc.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)
rh = cc.GetEvents(skR, ReplyEvent())
qh = cc.GetEvents(skQ, QuoteEvent())

skC.SKCenterLib_SetLogPath(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\CapitalLog")
if skC.SKCenterLib_Login(CUST_ID, PASSWORD) != 0:
    print("Login FAILED"); root.destroy(); sys.exit(1)
print("[1] Login OK")

nCode = skQ.SKQuoteLib_EnterMonitorLONG()
print(f"[2] EnterMonitor: {skC.SKCenterLib_GetReturnCodeMessage(nCode)}")

def count_valid():
    valid = 0
    for mk in [0, 1]:
        idx = 0
        while idx < 5000:
            pStock = sk.SKSTOCKLONG()
            try:
                pStock, nc = skQ.SKQuoteLib_GetStockByIndexLONG(mk, idx, pStock)
                if nc != 0: break
            except: break
            dec = pStock.sDecimal if pStock.sDecimal > 0 else 2
            div = 10 ** dec
            if pStock.nOpen / div > 0 and pStock.nRef / div > 0:
                valid += 1
            idx += 1
    return valid

def check():
    v = count_valid()
    print(f"  t={check.t}s: valid={v} price_events={price_count[0]} lists={list_events}")
    check.t += 2
    if v >= 500:
        do_scan()
    elif check.t > 30:
        do_scan()
    else:
        root.after(2000, check)
check.t = 0

def do_scan():
    print(f"\n[FINAL SCAN] price_events={price_count[0]}")
    t0 = time.time()
    total=0; valid=0; gaps=[]
    for mk in [0,1]:
        idx=0
        while idx<5000:
            pStock = sk.SKSTOCKLONG()
            try:
                pStock, nc = skQ.SKQuoteLib_GetStockByIndexLONG(mk, idx, pStock)
                if nc!=0: break
            except: break
            total+=1
            code=str(pStock.bstrStockNo).strip()
            dec=pStock.sDecimal if pStock.sDecimal>0 else 2
            div=10**dec
            op=pStock.nOpen/div; pc=pStock.nRef/div
            if op>0 and pc>0:
                valid+=1
                gap=(op-pc)/pc
                if abs(gap)>=0.03:
                    gaps.append((code,mk,op,pc,round(gap*100,2)))
            idx+=1
    st=time.time()-t0
    print(f"  Total:{total} Valid:{valid} Time:{st:.3f}s")
    print(f"  |gap|>=3%:{len(gaps)} |gap|>=5%:{len([g for g in gaps if abs(g[4])>=5])}")
    if gaps:
        gaps.sort(key=lambda x:abs(x[4]),reverse=True)
        for g in gaps[:15]:
            print(f"    {g[0]:<6} gap={g[4]:+.1f}% open={g[2]:.2f} prev={g[3]:.2f}")
    root.quit()

print("[3] Monitoring data flow (up to 30s)...")
root.after(2000, check)
root.mainloop()
root.destroy()
