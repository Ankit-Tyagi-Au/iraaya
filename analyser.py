"""Load, validate and summarise business sales data with pandas."""

import difflib
import os
import re

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ["Date", "Product", "Region", "Total_Revenue"]

# Keep the AI context a sensible size for large files
MAX_PRODUCTS_IN_CONTEXT = 15
MAX_MONTHS_IN_CONTEXT = 24

# A month must be at least this far from the trend to count as unusual
MIN_ANOMALY_PCT = 30

# Individual records sent to the AI: every row for small files, otherwise
# only the rows that match the question (dates or names mentioned in it)
ALL_ROWS_LIMIT = 40
MATCHED_ROWS_LIMIT = 25

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"


def load_data(file) -> pd.DataFrame:
    """Read a CSV or Excel file (path or uploaded file) and clean it.

    Rows with an unreadable date or revenue are dropped; how many is
    stored in df.attrs["dropped_rows"] so validate_data can warn about it.
    """
    name = getattr(file, "name", str(file))
    ext = os.path.splitext(name)[1].lower()

    try:
        if ext == ".csv":
            df = pd.read_csv(file)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(file)
        else:
            raise ValueError(
                f"Unsupported file type '{ext}'. "
                "Please upload a CSV or Excel file."
            )
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Could not read the file: {e}") from e

    return clean_dataframe(df)


def _to_number(series: pd.Series) -> pd.Series:
    """Numbers written as text ("₹1,000", "$ 500", "1 200") -> numbers."""
    if not pd.api.types.is_numeric_dtype(series):
        series = series.astype(str).str.replace(r"[^0-9.\-]", "", regex=True)
    return pd.to_numeric(series, errors="coerce")


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Tidy a table from any source (CSV, Excel, PDF, Word).

    Rows with an unreadable date or revenue are dropped; how many is
    stored in df.attrs["dropped_rows"] so validate_data can warn about it.
    """
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    rows_before = len(df)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"])
    if "Total_Revenue" in df.columns:
        df["Total_Revenue"] = _to_number(df["Total_Revenue"])
        df = df.dropna(subset=["Total_Revenue"])
    for col in ("Units_Sold", "Unit_Price"):
        if col in df.columns:
            df[col] = _to_number(df[col])

    df = df.sort_values("Date") if "Date" in df.columns else df
    df = df.reset_index(drop=True)
    df.attrs["dropped_rows"] = rows_before - len(df)
    return df


def validate_data(df) -> dict:
    missing = [
        c for c in REQUIRED_COLUMNS
        if c not in df.columns
    ]
    warnings = []

    dropped = df.attrs.get("dropped_rows", 0)
    if dropped:
        warnings.append(
            f"{dropped} rows skipped because the date "
            "or revenue could not be read"
        )
    if not missing and len(df) == 0:
        warnings.append("The file has no usable rows")
    if not missing and len(df) and _monthly(df).size < 3:
        warnings.append(
            "Less than 3 months of data — trends and "
            "forecasts will not be reliable"
        )

    return {
        "is_valid": len(missing) == 0 and len(df) > 0,
        "missing_columns": missing,
        "warnings": warnings,
        "row_count": len(df)
    }


def _monthly(df) -> pd.Series:
    return df.groupby(
        df.Date.dt.to_period("M")
    ).Total_Revenue.sum()


def _stringify_keys(series: pd.Series) -> dict:
    return {
        str(k): round(float(v), 2)
        for k, v in series.items()
    }


def get_summary(df) -> dict:
    total_revenue = df.Total_Revenue.sum()
    total_transactions = len(df)

    monthly = _monthly(df)
    best_month = str(monthly.idxmax())

    by_product = df.groupby(
        "Product"
    ).Total_Revenue.sum().sort_values(ascending=False)
    best_product = by_product.idxmax()
    worst_product = by_product.idxmin()

    by_region = df.groupby(
        "Region"
    ).Total_Revenue.sum().sort_values(ascending=False)
    best_region = by_region.idxmax()

    date_range = (
        f"{df.Date.min().date()} "
        f"to {df.Date.max().date()}"
    )

    return {
        "total_revenue": round(
            float(total_revenue), 2
        ),
        "total_transactions": total_transactions,
        "best_month": best_month,
        "best_product": best_product,
        "worst_product": worst_product,
        "best_region": best_region,
        "date_range": date_range,
        "products_list": list(
            df.Product.unique()
        ),
        "regions_list": list(
            df.Region.unique()
        ),
        "monthly_revenue": _stringify_keys(monthly),
        "top_products": _stringify_keys(by_product),
        "regional_revenue": _stringify_keys(by_region)
    }


def _growth_pct(series: pd.Series, window: int = 3):
    """Typical (median) month of the last `window` months vs the first.

    Median rather than mean, so one unusual month at either end
    (a crash or a seasonal peak) does not distort growth.
    """
    if len(series) < window * 2:
        window = max(1, len(series) // 2)
    first = series.iloc[:window].median()
    last = series.iloc[-window:].median()
    if not first:
        return None
    return round(float((last - first) / first * 100), 1)


def _pivot_by_month(df, column: str, keep: list) -> str:
    table = df[df[column].isin(keep)].groupby([
        df.Date.dt.to_period("M"), column
    ]).Total_Revenue.sum().unstack(fill_value=0)
    table = table.tail(MAX_MONTHS_IN_CONTEXT)
    table.index = table.index.astype(str)
    return table.round(0).astype(int).to_string()


def _rows_as_text(rows: pd.DataFrame) -> str:
    rows = rows.copy()
    rows["Date"] = rows["Date"].dt.strftime("%Y-%m-%d")
    return rows.to_csv(index=False).strip()


def _dates_in(text: str):
    """Exact dates and whole months mentioned in the text."""
    t = text.lower()
    days, months = set(), set()
    for y, m, d in re.findall(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t):
        days.add((int(y), int(m), int(d)))
    for d, m, y in re.findall(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", t):
        days.add((int(y), int(m), int(d)))      # day/month/year
    for d, mon, y in re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MON + r",?\s+(\d{4})\b", t):
        days.add((int(y), MONTHS[mon], int(d)))
    for mon, d, y in re.findall(r"\b" + _MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", t):
        days.add((int(y), MONTHS[mon], int(d)))
    for mon, y in re.findall(r"\b" + _MON + r"\s+(\d{4})\b", t):
        months.add((int(y), MONTHS[mon]))
    # "15 April 2024" also contains "April 2024": the exact day wins
    months -= {(y, m) for y, m, _ in days}
    return days, months


def _names_in(df: pd.DataFrame, text: str) -> dict:
    """Text values (products, regions...) mentioned in the text, allowing
    for small spelling or speech-to-text differences ("next thing" -> Nexthink)."""
    t = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    words = t.split()
    grams = set(words) | {a + b for a, b in zip(words, words[1:])}
    found = {}
    for col in df.select_dtypes(include=["object", "string"]).columns:
        values = [str(v) for v in df[col].dropna().unique()[:2000]]
        exact = {v for v in values if v.lower() in t}
        if exact:
            found[col] = exact
            continue
        # Near matches only on words that identify a single value
        # ("india" is shared by four regions, so it can't pick one)
        word_owner = {}
        for v in values:
            for w in set(re.sub(r"[^a-z0-9 ]", " ", v.lower()).split()):
                word_owner.setdefault(w, set()).add(v)
        near = set()
        for w, owners in word_owner.items():
            if len(w) >= 5 and len(owners) == 1 and \
                    difflib.get_close_matches(w, grams, n=1, cutoff=0.8):
                near |= owners
        if near:
            found[col] = near
    return found


def find_relevant_rows(df: pd.DataFrame, question: str) -> str:
    """Records matching the question, for files too big to send in full."""
    if len(df) <= ALL_ROWS_LIMIT:
        return ""   # every row is already in the data context
    days, months = _dates_in(question)
    mask = pd.Series(False, index=df.index)
    for y, m, d in days:
        mask |= (df.Date.dt.year == y) & (df.Date.dt.month == m) & (df.Date.dt.day == d)
    for y, m in months:
        mask |= (df.Date.dt.year == y) & (df.Date.dt.month == m)
    names = _names_in(df, question)
    # Broad columns like Region match too many rows on their own, so
    # names only narrow things down when no date was mentioned
    for col, values in names.items():
        col_mask = df[col].astype(str).isin(values)
        mask = (mask & col_mask) if (days or months) and mask.any() else (mask | col_mask)
    rows = df[mask]
    if rows.empty:
        return ""
    if len(rows) > MATCHED_ROWS_LIMIT and not (days or months):
        return ""   # broad question: the summaries already answer it
    shown = rows.head(MATCHED_ROWS_LIMIT)
    # Exact totals, so the AI never has to add numbers up itself
    totals = (
        "EXACT TOTALS (use these for any total; a single row is only one "
        f"region or customer):\nAll {len(rows)} matching rows: "
        f"{rows.Total_Revenue.sum():,.2f}"
    )
    for col in ("Product", "Region"):
        if col in rows.columns and rows[col].nunique() > 1:
            top = rows.groupby(col).Total_Revenue.sum().sort_values(ascending=False).head(5)
            totals += f"\nTotal by {col.lower()} (all matching rows): " + "; ".join(
                f"{k} {v:,.2f}" for k, v in top.items())
    return (
        f"RECORDS MATCHING THIS QUESTION ({len(shown)} of {len(rows)} "
        f"matching rows shown):\n{totals}\n{_rows_as_text(shown)}"
    )


def vocabulary_hint(df: pd.DataFrame, max_chars: int = 600) -> str:
    """Names from the data, to help speech-to-text spell them correctly."""
    names = []
    for col in ("Product", "Region", "Customer_Type"):
        if col in df.columns:
            names += [str(v) for v in df[col].dropna().unique()]
    return ", ".join(names)[:max_chars]


def _breakdown(df, column: str) -> str:
    if column not in df.columns:
        return ""
    totals = df.groupby(column).Total_Revenue.sum().sort_values(
        ascending=False
    )
    total = totals.sum()
    lines = [
        f"  {k}: {v:,.0f} ({v / total * 100:.1f}%)"
        for k, v in totals.items()
    ]
    return f"\nREVENUE BY {column.upper().replace('_', ' ')}:\n" + "\n".join(lines) + "\n"


def get_data_context(df) -> str:
    """Text summary of the data that the AI answers from."""
    summary = get_summary(df)
    monthly = _monthly(df)

    top_products = list(summary["top_products"].keys())[:MAX_PRODUCTS_IN_CONTEXT]
    regions = list(summary["regional_revenue"].keys())[:MAX_PRODUCTS_IN_CONTEXT]

    product_growth = {
        p: _growth_pct(_monthly(df[df.Product == p]))
        for p in top_products
    }
    region_growth = {
        r: _growth_pct(_monthly(df[df.Region == r]))
        for r in regions
    }

    anomalies = detect_anomalies(df)
    anomaly_text = "\n".join(
        f"  {a['month']}: {a['revenue']:,.0f} vs expected "
        f"{a['expected']:,.0f} ({a['difference_pct']:+.1f}%)"
        for a in anomalies
    ) or "  None detected"

    health = calculate_health_score(df)
    all_rows = (
        f"\nALL RECORDS ({len(df)} rows):\n{_rows_as_text(df)}\n"
        if len(df) <= ALL_ROWS_LIMIT else ""
    )
    n_products = len(summary["top_products"])
    shown_note = (
        f"; top {len(top_products)} of {n_products} shown"
        if n_products > len(top_products) else ""
    )

    def fmt(d):
        return "\n".join(f"  {k}: {v:,.0f}" for k, v in d.items())

    def fmt_pct(v):
        return f"{v:+.1f}%" if v is not None else "n/a"

    def fmt_growth(d):
        return "\n".join(f"  {k}: {fmt_pct(v)}" for k, v in d.items())

    return f"""
BUSINESS DATA SUMMARY:
Total Revenue: {summary['total_revenue']:,.2f}
Total Transactions: {summary['total_transactions']}
Date Range: {summary['date_range']}
Best Month: {summary['best_month']}
Best Product: {summary['best_product']} ({summary['top_products'][summary['best_product']]:,.0f})
Worst Product: {summary['worst_product']} ({summary['top_products'][summary['worst_product']]:,.0f})
Number of products: {len(summary['top_products'])}
Best Region: {summary['best_region']} ({summary['regional_revenue'][summary['best_region']]:,.0f})
Overall growth (typical month of last 3 vs first 3): {fmt_pct(_growth_pct(monthly))}
Business Health Score: {health['score']}/100 ({health['label']})

MONTHLY REVENUE:
{fmt(summary['monthly_revenue'])}

REVENUE BY PRODUCT (highest first{shown_note}):
{fmt({k: summary['top_products'][k] for k in top_products})}

PRODUCT GROWTH (typical month of last 3 vs first 3):
{fmt_growth(product_growth)}

REVENUE BY REGION (highest first):
{fmt({k: summary['regional_revenue'][k] for k in regions})}

REGION GROWTH (typical month of last 3 vs first 3):
{fmt_growth(region_growth)}
{_breakdown(df, 'Customer_Type')}{_breakdown(df, 'Payment_Method')}
MONTHLY REVENUE BY PRODUCT:
{_pivot_by_month(df, 'Product', top_products)}

MONTHLY REVENUE BY REGION:
{_pivot_by_month(df, 'Region', regions)}

UNUSUAL MONTHS (compared with the overall trend):
{anomaly_text}
{all_rows}"""


def detect_anomalies(df) -> list:
    """Flag months far above or below the overall trend.

    Compares each month with a straight-line trend (so normal growth
    is not flagged) and uses a robust z-score based on the median
    absolute deviation, so one extreme month cannot hide itself.
    """
    monthly = _monthly(df)
    if len(monthly) < 4:
        return []

    x = np.arange(len(monthly))
    slope, intercept = np.polyfit(x, monthly.values, 1)
    expected = slope * x + intercept
    residuals = monthly.values - expected

    median = np.median(residuals)
    mad = np.median(np.abs(residuals - median))
    if mad == 0:
        return []
    robust_z = 0.6745 * (residuals - median) / mad

    anomalies = []
    for i, (period, revenue) in enumerate(monthly.items()):
        exp = expected[i]
        diff_pct = (revenue - exp) / exp * 100 if exp else 0.0
        if abs(robust_z[i]) <= 3.5 or abs(diff_pct) < MIN_ANOMALY_PCT:
            continue
        anomalies.append({
            "month": str(period),
            "revenue": round(float(revenue), 2),
            "expected": round(float(exp), 2),
            "difference_pct": round(float(diff_pct), 1),
            "type": "high" if revenue > exp else "low"
        })

    return anomalies


def calculate_health_score(
    df
) -> dict:
    monthly = _monthly(df).values

    if len(monthly) < 2:
        return {
            "score": 50,
            "label": "Average",
            "color": "yellow",
            "factors": [
                "Not enough data yet"
            ]
        }

    # Typical month of first vs last 3, so one unusual month
    # at either end does not swing the score
    growth = _growth_pct(pd.Series(monthly)) or 0

    cv = (
        np.std(monthly)
        / np.mean(monthly)
    )

    score = 50
    factors = []

    if growth > 20:
        score += 25
        factors.append(
            f"Strong revenue growth ({growth:+.0f}%)"
        )
    elif growth > 0:
        score += 10
        factors.append(
            f"Positive revenue growth ({growth:+.0f}%)"
        )
    else:
        score -= 15
        factors.append(
            f"Revenue declining ({growth:+.0f}%)"
        )

    if cv < 0.2:
        score += 15
        factors.append(
            "Very consistent sales"
        )
    elif cv < 0.4:
        score += 5
        factors.append(
            "Reasonably consistent sales"
        )
    else:
        score -= 10
        factors.append(
            "Sales are inconsistent"
        )

    n_products = df.Product.nunique()
    if n_products >= 4:
        score += 10
        factors.append(
            "Good product diversification"
        )

    score = max(0, min(100, score))

    if score >= 80:
        label = "Excellent"
        color = "green"
    elif score >= 60:
        label = "Good"
        color = "blue"
    elif score >= 40:
        label = "Average"
        color = "yellow"
    else:
        label = "Needs Attention"
        color = "red"

    return {
        "score": score,
        "label": label,
        "color": color,
        "factors": factors
    }
