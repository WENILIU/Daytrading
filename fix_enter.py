path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add EnterMonitor after login
old = '        self.log.info(f"Login OK: {msg}")'
new = '''        self.log.info(f"Login OK: {msg}")

        # Connect to quote server (real-time stock data for scanning)
        nCode = self.quote_lib.SKQuoteLib_EnterMonitorLONG()
        if nCode == 0:
            self.log.info("Quote server connected. Real-time data ready.")
        else:
            msg2 = self.m_pSKCenter.SKCenterLib_GetReturnCodeMessage(nCode)
            self.log.warning(f"Quote server failed: {msg2}")'''

content = content.replace(old, new)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Added EnterMonitor after login.")
