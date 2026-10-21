import comtypes.client
import time

comtypes.client.GetModule(r'D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64\SKCOM.dll')
import comtypes.gen.SKCOMLib as sk

# Create objects
m_pSKCenter = comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)
m_pSKReply = comtypes.client.CreateObject(sk.SKReplyLib, interface=sk.ISKReplyLib)
m_pSKOrder = comtypes.client.CreateObject(sk.SKOrderLib, interface=sk.ISKOrderLib)

# Register ReplyLib event FIRST (required before login)
class SKReplyLibEvent:
    def OnReplyMessage(self, bstrUserID, bstrMessages):
        print(f"  [Reply] {bstrUserID}: {bstrMessages[:100]}")
        return -1

reply_event = SKReplyLibEvent()
reply_handler = comtypes.client.GetEvents(m_pSKReply, reply_event)
print("ReplyLib event registered")

# Set production environment
nCode = m_pSKCenter.SKCenterLib_SetAuthority(0)
print(f"SetAuthority: {m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)}")

# Login
nCode = m_pSKCenter.SKCenterLib_Login('D121280815', 'test')
msg = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
print(f"Login: code={nCode}, msg={msg}")
