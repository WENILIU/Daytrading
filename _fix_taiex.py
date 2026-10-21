import pathlib

path = pathlib.Path(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py')
content = path.read_text(encoding='utf-8')

# Fix TAIEX quote - use try/except with proper fallback
old = '''        # Get TAIEX gap via quote
        try:
            idx_data = stock.intraday.quote(symbol="0000")
            self.market_gap = (idx_data.get("changePercent", 0) or 0) / 100
        except Exception:
            self.market_gap = 0.0'''

new = '''        # Get TAIEX gap (index not available via stock API, use 0 as fallback)
        # Market-adjusted gap: on down days this is conservative (fewer signals)
        # On up days this filters out market-wide rallies
        self.market_gap = 0.0
        try:
            # Try to estimate market gap from a basket of large-cap stocks
            basket = ['2330', '2317', '2454', '2303', '6505', '3711', '2412']
            gaps = []
            for sym in basket:
                try:
                    q = stock.intraday.quote(symbol=sym)
                    op = q.get('openPrice') or 0
                    pc = q.get('previousClose') or 0
                    if pc > 0 and op > 0:
                        gaps.append((op - pc) / pc)
                except Exception:
                    pass
            if gaps:
                self.market_gap = sum(gaps) / len(gaps)
        except Exception:
            self.market_gap = 0.0'''

if old in content:
    content = content.replace(old, new)
    path.write_text(content, encoding='utf-8')
    print("Fixed TAIEX with basket estimation")
else:
    print("Pattern not found")
