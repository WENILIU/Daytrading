import pathlib

p = pathlib.Path(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_auto.py')
content = p.read_text(encoding='utf-8')

# Update CA path
old = 'ca_path = r"C:\\Users\\weni.liu\\Documents\\CA\\your_cert.pfx"'
new = 'ca_path = r"D:\\CA\\D121280815.capitalwebca"'

content = content.replace(old, new)
p.write_text(content, encoding='utf-8')
print('CA path updated')
