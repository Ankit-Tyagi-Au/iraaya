"""Turn a raw table from anywhere in the world into iRaaya's standard columns.

- Recognises common column names ("Amount", "Sales", "Item", "Order Date"...)
- Only Date and revenue are required; Product and Region are optional
- Reads numbers written in US/UK (1,234.56), Indian (12,34,567.00),
  European (1.234,56) and space-separated (1 234,56) styles
- Works out whether dates are day/month or month/day from the data
"""

import re

import pandas as pd

ALL = "All"   # stands in for a missing Product or Region column

# Standard column -> names people use for it, in English and the other
# iRaaya languages (lower case; spaces, _ - . / ignored)
COLUMN_SYNONYMS = {
    "Date": [
        "date", "orderdate", "invoicedate", "saledate", "salesdate",
        "transactiondate", "billdate", "day", "datetime", "timestamp",
        "createdat", "paymentdate", "receiptdate", "datum", "fecha", "data",
        "datedevente", "fechadeventa", "dataventa", "दिनांक", "तारीख", "日期",
        "销售日期", "日付", "날짜", "التاريخ", "تاريخ", "ngày", "ngàybán", "petsa",
        "ημερομηνία",
    ],
    "Total_Revenue": [
        "totalrevenue", "revenue", "total", "amount", "sales", "totalsales",
        "netsales", "saleamount", "salesamount", "totalamount",
        "grosssales", "turnover", "income", "value", "netamount",
        "grandtotal", "billamount", "invoiceamount", "total_revenue",
        "umsatz", "betrag", "gesamt", "erlös", "montant",
        "chiffredaffaires", "ventes", "total€", "importe", "ventas",
        "venta", "ingresos", "valor", "receita", "faturamento", "importo",
        "ricavi", "vendite", "राशि", "बिक्री", "कुल", "金额", "销售额", "营业额",
        "売上", "売上高", "金額", "매출", "금액", "매출액", "المبلغ", "المبيعات",
        "الإيرادات", "doanhthu", "sốtiền", "thànhtiền", "halaga", "benta",
        "ποσό", "πωλήσεις", "έσοδα",
    ],
    "Product": [
        "product", "productname", "item", "itemname", "sku", "menuitem",
        "dish", "service", "article", "description", "productdescription",
        "category", "produkt", "artikel", "produit", "producto", "artículo",
        "produto", "prodotto", "articolo", "उत्पाद", "वस्तु", "产品", "商品",
        "品名", "상품", "제품", "المنتج", "منتج", "sảnphẩm", "mặthàng",
        "produkto", "προϊόν",
    ],
    "Region": [
        "region", "area", "location", "city", "store", "branch", "outlet",
        "state", "zone", "market", "country", "shop", "site", "filiale",
        "standort", "région", "magasin", "ville", "región", "tienda",
        "sucursal", "ciudad", "loja", "cidade", "negozio", "città",
        "regione", "क्षेत्र", "शहर", "地区", "门店", "城市", "地域", "店舗", "지역",
        "매장", "المنطقة", "الفرع", "khuvực", "cửahàng", "rehiyon",
        "tindahan", "περιοχή", "κατάστημα",
    ],
    "Units_Sold": [
        "unitssold", "units", "quantity", "qty", "quantitysold", "unitsold",
        "menge", "anzahl", "quantité", "cantidad", "quantidade", "quantità",
        "मात्रा", "数量", "수량", "الكمية", "sốlượng", "dami", "ποσότητα",
    ],
    "Unit_Price": [
        "unitprice", "price", "rate", "sellingprice", "priceperunit",
        "preis", "einzelpreis", "prix", "prixunitaire", "precio",
        "preciounitario", "preço", "prezzo", "कीमत", "单价", "価格", "単価", "단가",
        "가격", "السعر", "giá", "đơngiá", "presyo", "τιμή",
    ],
    "Customer_Type": [
        "customertype", "customer", "segment", "channel", "customergroup",
        "ordertype", "saletype", "orderchannel", "servicetype",
        "servicemode", "customercategory", "kundentyp", "kundengruppe",
        "bestellart", "typeclient", "typedecommande", "tipocliente",
        "tipodepedido", "tipodecliente", "tipodiordine", "ग्राहकप्रकार",
        "ऑर्डरप्रकार", "客户类型", "订单类型", "顧客区分", "注文種別", "고객유형", "주문유형",
        "نوعالعميل", "نوعالطلب", "loạikháchhàng", "loạiđơn",
        "urinngcustomer", "τύποςπελάτη",
    ],
    "Payment_Method": [
        "paymentmethod", "payment", "paymentmode", "modeofpayment",
        "tender", "paidby", "paymenttype", "payby", "zahlungsart",
        "zahlungsmethode", "modedepaiement", "moyendepaiement",
        "métodopago", "metodopago", "formadepago", "formadepagamento",
        "metododipagamento", "भुगतान", "भुगतानमाध्यम", "付款方式", "支付方式",
        "支払方法", "決済方法", "결제방법", "결제수단", "طريقةالدفع", "phươngthứcthanhtoán",
        "paraanngpagbabayad", "τρόποςπληρωμής",
    ],
}
REQUIRED = ["Date", "Total_Revenue"]
OPTIONAL_FILLED = ["Product", "Region"]


def _norm(name) -> str:
    return re.sub(r"[\s_\-./]+", "", str(name).strip().lower())


def map_columns(columns) -> dict:
    """{original column name: standard name} for the columns we recognise.
    Exact standard names win over synonyms; each standard name is used once."""
    mapping, used = {}, set()
    normed = {c: _norm(c) for c in columns}
    for target, synonyms in COLUMN_SYNONYMS.items():
        # the standard name itself first, then synonyms in order of preference
        for wanted in [_norm(target)] + synonyms:
            match = next((c for c, n in normed.items() if n == wanted and c not in mapping), None)
            if match is not None:
                mapping[match] = target
                used.add(target)
                break
    return mapping


def can_build_revenue(standard_columns) -> bool:
    cols = set(standard_columns)
    return "Total_Revenue" in cols or {"Units_Sold", "Unit_Price"} <= cols


def looks_like_sales_table(columns) -> bool:
    """True if a header row has a date and something we can use as revenue."""
    std = set(map_columns(columns).values())
    return "Date" in std and can_build_revenue(std)


# ---------- numbers ----------

_CLEAN = re.compile(r"[^\d,.\-]")   # drop currency symbols, letters, spaces


def detect_number_style(values: pd.Series) -> str:
    """'dot' (1,234.56 / 12,34,567.00) or 'comma' (1.234,56 / 1 234,56)."""
    dot = comma = 0
    for raw in values.dropna().astype(str).head(500):
        v = _CLEAN.sub("", raw)
        if re.search(r"\.\d{3}(\.|,|$)", v) and "," in v and v.rfind(",") > v.rfind("."):
            comma += 2                      # 1.234,56
        elif re.search(r",\d{1,2}$", v) and "." not in v:
            comma += 1                      # 1234,5  /  1 234,56
        elif re.search(r"\.\d{3}\.\d{3}", v):
            comma += 1                      # 1.234.567
        elif re.search(r"\.\d{1,2}$", v) or re.search(r",\d{3}(,|\.|$)", v):
            dot += 1
    return "comma" if comma > dot else "dot"


def to_number(series: pd.Series, style: str = None) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series
    style = style or detect_number_style(series)
    s = series.astype(str).str.replace(_CLEAN, "", regex=True)
    if style == "comma":
        s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    else:
        s = s.str.replace(",", "", regex=False)
    return pd.to_numeric(s, errors="coerce")


# ---------- dates ----------

def detect_date_order(values: pd.Series) -> str:
    """'day-first', 'month-first', or 'unknown' for dates like 03/04/2025."""
    first_big = second_big = False
    for raw in values.dropna().astype(str).head(1000):
        m = re.match(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", raw)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        first_big |= a > 12
        second_big |= b > 12
    if first_big and not second_big:
        return "day-first"
    if second_big and not first_big:
        return "month-first"
    return "unknown"


def parse_dates(series: pd.Series, default_order: str = "day-first"):
    """Returns (dates, how the order was decided)."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series, "as stored in the file"
    text = series.astype(str).str.strip()
    iso = text.str.match(r"^\d{4}-\d{1,2}-\d{1,2}")
    if iso.mean() > 0.8:
        return pd.to_datetime(text, errors="coerce", format="ISO8601"), "year-month-day"
    order = detect_date_order(text)
    decided = order if order != "unknown" else default_order
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=(decided == "day-first"), format="mixed")
    how = decided if order != "unknown" else f"{decided} (your Settings choice; the file could be read either way)"
    return parsed, how


# ---------- whole table ----------

def prepare_table(raw: pd.DataFrame, default_date_order: str = "day-first"):
    """Standardise a raw table. Returns (df, report) where report says what
    was recognised, filled in, skipped and how numbers/dates were read."""
    raw = raw.copy()
    raw.columns = [str(c).strip() for c in raw.columns]
    raw = raw.dropna(how="all")
    missing_values = {c: int(raw[c].isna().sum() + (raw[c].astype(str).str.strip() == "").sum())
                      for c in raw.columns}

    mapping = map_columns(raw.columns)
    df = raw.rename(columns=mapping)
    std = set(mapping.values())
    report = {
        "mapping": mapping,
        "unused_columns": [c for c in raw.columns if c not in mapping],
        "missing_values": {c: n for c, n in missing_values.items() if n},
        "filled": [],
        "computed": [],
        "missing_required": [],
        "number_style": None,
        "date_order": None,
        "rows_in_file": len(raw),
        "dropped_rows": 0,
    }

    if "Date" not in std:
        report["missing_required"].append("Date")
    if not can_build_revenue(std):
        report["missing_required"].append("Total_Revenue")
    if report["missing_required"]:
        df.attrs["import_report"] = report      # so the message can list the columns found
        return df, report

    df["Date"], report["date_order"] = parse_dates(df["Date"], default_date_order)

    number_cols = [c for c in ("Total_Revenue", "Units_Sold", "Unit_Price") if c in df.columns]
    sample = pd.concat([df[c] for c in number_cols if not pd.api.types.is_numeric_dtype(df[c])]) \
        if any(not pd.api.types.is_numeric_dtype(df[c]) for c in number_cols) else pd.Series(dtype=object)
    style = detect_number_style(sample) if len(sample) else "dot"
    if len(sample):
        report["number_style"] = "1.234,56" if style == "comma" else "1,234.56"
    for c in number_cols:
        df[c] = to_number(df[c], style)

    if "Total_Revenue" not in df.columns:
        df["Total_Revenue"] = df["Units_Sold"] * df["Unit_Price"]
        report["computed"].append("Total_Revenue = Units_Sold × Unit_Price")

    for col in OPTIONAL_FILLED:
        if col not in df.columns:
            df[col] = ALL
            report["filled"].append(col)
        else:
            df[col] = df[col].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")

    before = len(df)
    df = df.dropna(subset=["Date", "Total_Revenue"])
    report["dropped_rows"] = before - len(df)
    df = df.sort_values("Date", kind="stable").reset_index(drop=True)
    df.attrs["dropped_rows"] = report["dropped_rows"]
    df.attrs["import_report"] = report
    return df, report
