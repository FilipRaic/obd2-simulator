# .docx tooling

There is no Microsoft Word on the machine this project is built on, so every
`.docx` this project ships is written by editing `word/document.xml` inside the
zip archive directly. These are the tools that do it. They moved here from
`../Pisani dio/Slike za rad/alati/` on 15.08.2026., because generators belong
with the code and only generated files belong next to the document.

Their main subject is the device's technical documentation
(`../OBD2_Simulator_Dokumentacija/`), which is built from Markdown, but nothing
here is tied to one document - the target is an argument, so the same tools
serve the written documentation and the purchase lists.

| Script | What it does |
|---|---|
| `md2docx.py` | Rebuilds a `.docx` from a Markdown file, reusing an existing `.docx` as the style carrier. Supports only what these documents use: headings 1-3, paragraphs, bold, code, tables, block quotes, bullet and numbered lists |
| `docx_text_edit.py` | Replaces text inside `<w:t>` nodes one node at a time. Word splits a sentence across runs whenever formatting changes, so a plain search over `document.xml` misses half the targets |
| `docx_replace.py` | Literal replacements over the raw `document.xml`, for markup that spans nodes. Every pattern must match exactly once |
| `docx_table_edit.py` | Table cells by index `(table, row, cell)` instead of by text marker. The marker approach hits the first matching row, which is how a value aimed at table 6 once landed in table 2 |
| `docx-edit.ps1` | The older PowerShell helper, dot-sourced. It also handles images in `word/media/`, which the Python tools do not. **Save it as UTF-8 with BOM** - PowerShell 5.1 misreads BOM-less UTF-8 and corrupts the Croatian strings |
| `update_toc.py` | Refreshes the table of contents through LibreOffice (`officehelper`, UNO bridge) |

Two rules the hard way:

- Rebuild the zip in **Create** mode, never Update. .NET's Update mode leaves
  inconsistent local headers on entries copied from a streamed zip, and
  LibreOffice then refuses the file.
- A silent zero-match is how a document quietly keeps an old number, so the
  tools insist a pattern matches exactly once and write nothing otherwise.

The figure generator of the written documentation (`figgen`) is **not** here. It
draws Croatian figures that exist only for that document, so it stays in
`../Pisani dio/Slike za rad/alati/figgen/`.
