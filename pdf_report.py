"""PDF exports: the business report and the conversation (ReportLab).

Fonts: a Unicode font (DejaVu Sans on the server, Arial Unicode on a Mac)
covers Latin, Greek, Vietnamese and more; Chinese, Japanese and Korean use
ReportLab's built-in CID fonts. Scripts that need letter shaping (Hindi,
Arabic...) can't be drawn correctly by ReportLab, so those texts are left
out with a note — the conversation can still be saved as a text file.
"""

import io
import os
import re
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from formatting import CURRENCIES, fmt_compact, fmt_money

BRAND = colors.HexColor("#0ea5e9")
INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#cbd5e1")
INSIGHT_COLORS = {
    "positive": colors.HexColor("#059669"),
    "warning": colors.HexColor("#dc2626"),
    "tip": colors.HexColor("#0284c7"),
}

# ---------- fonts ----------

UNICODE_FONT_FILES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",          # Streamlit Cloud (packages.txt)
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",     # macOS
    "/Library/Fonts/Arial Unicode.ttf",
]
CJK_FONTS = {"zh": "STSong-Light", "ja": "HeiseiMin-W3", "ko": "HYSMyeongJo-Medium"}
_SHAPED_SCRIPTS = re.compile(r"[֐-ࣿऀ-෿฀-๿က-႟]")  # Hebrew..Arabic, Indic, Thai, Myanmar
_CJK = {
    "zh": re.compile(r"[一-鿿㐀-䶿]"),
    "ja": re.compile(r"[぀-ヿ]"),
    "ko": re.compile(r"[가-힯ᄀ-ᇿ]"),
}


def _unicode_font() -> str:
    for path in UNICODE_FONT_FILES:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("iRaayaUnicode", path))
                return "iRaayaUnicode"
            except Exception:
                continue
    return "Helvetica"


UNICODE = _unicode_font()
LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")
try:
    _GLYPHS = set(pdfmetrics.getFont(UNICODE).face.charToGlyph)
except Exception:
    _GLYPHS = None      # built-in font: covered by the cp1252 check

# Currency symbols a font may lack (₹ is newer than many fonts) -> ISO code
_SYMBOL_CODES = {}
for _label, _c in CURRENCIES.items():
    if _c:
        _code = _c[1].rsplit("(", 1)[-1].rstrip(")") if "(" in _c[1] else _label.split()[0]
        for _ch in _c[0].strip():
            if ord(_ch) > 127:
                _SYMBOL_CODES.setdefault(_ch, _code + " ")


def _safe(text: str) -> str:
    """Replace currency signs the font can't draw with their code (₹ -> INR)."""
    text = str(text or "")
    if _GLYPHS is None:
        return text
    return "".join(_SYMBOL_CODES[ch] if ch in _SYMBOL_CODES and ord(ch) not in _GLYPHS else ch
                   for ch in text)


for _name in CJK_FONTS.values():
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(_name))
    except Exception:
        pass


def font_for(text: str) -> str | None:
    """Font that can draw this text, or None if the PDF can't show it."""
    text = str(text or "")
    if _SHAPED_SCRIPTS.search(text):
        return None
    for lang in ("ja", "ko", "zh"):          # Japanese kana before shared Han
        if _CJK[lang].search(text):
            return CJK_FONTS[lang]
    if UNICODE == "Helvetica":
        try:
            text.encode("cp1252")
        except UnicodeEncodeError:
            return None
    return UNICODE


def _p(text, style, font=None) -> Paragraph:
    font = font or font_for(text) or style.fontName
    if font == UNICODE:
        text = _safe(text)
    s = ParagraphStyle(f"{style.name}-{font}", parent=style, fontName=font)
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), s)


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontName=UNICODE, fontSize=22,
                                textColor=INK, alignment=0, spaceAfter=2),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=UNICODE, fontSize=13,
                             textColor=INK, spaceBefore=10, spaceAfter=5),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName=UNICODE, fontSize=11,
                             spaceBefore=5, spaceAfter=2),
        "body": ParagraphStyle("b", parent=base["Normal"], fontName=UNICODE, fontSize=9.5,
                               leading=13, spaceAfter=3),
        "muted": ParagraphStyle("m", parent=base["Normal"], fontName=UNICODE, fontSize=8.5,
                                leading=11, textColor=MUTED),
        "white": ParagraphStyle("w", parent=base["Normal"], fontName=UNICODE, fontSize=9.5,
                                textColor=colors.white),
    }


def _month_name(period, short: bool = False) -> str:
    """'2025-06' -> 'June 2025' (or 'Jun 25')."""
    try:
        return datetime.strptime(str(period), "%Y-%m").strftime("%b %y" if short else "%B %Y")
    except ValueError:
        return str(period)


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(15 * mm, 12 * mm, A4[0] - 15 * mm, 12 * mm)
    canvas.setFont(UNICODE, 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(15 * mm, 8 * mm, "Powered by iRaaya · Built by Riverrax · riverrax.com")
    canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _doc(buffer, title):
    return SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=18 * mm, title=title, author="iRaaya by Riverrax",
    )


def _stamp(company: str, subtitle: str, lines: list, S) -> Table:
    """Company 'stamp' header: bordered box with name, report type, details."""
    logo = Image(LOGO, width=20 * mm, height=20 * mm) if os.path.exists(LOGO) else ""
    rows = [[_p(company or "My Business", S["title"]), logo], [_p(subtitle, S["h3"]), ""]]
    rows += [[_p(line, S["muted"]), ""] for line in lines]
    t = Table(rows, colWidths=[155 * mm, 25 * mm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.5, BRAND),
        ("LINEBELOW", (0, 1), (-1, 1), 0.5, LINE),
        ("SPAN", (1, 0), (1, 1)),
        ("VALIGN", (1, 0), (1, 1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#f0f9ff")),
    ]))
    return t


def _table(rows, widths, S, header_color=BRAND):
    head = [[_p(c, S["white"]) for c in rows[0]]]
    body = [[_p(c, S["body"]) for c in r] for r in rows[1:]]
    t = Table(head + body, colWidths=widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _bar_chart(title, labels, values, symbol, style, horizontal=False, highlight=None):
    """A simple chart drawn by ReportLab itself (no browser needed)."""
    d = Drawing(180 * mm, 70 * mm)
    d.add(String(0, 66 * mm, title, fontName=UNICODE, fontSize=10, fillColor=INK))
    chart = HorizontalBarChart() if horizontal else VerticalBarChart()
    chart.x, chart.y = (38 * mm, 8 * mm) if horizontal else (16 * mm, 14 * mm)
    chart.width = 180 * mm - chart.x - 6 * mm
    chart.height = 50 * mm if horizontal else 46 * mm
    chart.data = [list(values)]
    chart.categoryAxis.categoryNames = [str(l)[:18] for l in labels]
    chart.categoryAxis.labels.fontName = UNICODE
    chart.categoryAxis.labels.fontSize = 6.5
    if not horizontal:
        chart.categoryAxis.labels.angle = 45
        chart.categoryAxis.labels.boxAnchor = "ne"
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontName = UNICODE
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labelTextFormat = lambda v: _safe(fmt_compact(v, symbol, style))
    chart.bars[0].fillColor = BRAND
    chart.bars[0].strokeColor = None
    for i in (highlight or []):
        chart.bars[(0, i)].fillColor = colors.HexColor("#ef4444")
    d.add(chart)
    return d


def generate_pdf(
    summary: dict,
    insights: list,
    forecast: dict,
    company_name: str = "My Business",
    health: dict = None,
    anomalies: list = None,
    symbol: str = "",
    style: str = "intl",
    cards: dict = None,
    filters_text: str = "",
    monthly: dict = None,
    products: dict = None,
) -> bytes:
    """The business report. monthly/products: {label: revenue} for the charts."""
    S = _styles()
    money = lambda v: fmt_money(v, symbol, style)
    buffer = io.BytesIO()
    story = [_stamp(
        company_name, "Business Intelligence Report",
        [f"Data period: {summary.get('date_range', 'N/A')}",
         f"Filters: {filters_text}" if filters_text else "Filters: none (all data)",
         f"Generated: {datetime.now().strftime('%d %B %Y')}"], S),
        Spacer(1, 6 * mm)]

    story.append(_p("Key Metrics", S["h2"]))
    c = cards or {}
    pct = lambda v: "" if v is None else f" ({v:+.1f}% vs previous period)"
    rows = [["Metric", "Value"],
            ["Total revenue", money(c.get("total", summary.get("total_revenue"))) + pct(c.get("total_change"))],
            ["Average monthly revenue", money(c.get("avg_monthly", 0)) + pct(c.get("avg_monthly_change"))]]
    mom = c.get("mom")
    if mom and mom.get("pct") is not None:
        rows.append(["Month over month", f"{mom['pct']:+.1f}% ({mom['label']})"])
    rows += [["Best month", _month_name(summary.get("best_month", "N/A"))],
             ["Best product", str(summary.get("best_product", "N/A"))],
             ["Lowest product", str(summary.get("worst_product", "N/A"))],
             ["Best region", str(summary.get("best_region", "N/A"))],
             ["Transactions", f"{c.get('transactions', summary.get('total_transactions', 0)):,}" + pct(c.get("transactions_change"))]]
    if health:
        rows.append(["iRaaya health score", f"{health['score']}/100 ({health['label']})"])
    story += [_table(rows, [65 * mm, 115 * mm], S), Spacer(1, 4 * mm)]

    if monthly:
        flagged = {a["month"] for a in (anomalies or [])}
        keys = [str(k) for k in monthly]
        story.append(_bar_chart("Revenue by month (red = unusual month)",
                                [_month_name(k, short=True) for k in keys], list(monthly.values()),
                                symbol, style, highlight=[i for i, k in enumerate(keys) if k in flagged]))
    if products:
        items = sorted(products.items(), key=lambda kv: kv[1])[-10:]
        story.append(_bar_chart("Top products by revenue", [k for k, _ in items],
                                [v for _, v in items], symbol, style, horizontal=True))

    if anomalies:
        story.append(_p("Unusual Months", S["h2"]))
        for a in anomalies:
            direction = "above" if a["type"] == "high" else "below"
            story.append(_p(f"{a['month']}: revenue {money(a['revenue'])}, "
                            f"{abs(a['difference_pct'])}% {direction} the expected {money(a['expected'])}", S["body"]))

    if insights:
        story.append(_p("iRaaya Insights", S["h2"]))
        printable = [i for i in insights if font_for(i.get("title")) and font_for(i.get("detail"))]
        if len(printable) < len(insights):
            story.append(_p("Some insights are in a script this PDF can't display (for example "
                            "Hindi or Arabic). Generate them in English to include them here.", S["muted"]))
        for n, ins in enumerate(printable, 1):
            h = ParagraphStyle(f"ins{n}", parent=S["h3"],
                               textColor=INSIGHT_COLORS.get(ins.get("type"), INSIGHT_COLORS["tip"]))
            story.append(KeepTogether([_p(f"{n}. {ins.get('title', '')}", h), _p(ins.get("detail", ""), S["body"])]))

    if forecast:
        story.append(_p("Revenue Forecast", S["h2"]))
        story.append(_p(f"Business trend: {forecast.get('trend', 'stable')} "
                        f"({forecast.get('monthly_change_pct', 0):+}% per month). "
                        f"Trend fit: {forecast.get('fit_pct', 0)}%.", S["body"]))
        rows = [["Month", "Forecast", "Likely range"]] + [
            [f["date"], money(f["predicted_revenue"]), f"{money(f['low'])} – {money(f['high'])}"]
            for f in forecast.get("forecast", [])]
        story += [_table(rows, [40 * mm, 50 * mm, 90 * mm], S, colors.HexColor("#10b981")), Spacer(1, 2 * mm)]
        story.append(_p("Trend fit shows how closely past months follow a straight line (100% = "
                        "perfectly). The forecast follows the overall trend and does not include "
                        "seasonal peaks.", S["muted"]))
        if forecast.get("excluded_months"):
            story.append(_p(f"Unusual months left out of the trend: {', '.join(forecast['excluded_months'])}", S["muted"]))

    if health and health.get("factors"):
        story.append(_p("What affects the health score", S["h2"]))
        story += [_p(f"• {f}", S["body"]) for f in health["factors"]]

    _doc(buffer, "iRaaya Business Report").build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def conversation_text(messages: list, company: str = "") -> str:
    """The conversation as plain text (works in every language)."""
    lines = [f"iRaaya conversation{' — ' + company if company else ''}",
             f"Saved {datetime.now().strftime('%d %B %Y %H:%M')}", ""]
    for m in messages:
        who = "You" if m["role"] == "user" else "iRaaya"
        lines += [f"[{m.get('time', '')}] {who}:", m["content"], ""]
    lines.append("Powered by iRaaya · Built by Riverrax · riverrax.com")
    return "\n".join(lines)


def generate_conversation_pdf(messages: list, company: str = "") -> tuple:
    """Returns (pdf_bytes, skipped_count). Messages in a script the PDF
    can't draw are replaced by a note (use the text file for those)."""
    S = _styles()
    buffer = io.BytesIO()
    story = [_stamp(company or "iRaaya", "Conversation with iRaaya",
                    [f"Saved {datetime.now().strftime('%d %B %Y %H:%M')}"], S), Spacer(1, 5 * mm)]
    skipped = 0
    for m in messages:
        who, color = ("You", colors.HexColor("#1e3a8a")) if m["role"] == "user" else ("iRaaya", colors.HexColor("#065f46"))
        head = ParagraphStyle(f"who-{who}", parent=S["h3"], textColor=color)
        story.append(_p(f"{who}  ·  {m.get('time', '')}", head, UNICODE))
        font = font_for(m["content"])
        if font:
            story.append(_p(m["content"], S["body"], font))
        else:
            skipped += 1
            story.append(_p("(This message is in a script the PDF can't display — "
                            "see the text file download.)", S["muted"]))
    _doc(buffer, "iRaaya conversation").build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue(), skipped
