# -*- coding: utf-8 -*-
"""Extract the text of the Capital COM manual so the smart-order / balance field
layout can be read from the vendor's own definition instead of guessed from rows.
docx is a zip; word/document.xml holds the body. Writes plain text next to it."""
import zipfile, re, sys
from pathlib import Path

src = Path(r"D:\CapitalAPI\CapitalAPI_2.13.59_PythonExample\策略王COM元件使用說明_V2.13.59.docx")
xml = zipfile.ZipFile(src).read("word/document.xml").decode("utf-8", "ignore")
# paragraphs and table cells are the units that matter; keep them on separate lines
xml = re.sub(r"</w:p>", "\n", xml)
xml = re.sub(r"</w:tc>", " | ", xml)
xml = re.sub(r"</w:tr>", "\n", xml)
text = re.sub(r"<[^>]+>", "", xml)
text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
lines = [ln.strip() for ln in text.splitlines()]
lines = [ln for ln in lines if ln]
out = Path("_capital_manual.txt")
out.write_text("\n".join(lines), encoding="utf-8")
print(f"{src.name}: {len(lines)} lines -> {out}")
