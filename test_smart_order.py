import sys, time
import comtypes.client

SKCOM_PATH = r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll"
comtypes.client.GetModule(SKCOM_PATH)
import comtypes.gen.SKCOMLib as sk

CUST_ID = "D121280815"
PASSWORD = "Zaq582811@"
ACCOUNT = "913R0438724"

def main():
    m_pSKCenter = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
    m_pSKOrder = comtypes.client.CreateObject(sk.SKOrderLib, interface=sk.ISKOrderLib)
    m_pSKReply = comtypes.client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)

    class ReplyEvent:
        def OnReplyMessage(self, bstrUserID, bstrMessages):
            print(f"  [Reply] {bstrMessages}")
            return -1

    class OrderEvent:
        def OnAccount(self, *args):
            return -1
        def OnOrderResult(self, *args):
            print(f"  [OnOrderResult] {args}")
            return -1
        def OnFill(self, *args):
            print(f"  [OnFill] {args}")
            return -1
        def OnCancel(self, *args):
            print(f"  [OnCancel] {args}")
            return -1
        def OnOpen(self, *args):
            print(f"  [OnOpen] {args}")
            return -1

    reply_handler = comtypes.client.GetEvents(m_pSKReply, ReplyEvent())
    order_handler = comtypes.client.GetEvents(m_pSKOrder, OrderEvent())

    m_pSKCenter.SKCenterLib_SetAuthority(0)
    nCode = m_pSKCenter.SKCenterLib_Login(CUST_ID, PASSWORD)
    if nCode != 0:
        print(f"Login failed: {nCode}"); return
    print("Login OK")

    m_pSKOrder.SKOrderLib_Initialize()
    m_pSKOrder.ReadCertByID(CUST_ID)

    # 3481 prev_close=48.25, limit_down=44.85
    limit_down = "44.85"
    print(f"\n--- TEST: 3481 buy 1 zhang @ {limit_down} (limit-down) ---")
    print(f"  Account: {ACCOUNT}")
    
    oOrder = sk.STOCKORDER()
    oOrder.bstrFullAccount = ACCOUNT
    oOrder.bstrStockNo = "3481"
    oOrder.sPrime = 0
    oOrder.sPeriod = 0
    oOrder.sFlag = 0
    oOrder.sBuySell = 0
    oOrder.nTradeType = 0
    oOrder.nSpecialTradeType = 2   # LIMIT
    oOrder.bstrPrice = limit_down
    oOrder.nQty = 1

    nRet = m_pSKOrder.SendStockOrder(CUST_ID, False, oOrder)
    print(f"  Result: {nRet}")
    
    print("\nWaiting 8s...")
    for i in range(8):
        time.sleep(1)
        print(f"  ...{i+1}s")

    print("\nDone. Check app!")

if __name__ == "__main__":
    main()
