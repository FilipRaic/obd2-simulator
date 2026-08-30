# -*- coding: utf-8 -*-
"""Targeted literal replacements inside word/document.xml of a .docx.

Every pattern must match exactly once, otherwise nothing is written. That
guard exists because a silent zero-match is how a document quietly keeps an
old number.

    python docx_replace.py <file.docx> <pairs.json>

pairs.json is a list of [old, new] pairs.
"""
import json
import shutil
import sys
import zipfile

doc, pairs_file = sys.argv[1], sys.argv[2]
pairs = json.load(open(pairs_file, encoding="utf-8"))

zin = zipfile.ZipFile(doc)
parts = {n: zin.read(n) for n in zin.namelist()}
zin.close()

xml = parts["word/document.xml"].decode("utf-8")
for old, new in pairs:
    n = xml.count(old)
    if n != 1:
        sys.exit("ABORT: %d matches (expected 1) for: %s" % (n, old[:90]))
    xml = xml.replace(old, new)
parts["word/document.xml"] = xml.encode("utf-8")

shutil.copy2(doc, doc + ".bak")
zout = zipfile.ZipFile(doc, "w", zipfile.ZIP_DEFLATED)
for name, data in parts.items():
    zout.writestr(name, data)
zout.close()
print("OK, %d replacements in %s" % (len(pairs), doc))
