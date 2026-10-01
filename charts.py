"""Plotly charts for the iRaaya dashboard (dark theme).

Every chart takes the currency symbol and number style so labels read
naturally anywhere in the world (₹39.8L, $3.9M, 1.234 €...).
"""

import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from formatting import fmt_compact, fmt_money, plotly_separators

BG = "#1e293b"
PALETTE = ["#0ea5e9", "#10b981", "#818cf8", "#f59e0b", "#f472b6", "#94a3b8"]
ANOMALY_COLOR = "#ef4444"
HEIGHT = 450


def _nice_step(span: float) -> float:
    if span <= 0:
        return 1
    raw = span / 5
    power = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if m * power >= raw:
            return m * power
    return 10 * power


def money_ticks(low: float, high: float, symbol: str, style: str):
    """Axis ticks written the same way as the labels (₹10L, $2M, 1,5M €)."""
    low, high = min(0.0, low), max(high, 1.0)
    step = _nice_step(high - low)
    start = math.floor(low / step) * step
    vals = [start + i * step for i in range(int((high - start) / step) + 2)]
    return vals, [fmt_compact(v, symbol, style) if v else f"{symbol}0" for v in vals]


def _style(fig, symbol: str = "", style: str = "intl", y_title: str = "Revenue",
           money_axis: str = "y", low: float = 0, high: float = None, headroom: float = 1.12):
    fig.update_layout(
        plot_bgcolor=BG,
        paper_bgcolor=BG,
        height=HEIGHT,
        margin=dict(l=10, r=10, t=60, b=10),
        legend_title_text="",
        hoverlabel=dict(bgcolor="#0f172a"),
        separators=plotly_separators(style),
        title_font_size=17,
    )
    fig.update_xaxes(gridcolor="#334155")
    fig.update_yaxes(gridcolor="#334155")
    axis = fig.update_yaxes if money_axis == "y" else fig.update_xaxes
    if high is not None:
        vals, text = money_ticks(low, high * headroom, symbol, style)
        axis(tickvals=vals, ticktext=text, title_text=y_title,
             range=[min(0, low), high * headroom])
    else:
        axis(tickprefix=symbol, tickformat="~s", title_text=y_title)
    return fig


def _months(df: pd.DataFrame) -> pd.DataFrame:
    monthly = df.groupby(df.Date.dt.to_period("M")).Total_Revenue.sum().reset_index()
    monthly.columns = ["Month", "Revenue"]
    return monthly


def revenue_by_month(df: pd.DataFrame, anomaly_months: list = None,
                     symbol: str = "", style: str = "intl"):
    """Monthly revenue bars with value labels. Unusual months are red."""
    monthly = _months(df)
    anomaly_months = set(anomaly_months or [])
    monthly["Status"] = ["Unusual month" if str(m) in anomaly_months else "Normal" for m in monthly.Month]
    monthly["Label"] = [fmt_compact(v, symbol, style) for v in monthly.Revenue]
    monthly["Full"] = [fmt_money(v, symbol, style) for v in monthly.Revenue]
    monthly["Name"] = [m.strftime("%b %Y") for m in monthly.Month]
    monthly["Change"] = monthly.Revenue.pct_change().mul(100).map(
        lambda v: "" if pd.isna(v) else f"<br>{v:+.1f}% vs previous month")

    fig = px.bar(
        monthly, x="Name", y="Revenue", color="Status", text="Label",
        title="📅 Revenue by month",
        template="plotly_dark",
        color_discrete_map={"Normal": "#0ea5e9", "Unusual month": ANOMALY_COLOR},
        custom_data=["Full", "Change"],
    )
    fig.update_traces(
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>%{customdata[0]}%{customdata[1]}<extra></extra>",
    )
    fig.update_layout(showlegend=bool(anomaly_months))
    fig.update_xaxes(type="category", categoryorder="array",
                     categoryarray=list(monthly.Name), title_text="")
    return _style(fig, symbol, style, high=monthly.Revenue.max(), headroom=1.15)


def top_products(df: pd.DataFrame, symbol: str = "", style: str = "intl"):
    """Products by revenue, each labelled with its share of the total."""
    by_product = df.groupby("Product").Total_Revenue.sum().sort_values()
    total = by_product.sum()
    data = pd.DataFrame({
        "Product": by_product.index,
        "Revenue": by_product.values,
        "Label": [f"{fmt_compact(v, symbol, style)} · {v / total * 100:.0f}%" if total else ""
                  for v in by_product.values],
        "Full": [fmt_money(v, symbol, style) for v in by_product.values],
        "Share": [f"{v / total * 100:.1f}%" if total else "" for v in by_product.values],
    })
    fig = px.bar(
        data, x="Revenue", y="Product", orientation="h", text="Label",
        title="🏆 Products by revenue (share of total)",
        template="plotly_dark", color_discrete_sequence=["#10b981"],
        custom_data=["Full", "Share"],
    )
    fig.update_traces(
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br>%{customdata[1]} of total<extra></extra>",
    )
    # Extra room on the right so the longest label isn't cut off
    _style(fig, symbol, style, y_title="", money_axis="x",
           high=by_product.max() if len(by_product) else 0, headroom=1.35)
    fig.update_xaxes(title_text="Revenue")
    fig.update_yaxes(title_text="")
    return fig


def revenue_trend(df: pd.DataFrame, symbol: str = "", style: str = "intl"):
    """Revenue on each sales date, with a 30-day moving average."""
    daily = df.groupby("Date").Total_Revenue.sum().sort_index()
    average = daily.rolling("30D").mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily.index, y=daily.values, name="Revenue", mode="lines",
        line=dict(color="#38bdf8", width=1.5),
        customdata=[fmt_money(v, symbol, style) for v in daily.values],
        hovertemplate="%{x|%d %b %Y}<br>%{customdata}<extra>Revenue</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=average.index, y=average.values, name="30-day average", mode="lines",
        line=dict(color="#f59e0b", width=3),
        customdata=[fmt_money(v, symbol, style) for v in average.values],
        hovertemplate="%{x|%d %b %Y}<br>%{customdata}<extra>30-day average</extra>",
    ))
    fig.update_layout(title="📈 Revenue trend with 30-day average", template="plotly_dark",
                      legend=dict(orientation="h", y=1.08, x=1, xanchor="right"))
    fig.update_xaxes(title_text="")
    lo, hi = float(daily.min()) if len(daily) else 0, float(daily.max()) if len(daily) else 0
    _style(fig, symbol, style, high=hi, headroom=1.08)
    vals, text = money_ticks(0, hi * 1.08, symbol, style)
    fig.update_yaxes(tickvals=vals, ticktext=text, range=[max(0, lo * 0.85), hi * 1.08])
    return fig


def regional_performance(df: pd.DataFrame, symbol: str = "", style: str = "intl",
                         growth: dict = None):
    """Revenue per region, labelled with growth vs the previous period."""
    by_region = df.groupby("Region").Total_Revenue.sum().sort_values(ascending=False)
    growth = growth or {}

    def label(region, value):
        g = growth.get(region)
        return fmt_compact(value, symbol, style) + (f" ({g:+.0f}%)" if g is not None else "")

    data = pd.DataFrame({
        "Region": by_region.index,
        "Revenue": by_region.values,
        "Label": [label(r, v) for r, v in by_region.items()],
        "Full": [fmt_money(v, symbol, style) for v in by_region.values],
        "Growth": ["" if growth.get(r) is None else f"<br>{growth[r]:+.1f}% vs previous period"
                   for r in by_region.index],
    })
    fig = px.bar(
        data, x="Region", y="Revenue", color="Region", text="Label",
        title="🌍 Revenue by region" + (" (growth vs previous period)" if growth else ""),
        template="plotly_dark", color_discrete_sequence=PALETTE,
        custom_data=["Full", "Growth"],
    )
    fig.update_traces(
        textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{x}</b><br>%{customdata[0]}%{customdata[1]}<extra></extra>",
    )
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title_text="")
    return _style(fig, symbol, style, high=by_region.max() if len(by_region) else 0, headroom=1.15)


def product_comparison(df: pd.DataFrame, symbol: str = "", style: str = "intl"):
    """One line per product over time (easier to read than 100+ bars)."""
    monthly = df.groupby([df.Date.dt.to_period("M"), "Product"]).Total_Revenue.sum().reset_index()
    monthly.columns = ["Month", "Product", "Revenue"]
    months = sorted(monthly.Month.unique())
    monthly["Name"] = [m.strftime("%b %Y") for m in monthly.Month]
    monthly["Full"] = [fmt_money(v, symbol, style) for v in monthly.Revenue]
    fig = px.line(
        monthly.sort_values("Month"), x="Name", y="Revenue", color="Product", markers=True,
        title="📊 Products compared month by month",
        template="plotly_dark", color_discrete_sequence=PALETTE, custom_data=["Full"],
    )
    fig.update_traces(hovertemplate="<b>%{fullData.name}</b><br>%{x}<br>%{customdata[0]}<extra></extra>")
    fig.update_xaxes(type="category", categoryorder="array",
                     categoryarray=[m.strftime("%b %Y") for m in months], title_text="")
    return _style(fig, symbol, style, high=monthly.Revenue.max() if len(monthly) else 0, headroom=1.1)


def table_charts(rows: list, limit: int = 3) -> list:
    """Bar charts for any table (from a document or a spreadsheet): one
    chart per number column, so numbers on different scales (revenue vs
    % change) each stay readable. The first mostly-text column gives the
    labels; "$512,300", "+9%", "1.234,56" all count as numbers.
    Returns [] if the table has nothing to chart."""
    from importer import to_number

    if not rows or len(rows) < 3:
        return []
    header = [str(h).strip() or f"Column {i + 1}" for i, h in enumerate(rows[0])]
    body = [list(r) + [""] * (len(header) - len(r)) for r in rows[1:]]
    data = pd.DataFrame([r[:len(header)] for r in body], columns=header)
    numeric = {}
    for col in data.columns:
        values = to_number(data[col].astype(str))
        if values.notna().mean() >= 0.7:
            numeric[col] = values
    labels = [c for c in data.columns if c not in numeric]
    if not numeric or not labels or len(data) > 60:
        return []
    label = labels[0]
    figs = []
    for col in list(numeric)[:limit]:
        chart = pd.DataFrame({label: data[label].astype(str), col: numeric[col]}).dropna()
        if chart.empty:
            continue
        is_pct = data[col].astype(str).str.contains("%").mean() > 0.5
        def show(v):
            if is_pct:
                return f"{v:+,.4g}%"
            return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.4g}"
        chart["_text"] = chart[col].map(show)
        fig = px.bar(chart, x=label, y=col, text="_text", template="plotly_dark",
                     title=f"📊 {col} by {label}", color_discrete_sequence=[PALETTE[len(figs) % len(PALETTE)]])
        fig.update_traces(textposition="outside", cliponaxis=False)
        lo, hi = chart[col].min(), chart[col].max()
        fig.update_layout(plot_bgcolor=BG, paper_bgcolor=BG, height=380, showlegend=False,
                          margin=dict(l=10, r=10, t=60, b=10), yaxis_title="", xaxis_title="")
        fig.update_yaxes(gridcolor="#334155", range=[min(0, lo * 1.2), max(0, hi * 1.2) or 1])
        figs.append(fig)
    return figs
