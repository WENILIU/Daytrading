import comtypes.client
import time

comtypes.client.GetModule(r'D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll')
import comtypes.gen.SKCOMLib as sk

m_pSKCenter = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
m_pSKReply = comtypes.client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)
m_pSKOrder = comtypes.client.CreateObject(sk.SKOrderLib, interface=sk.ISKOrderLib)

class ReplyEvent:
    def OnReplyMessage(self, bstrUserID, bstrMessages):
        print(f"  [Reply] {bstrUserID}: {bstrMessages[:200]}")
        return -1

handler = comtypes.client.GetEvents(m_pSKReply, ReplyEvent())
m_pSKCenter.SKCenterLib_SetAuthority(0)

print("Login...")
nCode = m_pSKCenter.SKCenterLib_Login('D121280815', 'Zaq582811@')
msg = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
print(f"  Result: code={nCode}, msg={msg}")

if nCode == 0:
    print("\nSUCCESS! Initializing order system...")
    m_pSKOrder.SKOrderLib_Initialize()
    m_pSKOrder.GetUserAccount()
    time.sleep(3)
    print("Done. Ready to trade!")
