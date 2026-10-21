import comtypes.client
import time

comtypes.client.GetModule(r'D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll')
import comtypes.gen.SKCOMLib as sk

m_pSKCenter = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
m_pSKReply = comtypes.client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)

class ReplyEvent:
    def OnReplyMessage(self, bstrUserID, bstrMessages):
        print(f"  [Reply] {bstrUserID}: {bstrMessages[:200]}")
        return -1

handler = comtypes.client.GetEvents(m_pSKReply, ReplyEvent())

m_pSKCenter.SKCenterLib_SetAuthority(0)

# GenerateKeyCert with login ID
print("Step 1: GenerateKeyCert...")
nCode = m_pSKCenter.SKCenterLib_GenerateKeyCert('D121280815')
msg = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
print(f"  Result: code={nCode}, msg={msg}")

time.sleep(3)

# Then login
print("\nStep 2: Login...")
nCode = m_pSKCenter.SKCenterLib_Login('D121280815', 'Zaq582811@')
msg = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
print(f"  Result: code={nCode}, msg={msg}")
