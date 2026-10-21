path = r"C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\backtest_regime_filter.py"
content = open(path, "r", encoding="utf-8").read()
old = "sigs = sigs.merge(daily_mkt[['date', 'ma20', 'ma60', 'pct_from_high', 'vol_5', 'market_ret']], "
new = "sigs = sigs.merge(daily_mkt[['date', 'market_index', 'ma20', 'ma60', 'pct_from_high', 'vol_5', 'market_ret']], "
content = content.replace(old, new)
open(path, "w", encoding="utf-8").write(content)
print("Fixed: added market_index to merge")
