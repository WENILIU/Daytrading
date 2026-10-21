import pathlib

path = pathlib.Path(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py')
content = path.read_text(encoding='utf-8')

# Replace the connect method to register ReplyLib first
old_connect = '''    def connect(self):
        """Login to Capital Securities via SKCOM"""
        self.log.info("Connecting to Capital Securities (SKCOM)...")

        # Create COM objects
        self.m_pSKCenter = comtypes.client.CreateObject(
            sk.SKCenterLib, interface=sk.ISKCenterLib)
        self.m_pSKOrder = comtypes.client.CreateObject(
            sk.SKOrderLib, interface=sk.ISKOrderLib)
        self.m_pSKQuote = comtypes.client.CreateObject(
            sk.SKQuoteLib, interface=sk.ISKQuoteLib)
        self.m_pSKReply = comtypes.client.CreateObject(
            sk.SKReplyLib, interface=sk.ISKReplyLib)

        # Set production environment
        self.m_pSKCenter.SKCenterLib_SetAuthority(0)

        # Login
        nCode = self.m_pSKCenter.SKCenterLib_Login(
            self.config.cust_cert_id, self.config.password)
        msg = self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
        if nCode != 0:
            raise ConnectionError(f"Login failed: {msg}")
        self.log.info(f"Login OK: {msg}")
        self._logged_in = True'''

new_connect = '''    def connect(self):
        """Login to Capital Securities via SKCOM"""
        self.log.info("Connecting to Capital Securities (SKCOM)...")

        # Create COM objects
        self.m_pSKCenter = comtypes.client.CreateObject(
            sk.SKCenterLib, interface=sk.ISKCenterLib)
        self.m_pSKOrder = comtypes.client.CreateObject(
            sk.SKOrderLib, interface=sk.ISKOrderLib)
        self.m_pSKQuote = comtypes.client.CreateObject(
            sk.SKQuoteLib, interface=sk.ISKQuoteLib)
        self.m_pSKReply = comtypes.client.CreateObject(
            sk.SKReplyLib, interface=sk.ISKReplyLib)

        # Register ReplyLib event FIRST (required before login)
        class SKReplyLibEvent:
            def OnReplyMessage(self, bstrUserID, bstrMessages):
                self_ref = self
                self_ref.log.info(f"  [Reply] {bstrUserID}: {bstrMessages[:100]}")
                return -1

        reply_event = SKReplyLibEvent()
        reply_event.log = self.log
        self._reply_handler = comtypes.client.GetEvents(
            self.m_pSKReply, reply_event)

        # Set production environment
        self.m_pSKCenter.SKCenterLib_SetAuthority(0)

        # Login
        nCode = self.m_pSKCenter.SKCenterLib_Login(
            self.config.cust_cert_id, self.config.password)
        msg = self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
        if nCode != 0:
            raise ConnectionError(f"Login failed: {msg}")
        self.log.info(f"Login OK: {msg}")
        self._logged_in = True'''

if old_connect in content:
    content = content.replace(old_connect, new_connect)
    path.write_text(content, encoding='utf-8')
    print("Fixed login order")
else:
    print("Pattern not found - checking...")
    # Find the connect method
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'def connect' in line and 'Simulator' not in lines[max(0,i-5):i]:
            print(f"Found connect at line {i+1}")
            break
