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
connected_kinds = []

class ReplyEvent:
    def OnReplyMessage(self, b, m): return -1

class QuoteEvent:
    def OnConnection(self, nKind, nCode):
        connected_kinds.append((nKind, nCode))
        print(f"  [EVENT] OnConnection kind={nKind} code={nCode}")
        return -1
    def OnNotifyStockList(self, sMarketNo, bstrStockData):
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

def try_request_stocks():
    print(f"[3] Connection kinds so far: {connected_kinds}")
    nc = skQ.SKQuoteLib_IsConnected()
    print(f"[3] IsConnected={nc}")
    
    # Try RequestStocks with page number
    with open("all_stocks.txt") as f:
        stocks = [s.strip() for s in f if s.strip()][:100]
    stock_str = ",".join(stocks)
    
    # COM RequestStocks signature: (psPageNo, bstrStockNo)
    psPageNo = ctypes.c_short(0)
    try:
        result = skQ.SKQuoteLib_RequestStocks(psPageNo, stock_str)
        print(f"[4] RequestStocks page=0: {result}")
    except Exception as e:
        print(f"[4] RequestStocks error: {e}")
        # Try without page
        try:
            nc = skQ.SKQuoteLib_RequestStocks(0, stock_str)
            print(f"[4b] RequestStocks(0, str): {skC.SKCenterLib_GetReturnCodeMessage(nc)}")
        except Exception as e2:
            print(f"[4c] Also failed: {e2}")
    
    root.after(5000, check_prices)

def check_prices():
    print(f"[5] prices={price_count[0]}")
    if price_count[0] > 50:
        do_scan()
    else:
        root.after(3000, do_scan)

def do_scan():
    print(f"[6] SCANNING (prices={price_count[0]})...")
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
    print(f"  |gap|>=3%:{len(gaps)}")
    if gaps:
        gaps.sort(key=lambda x:abs(x[4]),reverse=True)
        for g in gaps[:10]:
            print(f"    {g[0]:<6} gap={g[4]:+.1f}%")
    root.quit()

print("[3] Waiting 5s for connection...")
root.after(5000, try_request_stocks)
root.after(25000, do_scan)
root.mainloop()
root.destroy()
