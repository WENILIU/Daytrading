path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
content = open(path, 'r', encoding='utf-8').read()

# Remove the dead SKOrderLibEvent class (lines 342-385 equivalent)
# It starts with "        # Register OrderLib events" and the first class definition
# The actual working code is the make_order_event closure

old_dead = '''        # Register OrderLib events (OnAccount, OnOrderResult)
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
        def make_order_event(trader_ref):'''

new_clean = '''        # Register OrderLib events (OnAccount, OnOrderResult, OnFill, OnCancel)
        def make_order_event(trader_ref):'''

if old_dead in content:
    content = content.replace(old_dead, new_clean)
    print("Removed dead code, kept closure-based handler")
else:
    print("Pattern not found - checking...")
    idx = content.find("class SKOrderLibEvent")
    if idx > 0:
        print(f"Found at {idx}")
    else:
        print("Not found at all")

open(path, 'w', encoding='utf-8').write(content)
