"""Read PDF and Word (.docx) files.

A file that contains a sales table (Date, Product, Region, Total_Revenue)
becomes normal iRaaya data. Any other file is treated as a document whose
text iRaaya can answer questions about.
"""

import os
import re

import docx
import pandas as pd
import pdfplumber
from docx.table import Table
from docx.text.paragraph import Paragraph

from importer import looks_like_sales_table

DOCUMENT_TYPES = (".pdf", ".docx", ".txt")

# Groq's free plan allows ~8,000 tokens a minute, so documents longer than
# this are not sent whole: only the parts most relevant to each question
FULL_TEXT_LIMIT = 12000      # characters (~3,000 tokens)
CHUNK_SIZE = 1500
CHUNKS_PER_QUESTION = 4


def _clean_rows(table):
    return [[(c or "").strip() for c in row] for row in table if any((c or "").strip() for c in row)]


def find_sales_table(tables: list):
    """Combine the tables whose header looks like sales data (a date and a
    revenue/amount column). Tables that continue on the next page without
    a header are added too. Columns are standardised later by the importer."""
    header, rows = None, []
    for table in tables:
        table = _clean_rows(table)
        if not table:
            continue
        names = [str(c).strip() for c in table[0]]
        if looks_like_sales_table(names):
            if header is None:
                header = names
            if [n.lower() for n in names] == [h.lower() for h in header]:
                rows += table[1:]
        elif header is not None and len(table[0]) == len(header):
            rows += table          # continuation without a header row
    if header is None or not rows:
        return None
    return pd.DataFrame(rows, columns=header)


def _lines(page, tolerance: float = 3):
    """Words on a page grouped into lines (top to bottom)."""
    lines = []
    for w in sorted(page.extract_words(), key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) <= tolerance:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _header_columns(line):
    """Group header words into columns ('Units Sold' is one column).
    Returns [(name, x0, x1)] if the line has the required columns."""
    cols = []
    for w in line:
        if cols and w["x0"] - cols[-1][2] < 6:          # same phrase
            cols[-1] = (cols[-1][0] + " " + w["text"], cols[-1][1], w["x1"])
        else:
            cols.append((w["text"], w["x0"], w["x1"]))
    if looks_like_sales_table([c[0] for c in cols]):
        return cols
    return None


def _aligned_table(pdf):
    """Table made of aligned text without lines: every word below the
    header goes into the column it sits under (by its centre)."""
    header, bounds, rows = None, None, []
    for page in pdf.pages:
        for line in _lines(page):
            cols = _header_columns(line)
            if cols:
                if header is None:
                    header = [c[0] for c in cols]
                    # Boundaries halfway between neighbouring header columns
                    bounds = [(a[2] + b[1]) / 2 for a, b in zip(cols, cols[1:])]
                continue
            if header is None:
                continue
            cells = [[] for _ in header]
            for w in line:
                centre = (w["x0"] + w["x1"]) / 2
                idx = sum(centre > b for b in bounds)
                cells[idx].append(w["text"])
            row = [" ".join(c) for c in cells]
            if sum(bool(c) for c in row) >= len(header) - 1:   # skip titles/notes
                rows.append(row)
    return [[header] + rows] if header and rows else []


def _page_marker(n: int) -> str:
    return f"[Page {n}]"


def _read_pdf(file):
    tables, pages_text, found = [], [], []
    with pdfplumber.open(file) as pdf:
        n_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            page_tables = page.extract_tables() or []     # tables with lines
            tables += page_tables
            found += [{"page": i, "rows": _clean_rows(t)} for t in page_tables if len(_clean_rows(t)) >= 2]
            pages_text.append(f"{_page_marker(i)}\n{page.extract_text() or ''}")
        if find_sales_table(tables) is None:
            tables = _aligned_table(pdf)                  # tables without lines
    return tables, "\n\n".join(pages_text), n_pages, "pdf", found


RENDERED_BREAK = "<w:lastRenderedPageBreak"
HARD_BREAK = 'w:type="page"'


def _read_docx(file):
    """Word files don't store pages: Word lays them out when it opens the
    file. When saved by Word, the file records where each page started
    ("last rendered page break"); otherwise only manual page breaks
    (Ctrl+Enter) are known. Pages are counted from whichever exists."""
    d = docx.Document(file)
    body_xml = d.element.body.xml
    marker = RENDERED_BREAK if RENDERED_BREAK in body_xml else HARD_BREAK
    has_pages = marker in body_xml

    tables, parts, page, found = [], [_page_marker(1)] if has_pages else [], 1, []
    for block in d.iter_inner_content():          # paragraphs and tables, in order
        xml = block._element.xml
        breaks = xml.count(marker) if has_pages else 0
        if isinstance(block, Table):
            rows = [[cell.text for cell in row.cells] for row in block.rows]
            tables.append(rows)
            if len(_clean_rows(rows)) >= 2:
                found.append({"page": page if has_pages else None, "rows": _clean_rows(rows)})
            text = "\n".join(" | ".join(r) for r in rows)
            before = False
        else:
            text = block.text
            first_text = xml.find("<w:t")
            before = breaks and (first_text == -1 or xml.find(marker) < first_text)
        if before:                                 # page starts at this block
            for _ in range(breaks):
                page += 1
                parts.append(_page_marker(page))
            breaks = 0
        if text.strip():
            parts.append(text)
        for _ in range(breaks):                    # page starts inside/after it
            page += 1
            parts.append(_page_marker(page))
    source = (
        "word-layout" if marker == RENDERED_BREAK and has_pages
        else "manual-breaks" if has_pages else None
    )
    return tables, "\n".join(parts), (page if has_pages else None), source, found


def read_document(file) -> dict:
    """Returns {"kind": "table", "df": DataFrame} for a sales table, or
    {"kind": "document", "text": str, "pages": int|None}.
    Raises ValueError with a plain-words message if it can't be read."""
    name = getattr(file, "name", str(file))
    ext = os.path.splitext(name)[1].lower()
    try:
        if ext == ".pdf":
            tables, text, pages, page_source, found = _read_pdf(file)
        elif ext == ".docx":
            tables, text, pages, page_source, found = _read_docx(file)
        elif ext == ".txt":
            data = file.getvalue() if hasattr(file, "getvalue") else open(file, "rb").read()
            for enc in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    text = data.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            tables, pages, page_source, found = [], None, None, []
        else:
            raise ValueError(f"Unsupported document type '{ext}'.")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Could not read this file: {e}") from e

    df = find_sales_table(tables)
    if df is not None:
        return {"kind": "table", "df": df}
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) < 20:
        raise ValueError(
            "This file has no text iRaaya can read. If it's a scanned PDF (a photo "
            "of pages), iRaaya can't read it yet — please use a PDF with real text, "
            "or a Word or Excel file."
        )
    return {"kind": "document", "text": text, "pages": pages, "page_source": page_source,
            "tables": found}


PAGE_QUESTION = re.compile(
    r"(?:page|pg|p\.|पेज|पृष्ठ)\s*(?:no\.?|number|num|#|नंबर|संख्या)?\s*(\d{1,4})",
    re.IGNORECASE,
)


PAGE_SOURCES = {
    "pdf": "Page numbers are exact (from the PDF).",
    "word-layout": (
        "Page numbers come from the page layout Microsoft Word saved in this "
        "file. They match what Word showed when the file was last saved; "
        "another device, font or paper size can shift them."
    ),
    "manual-breaks": (
        "This file only records manual page breaks (Ctrl+Enter), so these "
        "'pages' may not match what you see in Word. For exact page numbers, "
        "save the file as PDF and upload that."
    ),
    None: (
        "This Word file does not record pages, so iRaaya can't tell what is "
        "on a given page. For page questions, save it as PDF and upload that."
    ),
}


def page_overview(text: str, words: int = 12) -> list:
    """[(page number, first words)] so users can match iRaaya's pages."""
    return [
        (n, " ".join(body.split()[:words]) + ("…" if len(body.split()) > words else ""))
        for n, body in _pages(text).items()
    ]


def _pages(text: str) -> dict:
    """{page number: text} from [Page N] markers."""
    found = re.split(r"\[Page (\d+)\]\n?", text)
    return {int(n): body.strip() for n, body in zip(found[1::2], found[2::2])}


def document_context(text: str, question: str = "") -> str:
    """The document text for the AI: whole if short, otherwise the parts
    that share the most words with the question (plus the beginning).
    Pages asked about by number ("page 5") are always included."""
    pages = _pages(text)
    asked = [int(n) for n in PAGE_QUESTION.findall(question)]
    notes = []
    if asked and not pages:
        notes.append(
            "NOTE: this file does not record page numbers (Word lays out "
            "pages only when it opens a file), so pages cannot be identified."
        )
    for n in asked:
        if pages and n not in pages:
            notes.append(f"NOTE: the document has {max(pages)} pages; page {n} does not exist.")
    note = ("\n".join(notes) + "\n\n") if notes else ""

    if len(text) <= FULL_TEXT_LIMIT:
        return note + text

    wanted = [f"{_page_marker(n)}\n{pages[n]}" for n in asked if n in pages]
    if wanted:
        return (
            note + f"(Long document: showing the page(s) asked about, "
            f"out of {max(pages)} pages.)\n\n" + "\n\n".join(wanted)[:FULL_TEXT_LIMIT]
        )
    chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    q_words = {w for w in re.findall(r"[a-z0-9]{3,}", question.lower())}
    scored = sorted(
        range(1, len(chunks)),
        key=lambda i: -len(q_words & set(re.findall(r"[a-z0-9]{3,}", chunks[i].lower()))),
    )
    keep = sorted([0] + scored[:CHUNKS_PER_QUESTION - 1])
    return note + (
        f"(Long document: showing {len(keep)} of {len(chunks)} parts, the "
        f"beginning and those most related to the question.)\n\n"
        + "\n\n[...]\n\n".join(chunks[i] for i in keep)
    )
