import comtypes.client
import time
import os

# Make sure SKCOM can find the cert - set working dir to SKCOM folder
os.chdir(r'D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\元件\x64')

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

# Try login with cert in working directory
print("Login (cert in working dir)...")
nCode = m_pSKCenter.SKCenterLib_Login('D121280815', 'Zaq582811@')
msg = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
print(f"  Result: code={nCode}, msg={msg}")

# Also try SKCenterLib_LoginGW (gateway login?)
print("\nLoginGW...")
try:
    nCode = m_pSKCenter.SKCenterLib_LoginGW('D121280815', 'Zaq582811@')
    msg = m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
    print(f"  Result: code={nCode}, msg={msg}")
except Exception as e:
    print(f"  Error: {e}")
