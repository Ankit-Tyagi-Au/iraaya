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


# ---------- Home screen: snapshot, 3 things to know, monthly target ----------

def _daily(df: pd.DataFrame) -> pd.Series:
    return df.groupby(df.Date.dt.normalize()).Total_Revenue.sum().sort_index()


def day_snapshot(df: pd.DataFrame, today) -> dict:
    """Sales on `today` (or, if there are none, on the latest day in the
    file) compared with a usual day of the same weekday: the median of
    that weekday over the 8 weeks before. pct is None without history."""
    daily = _daily(df)
    if daily.empty:
        return None
    today = pd.Timestamp(today).normalize()
    is_today = today in daily.index
    day = today if is_today else daily.index.max()
    earlier = daily[(daily.index < day) & (daily.index >= day - pd.Timedelta(weeks=8))]
    same_weekday = earlier[earlier.index.dayofweek == day.dayofweek]
    usual = float(same_weekday.median()) if len(same_weekday) >= 2 else None
    total = float(daily[day])
    return {"day": day, "is_today": is_today, "total": total, "usual": usual,
            "pct": _change(total, usual) if usual else None}


def _window_change(df: pd.DataFrame, col: str, end: pd.Timestamp, days: int = 7):
    """Per value of col: (change %, revenue now) for the last `days` days
    ending at `end` vs the `days` before."""
    now = df[(df.Date > end - pd.Timedelta(days=days)) & (df.Date <= end + pd.Timedelta(days=1))]
    before = df[(df.Date > end - pd.Timedelta(days=2 * days)) & (df.Date <= end - pd.Timedelta(days=days))]
    a, b = now.groupby(col).Total_Revenue.sum(), before.groupby(col).Total_Revenue.sum()
    out = {}
    for key in a.index.union(b.index):
        n, p = float(a.get(key, 0)), float(b.get(key, 0))
        if p > 0:
            out[key] = (_change(n, p), n)
    return out


def home_insights(df: pd.DataFrame, fmt_money=lambda v: f"{v:,.0f}", all_label: str = "All") -> list:
    """Up to 3 plain-language facts worked out from the data (no AI, so
    always accurate): the product that moved most this week, the place
    that moved most, and the best day of the week.
    Returns [{"kind": "up"|"down"|"tip", "text": str}]."""
    daily = _daily(df)
    if len(daily) < 14:
        return []
    end = daily.index.max()
    facts = []
    for col, word in (("Product", ""), ("Region", "in ")):
        if col not in df.columns or df[col].nunique() < 2 or set(df[col].unique()) == {all_label}:
            continue
        changes = _window_change(df, col, end)
        # Ignore tiny sellers: a jump from 1 sale to 3 isn't news
        total_now = sum(n for _, n in changes.values()) or 1
        big = {k: v for k, v in changes.items() if v[1] / total_now >= 0.05 and v[0] is not None}
        if not big:
            continue
        key, (pct, _) = max(big.items(), key=lambda kv: abs(kv[1][0]))
        if abs(pct) < 5:
            continue
        up = pct > 0
        subject = f"{key} sales are" if col == "Product" else f"Sales {word}{key} are"
        facts.append({"kind": "up" if up else "down",
                      "text": f"{subject} {'up' if up else 'down'} {abs(pct):.0f}% in the last 7 days"})
    recent = daily[daily.index > end - pd.Timedelta(weeks=12)]
    by_weekday = recent.groupby(recent.index.dayofweek).mean()
    if len(by_weekday) >= 5:
        best = int(by_weekday.idxmax())
        names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        facts.append({"kind": "tip",
                      "text": f"{names[best]} is your best day (about {fmt_money(by_weekday.max())} "
                              f"on average), so get ready on {names[(best - 1) % 7]}"})
    return facts[:3]


def target_progress(df: pd.DataFrame, target: float, today) -> dict:
    """Progress towards a monthly sales target. Uses the current month when
    the file has sales in it, otherwise the latest month in the file
    (which is then finished, so nothing is 'still needed')."""
    if not target or df.empty:
        return None
    today = pd.Timestamp(today).normalize()
    latest = df.Date.max()
    month = today.to_period("M") if (df.Date.dt.to_period("M") == today.to_period("M")).any() \
        else latest.to_period("M")
    sold = float(df[df.Date.dt.to_period("M") == month].Total_Revenue.sum())
    current = month == today.to_period("M")
    days_left = (month.days_in_month - today.day) if current else 0
    remaining = max(target - sold, 0)
    return {"month": month, "sold": sold, "target": float(target), "pct": sold / target * 100,
            "current": current, "days_left": days_left,
            "per_day": remaining / days_left if current and days_left > 0 and remaining else None}
