"""Plotly charts for the iRaaya dashboard (dark theme)."""

import pandas as pd
import plotly.express as px

BG = "#1e293b"
PALETTE = ["#0ea5e9", "#10b981", "#818cf8", "#f59e0b", "#f472b6", "#94a3b8"]
ANOMALY_COLOR = "#ef4444"


def _style(fig, y_title: str = "Revenue"):
    fig.update_layout(
        plot_bgcolor=BG,
        paper_bgcolor=BG,
        margin=dict(l=10, r=10, t=50, b=10),
        legend_title_text="",
        hoverlabel=dict(bgcolor="#0f172a"),
    )
    fig.update_yaxes(title_text=y_title, tickformat=",.0f", gridcolor="#334155")
    fig.update_xaxes(gridcolor="#334155")
    return fig


def revenue_by_month(
    df: pd.DataFrame,
    anomaly_months: list = None
):
    """Monthly revenue bars. Months in anomaly_months are shown in red."""
    monthly = df.groupby(
        df.Date.dt.to_period("M")
    ).Total_Revenue.sum().reset_index()
    monthly.columns = ["Month", "Revenue"]
    monthly["Month"] = monthly[
        "Month"
    ].astype(str)

    anomaly_months = set(anomaly_months or [])
    monthly["Status"] = [
        "Unusual month" if m in anomaly_months else "Normal"
        for m in monthly.Month
    ]

    fig = px.bar(
        monthly,
        x="Month",
        y="Revenue",
        color="Status",
        title="Revenue by Month",
        template="plotly_dark",
        color_discrete_map={
            "Normal": "#0ea5e9",
            "Unusual month": ANOMALY_COLOR,
        },
    )
    fig.update_traces(hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>")
    fig.update_layout(showlegend=bool(anomaly_months))
    # Keep months in date order (colour groups would otherwise be split)
    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=list(monthly.Month),
        title_text="",
    )
    return _style(fig)


def top_products(
    df: pd.DataFrame
):
    by_product = df.groupby(
        "Product"
    ).Total_Revenue.sum().reset_index()
    by_product.columns = [
        "Product", "Revenue"
    ]
    by_product = by_product.sort_values(
        "Revenue"
    )

    fig = px.bar(
        by_product,
        x="Revenue",
        y="Product",
        orientation="h",
        title="Top Products by Revenue",
        template="plotly_dark",
        color_discrete_sequence=["#10b981"],
    )
    fig.update_traces(hovertemplate="%{y}<br>%{x:,.0f}<extra></extra>")
    _style(fig, y_title="")
    fig.update_xaxes(title_text="Revenue", tickformat=",.0f")
    return fig


def revenue_trend(
    df: pd.DataFrame
):
    daily = df.groupby(
        "Date"
    ).Total_Revenue.sum().reset_index()

    fig = px.line(
        daily,
        x="Date",
        y="Total_Revenue",
        title="Revenue Trend",
        template="plotly_dark",
        color_discrete_sequence=["#38bdf8"],
    )
    fig.update_traces(hovertemplate="%{x|%d %b %Y}<br>%{y:,.0f}<extra></extra>")
    fig.update_xaxes(title_text="")
    return _style(fig)


def regional_performance(
    df: pd.DataFrame
):
    by_region = df.groupby(
        "Region"
    ).Total_Revenue.sum().reset_index()
    by_region.columns = [
        "Region", "Revenue"
    ]
    by_region = by_region.sort_values("Revenue", ascending=False)

    fig = px.bar(
        by_region,
        x="Region",
        y="Revenue",
        title="Revenue by Region",
        template="plotly_dark",
        color="Region",
        color_discrete_sequence=PALETTE,
    )
    fig.update_traces(hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>")
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title_text="")
    return _style(fig)


def product_comparison(
    df: pd.DataFrame
):
    """One line per product over time.

    Lines instead of grouped bars: with 18 months x 6 products,
    grouped bars become 100+ thin bars that are hard to read.
    """
    monthly_product = df.groupby([
        df.Date.dt.to_period("M"),
        "Product"
    ]).Total_Revenue.sum().reset_index()
    monthly_product.columns = [
        "Month", "Product", "Revenue"
    ]
    monthly_product["Month"] = (
        monthly_product["Month"].astype(str)
    )

    fig = px.line(
        monthly_product,
        x="Month",
        y="Revenue",
        color="Product",
        markers=True,
        title="Product Comparison by Month",
        template="plotly_dark",
        color_discrete_sequence=PALETTE,
    )
    fig.update_traces(hovertemplate="%{fullData.name}<br>%{x}<br>%{y:,.0f}<extra></extra>")
    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=sorted(monthly_product.Month.unique()),
        title_text="",
    )
    return _style(fig)
