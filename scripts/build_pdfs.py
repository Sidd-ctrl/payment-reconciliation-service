#!/usr/bin/env python3
"""Render docs/*.md to premium navy/gold PDFs (code review, design note, README summary)."""

import pathlib
import sys

import markdown
from weasyprint import HTML

ROOT = pathlib.Path(__file__).resolve().parents[1]

CSS = """
@page {
  size: A4;
  margin: 17mm 15mm 19mm 15mm;
  background: #FFFFFF;
  @bottom-left  { content: "GHARANA HOME CO. — CONFIDENTIAL"; font-size: 6.5pt; letter-spacing: 1.5pt; color: #B08D2E; font-family: Georgia, serif; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font-size: 6.5pt; color: #0F1B33; font-family: Georgia, serif; }
  @top-right    { content: "PAYMENT RECONCILIATION"; font-size: 6.5pt; letter-spacing: 2pt; color: #8FA3C7; font-family: Georgia, serif; }
}
@page :first { margin-top: 20mm; }
* { box-sizing: border-box; }
body {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 9.6pt; line-height: 1.32; color: #1B2A4A;
}
h1 {
  font-size: 21pt; line-height: 1.2; color: #0F1B33;
  border-bottom: 2.6pt solid #D4AF37; padding-bottom: 6pt; margin: 0 0 12pt 0;
  letter-spacing: 0.3pt;
}
h2 {
  font-size: 12.5pt; color: #FFFFFF; background: #0F1B33;
  padding: 3pt 8pt; margin: 16pt 0 8pt 0; letter-spacing: 0.6pt;
  border-left: 6pt solid #D4AF37; page-break-after: avoid;
}
h3 { font-size: 10.5pt; color: #8A6B1D; margin: 12pt 0 5pt 0; page-break-after: avoid; }
p { margin: 5pt 0 7pt 0; text-align: justify; }
ul, ol { margin: 4pt 0 8pt 16pt; padding-left: 10pt; }
li { margin: 2.4pt 0; }
strong { color: #0F1B33; }
code {
  font-family: 'DejaVu Sans Mono', monospace; font-size: 8.2pt;
  background: #F4EFDF; color: #5A4A12; padding: 0.5pt 3pt; border-radius: 3pt;
}
pre {
  background: #0B1426; color: #E8D9A0; padding: 8pt 10pt; border-radius: 5pt;
  border-left: 4pt solid #D4AF37; font-size: 7.6pt; line-height: 1.28;
  overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; page-break-inside: auto;
}
pre code { background: transparent; color: inherit; padding: 0; font-size: 7.6pt; }
table { width: 100%; border-collapse: collapse; margin: 6pt 0 10pt 0; font-size: 8.6pt; page-break-inside: auto; }
th { background: #0F1B33; color: #F5E7BE; text-align: left; padding: 4pt 6pt; letter-spacing: 0.5pt; font-size: 7.8pt; text-transform: uppercase; }
td { border-bottom: 0.6pt solid #E3D9B8; padding: 3.5pt 6pt; }
tr:nth-child(even) td { background: #FBF8EC; }
tr { page-break-inside: avoid; }
blockquote {
  border-left: 4pt solid #D4AF37; background: #FBF8EC; margin: 8pt 0; padding: 6pt 10pt;
  color: #4A4030; font-style: italic;
}
hr { border: none; border-top: 0.8pt solid #D4AF37; margin: 14pt 0; }
"""

COMPACT_CSS = """
@page { size: A4; margin: 11mm 12mm 13mm 12mm;
  @bottom-left  { content: "GHARANA HOME CO. — CONFIDENTIAL"; font-size: 6pt; letter-spacing: 1.2pt; color: #B08D2E; font-family: Georgia, serif; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font-size: 6pt; color: #0F1B33; font-family: Georgia, serif; }
  @top-right    { content: "PRODUCTION DESIGN NOTE"; font-size: 6pt; letter-spacing: 1.5pt; color: #8FA3C7; font-family: Georgia, serif; } }
* { box-sizing: border-box; }
body { font-family: Georgia, serif; font-size: 8pt; line-height: 1.19; color: #1B2A4A; }
h1 { font-size: 15pt; color: #0F1B33; border-bottom: 2.4pt solid #D4AF37; padding-bottom: 4pt; margin: 0 0 8pt 0; }
h2 { font-size: 9.6pt; color: #FFFFFF; background: #0F1B33; padding: 1.6pt 7pt; margin: 8pt 0 4pt 0; border-left: 5pt solid #D4AF37; page-break-after: avoid; letter-spacing: 0.4pt; }
p { margin: 3pt 0 5pt 0; text-align: justify; }
ul, ol { margin: 2pt 0 6pt 14pt; padding-left: 8pt; }
li { margin: 1.6pt 0; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 6.9pt; background: #F4EFDF; padding: 0 3pt; border-radius: 3pt; }
pre { background: #0B1426; color: #E8D9A0; padding: 6pt 8pt; border-radius: 4pt; border-left: 3pt solid #D4AF37; font-size: 6.4pt; line-height: 1.2; white-space: pre-wrap; page-break-inside: avoid; }
table { width: 100%; border-collapse: collapse; margin: 4pt 0 6pt 0; font-size: 7.2pt; }
th { background: #0F1B33; color: #F5E7BE; text-align: left; padding: 3pt 5pt; font-size: 6.4pt; text-transform: uppercase; }
td { border-bottom: 0.5pt solid #E3D9B8; padding: 2.4pt 5pt; }
tr { page-break-inside: avoid; }
"""

def render(md_path: pathlib.Path, pdf_path: pathlib.Path, css: str):
    html_body = markdown.markdown(
        md_path.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
    )
    html = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{html_body}</body></html>"
    HTML(string=html, base_url=str(ROOT)).write_pdf(str(pdf_path))
    print(f"  {md_path.name} -> {pdf_path.name}")

if __name__ == "__main__":
    targets = sys.argv[1:] or ["docs/code-review.md", "docs/production-design-note.md", "docs/assumptions.md"]
    for target in targets:
        src = ROOT / target
        css = COMPACT_CSS if "design-note" in target else CSS
        render(src, src.with_suffix(".pdf"), css)
