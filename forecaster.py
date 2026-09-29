"""Simple, honest revenue forecast: a straight-line trend over monthly revenue.

What it does and does not do:
- Fits a straight line through monthly revenue (scikit-learn LinearRegression)
- Leaves out unusual months (e.g. a one-off crash) so they do not drag the line
- Gives a likely range (low to high) based on how far past months
  typically sat from the line
- Does NOT model seasonality: with under 2 years of data a seasonal
  pattern cannot be estimated reliably
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression

from formatting import fmt_money, plotly_separators

from analyser import detect_anomalies

MIN_MONTHS = 3
FORECAST_MONTHS = 3
# Monthly slope as a share of average revenue that counts as a real trend
TREND_THRESHOLD = 0.01


def forecast_revenue(
    df: pd.DataFrame
) -> dict:
    """Forecast the next 3 months. Returns None if there is too little data."""

    monthly = df.groupby(
        df.Date.dt.to_period("M")
    ).Total_Revenue.sum().reset_index()
    monthly.columns = ["Period", "Revenue"]

    if len(monthly) < MIN_MONTHS:
        return None

    anomaly_months = {a["month"] for a in detect_anomalies(df)}
    is_normal = ~monthly.Period.astype(str).isin(anomaly_months)
    fit_data = monthly[is_normal]

    X_all = np.arange(len(monthly)).reshape(-1, 1)
    X = X_all[is_normal.values]
    y = fit_data.Revenue.values

    model = LinearRegression()
    model.fit(X, y)

    # How well the straight line fits past months (R squared, 0-100%)
    fit_pct = round(
        max(0.0, min(100.0, model.score(X, y) * 100)), 1
    )

    # Likely range: about 95% of normal past months fell within this distance
    residual_std = float(np.std(y - model.predict(X), ddof=1)) if len(y) > 2 else 0.0
    margin = 1.96 * residual_std

    last_period = monthly.Period.iloc[-1]
    forecast = []
    for i in range(1, FORECAST_MONTHS + 1):
        future_idx = len(monthly) + i - 1
        pred = float(model.predict([[future_idx]])[0])
        forecast.append({
            "date": str(last_period + i),
            "predicted_revenue": max(0.0, round(pred, 2)),
            "low": max(0.0, round(pred - margin, 2)),
            "high": max(0.0, round(pred + margin, 2)),
        })

    slope = float(model.coef_[0])
    relative_slope = slope / float(np.mean(y)) if np.mean(y) else 0.0
    if relative_slope > TREND_THRESHOLD:
        trend = "growing"
    elif relative_slope < -TREND_THRESHOLD:
        trend = "declining"
    else:
        trend = "stable"

    historical = [
        {
            "date": str(row.Period),
            "revenue": round(
                float(row.Revenue), 2
            )
        }
        for _, row in monthly.iterrows()
    ]

    return {
        "historical": historical,
        "forecast": forecast,
        "trend": trend,
        "monthly_change": round(slope, 2),
        "monthly_change_pct": round(relative_slope * 100, 1),
        "next_month_prediction": forecast[0]["predicted_revenue"],
        "fit_pct": fit_pct,
        "excluded_months": sorted(anomaly_months),
    }


def forecast_chart(
    historical: list,
    forecast: list,
    symbol: str = "",
    style: str = "intl"
):
    fig = go.Figure()

    def month_name(p):
        try:
            return pd.Period(p).strftime("%b %Y")
        except Exception:
            return p

    hist_x = [month_name(h["date"]) for h in historical]
    hist_y = [h["revenue"] for h in historical]

    # Start the forecast line at the last actual month so the lines connect
    fc_x = [hist_x[-1]] + [month_name(f["date"]) for f in forecast]
    fc_y = [hist_y[-1]] + [f["predicted_revenue"] for f in forecast]
    low_y = [hist_y[-1]] + [f["low"] for f in forecast]
    high_y = [hist_y[-1]] + [f["high"] for f in forecast]

    fig.add_trace(go.Scatter(
        x=fc_x + fc_x[::-1],
        y=high_y + low_y[::-1],
        fill="toself",
        mode="lines",
        fillcolor="rgba(16, 185, 129, 0.15)",
        line=dict(width=0),
        hoverinfo="skip",
        name="Likely range",
    ))

    fig.add_trace(go.Scatter(
        x=hist_x,
        y=hist_y,
        name="Actual Revenue",
        line=dict(
            color="#0ea5e9",
            width=2
        ),
        mode="lines+markers",
        customdata=[fmt_money(v, symbol, style) for v in hist_y],
        hovertemplate="%{x}<br>%{customdata}<extra>Actual</extra>",
    ))

    fig.add_trace(go.Scatter(
        x=fc_x,
        y=fc_y,
        name="Forecast",
        line=dict(
            color="#10b981",
            width=2,
            dash="dash"
        ),
        mode="lines+markers",
        customdata=[fmt_money(v, symbol, style) for v in fc_y],
        hovertemplate="%{x}<br>%{customdata}<extra>Forecast</extra>",
    ))

    fig.update_layout(
        title="🔮 Revenue forecast (next 3 months)",
        template="plotly_dark",
        plot_bgcolor="#1e293b",
        paper_bgcolor="#1e293b",
        xaxis_title="",
        yaxis_title="Revenue",
        height=450,
        separators=plotly_separators(style),
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", y=-0.15),
    )
    # Keep months in date order (the range band is drawn first and
    # would otherwise put forecast months before the history)
    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=hist_x + fc_x[1:],
        gridcolor="#334155",
    )
    from charts import money_ticks
    top = max(max(high_y), max(hist_y)) * 1.08
    vals, text = money_ticks(0, top, symbol, style)
    fig.update_yaxes(tickvals=vals, ticktext=text, range=[0, top], gridcolor="#334155")

    return fig
