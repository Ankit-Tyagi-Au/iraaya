"""Filters and the numbers behind the dashboard cards."""

import pandas as pd

FILTER_COLUMNS = {
    "Product": "Products",
    "Region": "Regions",
    "Customer_Type": "Customer types",
    "Payment_Method": "Payment methods",
}


def apply_filters(df: pd.DataFrame, start=None, end=None, choices: dict = None) -> pd.DataFrame:
    """Rows between start and end (inclusive dates) that match the chosen
    values for each column. An empty choice means 'all'."""
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= df.Date >= pd.Timestamp(start)
    if end is not None:
        mask &= df.Date < pd.Timestamp(end) + pd.Timedelta(days=1)
    for col, values in (choices or {}).items():
        if values and col in df.columns:
            mask &= df[col].astype(str).isin([str(v) for v in values])
    return df[mask]


def previous_range(start, end):
    """The period just before start. Whole calendar months (e.g. Jan-Mar)
    compare with the same number of whole months before (Oct-Dec);
    otherwise with the same number of days."""
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if start.day == 1 and (end + pd.Timedelta(days=1)).day == 1:
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        prev_start = start - pd.DateOffset(months=months)
        return prev_start, start - pd.Timedelta(days=1)
    length = end - start + pd.Timedelta(days=1)
    prev_end = start - pd.Timedelta(days=1)
    return prev_end - length + pd.Timedelta(days=1), prev_end


def previous_period(df: pd.DataFrame, start, end, choices: dict = None) -> pd.DataFrame:
    """The same filters over the period just before start."""
    prev_start, prev_end = previous_range(start, end)
    return apply_filters(df, prev_start, prev_end, choices)


def _change(now, before):
    if before in (None, 0) or pd.isna(before):
        return None
    return (now - before) / abs(before) * 100


def _monthly(df: pd.DataFrame) -> pd.Series:
    return df.groupby(df.Date.dt.to_period("M")).Total_Revenue.sum()


def month_over_month(df: pd.DataFrame):
    """Growth of the latest complete month vs the month before it.
    A latest month with clearly fewer sales days than usual is treated as
    still in progress and skipped. Returns dict or None."""
    if df.empty:
        return None
    monthly = _monthly(df)
    days = df.groupby(df.Date.dt.to_period("M")).Date.nunique()
    if len(monthly) < 2:
        return None
    partial = False
    if len(days) >= 3 and days.iloc[-1] < 0.75 * days.iloc[:-1].median():
        monthly = monthly.iloc[:-1]
        partial = True
        if len(monthly) < 2:
            return None
    last, prev = monthly.index[-1], monthly.index[-2]
    return {
        "pct": _change(monthly.iloc[-1], monthly.iloc[-2]),
        "label": f"{last.strftime('%b %Y')} vs {prev.strftime('%b %Y')}",
        "skipped_partial_month": partial,
    }


def card_numbers(current: pd.DataFrame, previous: pd.DataFrame) -> dict:
    """Everything the 6 dashboard cards show."""
    months_now = _monthly(current)
    months_before = _monthly(previous) if not previous.empty else pd.Series(dtype=float)
    total, total_prev = current.Total_Revenue.sum(), previous.Total_Revenue.sum()
    avg, avg_prev = (months_now.mean() if len(months_now) else 0), (
        months_before.mean() if len(months_before) else None)
    by_product = current.groupby("Product").Total_Revenue.sum()
    best_month = months_now.idxmax() if len(months_now) else None
    return {
        "total": total,
        "total_change": _change(total, total_prev) if not previous.empty else None,
        "transactions": len(current),
        "transactions_change": _change(len(current), len(previous)) if not previous.empty else None,
        "avg_monthly": avg,
        "avg_monthly_change": _change(avg, avg_prev) if avg_prev else None,
        "best_month": best_month,
        "best_month_revenue": months_now.max() if len(months_now) else 0,
        "best_product": by_product.idxmax() if len(by_product) else None,
        "best_product_share": (by_product.max() / total * 100) if total else 0,
        "mom": month_over_month(current),
        "months": len(months_now),
    }


def growth_by(current: pd.DataFrame, previous: pd.DataFrame, column: str) -> dict:
    """{value: % change vs the previous period} for each value of a column."""
    if previous.empty or column not in current.columns:
        return {}
    now = current.groupby(column).Total_Revenue.sum()
    before = previous.groupby(column).Total_Revenue.sum()
    return {k: _change(v, before.get(k)) for k, v in now.items()}
