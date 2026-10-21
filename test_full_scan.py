"""
Full scan: hidden tkinter + COM (correct event registration order)
"""
import sys, os, time
sys.path.insert(0, r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")
os.add_dll_directory(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64")

import tkinter as tk
import comtypes.client as cc
cc.GetModule(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll")
import comtypes.gen.SKCOMLib as sk
import pandas as pd

CUST_ID = "D121280815"
PASSWORD = "Zaq582811@"

stock_list_ready = [False]
price_count = [0]

class ReplyEvent:
    def OnReplyMessage(self, bstrUserID, bstrMessages):
        return -1

class QuoteEvent:
    def OnNotifyStockList(self, sMarketNo, bstrStockData):
        stock_list_ready[0] = True
        return -1
    def OnNotifyPriceLONG(self, *args):
        price_count[0] += 1
        return -1
    def OnNotifyTicksLONG(self, *args): return -1
    def OnNotifyBest5LONG(self, *args): return -1

def main():
    print("=" * 70)
    print("FULL SCAN: hidden tkinter + COM")
    print("=" * 70)
    
    root = tk.Tk()
    root.withdraw()
    
    # Create objects
    skC = cc.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
    skQ = cc.CreateObject(sk.SKQuoteLib, interface=sk.ISKQuoteLib)
    skR = cc.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)
    
    # Register ReplyLib FIRST (required before login!)
    reply_handler = cc.GetEvents(skR, ReplyEvent())
    print("[0] ReplyLib registered")
    
    # Register QuoteLib events
    quote_handler = cc.GetEvents(skQ, QuoteEvent())
    print("[0] QuoteLib registered")
    
    # Login
    skC.SKCenterLib_SetLogPath(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\CapitalLog")
    nCode = skC.SKCenterLib_Login(CUST_ID, PASSWORD)
    if nCode != 0:
        print(f"Login failed: {skC.SKCenterLib_GetReturnCodeMessage(nCode)}")
        root.destroy()
        return
    print("[1] Login OK")
    
    # EnterMonitor
    nCode = skQ.SKQuoteLib_EnterMonitorLONG()
    if nCode != 0:
        print(f"EnterMonitor failed: {skC.SKCenterLib_GetReturnCodeMessage(nCode)}")
        root.destroy()
        return
    print("[2] EnterMonitor OK")
    
    # Wait for data via tkinter event loop
    print("[3] Waiting for data push...")
    
    def check():
        print(f"  Prices: {price_count[0]}, StockList: {stock_list_ready[0]}")
        if price_count[0] > 100:
            do_scan(root, skQ)
        elif stock_list_ready[0]:
            # Stock list received, wait a bit more for prices
            root.after(3000, lambda: do_scan(root, skQ))
        else:
            root.after(2000, check)
    
    root.after(2000, check)
    root.after(20000, lambda: do_scan(root, skQ))  # Force scan after 20s
    
    root.mainloop()


def do_scan(root, skQ):
    print(f"\n[4] SCANNING (prices: {price_count[0]})...")
    t0 = time.time()
    
    total = 0
    valid = 0
    gaps = []
    
    for market_no in [0, 1]:
        idx = 0
        while idx < 5000:
            pStock = sk.SKSTOCKLONG()
            try:
                pStock, nCode = skQ.SKQuoteLib_GetStockByIndexLONG(market_no, idx, pStock)
                if nCode != 0: break
            except: break
            
            total += 1
            code = str(pStock.bstrStockNo).strip()
            dec = pStock.sDecimal if pStock.sDecimal > 0 else 2
            div = 10 ** dec
            op = pStock.nOpen / div
            pc = pStock.nRef / div
            
            if op > 0 and pc > 0:
                valid += 1
                gap = (op - pc) / pc
                if abs(gap) >= 0.03:
                    gaps.append((code, market_no, op, pc, pStock.nClose/div, round(gap*100, 2), pStock.nTQty))
            idx += 1
    
    scan_time = time.time() - t0
    
    print(f"\n{'='*70}")
    print(f"  Total: {total}  Valid: {valid}")
    print(f"  Scan: {scan_time:.3f}s ({total/max(scan_time,0.001):.0f}/sec)")
    print(f"  |gap|>=3%: {len(gaps)}")
    print(f"  |gap|>=5%: {len([g for g in gaps if abs(g[5]) >= 5])}")
    
    if gaps:
        gaps.sort(key=lambda x: abs(x[5]), reverse=True)
        print(f"\n  {'Code':<6} {'Mkt':>3} {'Open':>8} {'Prev':>8} {'Close':>8} {'Gap%':>7} {'Qty':>10}")
        for g in gaps[:30]:
            print(f"  {g[0]:<6} {g[1]:>3} {g[2]:>8.2f} {g[3]:>8.2f} {g[4]:>8.2f} {g[5]:>+6.1f}% {g[6]:>10}")
    
    if gaps:
        df = pd.DataFrame(gaps, columns=['code','market','open','prev_close','close','gap_pct','qty'])
        df.to_csv(r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\scan_result_20261021.csv", index=False, encoding='utf-8-sig')
        print(f"\n  Saved: scan_result_20261021.csv")
    
    root.quit()
    root.destroy()


if __name__ == "__main__":
    main()
