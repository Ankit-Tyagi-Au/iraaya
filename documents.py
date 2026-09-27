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

from analyser import REQUIRED_COLUMNS

DOCUMENT_TYPES = (".pdf", ".docx")

# Groq's free plan allows ~8,000 tokens a minute, so documents longer than
# this are not sent whole: only the parts most relevant to each question
FULL_TEXT_LIMIT = 12000      # characters (~3,000 tokens)
CHUNK_SIZE = 1500
CHUNKS_PER_QUESTION = 4


def _column_name(text) -> str:
    """'Total Revenue ' -> 'Total_Revenue' so headers match our columns."""
    return re.sub(r"\s+", "_", str(text or "").strip()).replace("-", "_")


def _clean_rows(table):
    return [[(c or "").strip() for c in row] for row in table if any((c or "").strip() for c in row)]


def find_sales_table(tables: list):
    """Combine the tables whose header has the required columns. Tables that
    continue on the next page without a header are added too."""
    wanted = {c.lower() for c in REQUIRED_COLUMNS}
    header, rows = None, []
    for table in tables:
        table = _clean_rows(table)
        if not table:
            continue
        names = [_column_name(c) for c in table[0]]
        if wanted <= {n.lower() for n in names}:
            if header is None:
                header = names
            if [n.lower() for n in names] == [h.lower() for h in header]:
                rows += table[1:]
        elif header is not None and len(table[0]) == len(header):
            rows += table          # continuation without a header row
    if header is None or not rows:
        return None
    df = pd.DataFrame(rows, columns=header)
    # Match our exact column spelling (e.g. 'total_revenue' -> 'Total_Revenue')
    canonical = {c.lower(): c for c in REQUIRED_COLUMNS}
    return df.rename(columns={c: canonical.get(c.lower(), c) for c in df.columns})


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
    names = {_column_name(c[0]).lower() for c in cols}
    if {c.lower() for c in REQUIRED_COLUMNS} <= names:
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


def _read_pdf(file):
    tables, pages_text = [], []
    with pdfplumber.open(file) as pdf:
        n_pages = len(pdf.pages)
        for page in pdf.pages:
            tables += page.extract_tables() or []        # tables with lines
            pages_text.append(page.extract_text() or "")
        if find_sales_table(tables) is None:
            tables = _aligned_table(pdf)                  # tables without lines
    return tables, "\n\n".join(t for t in pages_text if t.strip()), n_pages


def _read_docx(file):
    d = docx.Document(file)
    tables = [[[cell.text for cell in row.cells] for row in t.rows] for t in d.tables]
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t in tables:          # keep table text readable in document mode too
        parts += [" | ".join(r) for r in t]
    return tables, "\n".join(parts), None


def read_document(file) -> dict:
    """Returns {"kind": "table", "df": DataFrame} for a sales table, or
    {"kind": "document", "text": str, "pages": int|None}.
    Raises ValueError with a plain-words message if it can't be read."""
    name = getattr(file, "name", str(file))
    ext = os.path.splitext(name)[1].lower()
    try:
        if ext == ".pdf":
            tables, text, pages = _read_pdf(file)
        elif ext == ".docx":
            tables, text, pages = _read_docx(file)
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
            "No readable text found. If this is a scanned PDF (a photo of "
            "pages), iRaaya can't read it yet — please upload a PDF with "
            "real text, or a Word or Excel file."
        )
    return {"kind": "document", "text": text, "pages": pages}


def document_context(text: str, question: str = "") -> str:
    """The document text for the AI: whole if short, otherwise the parts
    that share the most words with the question (plus the beginning)."""
    if len(text) <= FULL_TEXT_LIMIT:
        return text
    chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    q_words = {w for w in re.findall(r"[a-z0-9]{3,}", question.lower())}
    scored = sorted(
        range(1, len(chunks)),
        key=lambda i: -len(q_words & set(re.findall(r"[a-z0-9]{3,}", chunks[i].lower()))),
    )
    keep = sorted([0] + scored[:CHUNKS_PER_QUESTION - 1])
    return (
        f"(Long document: showing {len(keep)} of {len(chunks)} parts, the "
        f"beginning and those most related to the question.)\n\n"
        + "\n\n[...]\n\n".join(chunks[i] for i in keep)
    )
