"""One-page PDF business report (ReportLab)."""

import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle
)
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable
)

BRAND = colors.HexColor("#0ea5e9")
INSIGHT_COLORS = {
    "positive": colors.HexColor("#059669"),
    "warning": colors.HexColor("#d97706"),
    "tip": colors.HexColor("#0284c7"),
}


def _money(value) -> str:
    try:
        return f"{float(value):,.0f}"
    except (TypeError, ValueError):
        return "N/A"


def _latin_only(text: str) -> bool:
    """The built-in PDF fonts only cover Western European characters."""
    try:
        str(text).encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def _p(text, style) -> Paragraph:
    # Escape &, < and > so AI-written text can't break ReportLab's markup
    return Paragraph(escape(str(text)), style)


def generate_pdf(
    summary: dict,
    insights: list,
    forecast: dict,
    company_name: str = "My Business",
    health: dict = None,
    anomalies: list = None
) -> bytes:

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=15*mm,
        bottomMargin=15*mm,
        title="iRaaya Business Report",
        author="iRaaya by Riverrax",
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontSize=24,
        textColor=BRAND,
        spaceAfter=6
    )

    h2_style = ParagraphStyle(
        "h2",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor(
            "#0f172a"
        ),
        spaceBefore=12,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        "body",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=4
    )

    muted_style = ParagraphStyle(
        "muted",
        parent=body_style,
        textColor=colors.HexColor("#64748b"),
        fontSize=9,
    )

    story = []

    story.append(
        Paragraph("iRaaya", title_style)
    )
    story.append(
        Paragraph(
            "Business Intelligence Report",
            styles["Heading2"]
        )
    )
    story.append(_p(f"Company: {company_name}", body_style))
    story.append(_p(f"Data period: {summary.get('date_range', 'N/A')}", body_style))
    story.append(
        _p(
            f"Generated: "
            f"{datetime.now().strftime('%d %B %Y')}",
            body_style
        )
    )
    story.append(
        HRFlowable(width="100%", color=BRAND)
    )
    story.append(Spacer(1, 6*mm))

    story.append(
        Paragraph(
            "Key Metrics",
            h2_style
        )
    )

    metrics_data = [
        ["Metric", "Value"],
        ["Total Revenue", _money(summary.get("total_revenue"))],
        ["Best Month", str(summary.get("best_month", "N/A"))],
        ["Best Product", str(summary.get("best_product", "N/A"))],
        ["Lowest Product", str(summary.get("worst_product", "N/A"))],
        ["Best Region", str(summary.get("best_region", "N/A"))],
        ["Total Transactions", f"{summary.get('total_transactions', 0):,}"],
    ]
    if health:
        metrics_data.append(
            ["iRaaya Health Score", f"{health['score']}/100 ({health['label']})"]
        )

    header_style = ParagraphStyle(
        "header", parent=body_style,
        textColor=colors.white, fontName="Helvetica-Bold",
    )
    metrics_table = Table(
        [[_p(c, header_style) for c in metrics_data[0]]]
        + [[_p(c, body_style) for c in row] for row in metrics_data[1:]],
        colWidths=[80*mm, 100*mm]
    )
    metrics_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f1f5f9")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("PADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(metrics_table)
    story.append(Spacer(1, 4*mm))

    if anomalies:
        story.append(Paragraph("Unusual Months", h2_style))
        for a in anomalies:
            direction = "above" if a["type"] == "high" else "below"
            story.append(_p(
                f"{a['month']}: revenue {_money(a['revenue'])}, "
                f"{abs(a['difference_pct'])}% {direction} the expected "
                f"{_money(a['expected'])}",
                body_style
            ))

    if insights:
        story.append(
            Paragraph(
                "iRaaya Insights",
                h2_style
            )
        )
        printable = [
            i for i in insights
            if _latin_only(i.get("title", "")) and _latin_only(i.get("detail", ""))
        ]
        if not printable:
            story.append(_p(
                "Insights were generated in a language this PDF cannot "
                "display. Generate them in English to include them here.",
                muted_style
            ))
        for i, insight in enumerate(printable, 1):
            color = INSIGHT_COLORS.get(insight.get("type"), INSIGHT_COLORS["tip"])
            heading = ParagraphStyle(
                f"ins{i}", parent=styles["Heading3"], textColor=color,
                spaceBefore=6, spaceAfter=2,
            )
            story.append(_p(f"{i}. {insight.get('title', '')}", heading))
            story.append(_p(insight.get("detail", ""), body_style))

    if forecast:
        story.append(
            Paragraph(
                "Revenue Forecast",
                h2_style
            )
        )
        story.append(_p(
            f"Business trend: {forecast.get('trend', 'stable')} "
            f"({forecast.get('monthly_change_pct', 0):+}% per month)",
            body_style
        ))

        fc_rows = [["Month", "Forecast", "Likely range"]] + [
            [f["date"], _money(f["predicted_revenue"]),
             f"{_money(f['low'])} - {_money(f['high'])}"]
            for f in forecast.get("forecast", [])
        ]
        fc_table = Table(fc_rows, colWidths=[40*mm, 50*mm, 90*mm])
        fc_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10b981")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(fc_table)
        story.append(Spacer(1, 2*mm))
        story.append(_p(
            f"Trend fit: {forecast.get('fit_pct', 0)}% of month-to-month "
            "variation is explained by the trend line. The forecast follows "
            "the overall trend and does not include seasonal peaks.",
            muted_style
        ))
        excluded = forecast.get("excluded_months") or []
        if excluded:
            story.append(_p(
                f"Unusual months left out of the trend: {', '.join(excluded)}",
                muted_style
            ))

    story.append(Spacer(1, 10*mm))
    story.append(
        HRFlowable(width="100%", color=colors.HexColor("#cbd5e1"))
    )
    story.append(
        Paragraph(
            "Powered by iRaaya · "
            "Built by Riverrax · "
            "riverrax.com",
            muted_style
        )
    )

    doc.build(story)
    return buffer.getvalue()
