import pathlib

p = pathlib.Path(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py')
content = p.read_text(encoding='utf-8')

content = content.replace('api_key = "YOUR_API_KEY"', 'api_key = "D121280815"')

p.write_text(content, encoding='utf-8')
print('API key updated to D121280815')
