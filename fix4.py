path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
content = open(path, 'r', encoding='utf-8').read()

# Fix: Add ReadCertByID and OrderLib events registration after SKOrderLib_Initialize
old_init = '''        # Initialize order system
        self.m_pSKOrder.SKOrderLib_Initialize()

        # Get trading account
        self.m_pSKOrder.GetUserAccount()
        time.sleep(2)  # Wait for OnAccount callback'''

new_init = '''        # Initialize order system
        self.m_pSKOrder.SKOrderLib_Initialize()

        # Read certificate (required for placing orders)
        nCert = self.m_pSKOrder.ReadCertByID(self.config.cust_cert_id)
        if nCert != 0:
            self.log.warning(f"ReadCertByID returned {nCert}, orders may fail")
        else:
            self.log.info("Certificate verified OK")

        # Register OrderLib events (OnAccount, OnOrderResult)
        class SKOrderLibEvent:
            def OnAccount(self, *args):
                try:
                    # args[1] is comma-separated: TYPE,BRANCH,,ACCT,CUSTID,NAME,FLAG
                    data = args[1] if len(args) > 1 else str(args)
                    parts = data.split(",")
                    if len(parts) >= 4 and parts[0] == "TS":
                        branch = parts[1]
                        acct_num = parts[3]
                        full = f"{branch}{acct_num}"
                        self_ref.log.info(f"  [Account detected] {full}")
                        if not self_ref.account:
                            self_ref.account = full
                except Exception as e:
                    self_ref.log.warning(f"  [OnAccount] parse error: {e}")
                return -1

            def OnOrderResult(self, *args):
                try:
                    self_ref.log.info(f"  [OrderResult] {args}")
                except Exception:
                    pass
                return -1

            def OnFill(self, *args):
                try:
                    self_ref.log.info(f"  [FILL] {args}")
                except Exception:
                    pass
                return -1

            def OnCancel(self, *args):
                try:
                    self_ref.log.info(f"  [CANCEL] {args}")
                except Exception:
                    pass
                return -1

            def OnOpen(self, *args):
                return -1

        order_event = SKOrderLibEvent()
        order_event.log = self.log
        order_event._ref = self
        # Use closure to access self
        def make_order_event(trader_ref):
            class OLE:
                def OnAccount(self_inner, *args):
                    try:
                        data = args[1] if len(args) > 1 else str(args)
                        parts = data.split(",")
                        if len(parts) >= 4 and parts[0] == "TS":
                            branch = parts[1]
                            acct_num = parts[3]
                            full = f"{branch}{acct_num}"
                            trader_ref.log.info(f"  [Account detected] {full}")
                            if not trader_ref.account:
                                trader_ref.account = full
                    except Exception as e:
                        trader_ref.log.warning(f"  [OnAccount] parse error: {e}")
                    return -1
                def OnOrderResult(self_inner, *args):
                    trader_ref.log.info(f"  [OrderResult] {args}")
                    return -1
                def OnFill(self_inner, *args):
                    trader_ref.log.info(f"  [FILL] {args}")
                    return -1
                def OnCancel(self_inner, *args):
                    trader_ref.log.info(f"  [CANCEL] {args}")
                    return -1
                def OnOpen(self_inner, *args):
                    return -1
            return OLE()

        self._order_handler = comtypes.client.GetEvents(
            self.m_pSKOrder, make_order_event(self))

        # Get trading account
        self.m_pSKOrder.GetUserAccount()
        time.sleep(2)  # Wait for OnAccount callback'''

if old_init in content:
    content = content.replace(old_init, new_init)
    print("Fixed: Added ReadCertByID + OrderLib events")
else:
    print("ERROR: Pattern not found!")
    # Debug
    idx = content.find('SKOrderLib_Initialize')
    print(f"SKOrderLib_Initialize at position {idx}")
    print(repr(content[idx-50:idx+200]))

open(path, 'w', encoding='utf-8').write(content)
