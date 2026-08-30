# -*- coding: utf-8 -*-
"""Rebuild a .docx from a Markdown file, reusing an existing .docx as the
style carrier (styles.xml, numbering.xml, fonts, theme).

Only the constructs these purchase lists actually use are supported: headings
1 to 3, paragraphs, **bold**, `code`, tables, blockquotes and simple bullet
and numbered lists.

    python md2docx.py <in.md> <template_and_output.docx>
"""
import re
import shutil
import sys
import zipfile

md_path, docx_path = sys.argv[1], sys.argv[2]
lines = open(md_path, encoding="utf-8").read().split("\n")

BORDER = ('<w:tcBorders>'
          '<w:top w:val="single" w:sz="2" w:space="0" w:color="808080"/>'
          '<w:start w:val="single" w:sz="2" w:space="0" w:color="808080"/>'
          '<w:bottom w:val="single" w:sz="2" w:space="0" w:color="808080"/>'
          '<w:end w:val="single" w:sz="2" w:space="0" w:color="808080"/>'
          '</w:tcBorders>')


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def runs(text):
    """Inline markdown -> a list of <w:r>. Handles **bold**, `code`, [x](y)."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    out = []
    for part in re.split(r"(\*\*.+?\*\*|`[^`]+`)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            props, body = "<w:b/>", part[2:-2]
        elif part.startswith("`") and part.endswith("`"):
            props, body = '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>', part[1:-1]
        else:
            props, body = "", part
        out.append('<w:r><w:rPr>%s</w:rPr><w:t xml:space="preserve">%s</w:t></w:r>'
                   % (props, esc(body)))
    return "".join(out) or '<w:r><w:rPr></w:rPr><w:t/></w:r>'


def para(text, style="BodyText", extra=""):
    # An unknown w:pStyle inside a table cell makes LibreOffice drop the cell
    # content, so cells pass style=None and inherit the document default.
    ps = '<w:pStyle w:val="%s"/>' % style if style else ""
    return '<w:p><w:pPr>%s%s</w:pPr>%s</w:p>' % (ps, extra, runs(text))


def cell(text, header, width):
    shade = '<w:shd w:fill="EEEEEE" w:val="clear"/>' if header else ""
    body = ("**%s**" % text) if header and text and not text.startswith("**") else text
    return ('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s%s'
            '<w:vAlign w:val="center"/></w:tcPr>%s</w:tc>'
            % (width, BORDER, shade, para(body, None)))


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


body = []
i = 0
while i < len(lines):
    line = lines[i]
    s = line.strip()

    if not s:
        i += 1
        continue

    if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s):            # thematic break
        body.append(para("", "BodyText",
                         '<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1"'
                         ' w:color="808080"/></w:pBdr>'))
        i += 1
        continue

    if s.startswith("|"):                                   # table
        rows = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            rows.append(split_row(lines[i]))
            i += 1
        rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) or not c
                                           for c in r)]
        if not rows:
            continue
        ncol = max(len(r) for r in rows)
        width = 9070 // ncol
        xml = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
               '<w:tblW w:w="9070" w:type="dxa"/>'
               '<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>'
               + '<w:gridCol w:w="%d"/>' % width * ncol + '</w:tblGrid>']
        for n, r in enumerate(rows):
            r = r + [""] * (ncol - len(r))
            xml.append("<w:tr>" + "".join(cell(c, n == 0, width) for c in r) + "</w:tr>")
        xml.append("</w:tbl>")
        body.append("".join(xml))
        body.append(para(""))
        continue

    if s.startswith("#"):                                   # heading
        level = len(s) - len(s.lstrip("#"))
        body.append(para(s.lstrip("#").strip(), "Heading%d" % min(level, 3)))
        i += 1
        continue

    if s.startswith(">"):                                   # blockquote
        buf = []
        while i < len(lines) and lines[i].strip().startswith(">"):
            buf.append(lines[i].strip().lstrip(">").strip())
            i += 1
        body.append(para(" ".join(x for x in buf if x), "BodyText",
                         '<w:pBdr><w:left w:val="single" w:sz="12" w:space="8"'
                         ' w:color="808080"/></w:pBdr>'
                         '<w:ind w:left="454"/>'))
        continue

    m = re.match(r"^([-*]|\d+\.)\s+(.*)$", s)               # list item
    if m:
        num = 3 if m.group(1)[0].isdigit() else 1
        buf = [m.group(2)]
        i += 1
        while i < len(lines) and lines[i].startswith("  ") and lines[i].strip() \
                and not re.match(r"^\s*([-*]|\d+\.)\s", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        body.append(para(" ".join(buf), "BodyText",
                         '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="%d"/></w:numPr>'
                         '<w:ind w:hanging="283" w:left="709"/>' % num))
        continue

    buf = []                                                # plain paragraph
    while i < len(lines) and lines[i].strip() and not re.match(
            r"^\s*(\||#|>|[-*]\s|\d+\.\s)", lines[i]):
        buf.append(lines[i].strip())
        i += 1
    body.append(para(" ".join(buf)))

doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
       '<w:body>' + "".join(body) +
       '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
       '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"'
       ' w:header="0" w:footer="0" w:gutter="0"/></w:sectPr>'
       '</w:body></w:document>')

zin = zipfile.ZipFile(docx_path)
parts = {n: zin.read(n) for n in zin.namelist()}
zin.close()
parts["word/document.xml"] = doc.encode("utf-8")

shutil.copy2(docx_path, docx_path + ".bak")
zout = zipfile.ZipFile(docx_path, "w", zipfile.ZIP_DEFLATED)
for name, data in parts.items():
    zout.writestr(name, data)
zout.close()
print("rebuilt %s from %s (%d blocks)" % (docx_path, md_path, len(body)))
