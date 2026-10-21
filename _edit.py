import re

with open("gap_fade_auto.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace A/B split in confirm_and_enter
old1 = '''        # Split: Group A (normal) vs Group B (at limit, wait for unlock)
        self.pending_unlock = []
        group_a = []
        for _s in self.signals:
            if _s.is_at_limit:
                self.pending_unlock.append(_s)
            else:
                group_a.append(_s)
        if self.pending_unlock:
            self.log.info(f"  Group B (at limit): {len(self.pending_unlock)}")

        for sig in group_a:'''

new1 = '''        skipped_at_limit = 0

        for sig in self.signals:
            if sig.is_at_limit:
                skipped_at_limit += 1
                continue
'''

assert old1 in content, "Pattern 1 not found"
content = content.replace(old1, new1)

# 2. Replace docstring
content = content.replace(
    '        """Group A: enter immediately. Group B (at limit): defer to unlock."""',
    '        """Enter all signals immediately. Skip stocks at daily price limit."""'
)

# 3. Add skip log before Total exposure line
old3 = '''        self.log.info(
            f"  Total exposure: {total_exposure:,.0f} "
            f"({total_exposure/self.config.capital*100:.0f}%)")'''
new3 = '''        if skipped_at_limit:
            self.log.info(f"  Skipped (at price limit): {skipped_at_limit}")
        self.log.info(
            f"  Total exposure: {total_exposure:,.0f} "
            f"({total_exposure/self.config.capital*100:.0f}%)")'''
assert old3 in content, "Pattern 3 not found"
content = content.replace(old3, new3)

# 4. Remove _monitor_unlock and _enter_unlock methods
start_marker = "    def _monitor_unlock(self):"
end_marker = "    def monitor_positions(self):"
start_idx = content.index(start_marker)
end_idx = content.index(end_marker)
content = content[:start_idx] + content[end_idx:]

# 5. Remove Phase 1 from monitor_positions
old5 = '''    def monitor_positions(self):
        """Monitor: handle unlock entries for Group B, then wait for Smart Trade."""
        self.log.info("=" * 60)
        # Phase 1: Monitor Group B for unlock
        if hasattr(self, "pending_unlock") and self.pending_unlock:
            self._monitor_unlock()

        # Phase 2: Wait for Smart Trade completion
        self.log.info("STEP 3: Waiting for Smart Trade completion...")'''
new5 = '''    def monitor_positions(self):
        """Monitor: wait for Smart Trade completion."""
        self.log.info("=" * 60)
        self.log.info("STEP 3: Waiting for Smart Trade completion...")'''
assert old5 in content, "Pattern 5 not found"
content = content.replace(old5, new5)

with open("gap_fade_auto.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Edits applied.")

import py_compile
try:
    py_compile.compile("gap_fade_auto.py", doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")
