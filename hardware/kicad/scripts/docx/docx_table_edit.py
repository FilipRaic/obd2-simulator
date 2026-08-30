# -*- coding: utf-8 -*-
"""Index-based docx table editor - safe replacement for docx-edit.ps1 Set-RowCells.

Targets cells by (table_index, row_index, cell_index) instead of by text marker.
The text-marker approach in docx-edit.ps1 is what corrupted this document:
Set-RowCells hits the FIRST row containing the marker, so 'ESP32-S3' aimed at
table 6 landed in table 2 instead.

Cell text is set the same way Frag-SetText does it: the first <w:t> in the cell
receives the text, every other <w:t> is emptied, so run formatting survives.
Zip is rebuilt in Create mode (Update mode leaves bad local headers).
"""
import os, re, shutil, sys, zipfile

sys.stdout.reconfigure(encoding="utf-8")

# Target document. Pass one on the command line, or point OBD2_DOCX at it;
# there is deliberately no personal path baked in.
DOC = os.environ.get("OBD2_DOCX", "")

RE_TBL = re.compile(r"<w:tbl>.*?</w:tbl>", re.S)
RE_TR = re.compile(r"<w:tr(?: [^>]*)?>.*?</w:tr>", re.S)
RE_TC = re.compile(r"<w:tc(?: [^>]*)?>.*?</w:tc>", re.S)
RE_WT = re.compile(r"<w:t(?: [^>]*)?>(.*?)</w:t>", re.S)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def unesc(s):
    return (s.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))


def frag_text(frag):
    return "".join(unesc(m.group(1)) for m in RE_WT.finditer(frag))


def frag_set_text(frag, new):
    nodes = list(RE_WT.finditer(frag))
    if not nodes:
        return None
    out, pos = [], 0
    for i, n in enumerate(nodes):
        out.append(frag[pos:n.start()])
        pos = n.end()
        out.append('<w:t xml:space="preserve">' + esc(new) + "</w:t>" if i == 0 else "<w:t></w:t>")
    out.append(frag[pos:])
    return "".join(out)


class Doc:
    def __init__(self, path):
        self.path = path
        with zipfile.ZipFile(path) as z:
            self.xml = z.read("word/document.xml").decode("utf-8")
        self.log = []

    # --- addressing -------------------------------------------------------
    def _tbl(self, ti):
        ms = list(RE_TBL.finditer(self.xml))
        if not 1 <= ti <= len(ms):
            raise IndexError(f"tablica {ti} ne postoji (ima ih {len(ms)})")
        return ms[ti - 1]

    def rows(self, ti):
        t = self._tbl(ti)
        return [(t.start() + m.start(), t.start() + m.end(), m.group(0))
                for m in RE_TR.finditer(t.group(0))]

    def row_text(self, ti, ri):
        r = self.rows(ti)[ri]
        return [frag_text(c.group(0)) for c in RE_TC.finditer(r[2])]

    # --- mutation ---------------------------------------------------------
    def set_row(self, ti, ri, cells, expect=None):
        """cells: list, None entry = leave that cell untouched.
        expect: substring that MUST appear in the row - a guard against drift."""
        start, end, row = self.rows(ti)[ri]
        if expect is not None and expect not in frag_text(row):
            raise AssertionError(
                f"T{ti} R{ri}: ocekivao '{expect}', nasao '{frag_text(row)[:90]}'")
        tcs = list(RE_TC.finditer(row))
        out, pos = [], 0
        for i, tc in enumerate(tcs):
            out.append(row[pos:tc.start()])
            pos = tc.end()
            if i < len(cells) and cells[i] is not None:
                new = frag_set_text(tc.group(0), cells[i])
                out.append(new if new else tc.group(0))
            else:
                out.append(tc.group(0))
        out.append(row[pos:])
        self.xml = self.xml[:start] + "".join(out) + self.xml[end:]
        self.log.append(f"OK   T{ti} R{ri} <- {[c for c in cells if c]}")

    def clone_row_after(self, ti, ri, cells):
        """Duplicate row ri (keeps its formatting) and fill the copy."""
        start, end, row = self.rows(ti)[ri]
        tcs = list(RE_TC.finditer(row))
        out, pos = [], 0
        for i, tc in enumerate(tcs):
            out.append(row[pos:tc.start()])
            pos = tc.end()
            new = frag_set_text(tc.group(0), cells[i]) if i < len(cells) else None
            out.append(new if new else tc.group(0))
        out.append(row[pos:])
        self.xml = self.xml[:end] + "".join(out) + self.xml[end:]
        self.log.append(f"OK   T{ti} novi redak iza R{ri} <- {cells}")

    def replace_para_text(self, find, new, occurrence=1):
        """Replace the whole text of the Nth paragraph containing `find`."""
        hits = 0
        for m in re.finditer(r"<w:p(?: [^>]*)?>.*?</w:p>", self.xml, re.S):
            if find in frag_text(m.group(0)):
                hits += 1
                if hits == occurrence:
                    rep = frag_set_text(m.group(0), new)
                    if rep is None:
                        raise AssertionError(f"nema w:t u odlomku '{find}'")
                    self.xml = self.xml[:m.start()] + rep + self.xml[m.end():]
                    self.log.append(f"OK   odlomak '{find[:45]}...'")
                    return
        raise AssertionError(f"odlomak nije nadjen: '{find}' (pojava {occurrence})")

    def replace_inline(self, find, new, expect_count=None):
        """Replace `find` with `new` INSIDE paragraphs, across run boundaries,
        keeping every other run intact (citations, footnote refs, bold spans).

        Unlike replace_para_text this rewrites only the matched substring, so it
        is the safe choice for prose. Returns the number of paragraphs changed;
        pass expect_count to assert on it.

        One forward pass over the document: each paragraph is rewritten at most
        once and the scan continues AFTER the rewritten paragraph. (The earlier
        rescan-from-the-top loop went infinite whenever `new` contained `find`,
        e.g. when appending a sentence after an existing one - found 18.07.2026.)"""
        n = 0
        search_from = 0
        while True:
            for m in re.finditer(r"<w:p(?: [^>]*)?>.*?</w:p>", self.xml[search_from:], re.S):
                frag = m.group(0)
                nodes = list(RE_WT.finditer(frag))
                if not nodes:
                    continue
                texts = [unesc(x.group(1)) for x in nodes]
                at = "".join(texts).find(find)
                if at < 0:
                    continue
                end = at + len(find)
                out, pos, off, done = [], 0, 0, False
                for node, t in zip(nodes, texts):
                    s, e = off, off + len(t)
                    off = e
                    out.append(frag[pos:node.start()])
                    pos = node.end()
                    if e <= at or s >= end:          # run untouched by the match
                        out.append(node.group(0))
                        continue
                    keep_pre = t[:max(0, at - s)]
                    keep_post = t[max(0, end - s):] if e > end else ""
                    body = keep_pre + ("" if done else new) + keep_post
                    done = True
                    out.append('<w:t xml:space="preserve">' + esc(body) + "</w:t>")
                out.append(frag[pos:])
                new_frag = "".join(out)
                start = search_from + m.start()
                self.xml = self.xml[:start] + new_frag + self.xml[search_from + m.end():]
                search_from = start + len(new_frag)
                n += 1
                break
            else:
                break
        self.log.append(f"OK   replace_inline '{find[:40]}' x{n}")
        if expect_count is not None and n != expect_count:
            raise AssertionError(f"'{find[:50]}': ocekivao {expect_count} zamjena, napravio {n}")
        return n

    def save(self):
        import xml.etree.ElementTree as ET
        ET.fromstring(self.xml)  # refuse to write malformed XML
        tmp = self.path + ".tmp"
        with zipfile.ZipFile(self.path) as src, \
             zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for e in src.infolist():
                data = self.xml.encode("utf-8") if e.filename == "word/document.xml" else src.read(e.filename)
                dst.writestr(e.filename, data)
        shutil.move(tmp, self.path)
