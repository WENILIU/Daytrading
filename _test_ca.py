import comtypes.client
import time

comtypes.client.GetModule(r'D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll')
import comtypes.gen.SKCOMLib as sk

m_pSKCenter = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
m_pSKReply = comtypes.client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)

# Register ReplyLib
class ReplyEvent:
    def OnReplyMessage(self, bstrUserID, bstrMessages):
        print(f"  [Reply] {bstrUserID}: {bstrMessages[:200]}")
        return -1

handler = comtypes.client.GetEvents(m_pSKReply, ReplyEvent())

# Set production
m_pSKCenter.SKCenterLib_SetAuthority(0)

# Try GenerateKeyCert first (register device)
print("Trying GenerateKeyCert...")
nCode = m_pSKCenter.SKCenterLib_GenerateKeyCert()
msg = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
print(f"GenerateKeyCert: code={nCode}, msg={msg}")

time.sleep(2)

# Then try login
print("\nTrying Login...")
nCode = m_pSKCenter.SKCenterLib_Login('D121280815', 'Zaq582811@')
msg = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
print(f"Login: code={nCode}, msg={msg}")
