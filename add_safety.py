path = r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py'
content = open(path, 'r', encoding='utf-8').read()

# Add safety check for non-當沖 stocks in the order result handling
old = '''        if nCode == 0:
            sig.order_seq = bstrMessage
            sig.state = PositionState.FILLED
            self.active_positions[sig.symbol] = sig
            self.log.info(
                f"  SMART ORDER: {sig.symbol} {sig.direction.value} {sig.shares} shares "'''

new = '''        if nCode == 0:
            sig.order_seq = bstrMessage
            sig.state = PositionState.FILLED
            self.active_positions[sig.symbol] = sig
            self.log.info(
                f"  SMART ORDER: {sig.symbol} {sig.direction.value} {sig.shares} shares "'''

# Check if error handling already exists
if '924' in content or '不支持' in content or 'not support' in content.lower():
    print("Already has non-當沖 handling")
else:
    # Add to the error branch
    old_err = '''        except Exception as e:
            self.log.error(f"  {sig.symbol}: Smart Trade exception - {e}")
            sig.state = PositionState.CANCELLED
            return'''
    
    new_err = '''        except Exception as e:
            err_str = str(e)
            if '924' in err_str or '不支持' in err_str or 'not support' in err_str.lower():
                self.log.warning(f"  {sig.symbol}: Does not support day trade, SKIP")
            else:
                self.log.error(f"  {sig.symbol}: Smart Trade exception - {e}")
            sig.state = PositionState.CANCELLED
            return'''
    
    if old_err in content:
        content = content.replace(old_err, new_err)
        open(path, 'w', encoding='utf-8').write(content)
        print("Added non-當沖 safety handling")
    else:
        print("Pattern not found, checking...")
        idx = content.find("Smart Trade exception")
        if idx > 0:
            print(f"Found at {idx}")
            print(content[idx-100:idx+200])
