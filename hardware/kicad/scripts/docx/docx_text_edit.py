# -*- coding: utf-8 -*-
"""Replace text inside <w:t> nodes of a .docx, one node at a time.

Word splits a sentence across runs whenever formatting changes, so a plain
search over document.xml misses half the targets. This works on the text of
each <w:t> separately and insists that exactly one node contains the pattern.

    python docx_text_edit.py <file.docx> <pairs.json> [--dry]
"""
import json
import re
import shutil
import sys
import zipfile

doc, pairs_file = sys.argv[1], sys.argv[2]
dry = "--dry" in sys.argv
pairs = json.load(open(pairs_file, encoding="utf-8"))

zin = zipfile.ZipFile(doc)
parts = {n: zin.read(n) for n in zin.namelist()}
zin.close()
xml = parts["word/document.xml"].decode("utf-8")

NODE = re.compile(r"(<w:t(?: [^>]*)?>)(.*?)(</w:t>)", re.S)
failed = False

for old, new in pairs:
    hits = [m for m in NODE.finditer(xml) if old in m.group(2)]
    if len(hits) != 1:
        print("MISS (%d nodes): %s" % (len(hits), old[:80]))
        for m in hits[:3]:
            print("      node: %s" % m.group(2)[:160])
        failed = True
        continue
    m = hits[0]
    body = m.group(2).replace(old, new)
    if dry:
        print("OK   %s\n  ->  %s" % (old[:80], new[:80]))
        continue
    xml = xml[:m.start()] + m.group(1) + body + m.group(3) + xml[m.end():]

if failed:
    sys.exit("ABORT: at least one pattern did not match exactly one node")
if dry:
    sys.exit(0)

parts["word/document.xml"] = xml.encode("utf-8")
shutil.copy2(doc, doc + ".bak")
zout = zipfile.ZipFile(doc, "w", zipfile.ZIP_DEFLATED)
for name, data in parts.items():
    zout.writestr(name, data)
zout.close()
print("OK, %d replacements in %s" % (len(pairs), doc))
